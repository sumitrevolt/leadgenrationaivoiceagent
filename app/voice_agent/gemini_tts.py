"""
Gemini native TTS — free, natural Hindi voice using the EXISTING Gemini key.
===========================================================================

WHY (council 2026-06-25 + user direction): the residual "agent noob lagti"
signal is EdgeTTS hi-IN-SwaraNeural's flat timbre. User wants the OWN free stack
upgraded (no third-party paid voice API) — and the stack already carries a
Gemini key (LLM chain + STT). Gemini's native TTS (gemini-2.5-flash-preview-tts)
gives a far more human Hindi/Hinglish voice at ZERO new cost/credentials — it
reuses the same multi-key pool (app.voice_agent.gemini_keys).

DISCIPLINE (integration-engineering signature pattern):
  * INERT when no Gemini key OR GEMINI_TTS=0 → synth returns None instantly, so
    every caller transparently falls back to EdgeTTS (zero behaviour change).
  * NEVER raises. Time-capped. Quota/429 → rotate key once, else EdgeTTS floor.
  * Output is PCM (24kHz/16-bit/mono) → wrapped into a WAV container (pure-python,
    no ffmpeg) and returned base64. Frontend auto-detects WAV vs EdgeTTS mp3.

API: POST .../v1beta/models/{model}:generateContent?key=KEY
  body: {contents:[{parts:[{text}]}],
         generationConfig:{responseModalities:["AUDIO"],
           speechConfig:{voiceConfig:{prebuiltVoiceConfig:{voiceName}}}}}
  resp: candidates[0].content.parts[0].inlineData.data = base64 PCM
"""

from __future__ import annotations

import asyncio
import base64
import os
import struct

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_TIMEOUT_S = 8.0
_MAX_CHARS = 900  # replies are ~20 words; keep synth fast
_SAMPLE_RATE = 24000  # Gemini TTS output: 24kHz 16-bit mono PCM


def _model() -> str:
    return (os.environ.get("GEMINI_TTS_MODEL", "") or "gemini-2.5-flash-preview-tts").strip()


def _voice() -> str:
    # Warm female voice closest to the "Swara" persona. Configurable.
    return (os.environ.get("GEMINI_TTS_VOICE", "") or "Leda").strip() or "Leda"


def _flag_on() -> bool:
    # Default OFF (2026-06-28 latency finding: gemini-tts ~5s/sentence vs EdgeTTS
    # p50 3.3s) — the 2026-06-25 quality-motivated default-ON was superseded by
    # this data but only ever flipped via VPS .env, never here. Set GEMINI_TTS=1
    # to opt back in.
    return (os.environ.get("GEMINI_TTS", "0") or "0").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _key() -> str:
    try:
        from app.voice_agent.gemini_keys import active_key

        k = active_key()
        if k:
            return k
    except Exception:
        pass
    return (os.environ.get("GEMINI_API_KEY", "") or "").strip()


def is_enabled() -> bool:
    """True only when GEMINI_TTS flag on (default) AND a Gemini key exists."""
    return bool(_flag_on() and _key())


def _pcm_to_wav(pcm: bytes, rate: int = _SAMPLE_RATE) -> bytes:
    """Wrap raw 16-bit mono PCM in a minimal WAV header (browser-playable)."""
    n = len(pcm)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + n)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", n)
        + pcm
    )


def _extract_wav_b64(data: dict) -> str | None:
    try:
        cands = data.get("candidates") or []
        parts = ((cands[0].get("content") or {}).get("parts") or []) if cands else []
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data") or {}
            b64 = inline.get("data")
            if b64:
                pcm = base64.b64decode(b64)
                return base64.b64encode(_pcm_to_wav(pcm)).decode("ascii")
    except Exception:
        pass
    return None


async def _post(api_key: str, txt: str) -> tuple[int, dict]:
    try:
        import httpx  # local import keeps module light
    except Exception:
        return 0, {}
    url = _ENDPOINT.format(model=_model())
    payload = {
        "contents": [{"parts": [{"text": txt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": _voice()}}},
        },
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        r = await client.post(url, params={"key": api_key}, json=payload)
        return r.status_code, (r.json() if r.status_code == 200 else {})


async def synth_wav_b64(text: str) -> str | None:
    """Gemini-TTS WAV (base64) for `text`, or None on any miss (→ EdgeTTS).

    None when: flag off / no key (inert), empty text, quota-exhausted, API
    error/timeout. Rotates the Gemini key once on 429. Never raises."""
    txt = (text or "").strip()
    if not txt or not is_enabled():
        return None
    txt = txt[:_MAX_CHARS]

    try:
        from app.voice_agent.gemini_keys import advance_key, key_count
    except Exception:
        advance_key = lambda bad="": _key()  # noqa: E731
        key_count = lambda: 1  # noqa: E731

    for attempt in range(2):
        key = _key()
        if not key:
            return None
        try:
            status, data = await asyncio.wait_for(_post(key, txt), timeout=_TIMEOUT_S)
        except Exception as e:
            logger.warning("[gemini-tts] synth failed (%s) — EdgeTTS fallback", e)
            return None
        if status == 200:
            return _extract_wav_b64(data)  # str, or None if no audio part
        if status == 429 and key_count() > 1 and attempt == 0:
            advance_key(key)
            continue
        logger.warning("[gemini-tts] HTTP %s — EdgeTTS fallback", status)
        return None
    return None


__all__ = ["is_enabled", "synth_wav_b64"]
