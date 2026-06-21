"""
Vobiz WebSocket Streaming — conversational phone AI (bare-metal, no Pipecat).
=============================================================================

WHAT THIS IS
------------
Vobiz can stream a live PSTN call to our server over a WebSocket. For each call
Vobiz opens ONE WS to
``wss://<host>/api/telephony/vobiz/stream/<token>?niche=...&client_id=...`` and:

  * sends us the caller's audio as base64 **Linear PCM 16-bit little-endian,
    16 kHz, mono, ~20 ms (640-byte) frames** wrapped in JSON events — because
    our <Stream> verb requests ``contentType="audio/x-l16;rate=16000"`` (see
    vobiz_handler.build_stream_xml);
  * plays back the ``playAudio`` JSON we send (same L16/16 kHz/base64 format).

We run a full conversational loop per call:

    caller audio (PCM16 16k — already STT-ready, NO conversion needed)
        → energy/silence VAD          -> utterance boundary
        → STT chain: Groq Whisper-large-v3 (free, fast, PRIMARY when key set)
               → Gemini audio-in (multimodal, multi-key rotation)
               → vosk | faster-whisper (local, always-on fallback) -> user text
        → TelecallerBrain (lean phone prompt, KB-grounded; fallback LLMBrain) -> reply
        → EdgeTTS (hi-IN-SwaraNeural) -> MP3 bytes
        → pydub decode + resample     -> PCM16 16k mono
        → base64, 640-byte/20ms chunks -> {"event":"playAudio", ...} to Vobiz

NO µ-LAW / NO 8k RESAMPLE (the load-bearing simplification)
-----------------------------------------------------------
contentType=audio/x-l16;rate=16000 means inbound bytes ARE already PCM16 @16 kHz
(exactly what STT wants) and we send PCM16 @16 kHz straight back. audioop is now
used ONLY for RMS in the VAD, with a pure-Python fallback (_pcm_rms) so the call
keeps working even if audioop is unimportable.

GRACEFUL DEGRADATION (robustness > completeness)
------------------------------------------------
Everything is guarded; the socket NEVER crashes. Capability flags decide what
runs, and a missing capability is logged + skipped (the call still connects):

  * TTS_AVAILABLE  -> needs ``edge-tts`` AND ``pydub`` importable.
  * STT_AVAILABLE  -> ``google-genai`` (Gemini audio-in, primary) OR
                      ``vosk``/``faster-whisper`` (local fallback) importable.
  * audioop        -> stdlib (Python ≤3.12); on 3.13 falls back to audioop-lts.
                      Only RMS is used now; a manual int loop covers its absence.

TO GO LIVE ON THE VPS (Mumbai) you must install the heavy, optional deps:
    .venv/bin/pip install vosk            # or: faster-whisper
    # pydub + edge-tts already in requirements.txt
    # ffmpeg already installed on the VPS (deploy_vps.sh STEP 1) — pydub needs it
For vosk set ``VOSK_MODEL_PATH`` to a downloaded model dir (e.g. the small
hi/en model). Without these the WS still accepts + reads events, but cannot
hear or speak (logs "STT/TTS unavailable").

Protocol events (EXACT, per docs.vobiz.ai/xml/stream + /xml/stream/play-audio):
  recv: {"event":"start","start":{"streamSid":..,"callSid":..,"customParameters":{..}}}
        {"event":"media","media":{"payload":"<b64 PCM16 16k>"}}
        {"event":"stop"}
        {"event":"playedStream"}    # ack: our playAudio finished (no-op)
        {"event":"clearedAudio"}    # ack: clearAudio flushed buffer (no-op)
  send: {"event":"playAudio","media":{"contentType":"audio/x-l16","sampleRate":16000,"payload":"<b64 PCM16 16k>"}}
        {"event":"clearAudio"}      # flush playback on barge-in (no sid)
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import json
import os
import random
import re
import struct
import threading
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

# Per-turn latency metrics (P1 observability) — import-safe, stdlib-only deps.
# now_ms() is monotonic ms; record helper is gated (TURN_METRICS) + never-raises.
from app.voice_agent.turn_metrics import now_ms as _now_ms
from app.voice_agent.turn_metrics import record_turn as _record_turn_metric

logger = setup_logger(__name__)


# --------------------------------------------------------------------------- #
# Capability detection — light (find_spec does NOT import the heavy module).
# --------------------------------------------------------------------------- #
def _have(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _groq_key() -> str:
    """GROQ_API_KEY from env first, then settings.groq_api_key (.env). "" = off."""
    k = (os.environ.get("GROQ_API_KEY", "") or "").strip()
    if not k:
        try:
            from app.config import settings

            k = (getattr(settings, "groq_api_key", "") or "").strip()
        except Exception:
            pass
    return k


_VOSK_OK = _have("vosk")
_FWHISPER_OK = _have("faster_whisper")
_GENAI_OK = _have("google.genai")  # NEW google-genai SDK (Gemini audio-in STT)
_OPENAI_SDK_OK = _have("openai")  # Groq STT via shared free_ai layer (OpenAI-compatible)
_LOCAL_STT_OK = _VOSK_OK or _FWHISPER_OK  # local engines (whisper fallback chain)
# STT chain (auto): groq (free, fast Whisper-large-v3) -> gemini (multimodal,
# multi-key) -> whisper (local, always works). Groq counts as available only
# when the openai SDK is importable AND a GROQ_API_KEY is configured.
STT_AVAILABLE = _LOCAL_STT_OK or _GENAI_OK or (_OPENAI_SDK_OK and bool(_groq_key()))
TTS_AVAILABLE = _have("edge_tts") and _have("pydub")

# audioop is stdlib on Python ≤3.12; removed in 3.13 (use audioop-lts backport).
try:  # pragma: no cover - environment dependent
    import audioop  # type: ignore

    _AUDIOOP_OK = True
except Exception:  # pragma: no cover
    try:
        import audioop_lts as audioop  # type: ignore

        _AUDIOOP_OK = True
    except Exception:
        audioop = None  # type: ignore
        _AUDIOOP_OK = False


# --------------------------------------------------------------------------- #
# Tunables (env-overridable) — phone audio, so frames are 20 ms / 160 µ-law B.
# --------------------------------------------------------------------------- #
SAMPLE_RATE = 16000  # Vobiz L16 stream rate (contentType audio/x-l16;rate=16000)
STT_RATE = 16000  # STT models want 16 kHz PCM16 (== SAMPLE_RATE: no resample)
FRAME_PCM = 640  # 20 ms of PCM16 @ 16 kHz (16000 * 0.02 * 2 bytes)
_SIL_WIN_BYTES = 1024  # 512 samples @16k — Silero VAD min window (D-5 buffer floor)
PCM_SILENCE = b"\x00"  # PCM16 silence == zero bytes


def _env_num(name: str, default: float) -> float:
    """float(env) with safe fallback — bad env value must never kill import."""
    try:
        return float(os.environ.get(name, "") or default)
    except Exception:
        return default


# Shared turn-taking defaults (TURN_SILENCE_MS / TURN_VAD_RMS / TURN_BARGE_MIN_MS)
# give every audio path one knob. The VOBIZ_* envs below still WIN when set, so
# prod is unchanged; only the *defaults* now come from the shared helpers
# (~700 ms silence, RMS 300, ~100 ms barge-in). Import is defensive: if
# turn_detector can't load we keep literal fallbacks (zero behaviour change).
try:  # pragma: no cover - import-safety
    from app.voice_agent.turn_detector import barge_in_frames as _shared_barge_frames
    from app.voice_agent.turn_detector import turn_silence_ms as _shared_silence_ms
    from app.voice_agent.turn_detector import turn_vad_rms as _shared_vad_rms

    _DEF_VAD_RMS = _shared_vad_rms(300)
    _DEF_SILENCE_MS = _shared_silence_ms(650.0)  # keep snappy 650 ms vobiz default
    _DEF_BARGE_FRAMES = _shared_barge_frames(20.0, 100.0)  # 20 ms frames @16k
except Exception:
    _DEF_VAD_RMS, _DEF_SILENCE_MS, _DEF_BARGE_FRAMES = 300, 650.0, 5

_VAD_RMS = int(_env_num("VOBIZ_VAD_RMS", _DEF_VAD_RMS))  # PCM16 RMS speech gate
SILENCE_MS = _env_num(
    "VOBIZ_SILENCE_MS", _DEF_SILENCE_MS
)  # trailing silence that ends an utterance (VOBIZ_SILENCE_MS > TURN_SILENCE_MS > 650 ms default)
MIN_SPEECH_MS = _env_num("VOBIZ_MIN_SPEECH_MS", 300.0)  # ignore sub-300ms blips (coughs/clicks)
MIN_STT_MS = _env_num("VOBIZ_MIN_STT_MS", 400.0)  # drop sub-400ms utterances (STT unreliable)
MAX_UTTER_MS = 15000.0  # hard cap so a long monologue still gets processed
# ~100 ms of speech while we talk = barge-in. Env: VOBIZ_BARGE_MIN_FRAMES wins,
# else TURN_BARGE_MIN_MS (via shared helper), else 5 frames.
BARGE_MIN_FRAMES = max(1, int(_env_num("VOBIZ_BARGE_MIN_FRAMES", _DEF_BARGE_FRAMES)))
# D-13 no-input/silence policy (gated NOINPUT_POLICY, default OFF): caller silent
# this long after the bot finishes -> reprompt; after MAX reprompts -> graceful close.
NOINPUT_MS = _env_num("VOBIZ_NOINPUT_MS", 12000.0)  # 12 s of pure silence = no-input
NOINPUT_MAX_REPROMPTS = max(1, int(_env_num("VOBIZ_NOINPUT_MAX_REPROMPTS", 2)))


# --------------------------------------------------------------------------- #
# STT engine — lazy singleton (model load is heavy; reuse across calls).
# --------------------------------------------------------------------------- #
_STT_ENGINE: tuple | None = None  # ("vosk", model) | ("whisper", model)
_STT_INIT = False
_STT_LOCK = threading.Lock()  # module warmup thread vs executor threads


def _get_stt() -> tuple | None:
    """Load (once) the best available STT model. vosk if VOSK_MODEL_PATH set,
    else faster-whisper. Returns None if neither usable. THREAD-SAFE: module
    warmup thread + per-call executor threads race here; the lock makes late
    callers WAIT for the in-flight load instead of seeing a half-init None."""
    global _STT_ENGINE, _STT_INIT
    if _STT_INIT:
        return _STT_ENGINE
    with _STT_LOCK:
        if _STT_INIT:
            return _STT_ENGINE
        try:
            vosk_path = os.environ.get("VOSK_MODEL_PATH")
            if _VOSK_OK and vosk_path and os.path.isdir(vosk_path):
                try:
                    import vosk  # type: ignore

                    vosk.SetLogLevel(-1)
                    _STT_ENGINE = ("vosk", vosk.Model(vosk_path))
                    logger.info(f"[vobiz-stream] STT engine: vosk ({vosk_path})")
                    return _STT_ENGINE
                except Exception as e:
                    logger.warning(f"[vobiz-stream] vosk load failed: {e}")

            if _FWHISPER_OK:
                try:
                    from faster_whisper import WhisperModel  # type: ignore

                    # base >> tiny for Hindi (tiny Hindi pe bahut weak hai); CPU pe
                    # short utterances ~1-2.5s — acceptable. Env: FWHISPER_MODEL.
                    model_size = os.environ.get("FWHISPER_MODEL", "base")
                    _STT_ENGINE = (
                        "whisper",
                        WhisperModel(model_size, device="cpu", compute_type="int8"),
                    )
                    logger.info(f"[vobiz-stream] STT engine: faster-whisper ({model_size})")
                    return _STT_ENGINE
                except Exception as e:
                    logger.warning(f"[vobiz-stream] faster-whisper load failed: {e}")

            logger.warning("[vobiz-stream] no STT engine available — call will be deaf")
            _STT_ENGINE = None
            return None
        finally:
            _STT_INIT = True


def _stt_sync(kind: str, model: Any, pcm16: bytes) -> str:
    """Blocking transcription of PCM16 16 kHz bytes -> text. Runs in executor."""
    try:
        if kind == "vosk":
            import vosk  # type: ignore

            rec = vosk.KaldiRecognizer(model, STT_RATE)
            rec.AcceptWaveform(pcm16)
            res = json.loads(rec.FinalResult() or "{}")
            return (res.get("text") or "").strip()
        if kind == "whisper":
            import numpy as np  # numpy is a core dep

            audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
            # LANGUAGE FORCE (live-call lesson 2026-06-07): bina language ke
            # whisper Hindi speech ko English samajh ke garbage deta tha
            # ("Bory", "You have to call it a group here") → LLM bhi bhatak
            # jata tha. hi = Hindi/Hinglish dono ke liye sahi (Devanagari out,
            # Gemini handle karta hai). Env override: FWHISPER_LANG (e.g. en).
            lang = os.environ.get("FWHISPER_LANG", "hi")
            segments, _ = model.transcribe(
                audio,
                beam_size=1,
                language=lang,
                vad_filter=True,  # whisper-side VAD trims noise/silence edges
                condition_on_previous_text=False,  # short utterances — no drift
                # Domain prime: telephony audio me in words ki accuracy badhti hai.
                initial_prompt="Hinglish sales call: solar, real estate, insurance, leads, business, appointment.",
            )
            return " ".join(seg.text for seg in segments).strip()
    except Exception as e:
        logger.warning(f"[vobiz-stream] STT failed: {e}")
    return ""


# --------------------------------------------------------------------------- #
# Gemini audio-in STT (PRIMARY hearing, 2026-06-07) — whisper-base Hindi phone
# audio pe weak tha; Gemini multimodal audio ko DIRECT sunta hai (no ASR layer)
# aur Hinglish far better nikalta hai. NEW google-genai SDK (google.genai —
# old google.generativeai se alag namespace, dono coexist). Free tier audio
# input supported (flash-lite 30 RPM). Inline limit 20MB/request — hamare
# utterances ≤15s = ~480KB WAV, comfortably under. Failure of ANY kind => ""
# => caller whisper/vosk pe fall back karta hai (deafness impossible-by-design).
# Env: VOBIZ_STT=groq|gemini|whisper (default 'auto' = groq->gemini->whisper),
# STT_GEMINI_MODEL. Multi-key: app.voice_agent.gemini_keys (shared with LLM).
# --------------------------------------------------------------------------- #
_GEMINI_STT_PROMPT = (
    "Transcribe this Indian phone-call audio EXACTLY as spoken (Hinglish — "
    "Hindi in Devanagari, English words in English). Output ONLY the "
    "transcription, nothing else. If silence/noise, output nothing."
)
_GEMINI_STT_TIMEOUT = _env_num("VOBIZ_STT_TIMEOUT_S", 8.0)

# Per-key google-genai Client cache (multi-key rotation, 2026-06-07). STT shares
# the SAME process-wide active key as the LLM (app.voice_agent.gemini_keys) — so
# when STT exhausts key A's free quota, the LLM stops using A too, and the next
# audio turn rotates to key B. Each key gets its own cached Client (thread-safe).
_GENAI_CLIENTS: dict[str, Any] = {}
_GENAI_LOCK = threading.Lock()


def _get_genai_client(key: str = "") -> Any | None:
    """google-genai Client for ``key`` (defaults to the rotation pool's active
    key, else legacy single settings/env key). Cached per-key. None = SDK
    missing OR no key — caller falls back to whisper."""
    key = (key or "").strip()
    if not key:
        try:
            from app.voice_agent.gemini_keys import active_key

            key = (active_key() or "").strip()
        except Exception:
            key = ""
    if not key:  # legacy single-key fallback (pool import failed)
        try:
            from app.config import settings

            key = (getattr(settings, "gemini_api_key", "") or "").strip()
        except Exception:
            key = ""
        key = key or (os.environ.get("GEMINI_API_KEY", "") or "").strip()
    if not key:
        return None
    client = _GENAI_CLIENTS.get(key)
    if client is not None:
        return client
    with _GENAI_LOCK:
        client = _GENAI_CLIENTS.get(key)
        if client is None:
            try:
                from google import genai  # type: ignore

                client = genai.Client(api_key=key)
                _GENAI_CLIENTS[key] = client
                logger.info("[vobiz-stream] Gemini STT client ready (multi-key pool)")
            except Exception as e:
                logger.warning(f"[vobiz-stream] google-genai init failed: {e}")
                return None
    return client


def _gemini_stt_model() -> str:
    """STT_GEMINI_MODEL env > settings.default_llm; non-gemini value (e.g.
    gpt-4) audio-in pe hamesha fail hota — flash-lite pe clamp (max free quota)."""
    m = (os.environ.get("STT_GEMINI_MODEL", "") or "").strip()
    if not m:
        try:
            from app.config import settings

            m = (getattr(settings, "default_llm", "") or "").strip()
        except Exception:
            m = ""
    return m if m.startswith("gemini") else "gemini-2.5-flash-lite"


def _gemini_has_key() -> bool:
    """Any Gemini key configured (pool, then settings/env fallback)?"""
    try:
        from app.voice_agent.gemini_keys import gemini_keys

        if gemini_keys():
            return True
    except Exception:
        pass
    try:
        from app.config import settings

        if (getattr(settings, "gemini_api_key", "") or "").strip():
            return True
    except Exception:
        pass
    return bool(
        (os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEYS", "")).strip()
    )


def _stt_chain() -> list[str]:
    """Ordered STT providers to try this turn. ``VOBIZ_STT`` forces exactly ONE
    (groq|gemini|whisper). Default ('auto'/empty) = groq (key set) -> gemini
    (SDK+key) -> whisper. The chain ALWAYS ends with whisper so a missing or
    quota-exhausted cloud key can never make the call permanently deaf."""
    forced = (os.environ.get("VOBIZ_STT", "") or "").strip().lower()
    if forced in ("groq", "gemini", "whisper"):
        return [forced]
    chain: list[str] = []
    if _OPENAI_SDK_OK and _groq_key():
        chain.append("groq")
    if _GENAI_OK and _gemini_has_key():
        chain.append("gemini")
    chain.append("whisper")  # local fallback — always present in auto mode
    return chain


def _pcm_to_wav(pcm16: bytes, rate: int = SAMPLE_RATE) -> bytes:
    """PCM16 mono ko in-memory WAV container me wrap karo (stdlib wave) —
    Gemini ko self-describing audio chahiye (raw PCM inline reliable nahi)."""
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(rate)  # 16000 Hz
        wf.writeframes(pcm16)
    return buf.getvalue()


def _gemini_stt_sync(client: Any, model: str, wav_bytes: bytes, bias: str = "") -> str:
    """Blocking Gemini audio transcription (runs in executor). Raises on API
    error — async caller catch karke "" return karta hai (whisper fallback).
    `bias` (D-11, optional): niche/brand context appended to the prompt so
    domain entities transcribe right (default "" = unchanged)."""
    from google.genai import types  # type: ignore

    prompt = _GEMINI_STT_PROMPT
    if (bias or "").strip():
        prompt = f"{prompt}\nContext (likely entities/register, bias spelling): {bias}"
    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            prompt,
        ],
        config=types.GenerateContentConfig(temperature=0.0),
    )
    text = (getattr(resp, "text", None) or "").strip()
    # Model kabhi-kabhi quotes/backticks me wrap kar deta hai — unwrap.
    return text.strip("\"'` ").strip()


# --------------------------------------------------------------------------- #
# VAD helper — RMS of signed-16-bit LE PCM. Prefers audioop; never raises.
# --------------------------------------------------------------------------- #
def _pcm_rms(pcm16: bytes) -> int:
    """RMS amplitude of PCM16 (little-endian) bytes for energy VAD.

    Uses audioop.rms when available; falls back to a pure-Python loop so VAD
    keeps working even if audioop could not be imported. If both fail, returns
    a high value so we err on the side of 'speech' rather than going deaf."""
    if not pcm16:
        return 0
    if _AUDIOOP_OK:
        try:
            return audioop.rms(pcm16, 2)
        except Exception:
            pass
    try:
        import struct

        n = len(pcm16) // 2
        if n == 0:
            return 0
        samples = struct.unpack("<%dh" % n, pcm16[: n * 2])
        return int((sum(s * s for s in samples) / n) ** 0.5)
    except Exception:
        return 32767  # last resort: treat as speech (never permanently deaf)


# --------------------------------------------------------------------------- #
# Sentence splitter — for STREAMING TTS. Split a reply into sentences so we can
# synth + play sentence-by-sentence: the first audio starts after only the FIRST
# short sentence synthesizes, not the whole reply. Splits AFTER danda ।/./?/!
# that is FOLLOWED BY whitespace (so decimals like "10.5" and abbreviations stay
# intact); punctuation stays attached to its sentence (natural intonation). No
# delimiter / empty => the whole text as a single-element list (fast 1-sentence
# path, no regression — most brevity-prompt replies are one sentence).
# --------------------------------------------------------------------------- #
_SENT_SPLIT_RE = re.compile(r"(?<=[।.?!])\s+")


def _split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(t) if p and p.strip()]
    return parts or [t]


# --------------------------------------------------------------------------- #
# Pre-synthesized audio caches (PCM16 @16 kHz) — shared across calls per worker.
# Greeting: keyed by exact opener text+voice (niche/client embedded in text, so
# a stale entry can never play the WRONG greeting). Fillers: short "Hmm/Achha"
# acknowledgments played the instant STT text aata hai (perceived-latency fix).
# --------------------------------------------------------------------------- #
_GREET_CACHE: dict[str, bytes] = {}
_GREET_CACHE_MAX = 64
_FILLER_TEXTS = ("Hmm...", "Achha...", "Ji sir...", "Samajh gayi...", "Ek second...")
_FILLER_PCM: list[bytes] = []
_FILLER_STARTED = False  # synth fillers once per worker (first session does it)
_CELEBRATION_PCM: bytes | None = None
_CELEBRATION_STARTED = False


# --------------------------------------------------------------------------- #
# Per-call session — one instance per WebSocket (per Vobiz docs).
# --------------------------------------------------------------------------- #
class VobizStreamSession:
    """Drives one streamed phone call: listen -> understand -> reply -> speak,
    with energy-VAD turn-taking and barge-in. Never raises out of handle()."""

    def __init__(
        self,
        websocket: Any,
        niche: str = "general",
        client_id: str | None = None,
        client_name: str = "Demo Co",
        voice: str = "hi-IN-SwaraNeural",
    ) -> None:
        self.ws = websocket
        self.niche = (niche or "general").strip() or "general"
        self.client_id = client_id
        self.client_name = client_name or "Demo Co"
        self.voice_role = "telecaller"
        # Stable per-LEAD id for cross-session agent memory (customParameters se).
        # None = memory INERT (safe). call_sid use NAHI karte (har call naya).
        self._lead_phone: str | None = None
        self.voice = voice

        self.stream_sid: str | None = None
        self.hist: list[dict[str, str]] = []  # {role: user|assistant, content}
        self._closed = False
        self._started_at = datetime.now(timezone.utc)  # transcript meta
        self._stt_counts: dict[str, int] = {"groq": 0, "gemini": 0, "whisper": 0}

        # ── per-turn latency metrics (P1; TURN_METRICS, default on, log-only) ──
        # Stamped opportunistically by the hot path: _turn_t0_ms set per utterance,
        # _llm_first/_tts_first stamped by the LLM-stream gen + _play_frames. None
        # outside a turn so unrelated playback (greeting) never mis-stamps.
        self._turn_t0_ms: float | None = None
        self._turn_llm_first_ms: float | None = None
        self._turn_tts_first_ms: float | None = None
        self._turn_metrics: list[dict] = []  # accumulated for the transcript record
        self._stt_bias: str | None = None  # D-11 niche/brand STT bias (lazy, once)
        self._sil_buf = bytearray()  # D-5 per-session Silero rolling window (>=512 samples)
        # D-6 disclosure-leg lock: while the opener (which carries the TRAI AI
        # disclosure) plays, barge-in is ignored so the disclosure is always heard.
        # Cleared on opener-playback completion or a hard safety deadline.
        self._disclosure_active = False
        self._disclosure_deadline_ms = 0.0
        # D-13 no-input watchdog state (NOINPUT_POLICY, default OFF).
        self._last_activity_ms = 0.0
        self._noinput_reprompts = 0
        self._interruptions = 0  # P4-3: barge-in count (interruption tracking)

        # turn-taking / VAD state
        self._speech_buf: list[bytes] = []
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._had_speech = False
        self._speech_segments = 0  # rising-edge count (post-speech grace)
        self._vad_rms = _VAD_RMS

        # playback / barge-in state
        self._speaking = False
        self._play_task: asyncio.Task | None = None
        self._barge_frames = 0
        self._thinking = False
        self._bg_tasks: set = set()  # keep refs so tasks aren't GC'd mid-run

        # ── call recording (VOBIZ_CALL_RECORD=1 se enable) ───────────────────
        # Timeline-mixed PCM16 mono 16 kHz → ek WAV (caller + Swara same clock).
        # data/call_recordings/YYYY-MM-DD/call_{stream_sid}.wav
        # Flag OFF by default — storage cost aur privacy (DPDP consent) ke liye.
        self._rec_enabled: bool = os.environ.get("VOBIZ_CALL_RECORD", "0") == "1"
        self._rec_mixed: bytearray = bytearray()
        self._rec_timeline_samples: int = 0  # master clock = inbound media frames
        self._rec_bot_playhead: int | None = None

        # instant-greeting state (pre-synthesized at WS open, before 'start')
        self._greet_pcm: bytes | None = None
        self._platform_greet_pcms: list[bytes] | None = None
        self._pregen_task: asyncio.Task | None = None
        self._pitch_state = None  # PlatformPitchState when ai_marketing flow active

        # lazy helpers
        self._telecaller = None  # TelecallerBrain — lean phone-tuned (primary)
        self._telecaller_tried = False
        self._brain = None
        self._brain_tried = False
        self._ndm = None  # NaturalDialogManager fallback (cached — heavy)
        self._ndm_tried = False
        self._teardown_done = False  # idempotent _cleanup (WS disconnect + stop)
        # AMD (answering-machine detection) parity — GATED AMD_DETECT (default OFF).
        # Only the FIRST caller utterance is checked (voicemail greeting). When a
        # machine is detected the call is logged + closed to save credits (mirrors
        # the legacy Twilio AMD voicemail-drop/hangup in telephony/webhooks.py).
        # Flag OFF (default) = zero behavior change.
        self._amd_checked = False
        self._amd_machine = False

    # ------------------------------------------------------------------ #
    # Main receive loop
    # ------------------------------------------------------------------ #
    async def handle(self) -> None:
        try:
            await self.ws.accept()
        except Exception as e:
            logger.warning(f"[vobiz-stream] accept failed: {e}")
            return
        logger.info(
            f"[vobiz-stream] WS open niche={self.niche} client={self.client_id} "
            f"(STT={STT_AVAILABLE} TTS={TTS_AVAILABLE} audioop={_AUDIOOP_OK})"
        )
        # INSTANT GREETING — niche WS open par hi pata hai (query param), 'start'
        # event ka wait kyon karein? Opener PCM ABHI synth karo; _greet() phir
        # cache se turant bajata hai (repeat calls: 0ms synth). Fillers bhi.
        try:
            if TTS_AVAILABLE:
                self._pregen_task = asyncio.create_task(self._pregen_greeting())
                self._bg_tasks.add(self._pregen_task)
                self._pregen_task.add_done_callback(self._bg_tasks.discard)
                self._spawn(self._pregen_fillers())
                self._spawn(self._pregen_celebration_sfx())
        except Exception as e:
            logger.debug(f"[vobiz-stream] pregen spawn failed: {e}")
        # STT WARMUP — whisper/vosk model load 10-30s le sakta hai; abhi (greeting
        # ke dauran) executor me load karo taaki FIRST user turn slow na ho.
        # (Module import par bhi ek warmup thread chalta hai — yeh tab no-op hai.)
        try:
            if _LOCAL_STT_OK:

                async def _warm_stt() -> None:
                    try:
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, _get_stt)
                        logger.info("[vobiz-stream] STT warmup done")
                    except Exception as we:
                        logger.debug(f"[vobiz-stream] STT warmup failed: {we}")

                self._spawn(_warm_stt())
        except Exception as e:
            logger.debug(f"[vobiz-stream] STT warmup spawn failed: {e}")
        try:
            while not self._closed:
                try:
                    msg = await self.ws.receive()
                except Exception:
                    break  # disconnected
                mtype = msg.get("type")
                if mtype == "websocket.disconnect":
                    break
                raw = msg.get("text")
                if raw is None and msg.get("bytes") is not None:
                    try:
                        raw = msg["bytes"].decode("utf-8", "ignore")
                    except Exception:
                        raw = None
                if not raw:
                    continue
                try:
                    await self._on_event(raw)
                except Exception as e:
                    logger.warning(f"[vobiz-stream] event error: {e}")
        finally:
            await self._cleanup()

    async def _on_event(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning(f"[vobiz-stream] non-JSON frame: {raw[:120]!r}")
            return
        # Protocol visibility: pehle kuch raw events INFO me — Vobiz ke exact
        # field names/shape capture karne ke liye (media payload truncate).
        self._event_count = getattr(self, "_event_count", 0) + 1
        if self._event_count <= 6 and data.get("event") != "media":
            logger.info(f"[vobiz-stream] raw#{self._event_count}: {str(data)[:300]}")
        elif self._event_count <= 3:
            logger.info(f"[vobiz-stream] raw#{self._event_count} media keys: {list(data.keys())}")

        event = data.get("event")
        # Vobiz stream id field = "streamId" (NOT Twilio's streamSid). Capture
        # any known variant, top-level or inside start{}. playAudio doesn't even
        # need it — we only keep it for logging/checkpoints.
        start = data.get("start") or {}
        sid = (
            data.get("streamId")
            or data.get("streamSid")
            or data.get("stream_sid")
            or start.get("streamId")
            or start.get("streamSid")
            or start.get("stream_sid")
        )
        if sid and not self.stream_sid:
            self.stream_sid = sid

        if event == "media":
            payload = (data.get("media") or {}).get("payload")
            if payload:
                # Greet on first audio too (in case start was missed); NOT gated
                # on sid — Vobiz playAudio carries no stream id.
                await self._maybe_greet()
                await self._on_media(payload)
        elif event == "start":
            params = start.get("customParameters") or {}
            self.niche = (params.get("niche") or self.niche).strip() or "general"
            self.client_id = params.get("client_id") or self.client_id
            try:
                from app.voice_agent.voice_roles import normalize_role

                raw_role = params.get("voice_role") or params.get("flow") or "telecaller"
                self.voice_role = normalize_role(raw_role)
            except Exception:
                self.voice_role = "telecaller"
            # Optional stable lead id for agent memory (flag-gated; pure read).
            for _k in ("lead_phone", "lead_id", "from", "From", "caller", "customer_phone"):
                if params.get(_k):
                    self._lead_phone = str(params[_k]).strip()
                    break
            logger.info(
                f"[vobiz-stream] start streamId={self.stream_sid} "
                f"niche={self.niche} role={self.voice_role}"
            )
            await self._maybe_greet()
        elif event == "dtmf":
            digit = (data.get("dtmf") or {}).get("digit")
            logger.info(f"[vobiz-stream] dtmf={digit}")
        elif event == "stop":
            logger.info(f"[vobiz-stream] stop sid={self.stream_sid}")
            self._closed = True
        elif event == "playedStream":
            logger.debug("[vobiz-stream] playedStream (playAudio finished) — no-op")
        elif event == "clearedAudio":
            logger.debug("[vobiz-stream] clearedAudio (buffer flushed) — no-op")
        elif event == "connected":
            logger.info("[vobiz-stream] connected event")

    async def _maybe_greet(self) -> None:
        """Greet exactly once. NOT gated on stream id — Vobiz playAudio needs
        no sid, so we can (and must) speak as soon as the stream starts."""
        if getattr(self, "_greeted", False):
            return
        self._greeted = True
        await self._greet()

    # ------------------------------------------------------------------ #
    # Inbound audio -> VAD -> utterance
    # ------------------------------------------------------------------ #
    async def _on_media(self, payload: str) -> None:
        # L16: the base64 payload IS raw PCM16 @16 kHz already — NO µ-law decode
        # and NO 8k->16k resample. Decoded bytes go straight to VAD + STT buffer.
        try:
            pcm16 = base64.b64decode(payload)
        except Exception:
            return
        if not pcm16:
            return
        # Recording: mix caller audio onto the call timeline (WAV on hangup).
        if self._rec_enabled:
            self._rec_mix_caller(self._rec_timeline_samples, pcm16)
            self._rec_timeline_samples += len(pcm16) // 2
        rms = _pcm_rms(pcm16)
        is_speech = rms >= self._vad_rms
        # Silero VAD gate (USE_SILERO_VAD=1): filters ambient noise/echo from false
        # speech states. D-5 FIX: Silero needs >=512 samples @16k, but a frame is only
        # 320 (20 ms) -> the old per-frame call always fell back to RMS (Silero dead).
        # Buffer per-session to a small rolling window (PER SESSION, not the shared
        # singleton, so concurrent calls never mix audio) and gate on that. Returns
        # None when disabled/unavailable -> keep the RMS decision (zero change at default).
        try:
            from app.voice_agent.turn_detector import get_speech_gate

            self._sil_buf += pcm16
            if len(self._sil_buf) > _SIL_WIN_BYTES * 2:
                del self._sil_buf[: -_SIL_WIN_BYTES * 2]  # keep last ~64 ms
            if len(self._sil_buf) >= _SIL_WIN_BYTES:
                _sil = get_speech_gate().is_speech(bytes(self._sil_buf))
                if _sil is not None:
                    is_speech = _sil
        except Exception:
            pass
        # D-13 no-input watchdog: user speech resets timer + reprompt count; bot
        # playback resets the timer only (idle counts from when the bot STOPS).
        _na_now = _now_ms()
        if is_speech:
            self._last_activity_ms = _na_now
            self._noinput_reprompts = 0
        elif self._speaking:
            self._last_activity_ms = _na_now
        dur_ms = (len(pcm16) / 2) / SAMPLE_RATE * 1000.0  # 640 bytes == 20 ms

        # While we're speaking: only watch for barge-in (D-6: gated + disclosure-lock).
        if self._speaking:
            if is_speech and self._barge_allowed():
                self._barge_frames += 1
                if self._barge_frames < BARGE_MIN_FRAMES:
                    return
                await self._barge_in()  # cancels playback, sends clearAudio, falls through
            else:
                self._barge_frames = 0
                return

        # While thinking (STT+LLM+synth in flight): drop input to avoid pile-up.
        if self._thinking:
            return

        if is_speech:
            # Rising edge (silence→speech, or first speech) = a new speech segment.
            if self._silence_ms > 0 or not self._had_speech:
                self._speech_segments += 1
            self._speech_buf.append(pcm16)
            self._speech_ms += dur_ms
            self._silence_ms = 0.0
            self._had_speech = True
        elif self._had_speech:
            self._speech_buf.append(pcm16)  # keep a little trailing silence
            self._silence_ms += dur_ms

        # POST-SPEECH GRACE: beyond the silence + MIN_SPEECH_MS gates, require the
        # utterance to be "substantial" — ≥2 speech segments OR ≥400ms cumulative
        # speech — so a tiny 1-word blip doesn't finalize mid-sentence. A genuine
        # lone short word still goes through once the caller clearly stops
        # (≥2× SILENCE_MS) so "haan"/"ji" are never permanently dropped.
        substantial = self._speech_segments >= 2 or self._speech_ms >= 400.0
        # Short "hello/haan/ji" — 1 segment + ≥250ms is enough once silence ends.
        if not substantial and self._speech_ms >= 250.0 and self._silence_ms >= SILENCE_MS:
            substantial = True
        ended = (
            self._had_speech
            and self._silence_ms >= SILENCE_MS
            and self._speech_ms >= MIN_SPEECH_MS
            and substantial
        )
        # HARD end = 2x silence — always finalizes (also the Smart-Turn safety floor
        # so a "never endpoint" verdict can't hold a turn forever).
        hard_end = (
            self._had_speech
            and self._speech_ms >= MIN_SPEECH_MS
            and self._silence_ms >= SILENCE_MS * 2
        )
        if hard_end:
            ended = True
        too_long = self._speech_ms >= MAX_UTTER_MS
        if ended or too_long:
            # D-4: semantic end-of-turn confirm (USE_SMART_TURN). ONLY on a normal
            # silence-end (not the hard 2x-silence floor or the too_long cap): if
            # Smart-Turn says the caller only paused mid-sentence, keep listening.
            # Inert without pipecat/flag -> confirm_end_of_turn returns True -> unchanged.
            if ended and not too_long and not hard_end:
                try:
                    from app.voice_agent.turn_detector import confirm_end_of_turn

                    if not confirm_end_of_turn(
                        True, pcm16=b"".join(self._speech_buf), sample_rate=SAMPLE_RATE
                    ):
                        return  # mid-sentence pause — keep buffering this turn
                except Exception:
                    pass
            utt = b"".join(self._speech_buf)
            self._reset_speech()
            self._spawn(self._on_utterance(utt))
            return

        # D-13 no-input watchdog (gated NOINPUT_POLICY, default OFF): caller silent
        # too long while idle (bot not speaking/thinking, no utterance in progress)
        # -> reprompt, then graceful close. Debounced via _last_activity_ms reset.
        if (
            not self._had_speech
            and self._last_activity_ms > 0
            and (_na_now - self._last_activity_ms) >= NOINPUT_MS
            and self._noinput_enabled()
        ):
            self._last_activity_ms = _na_now
            self._spawn(self._noinput_handle())

    def _spawn(self, coro) -> None:
        """Fire-and-forget a coroutine, holding a ref until it finishes."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _reset_speech(self) -> None:
        self._speech_buf = []
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._had_speech = False
        self._speech_segments = 0

    def _disclosure_locked(self) -> bool:
        """D-6: True while the opener/AI-disclosure leg is playing and the lock is
        on (DISCLOSURE_LOCK, default ON) — barge-in is suppressed so the TRAI
        disclosure is always heard. Auto-clears past a hard safety deadline so it
        can never stick. Never raises."""
        try:
            if not self._disclosure_active:
                return False
            if (os.environ.get("DISCLOSURE_LOCK", "1") or "1").strip().lower() in (
                "0",
                "false",
                "no",
                "off",
            ):
                return False
            if _now_ms() > self._disclosure_deadline_ms:
                self._disclosure_active = False  # safety: never hold past the cap
                return False
            return True
        except Exception:
            return False

    def _barge_allowed(self) -> bool:
        """D-6: barge-in master gate. OFF when BARGE_IN_ENABLED=0 (bot can't be
        cut) or while the disclosure leg is locked. Default ON = current behaviour
        except the disclosure-leg protection."""
        try:
            if (os.environ.get("BARGE_IN_ENABLED", "1") or "1").strip().lower() in (
                "0",
                "false",
                "no",
                "off",
            ):
                return False
            return not self._disclosure_locked()
        except Exception:
            return True

    def _begin_disclosure(self) -> None:
        """Mark the opener/disclosure leg active (barge-locked) with a 6 s safety
        cap. Called right before the greeting plays."""
        self._disclosure_active = True
        self._disclosure_deadline_ms = _now_ms() + 6000.0

    @staticmethod
    def _noinput_enabled() -> bool:
        """D-13 no-input/silence policy gate (default OFF)."""
        return (os.environ.get("NOINPUT_POLICY", "0") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    async def _noinput_handle(self) -> None:
        """D-13: caller silent too long. Reprompt up to NOINPUT_MAX_REPROMPTS, then
        close gracefully. Best-effort / never raises. The caller (_on_media) already
        checked the flag + idle window; we re-check liveness to dodge a late race."""
        try:
            if self._closed or self._speaking or self._thinking or self._had_speech:
                return
            if self._noinput_reprompts < NOINPUT_MAX_REPROMPTS:
                self._noinput_reprompts += 1
                logger.info(
                    f"[vobiz-stream {self.stream_sid}] no-input reprompt "
                    f"#{self._noinput_reprompts}"
                )
                await self._say("Hello, kya aap line par hain? Boliye, main sun rahi hoon.")
            else:
                logger.info(f"[vobiz-stream {self.stream_sid}] no-input — graceful close")
                try:
                    await self._say_and_wait(
                        "Lagta hai abhi awaaz nahi aa rahi — main baad me try karungi. "
                        "Aapka din shubh rahe!"
                    )
                except Exception:
                    pass
                self._closed = True
                self._stop_play()
                try:
                    await self.ws.close()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[vobiz-stream] no-input handle failed: {e}")

    @staticmethod
    def _is_junk(text: str) -> bool:
        """True if STT text is junk — too short (<3 chars) or no alphanumeric/
        Devanagari word char (punctuation/noise only). Dropped before any LLM
        call so we never think (or spend) on garbage."""
        t = (text or "").strip()
        if len(t) < 3:
            return True
        return re.search(r"[0-9A-Za-zऀ-ॿ]", t) is None

    @staticmethod
    def _is_ivr_prompt(text: str) -> bool:
        """US/IN office IVR — record name / leave message (not a live human)."""
        low = (text or "").lower()
        markers = (
            "record your name",
            "reason for calling",
            "leave a message",
            "after the tone",
            "after the beep",
            "voicemail",
            "not available",
            "press 1",
            "press one",
            "extension",
            "mailbox",
        )
        return any(m in low for m in markers)

    @staticmethod
    def _ivr_voicemail_reply() -> str:
        return (
            "Namaste, main Swara LeadGen AI se bol rahi hoon. "
            "Chhote business ke liye AI marketing — posts, Google profile, festival posters, "
            "₹1,199 se shuru. Callback ke liye leadsgenai.in ya is number par reply kijiye. Dhanyavaad."
        )

    async def _on_utterance(self, pcm16: bytes) -> None:
        if self._thinking:
            return
        self._thinking = True
        # ── per-turn latency metrics (P1; TURN_METRICS, default on, log-only) ──
        # t0 = "user stopped talking". stt_ms is timed directly; llm_first/tts_first
        # are stamped by the LLM-stream gen + _play_frames; turn_ms computed at the
        # end. _record decides if this utterance is a real turn worth recording
        # (junk/duplicate STT noise is skipped). Never changes call behaviour.
        self._turn_t0_ms = _now_ms()
        self._turn_llm_first_ms = None
        self._turn_tts_first_ms = None
        _stt_ms: float | None = None
        _outcome = "ok"
        _record = False
        _reply_text = ""
        try:
            _t_stt = _now_ms()
            text = (await self._stt(pcm16) or "").strip()
            _stt_ms = _now_ms() - _t_stt
            if not text:
                _outcome = "empty_stt"
                _record = True
                return
            # JUNK GUARD — don't spend an LLM call (or speak) on garbage STT.
            # Too-short / punctuation-only / noise → drop silently, keep listening.
            if self._is_junk(text):
                logger.debug(f"[vobiz-stream] dropped junk STT: {text!r}")
                _outcome = "junk"
                return
            # Skip an exact repeat of the last user turn (STT echo / duplicate).
            last_user = next(
                (m.get("content", "") for m in reversed(self.hist) if m.get("role") == "user"), ""
            )
            if text == (last_user or "").strip():
                logger.debug(f"[vobiz-stream] dropped duplicate STT: {text!r}")
                _outcome = "dup"
                return
            logger.info(f"[vobiz-stream {self.stream_sid}] user: {text}")
            _record = True
            # IVR / voicemail gate — structured message, "dobara boliye" mat bolo.
            if self._is_ivr_prompt(text):
                reply = self._ivr_voicemail_reply()
                self.hist.append({"role": "user", "content": text})
                self.hist.append({"role": "assistant", "content": reply})
                logger.info(f"[vobiz-stream {self.stream_sid}] bot(ivr): {reply[:80]}...")
                _outcome = "ivr"
                _reply_text = reply
                await self._say(reply)
                return
            # AMD parity (GATED AMD_DETECT, default OFF) — check ONLY the first
            # caller utterance for a voicemail/answering-machine greeting. On a
            # machine, log + close the stream (saves credits) instead of running
            # the AI conversation against a recording. Never raises; flag OFF =
            # no-op so default flow is unchanged.
            if not self._amd_checked:
                self._amd_checked = True
                try:
                    if await self._amd_check(text):
                        _outcome = "amd"
                        return
                except Exception as e:
                    logger.debug(f"[vobiz-stream] AMD check skip: {e}")
            self.hist.append({"role": "user", "content": text})
            # SPONTANEITY: LLM+TTS se pehle turant cached "Hmm/Achha" filler
            # bajao — 1-3s ki think-window me line dead na lage. Inline await
            # (~0.5s, acceptable); _run_play har frame pe _speaking check karta
            # hai, isliye barge-in (jo flag girata hai) filler ko bhi kaat deta.
            try:
                _filler_on = (os.environ.get("USE_THINKING_FILLER", "1") or "1").strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "off",
                )
                if _filler_on and _FILLER_PCM and TTS_AVAILABLE and not self._speaking:
                    self._stop_play()
                    self._speaking = True
                    self._barge_frames = 0
                    await self._run_play(random.choice(_FILLER_PCM))  # D-7 thinking filler
            except Exception as e:
                logger.debug(f"[vobiz-stream] filler play failed: {e}")
            reply = await self._think_and_say_stream(text)
            if not reply:
                reply = await self._think(text)
                # Non-stream path has no token streaming → first-token == reply-ready.
                if self._turn_llm_first_ms is None and self._turn_t0_ms is not None:
                    self._turn_llm_first_ms = _now_ms() - self._turn_t0_ms
                if reply:
                    logger.info(f"[vobiz-stream {self.stream_sid}] bot: {reply}")
                    self.hist.append({"role": "assistant", "content": reply})
                    _reply_text = reply
                    await self._say(reply)
                else:
                    _outcome = "no_reply"
            elif reply:
                logger.info(f"[vobiz-stream {self.stream_sid}] bot(stream): {reply}")
                self.hist.append({"role": "assistant", "content": reply})
                _reply_text = reply
            elif text.strip():
                # Last-resort — user ne bola par koi reply generate nahi hua.
                fallback = "Ji sir, sun pa rahi hoon — haan boliye, kya help chahiye?"
                self.hist.append({"role": "assistant", "content": fallback})
                _outcome = "fallback"
                _reply_text = fallback
                await self._say(fallback)
        except Exception as e:
            logger.warning(f"[vobiz-stream] utterance handling failed: {e}")
            _outcome = "error"
        finally:
            self._thinking = False
            if _record:
                try:
                    turn_ms = (
                        _now_ms() - self._turn_t0_ms if self._turn_t0_ms is not None else None
                    )
                    self._record_turn(_stt_ms, turn_ms, _outcome, _reply_text)
                except Exception:
                    pass
            self._turn_t0_ms = None

    def _record_turn(
        self,
        stt_ms: float | None,
        turn_ms: float | None,
        outcome: str,
        reply_text: str,
    ) -> None:
        """Build + persist one per-turn latency record (P1). Best-effort; the
        accumulated list rides on the transcript and each turn is also appended
        to data/turn_metrics/ for cross-call P50/P95 rollups. Never raises."""
        rec = {
            "path": "vobiz_stream",
            "call_id": self.stream_sid or "",
            "niche": self.niche or "",
            "client_id": str(self.client_id or ""),
            "outcome": outcome,
            "stt_ms": round(stt_ms, 1) if stt_ms is not None else None,
            "llm_first_ms": (
                round(self._turn_llm_first_ms, 1)
                if self._turn_llm_first_ms is not None
                else None
            ),
            "tts_first_ms": (
                round(self._turn_tts_first_ms, 1)
                if self._turn_tts_first_ms is not None
                else None
            ),
            "turn_ms": round(turn_ms, 1) if turn_ms is not None else None,
            "reply_words": len((reply_text or "").split()),
        }
        # Keep the in-memory list bounded (a call won't reach this, but be safe).
        if len(self._turn_metrics) < 500:
            self._turn_metrics.append({k: v for k, v in rec.items() if v is not None})
        _record_turn_metric(rec)

    async def _amd_check(self, text: str) -> bool:
        """Answering-machine detection on the first caller utterance.

        GATED `AMD_DETECT` (default OFF). Returns True if a machine/voicemail was
        detected AND the call should be aborted (caller drops out of the loop);
        the caller in _on_utterance then returns early. Flag OFF → always False
        (no-op, default flow preserved). Never raises.

        Mirrors the legacy Twilio AMD in telephony/webhooks.py (machine → hang up
        / voicemail-drop) but for the LIVE Vobiz stream path, which has no
        provider AnsweredBy signal — so we use the transcript-based detector on
        the first greeting.
        """
        if os.environ.get("AMD_DETECT", "0").strip().lower() not in ("1", "true", "yes"):
            return False
        try:
            from app.voice_agent.amd import AnsweringMachineDetector

            detector = AnsweringMachineDetector()
            result = detector.detect_from_transcript(text)
        except Exception as e:
            logger.debug(f"[vobiz-stream] AMD detector unavailable: {e}")
            return False
        if not result.is_machine:
            return False

        self._amd_machine = True
        logger.info(
            f"[vobiz-stream {self.stream_sid}] AMD: machine detected "
            f"(conf={result.confidence}, reason={result.reason}) — aborting call"
        )
        try:  # Team feed visibility (best-effort)
            from app.platform.team import log_event

            log_event(
                "swara",
                "amd_machine",
                f"Voicemail/machine detected on call (niche {self.niche}) — aborted",
                status="warn",
                meta={"confidence": result.confidence, "reason": result.reason},
            )
        except Exception:
            pass
        # Close the WS gracefully — _cleanup() (idempotent) runs metering/transcript.
        try:
            self._closed = True
            self._stop_play()
            await self.ws.close()
        except Exception as e:
            logger.debug(f"[vobiz-stream] AMD close failed: {e}")
        return True

    def _get_stt_bias(self) -> str:
        """D-11 STT bias string for THIS call (niche + client), computed once.
        Niche/client are final after the 'start' event, so build lazily."""
        if self._stt_bias is None:
            try:
                from app.voice_agent.niche_scripts import stt_keyterms

                self._stt_bias = stt_keyterms(self.niche, self.client_name) or ""
            except Exception:
                self._stt_bias = ""
        return self._stt_bias

    async def _stt(self, pcm16: bytes) -> str:
        # Sub-350ms audio reliably transcribe NAHI hota (whisper blips pe
        # hallucinate karta hai — mishearing source) — drop early.
        try:
            if not pcm16 or (len(pcm16) / 2) / SAMPLE_RATE * 1000.0 < MIN_STT_MS:
                return ""
        except Exception:
            pass
        # PROVIDER CHAIN (2026-06-07): groq (free Whisper-large-v3, fast LPU) →
        # gemini (multimodal audio-in, multi-key) → whisper/vosk (local) → "".
        # Har provider fail/empty pe agla try hota hai — quota khatam ho jaaye
        # to bhi call deaf nahi hoti (chain hamesha local whisper pe khatam).
        for provider in _stt_chain():
            try:
                if provider == "groq":
                    text = await self._groq_transcribe(pcm16)
                elif provider == "gemini":
                    text = await self._gemini_transcribe(pcm16)
                else:
                    text = await self._whisper_transcribe(pcm16)
            except Exception as e:
                logger.warning(f"[vobiz-stream] STT provider {provider} errored: {e}")
                continue
            if text:
                self._stt_counts[provider] = self._stt_counts.get(provider, 0) + 1
                logger.debug(f"[vobiz-stream] stt={provider}: {text[:80]!r}")
                return text
        return ""

    async def _groq_transcribe(self, pcm16: bytes) -> str:
        """Groq Whisper-large-v3 STT (PRIMARY when GROQ_API_KEY set), via the
        shared free_ai layer (OpenAI-compatible audio.transcriptions). PCM16 16k
        → in-memory WAV → text. Returns "" on ANY failure (caller falls to
        gemini → local whisper). Free tier + Groq LPU = fast, strong on Hindi."""
        if not _groq_key():
            return ""
        try:
            from app.voice_agent.free_ai import transcribe_audio

            wav = _pcm_to_wav(pcm16)
            lang = (os.environ.get("GROQ_STT_LANG", "") or "hi").strip()
            text, _provider = await transcribe_audio(wav, language=lang, prompt=self._get_stt_bias())
            return (text or "").strip().strip("\"'` ").strip()
        except Exception as e:
            logger.warning(f"[vobiz-stream] Groq STT failed ({e}) — fallback")
            return ""

    async def _gemini_transcribe(self, pcm16: bytes) -> str:
        """Gemini multimodal audio-in STT: PCM16 16k → in-memory WAV →
        google-genai generate_content (executor, hard timeout). MULTI-KEY: uses
        the rotation pool's active key; on a quota/429 error it rotates to the
        next key and retries ONCE. Returns "" on any other failure — caller
        falls to whisper. Free-tier tokens (~32/sec audio); 15s ≈ 480KB WAV."""
        try:
            from app.voice_agent.gemini_keys import (
                active_key,
                advance_key,
                is_quota_error,
                key_count,
            )
        except Exception:  # pool unavailable — single-key, no rotation
            active_key = lambda: ""  # noqa: E731
            advance_key = lambda bad="": ""  # noqa: E731
            is_quota_error = lambda e: False  # noqa: E731
            key_count = lambda: 1  # noqa: E731

        loop = asyncio.get_event_loop()
        wav = _pcm_to_wav(pcm16)
        model = _gemini_stt_model()
        for attempt in range(2):
            key = active_key()
            try:
                client = await loop.run_in_executor(None, _get_genai_client, key)
                if client is None:
                    return ""
                text = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, _gemini_stt_sync, client, model, wav, self._get_stt_bias()
                    ),
                    timeout=_GEMINI_STT_TIMEOUT,
                )
                return (text or "").strip()
            except asyncio.TimeoutError:
                logger.warning("[vobiz-stream] Gemini STT timeout — whisper fallback")
                return ""
            except Exception as e:
                if attempt == 0 and is_quota_error(e) and key_count() > 1:
                    advance_key(key)
                    logger.warning("[vobiz-stream] Gemini STT quota — rotated key, retrying")
                    continue
                logger.warning(f"[vobiz-stream] Gemini STT failed ({e}) — whisper fallback")
                return ""
        return ""

    async def _whisper_transcribe(self, pcm16: bytes) -> str:
        """Local STT (faster-whisper / vosk) — always-available final fallback.
        Model load + transcription both in the executor so the event loop never
        blocks (warmup in-flight => the wait happens on a worker thread)."""
        loop = asyncio.get_event_loop()
        try:
            eng = await loop.run_in_executor(None, _get_stt)
            if not eng:
                return ""
            kind, model = eng
            return (await loop.run_in_executor(None, _stt_sync, kind, model, pcm16)) or ""
        except Exception as e:
            logger.warning(f"[vobiz-stream] local STT executor failed: {e}")
            return ""

    # ------------------------------------------------------------------ #
    # Platform pitch flow (ai_marketing outbound — LeadGen AI self-sale)
    # ------------------------------------------------------------------ #
    async def _platform_pitch_reply(self, text: str) -> str | None:
        if self._pitch_state is None:
            return None
        try:
            from app.voice_agent.platform_pitch import next_reply

            reply, self._pitch_state = next_reply(self._pitch_state, text)
            if reply is None:
                return None
            if self._pitch_state.phase == "discovery":
                # Phone cold-call: celebration chime = unprofessional; web-call only.
                if os.environ.get("PHONE_CELEBRATION", "0").strip().lower() in ("1", "true", "yes"):
                    await self._play_celebration()
                tc = self._get_telecaller()
                if tc is not None and hasattr(tc, "confirm_interest"):
                    tc.confirm_interest()
            return reply
        except Exception as e:
            logger.debug(f"[vobiz-stream] platform_pitch_reply failed: {e}")
            return None

    async def _play_celebration(self) -> None:
        """Short celebration SFX before praise line (platform yes-path)."""
        global _CELEBRATION_PCM
        pcm = _CELEBRATION_PCM
        if not pcm:
            try:
                from app.voice_agent.platform_pitch import generate_celebration_pcm

                pcm = generate_celebration_pcm()
            except Exception:
                return
        if not pcm or not TTS_AVAILABLE:
            return
        try:
            self._stop_play()
            self._speaking = True
            self._barge_frames = 0
            await self._run_play(pcm)
        except Exception as e:
            logger.debug(f"[vobiz-stream] celebration play failed: {e}")

    async def _say_and_wait(self, text: str) -> None:
        """Speak one line and wait until playback finishes."""
        await self._say(text)
        if self._play_task and not self._play_task.done():
            try:
                await self._play_task
            except asyncio.CancelledError:
                pass

    async def _pregen_celebration_sfx(self) -> None:
        global _CELEBRATION_PCM, _CELEBRATION_STARTED
        if _CELEBRATION_STARTED:
            return
        _CELEBRATION_STARTED = True
        try:
            from app.voice_agent.platform_pitch import (
                celebration_audio_path,
                generate_celebration_pcm,
            )

            path = celebration_audio_path()
            if path:
                pcm = await self._load_audio_file_pcm(path)
                if pcm:
                    _CELEBRATION_PCM = pcm
                    return
            _CELEBRATION_PCM = generate_celebration_pcm()
        except Exception as e:
            logger.debug(f"[vobiz-stream] celebration pregen failed: {e}")

    async def _load_audio_file_pcm(self, path: str) -> bytes:
        """Decode mp3/wav to PCM16 @16 kHz (pydub+ffmpeg when available)."""
        try:
            from pydub import AudioSegment

            def _decode() -> bytes:
                fmt = "mp3" if path.lower().endswith(".mp3") else "wav"
                seg = AudioSegment.from_file(path, format=fmt)
                seg = seg.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
                return seg.raw_data

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _decode)
        except Exception as e:
            logger.debug(f"[vobiz-stream] audio file decode failed ({path!r}): {e}")
            return b""

    # ------------------------------------------------------------------ #
    # Thinking (LLM) — niche-aware Hinglish reply, defensive fallbacks.
    # ------------------------------------------------------------------ #
    async def _think(self, text: str) -> str:
        # Platform pitch interest gate (ai_marketing only) — before LLM.
        pr = await self._platform_pitch_reply(text)
        if pr is not None:
            return pr

        # 1) TelecallerBrain — lean phone-tuned prompt (max 2 sentences, one
        #    question/turn, niche qualification flow). Empty reply => fall through.
        tc = self._get_telecaller()
        if tc is not None:
            try:
                reply = await tc.reply(self.hist, text)
                if reply and reply.strip():
                    return reply.strip()
            except Exception as e:
                logger.warning(f"[vobiz-stream] TelecallerBrain failed: {e}")

        # 2) LLMBrain — heavier generic brain (ML/RAG path).
        brain = self._get_brain()
        if brain is not None:
            try:
                reply = await brain.generate_response(
                    conversation_history=self.hist,
                    niche=self.niche,
                    client_name=self.client_name,
                    client_service=self.niche,
                )
                if reply and str(reply).strip():
                    return str(reply).strip()
            except Exception as e:
                logger.warning(f"[vobiz-stream] LLM failed: {e}")

        # 3) Fallback: NaturalDialogManager (rule-based reply, degrades w/o LLM).
        ndm = self._get_ndm()
        if ndm is not None:
            try:
                state = ndm.new_conversation()
                state.history = list(self.hist)
                out = await ndm.respond(text, state)
                if getattr(out, "text", "").strip():
                    return out.text.strip()
            except Exception as e:
                logger.debug(f"[vobiz-stream] natural_dialog fallback failed: {e}")

        return "Maaf kijiye, awaaz thodi clear nahi aayi — aap dobara bata sakte hain?"

    async def _think_and_say_stream(self, text: str) -> str:
        """LLM stream → sentence TTS pipeline (USE_LLM_STREAM_TTS=1). Returns full reply or ''."""
        try:
            from app.voice_agent.llm_stream_tts import stream_tts_enabled

            if not stream_tts_enabled() or not TTS_AVAILABLE:
                return ""
        except Exception:
            return ""
        pr = await self._platform_pitch_reply(text)
        if pr is not None:
            await self._say(pr)
            return pr
        tc = self._get_telecaller()
        if tc is None:
            return ""
        parts: list[str] = []

        async def _gen():
            async for sent in tc.reply_stream_sentences(self.hist, text):
                # P1: first streamed sentence → time-to-first-token for this turn.
                if self._turn_llm_first_ms is None and self._turn_t0_ms is not None:
                    self._turn_llm_first_ms = _now_ms() - self._turn_t0_ms
                parts.append(sent)
                yield sent

        try:
            await self._say_from_sentence_gen(_gen())
            return " ".join(parts).strip()
        except Exception as e:
            logger.debug("[vobiz-stream] think_and_say_stream failed: %s", e)
            return ""

    def _get_ndm(self):
        if self._ndm_tried:
            return self._ndm
        self._ndm_tried = True
        try:
            from app.voice_agent.natural_dialog import NaturalDialogManager

            # brain=False sentinel keeps it rule-based (None would auto-build LLM).
            self._ndm = NaturalDialogManager(
                niche=self.niche,
                client_name=self.client_name,
                client_service=self.niche,
                brain=False,
            )
        except Exception as e:
            logger.debug(f"[vobiz-stream] NaturalDialogManager unavailable: {e}")
            self._ndm = None
        return self._ndm

    def _get_telecaller(self):
        """Lazy per-session TelecallerBrain (built at first use, AFTER 'start'
        event — so niche/client from customParameters are already final)."""
        if self._telecaller_tried:
            return self._telecaller
        self._telecaller_tried = True
        try:
            from app.voice_agent.telecaller_brain import TelecallerBrain

            self._telecaller = TelecallerBrain(
                niche=self.niche,
                client_name=self.client_name,
                client_id=self.client_id,
                voice_role=getattr(self, "voice_role", "telecaller"),
            )
            # Agent memory (AGENT_MEMORY flag): per-(client+lead) subject -> cross-session
            # recall/remember in brain.reply(). Stable lead id na ho to inert (no leak).
            try:
                from app.voice_agent import agent_memory

                if agent_memory.is_enabled() and self._lead_phone:
                    self._telecaller.set_memory_subject(
                        f"{self.client_id or 'na'}:{self._lead_phone}"
                    )
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[vobiz-stream] TelecallerBrain unavailable: {e}")
            self._telecaller = None
        return self._telecaller

    def _get_brain(self):
        if self._brain_tried:
            return self._brain
        self._brain_tried = True
        try:
            from app.voice_agent.llm_brain import LLMBrain

            self._brain = LLMBrain()
        except Exception as e:
            logger.warning(f"[vobiz-stream] LLMBrain unavailable: {e}")
            self._brain = None
        return self._brain

    # ------------------------------------------------------------------ #
    # Outbound speech — EdgeTTS -> µ-law -> 20 ms frames
    # ------------------------------------------------------------------ #
    def _opening_line(self) -> str:
        """Public opener — wraps the raw line with the TRAI up-front AI-disclosure
        gate (always-on, never gated off) so every call discloses it is an AI
        BEFORE the pitch. All call-sites + the greeting cache-key go through here."""
        try:
            from app.voice_agent.niche_scripts import ensure_ai_disclosure, ensure_permission_ask

            # AI disclosure (always-on) + permission/timing ask (D-9, PERMISSION_OPENER).
            return ensure_permission_ask(ensure_ai_disclosure(self._opening_line_raw()))
        except Exception:
            return self._opening_line_raw()

    def _opening_line_raw(self) -> str:
        """PURELY STATIC permission-based opener (Gong: ~11% vs 2.3% generic).
        PREFERS the professional niche-script opening (researched, niche-specific)
        with placeholders filled; falls back to the NICHES pitch_hook template.
        NO TelecallerBrain/LLM/genai-import here: opener instant + WS-open par
        pre-synthesizable hona chahiye. (TelecallerBrain sirf _think replies ke
        liye hai.)"""
        try:
            from app.voice_agent.platform_pitch import is_platform_pitch, opening_segments

            if is_platform_pitch(self.niche):
                segs = opening_segments()
                return segs[0] if segs else ""
        except Exception:
            pass
        # 1) Professional script opening (best — niche-specific permission opener).
        try:
            from app.voice_agent.niche_scripts import get_script

            opening = (get_script(self.niche).get("opening") or "").strip()
            if opening:
                # Fill placeholders + align to the female Swara TTS voice.
                opening = (
                    opening.replace("[Company]", self.client_name)
                    .replace("[Name]", "Swara")
                    .replace("[Project]", "hamare project")
                    .replace("[project]", "hamare project")
                    .replace("raha hoon", "rahi hoon")
                )
                return opening
        except Exception:
            pass
        # 2) Fallback: NICHES pitch_hook template (previous behavior).
        hook = ""
        try:
            from app.niches import NICHES

            hook = (NICHES.get(self.niche, {}).get("pitch_hook") or "").strip()
        except Exception:
            pass
        try:  # same shortening as TelecallerBrain (module fn — no LLM/genai)
            from app.voice_agent.telecaller_brain import _short_hook

            hook = _short_hook(hook)
        except Exception:
            hook = hook[:90].rstrip(" ,.-")
        if hook:
            return (
                f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                f"Aapke kaam ki ek choti si baat hai — {hook} — kya main tees second me bata doon?"
            )
        return (
            f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
            "Kya main do minute le sakti hoon?"
        )

    def _greet_key(self) -> str:
        """Cache key = voice + exact opener text (niche/client embedded) —
        wrong-greeting collisions impossible by construction."""
        try:
            from app.voice_agent.platform_pitch import is_platform_pitch, opening_segments

            if is_platform_pitch(self.niche):
                segs = opening_segments()
                return f"{self.voice}|platform|{'|'.join(segs)}"
        except Exception:
            pass
        return f"{self.voice}|{self._opening_line()}"

    async def _pregen_greeting(self) -> None:
        """Synthesize the opener PCM at WS open (Vobiz 'start' se PEHLE) so
        _greet() can play it instantly. Cache hit (same niche+client+voice on a
        later call) => zero synth at all."""
        if not TTS_AVAILABLE:
            return
        try:
            from app.voice_agent.platform_pitch import is_platform_pitch, opening_segments

            if is_platform_pitch(self.niche):
                key = self._greet_key()
                cached = _GREET_CACHE.get(key)
                if isinstance(cached, list) and cached:
                    self._platform_greet_pcms = cached
                    return
                segs = opening_segments()
                pcms: list[bytes] = []
                for seg in segs:
                    pcm = await self._synth_pcm(seg)
                    if pcm:
                        pcms.append(pcm)
                if pcms:
                    if len(_GREET_CACHE) >= _GREET_CACHE_MAX:
                        _GREET_CACHE.clear()
                    _GREET_CACHE[key] = pcms
                    self._platform_greet_pcms = pcms
                return
        except Exception as e:
            logger.debug(f"[vobiz-stream] platform greeting pregen failed: {e}")
        try:
            key = self._greet_key()
            pcm = _GREET_CACHE.get(key)
            if not pcm:
                pcm = await self._synth_pcm(self._opening_line())
                if pcm:
                    if len(_GREET_CACHE) >= _GREET_CACHE_MAX:
                        _GREET_CACHE.clear()
                    _GREET_CACHE[key] = pcm
            self._greet_pcm = pcm or None
        except Exception as e:
            logger.debug(f"[vobiz-stream] greeting pregen failed: {e}")

    async def _pregen_fillers(self) -> None:
        """Pre-synthesize short acknowledgment fillers ONCE per worker."""
        global _FILLER_STARTED
        if _FILLER_STARTED or not TTS_AVAILABLE:
            return
        _FILLER_STARTED = True  # set first — concurrent sessions double-synth na karein
        for t in _FILLER_TEXTS:
            try:
                pcm = await self._synth_pcm(t)
                if pcm:
                    _FILLER_PCM.append(pcm)
            except Exception as e:
                logger.debug(f"[vobiz-stream] filler synth failed ({t!r}): {e}")

    async def _greet(self) -> None:
        try:
            from app.voice_agent.platform_pitch import (
                initial_state,
                is_platform_pitch,
                opening_segments,
            )

            if is_platform_pitch(self.niche):
                self._pitch_state = initial_state()
                segs = opening_segments()
                pcms = self._platform_greet_pcms
                if not pcms:
                    cached = _GREET_CACHE.get(self._greet_key())
                    if isinstance(cached, list):
                        pcms = cached
                self._begin_disclosure()  # D-6: barge-lock the opener (disclosure)
                for i, seg in enumerate(segs):
                    self.hist.append({"role": "assistant", "content": seg})
                    if TTS_AVAILABLE and pcms and i < len(pcms):
                        self._stop_play()
                        self._speaking = True
                        self._barge_frames = 0
                        await self._run_play(pcms[i])
                    else:
                        await self._say_and_wait(seg)
                self._disclosure_active = False
                return
        except Exception as e:
            logger.debug(f"[vobiz-stream] platform greet failed: {e}")

        line = self._opening_line()
        self.hist.append({"role": "assistant", "content": line})
        self._begin_disclosure()  # D-6: barge-lock the opener (disclosure)
        if TTS_AVAILABLE:
            try:
                pcm = self._greet_pcm or _GREET_CACHE.get(self._greet_key())
                if not pcm and self._pregen_task is not None and not self._pregen_task.done():
                    # pregen in flight — uske finish ka wait fresh-synth se
                    # kabhi slow nahi (same synth); shield: greet timeout par
                    # bhi pregen cache ke liye complete ho.
                    try:
                        await asyncio.wait_for(asyncio.shield(self._pregen_task), timeout=5.0)
                    except Exception:
                        pass
                    pcm = self._greet_pcm or _GREET_CACHE.get(self._greet_key())
                if pcm:
                    self._stop_play()
                    self._speaking = True
                    self._barge_frames = 0
                    self._play_task = asyncio.create_task(self._run_play(pcm))
                    return
            except Exception as e:
                logger.debug(f"[vobiz-stream] cached greet failed: {e}")
        await self._say(line)  # fallback: synth now (pregen failed/missing)

    async def _say(self, text: str) -> None:
        """Speak a reply via SENTENCE-CHUNKED STREAMING TTS (see _say_streaming):
        first audio starts after only the first short sentence (~300-500 ms), not
        after the whole reply is synthesized. The orchestrator IS self._play_task,
        so _stop_play()/_barge_in() cancel synth + playback together."""
        if not text or not text.strip():
            return
        if not TTS_AVAILABLE:
            logger.warning("[vobiz-stream] TTS unavailable (edge-tts/pydub) — skipping speak")
            return
        self._stop_play()
        self._speaking = True  # set early so the synth window also detects barge-in
        self._barge_frames = 0
        self._play_task = asyncio.create_task(self._say_streaming(text))

    async def _say_from_sentence_gen(self, sentence_gen) -> None:
        """Pipeline TTS from async sentence generator — synth N+1 while N plays."""
        if not TTS_AVAILABLE:
            return
        self._stop_play()
        self._speaking = True
        self._barge_frames = 0
        if self._rec_enabled:
            self._rec_begin_bot_playback()
        agen = sentence_gen.__aiter__()
        cur_synth: asyncio.Task | None = None
        next_synth: asyncio.Task | None = None
        cancelled = False
        try:
            try:
                first = await agen.__anext__()
            except StopAsyncIteration:
                return
            next_synth = asyncio.create_task(self._synth_pcm(first))
            async for sent in agen:
                cur_synth, next_synth = next_synth, asyncio.create_task(self._synth_pcm(sent))
                try:
                    pcm = await cur_synth
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                except Exception as e:
                    logger.warning(f"[vobiz-stream] sentence synth failed: {e}")
                    pcm = b""
                if not self._speaking or not pcm:
                    if not self._speaking:
                        cancelled = True
                    continue
                await self._play_frames(pcm)
            if next_synth:
                cur_synth = next_synth
                try:
                    pcm = await cur_synth
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                except Exception as e:
                    logger.warning(f"[vobiz-stream] sentence synth failed: {e}")
                    pcm = b""
                if self._speaking and pcm:
                    await self._play_frames(pcm)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            for t in (cur_synth, next_synth):
                if t and not t.done():
                    t.cancel()
            if not cancelled:
                self._speaking = False

    def _rec_ensure_samples(self, n_samples: int) -> None:
        need_bytes = n_samples * 2
        if len(self._rec_mixed) < need_bytes:
            pad = (need_bytes - len(self._rec_mixed)) // 2
            self._rec_mixed.extend(b"\x00\x00" * pad)

    def _rec_mix_caller(self, pos_samples: int, pcm: bytes) -> None:
        """Write caller PCM onto the mixed track (overwrites silence at pos)."""
        if not pcm:
            return
        n = len(pcm) // 2
        self._rec_ensure_samples(pos_samples + n)
        off = pos_samples * 2
        self._rec_mixed[off : off + len(pcm)] = pcm

    def _rec_mix_bot(self, pos_samples: int, pcm: bytes) -> None:
        """Mix Swara TTS PCM onto the mixed track at the live timeline offset."""
        if not pcm:
            return
        n = len(pcm) // 2
        self._rec_ensure_samples(pos_samples + n)
        for i in range(0, len(pcm) - 1, 2):
            idx = pos_samples * 2 + i
            a = struct.unpack_from("<h", self._rec_mixed, idx)[0]
            b = struct.unpack_from("<h", pcm, i)[0]
            s = a + b
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            struct.pack_into("<h", self._rec_mixed, idx, s)

    def _rec_begin_bot_playback(self) -> None:
        """Anchor bot audio at the current inbound timeline (when Swara starts speaking)."""
        self._rec_bot_playhead = self._rec_timeline_samples

    async def _say_streaming(self, text: str) -> None:
        """SENTENCE-CHUNKED STREAMING TTS — the low-latency speak path.

        Split the reply into sentences and run a 1-sentence-lookahead pipeline:
        synthesize sentence N+1 WHILE sentence N plays, so the first audio starts
        after only the FIRST short sentence synthesizes (~300-500 ms) instead of
        after the whole reply. Single-sentence replies (the common case under the
        brevity prompt) just synth+play that one sentence — no regression.

        This coroutine IS self._play_task, so _stop_play()/_barge_in() cancel it
        as a unit: the in-flight AND pending sentence synths are cancelled and
        playback stops. _speaking is owned by the canceller on barge-in (it
        already set it False); only NORMAL completion clears it here."""
        if self._rec_enabled:
            self._rec_begin_bot_playback()
        sentences = _split_sentences(text)
        cur_synth: asyncio.Task | None = None
        next_synth: asyncio.Task | None = None
        cancelled = False
        try:
            if not sentences:
                return
            # Prime the pump — start synthesizing the first sentence.
            next_synth = asyncio.create_task(self._synth_pcm(sentences[0]))
            for i in range(len(sentences)):
                cur_synth, next_synth = next_synth, None
                # Synthesize the NEXT sentence in parallel with THIS one's playback.
                if i + 1 < len(sentences):
                    next_synth = asyncio.create_task(self._synth_pcm(sentences[i + 1]))
                try:
                    pcm = await cur_synth
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                except Exception as e:
                    logger.warning(f"[vobiz-stream] sentence synth failed: {e}")
                    pcm = b""
                cur_synth = None
                if not self._speaking:  # barged-in during synth
                    break
                if pcm:
                    await self._play_frames(pcm)  # raises CancelledError on barge-in
                if not self._speaking:  # barged-in during playback
                    break
        except asyncio.CancelledError:
            cancelled = True
        except Exception as e:
            logger.debug(f"[vobiz-stream] streaming speak error: {e}")
        finally:
            # Always cancel any still-pending synth so a barge-in leaves NOTHING
            # running (no wasted CPU/network, no late audio after clearAudio).
            for t in (cur_synth, next_synth):
                if t is not None and not t.done():
                    t.cancel()
            # On cancellation the canceller owns _speaking (barge-in set it False,
            # a superseding _say set it True). Only clear it on normal completion.
            if not cancelled:
                self._speaking = False

    async def _synth_pcm(self, text: str) -> bytes:
        """EdgeTTS MP3 -> raw PCM16 16k mono (L16) bytes. Heavy decode in executor.
        NO µ-law, NO 8k — Vobiz playAudio takes L16 @16 kHz directly."""
        import edge_tts  # lazy

        # rate="+8%" = snappier delivery (lower perceived latency, still natural).
        # Guarded: an edge-tts build lacking the kwarg must NOT break synthesis.
        try:
            communicate = edge_tts.Communicate(text, self.voice, rate="+8%")
        except TypeError:
            communicate = edge_tts.Communicate(text, self.voice)
        mp3 = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                mp3.write(chunk.get("data") or b"")
        data = mp3.getvalue()
        if not data:
            return b""

        def _decode(mp3_bytes: bytes) -> bytes:
            from pydub import AudioSegment  # needs ffmpeg at runtime

            seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
            seg = seg.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
            return seg.raw_data

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _decode, data)

    async def _play_frames(self, pcm: bytes) -> None:
        """Send PCM16 @16 kHz as 20 ms L16 playAudio frames, paced ~real-time.
        Stops early if _speaking goes False (barge-in flag). Does NOT manage the
        _speaking flag — callers (_run_play / _say_streaming) own its lifecycle."""
        for i in range(0, len(pcm), FRAME_PCM):
            if not self._speaking:
                break  # barge-in flipped the flag (covers inline filler play too)
            frame = pcm[i : i + FRAME_PCM]
            if len(frame) < FRAME_PCM:
                frame = frame + PCM_SILENCE * (FRAME_PCM - len(frame))
            # P1: first bot audio frame of this turn (filler or reply) → perceived
            # time-to-first-audio. Guarded by _turn_t0_ms so non-turn playback
            # (greeting) never mis-stamps; set once per turn.
            if self._turn_tts_first_ms is None and self._turn_t0_ms is not None:
                self._turn_tts_first_ms = _now_ms() - self._turn_t0_ms
            # Recording: mix bot TTS onto the call timeline (same clock as caller).
            if self._rec_enabled and self._rec_bot_playhead is not None:
                self._rec_mix_bot(self._rec_bot_playhead, frame)
                self._rec_bot_playhead += len(frame) // 2
            # Vobiz playAudio: L16 @16k, base64 payload, NO streamSid field.
            await self._send(
                {
                    "event": "playAudio",
                    "media": {
                        "contentType": "audio/x-l16",
                        "sampleRate": SAMPLE_RATE,
                        "payload": base64.b64encode(frame).decode("ascii"),
                    },
                }
            )
            await asyncio.sleep(0.02)  # pace at ~real-time (20 ms/frame)

    async def _run_play(self, pcm: bytes) -> None:
        """Play a single pre-synthesized clip (greeting / filler). On NORMAL
        completion clears _speaking; on cancellation the canceller owns the flag
        (barge-in already set it False), so we leave it untouched."""
        try:
            if self._rec_enabled:
                self._rec_begin_bot_playback()
            await self._play_frames(pcm)
            self._speaking = False
            self._disclosure_active = False  # D-6: opener finished -> unlock barge
        except asyncio.CancelledError:
            pass  # barge-in / superseded — canceller owns _speaking
        except Exception as e:
            logger.debug(f"[vobiz-stream] playback error: {e}")
            self._speaking = False
            self._disclosure_active = False

    def _stop_play(self) -> None:
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
        self._play_task = None

    async def _barge_in(self) -> None:
        """User started talking over us — stop playback and flush Vobiz buffer."""
        self._barge_frames = 0
        self._interruptions += 1  # P4-3 interruption tracking
        self._stop_play()
        self._speaking = False
        await self._send({"event": "clearAudio"})
        logger.debug("[vobiz-stream] barge-in: playback cleared (clearAudio)")

    # ------------------------------------------------------------------ #
    async def _send(self, obj: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self.ws.send_text(json.dumps(obj))
        except Exception as e:
            logger.debug(f"[vobiz-stream] send failed: {e}")
            self._closed = True

    async def _cleanup(self) -> None:
        if self._teardown_done:
            return
        self._teardown_done = True
        self._closed = True
        self._stop_play()
        turns = len([m for m in self.hist if m.get("role") == "user"])
        ended = datetime.now(timezone.utc)
        dur = max(0.0, (ended - self._started_at).total_seconds())
        logger.info(
            f"[vobiz-stream] call summary sid={self.stream_sid} niche={self.niche} "
            f"client={self.client_id} dur={dur:.0f}s user_turns={turns} "
            f"msgs={len(self.hist)} stt={self._stt_counts}"
        )
        self._save_recording()
        self._persist_transcript(ended, dur, turns)
        # Minute metering + call.completed webhook (stream path has no CallManager ctx).
        try:
            from app.telephony.post_call_hooks import meter_call_completion

            await meter_call_completion(
                str(self.stream_sid or ""),
                client_id=str(self.client_id or ""),
                client_name=self.client_name or "",
                duration_seconds=int(dur),
            )
        except Exception as e:
            logger.debug(f"[vobiz-stream] meter_call_completion skip: {e}")
        # PROVIDER outbound webhook parity — the legacy call_manager path emits a
        # platform-level `call_completed` event (outbound_webhooks.emit) on every
        # completed call; the stream path was missing it, so integrations never
        # saw stream calls. Best-effort, never blocks teardown. (This is the
        # PLATFORM webhook; the per-customer `call.completed` rides on
        # meter_call_completion above — both now fire for stream calls.)
        try:
            from app.platform import outbound_webhooks as _ow

            await _ow.emit(
                "call_completed",
                {
                    "call_id": str(self.stream_sid or ""),
                    "outcome": "completed" if turns > 0 else "no_answer",
                    "duration_seconds": int(dur),
                    "lead_score": 0,
                    "phone": getattr(self, "_lead_phone", "") or "",
                    "niche": self.niche or "",
                    "client_id": str(self.client_id or ""),
                    "source": "vobiz_stream",
                },
                client_id=str(self.client_id or ""),
            )
        except Exception as e:
            logger.debug(f"[vobiz-stream] call_completed webhook skip: {e}")
        await self._auto_qualify(ended)
        try:  # Team activity: Swara ki call khatam — dashboard feed ke liye
            from app.platform.team import log_event

            log_event(
                "swara",
                "call_finished",
                f"Call done ({dur:.0f}s, {turns} user turns, niche {self.niche})",
                status="ok" if turns > 0 else "warn",
                meta={"stt_counts": dict(self._stt_counts), "duration_s": round(dur, 1)},
            )
        except Exception:
            pass

    def _persist_transcript(self, ended: datetime, dur_s: float, user_turns: int) -> None:
        """Har call ka full transcript + meta ek JSON line me append karo —
        data/call_transcripts/YYYY-MM-DD.jsonl. Yeh continuous-training fuel
        hai (STT/prompt tuning, few-shot mining, QA). Fully guarded — persist
        failure call teardown ko kabhi nahi todti."""
        if not self.hist:
            return
        try:
            rec = {
                "ts": ended.isoformat(timespec="seconds"),
                "started_at": self._started_at.isoformat(timespec="seconds"),
                "duration_s": round(dur_s, 1),
                "stream_sid": self.stream_sid,
                "niche": self.niche,
                "client_id": self.client_id,
                "client_name": self.client_name,
                "voice": self.voice,
                "user_turns": user_turns,
                "stt_counts": dict(self._stt_counts),
                "barge_count": self._interruptions,  # P4-3 interruption tracking
                "messages": self.hist,
            }
            # P1 observability: per-turn latency + call-level P50/P95 rollup so the
            # transcript itself is tunable without joining a separate file.
            if self._turn_metrics:
                rec["turn_metrics"] = self._turn_metrics
                try:
                    from app.voice_agent.turn_metrics import rollup as _tm_rollup

                    rec["turn_rollup"] = _tm_rollup(self._turn_metrics)
                except Exception:
                    pass
            out_dir = os.path.join("data", "call_transcripts")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, ended.strftime("%Y-%m-%d") + ".jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logger.info(f"[vobiz-stream] transcript saved -> {path} ({len(self.hist)} msgs)")
        except Exception as e:
            logger.warning(f"[vobiz-stream] transcript persist failed: {e}")

    async def _auto_qualify(self, ended: datetime) -> None:
        """Post-call AI qualification for the LIVE Vobiz stream path (mirrors
        call_manager). GATED AUTO_QUALIFY_CALLS=1 (default off = zero change).
        Best-effort / never-raise: writes data/call_qualifications.jsonl so the
        admin Post-Call tab populates for REAL Vobiz calls (not just legacy path)."""
        try:
            if os.environ.get("AUTO_QUALIFY_CALLS", "0").strip().lower() not in (
                "1",
                "true",
                "yes",
            ):
                return
            if not self.hist:
                return
            txt = "\n".join(
                f"{m.get('role', '?')}: {m.get('content', '')}"
                for m in self.hist
                if isinstance(m, dict)
            )
            if len(txt) < 10:
                return
            from app.voice_agent.call_qualifier import qualify_transcript

            lead_phone = getattr(self, "_lead_phone", "") or ""
            q = await qualify_transcript(txt, {"name": self.client_name or "", "phone": lead_phone})
            rec = {
                "call_id": self.stream_sid,
                "lead_id": lead_phone,
                "client_id": self.client_id or "",
                "niche": self.niche,
                "ts": ended.isoformat(timespec="seconds"),
                **q,
            }
            os.makedirs("data", exist_ok=True)
            with open(
                os.path.join("data", "call_qualifications.jsonl"), "a", encoding="utf-8"
            ) as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logger.info(
                f"[vobiz-stream] auto-qualify sid={self.stream_sid} "
                f"score={q.get('interest_score')} qualified={q.get('qualified')}"
            )
            # call.report.ready customer webhook — fires for EVERY report (qualified
            # or not); customer opted in via subscription. Inert w/o CUSTOMER_WEBHOOKS.
            try:
                from app.telephony.post_call_hooks import emit_call_report

                emit_call_report(
                    q,
                    client_id=str(self.client_id or ""),
                    phone=lead_phone,
                    call_id=str(self.stream_sid or ""),
                    niche=self.niche or "",
                    report_ready_at=rec["ts"],
                )
            except Exception:
                pass
            if q.get("qualified") and self.client_id:
                try:
                    from app.billing import lead_usage as _lead_usage

                    _lead_usage.record_qualified_lead(self.client_id, ref=str(self.stream_sid))
                except Exception:
                    pass
            try:
                from app.telephony.post_call_hooks import apply_qualified_downstream

                await apply_qualified_downstream(
                    q,
                    client_id=str(self.client_id or ""),
                    phone=lead_phone,
                    client_name=self.client_name or "",
                    call_id=str(self.stream_sid or ""),
                    niche=self.niche or "",
                )
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"[vobiz-stream] auto-qualify skip: {e}")

    def _save_recording(self) -> None:
        """Mixed conversation WAV on hangup (VOBIZ_CALL_RECORD=1).

        call_{sid}.wav — caller + Swara on one timeline (PCM16 mono 16 kHz).
        DPDP: 90-din ke baad purge karo (consent_ledger retention rule).
        """
        if not self._rec_enabled:
            return
        if not self._rec_mixed:
            return
        try:
            import uuid as _uuid
            import wave
            from pathlib import Path

            ended = datetime.now(timezone.utc)
            day_dir = Path("data") / "call_recordings" / ended.strftime("%Y-%m-%d")
            day_dir.mkdir(parents=True, exist_ok=True)
            uid = (self.stream_sid or _uuid.uuid4().hex[:8]).replace("/", "_")

            end_samples = max(
                self._rec_timeline_samples,
                self._rec_bot_playhead or 0,
            )
            pcm = bytes(self._rec_mixed[: end_samples * 2])
            out = day_dir / f"call_{uid}.wav"
            with wave.open(str(out), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
            kb = len(pcm) // 1024
            logger.info(f"[vobiz-stream] conversation rec -> call_{uid}.wav ({kb} KB)")
        except Exception as e:
            logger.warning(f"[vobiz-stream] recording save failed: {e}")


# --------------------------------------------------------------------------- #
# Module-level STT warmup
# --------------------------------------------------------------------------- #
if _LOCAL_STT_OK and os.environ.get("VOBIZ_STT_WARMUP", "1") != "0":
    try:
        threading.Thread(target=_get_stt, daemon=True, name="vobiz-stt-warmup").start()
    except Exception:
        pass


__all__ = ["VobizStreamSession", "STT_AVAILABLE", "TTS_AVAILABLE"]
