"""
Sarvam AI (Bulbul) TTS — OPTIONAL premium natural Hindi/Indian voice.
=====================================================================

WHY: free EdgeTTS hi-IN-SwaraNeural is intelligible but flat/synthetic on
Hinglish — the #1 "agent noob lagti hai" signal (council 2026-06-25). Sarvam
Bulbul is trained on Indian languages and sounds human on Hindi + code-mixed
English, the single biggest perceived-quality jump.

DISCIPLINE (codebase signature pattern — see integration-engineering skill):
  * INERT without `SARVAM_API_KEY` → synth_mp3_b64() returns None instantly, so
    every caller transparently falls back to EdgeTTS (zero behaviour change).
  * NEVER raises (caller is not defensive).
  * Time-capped so a slow API never stalls a turn.
  * Local monthly char-cap (`SARVAM_MONTHLY_CHAR_CAP`, default 200k; 0=off) so the
    free tier is never silently overspent — over cap → None → EdgeTTS floor.
  * Paid voice is OFF by default and only ever tried on the demo/web TTS path;
    it never auto-enables and EdgeTTS stays the guaranteed floor.

API (https://docs.sarvam.ai): POST https://api.sarvam.ai/text-to-speech
  headers: api-subscription-key, Content-Type: application/json
  body: {text, target_language_code:"hi-IN", model:"bulbul:v2",
         speaker, output_audio_codec:"mp3", pace}
  resp: {"request_id":..., "audios":["<base64 mp3>"]}
"""

from __future__ import annotations

import asyncio
import json
import os
import time

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ENDPOINT = "https://api.sarvam.ai/text-to-speech"
_TIMEOUT_S = 6.0
_MAX_CHARS = 1500  # bulbul:v2 per-request text limit
_USAGE_PATH = os.path.join("data", "sarvam_usage.json")


def _api_key() -> str:
    return (getattr(settings, "sarvam_api_key", "") or os.environ.get("SARVAM_API_KEY", "") or "").strip()


def is_enabled() -> bool:
    """True only when a Sarvam key is configured. No key = inert (EdgeTTS used)."""
    return bool(_api_key())


def _month_key() -> str:
    # time.gmtime() is allowed (Date.now()-style randomness ban applies to JS workflows,
    # not Python runtime). YYYY-MM bucket for the monthly cap.
    t = time.gmtime()
    return f"{t.tm_year:04d}-{t.tm_mon:02d}"


def _cap() -> int:
    try:
        return int(getattr(settings, "sarvam_monthly_char_cap", 0) or os.environ.get("SARVAM_MONTHLY_CHAR_CAP", 0) or 0)
    except Exception:
        return 0


def _usage_read() -> dict:
    try:
        with open(_USAGE_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _over_cap(add_chars: int) -> bool:
    """True if this synth would exceed the monthly char cap (0 = no cap)."""
    cap = _cap()
    if cap <= 0:
        return False
    data = _usage_read()
    used = int(data.get(_month_key(), 0) or 0)
    return (used + add_chars) > cap


def _usage_add(chars: int) -> None:
    try:
        os.makedirs(os.path.dirname(_USAGE_PATH), exist_ok=True)
        data = _usage_read()
        mk = _month_key()
        data[mk] = int(data.get(mk, 0) or 0) + int(chars)
        # keep only the last few months
        for k in sorted(data.keys())[:-4]:
            data.pop(k, None)
        with open(_USAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass  # usage tracking is best-effort; never break synth


async def synth_mp3_b64(text: str, *, pace: float = 1.1) -> str | None:
    """Sarvam Bulbul mp3 (base64) for `text`, or None on any miss (→ EdgeTTS).

    None when: no key (inert), empty text, over monthly cap, API error/timeout.
    pace 1.1 ≈ EdgeTTS +8% brisk telecaller feel. Never raises."""
    txt = (text or "").strip()
    if not txt or not is_enabled():
        return None
    txt = txt[:_MAX_CHARS]
    if _over_cap(len(txt)):
        logger.info("[sarvam-tts] monthly char-cap reached — EdgeTTS fallback")
        return None

    async def _call() -> str | None:
        try:
            import httpx  # local import — keeps module import light
        except Exception:
            return None
        payload = {
            "text": txt,
            "target_language_code": "hi-IN",
            "model": "bulbul:v2",
            "speaker": (getattr(settings, "sarvam_speaker", "") or "anushka").strip() or "anushka",
            "output_audio_codec": "mp3",
            "pace": pace,
        }
        headers = {"api-subscription-key": _api_key(), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            r = await client.post(_ENDPOINT, json=payload, headers=headers)
            if r.status_code != 200:
                logger.warning("[sarvam-tts] HTTP %s — EdgeTTS fallback", r.status_code)
                return None
            audios = (r.json() or {}).get("audios") or []
            b64 = (audios[0] if audios else "") or ""
            return b64 or None

    try:
        b64 = await asyncio.wait_for(_call(), timeout=_TIMEOUT_S)
    except Exception as e:
        logger.warning("[sarvam-tts] synth failed (%s) — EdgeTTS fallback", e)
        return None
    if b64:
        _usage_add(len(txt))
    return b64


__all__ = ["is_enabled", "synth_mp3_b64"]
