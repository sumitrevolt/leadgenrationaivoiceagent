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
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils.logger import setup_logger

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
_GENAI_OK = _have("google.genai")          # NEW google-genai SDK (Gemini audio-in STT)
_OPENAI_SDK_OK = _have("openai")           # Groq STT via shared free_ai layer (OpenAI-compatible)
_LOCAL_STT_OK = _VOSK_OK or _FWHISPER_OK   # local engines (whisper fallback chain)
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
SAMPLE_RATE = 16000     # Vobiz L16 stream rate (contentType audio/x-l16;rate=16000)
STT_RATE = 16000        # STT models want 16 kHz PCM16 (== SAMPLE_RATE: no resample)
FRAME_PCM = 640         # 20 ms of PCM16 @ 16 kHz (16000 * 0.02 * 2 bytes)
PCM_SILENCE = b"\x00"   # PCM16 silence == zero bytes

def _env_num(name: str, default: float) -> float:
    """float(env) with safe fallback — bad env value must never kill import."""
    try:
        return float(os.environ.get(name, "") or default)
    except Exception:
        return default


_VAD_RMS = int(_env_num("VOBIZ_VAD_RMS", 300))            # PCM16 RMS speech gate
SILENCE_MS = _env_num("VOBIZ_SILENCE_MS", 550.0)          # trailing silence that ends an utterance
MIN_SPEECH_MS = _env_num("VOBIZ_MIN_SPEECH_MS", 250.0)    # ignore sub-250ms blips (coughs/clicks)
MIN_STT_MS = _env_num("VOBIZ_MIN_STT_MS", 350.0)          # drop sub-350ms utterances (STT unreliable)
MAX_UTTER_MS = 15000.0  # hard cap so a long monologue still gets processed
BARGE_MIN_FRAMES = 5    # ~100 ms of speech while we talk = barge-in


# --------------------------------------------------------------------------- #
# STT engine — lazy singleton (model load is heavy; reuse across calls).
# --------------------------------------------------------------------------- #
_STT_ENGINE: Optional[tuple] = None   # ("vosk", model) | ("whisper", model)
_STT_INIT = False
_STT_LOCK = threading.Lock()          # module warmup thread vs executor threads


def _get_stt() -> Optional[tuple]:
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
                    _STT_ENGINE = ("whisper", WhisperModel(model_size, device="cpu", compute_type="int8"))
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
_GENAI_CLIENTS: Dict[str, Any] = {}
_GENAI_LOCK = threading.Lock()


def _get_genai_client(key: str = "") -> Optional[Any]:
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
    return bool((os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEYS", "")).strip())


def _stt_chain() -> List[str]:
    """Ordered STT providers to try this turn. ``VOBIZ_STT`` forces exactly ONE
    (groq|gemini|whisper). Default ('auto'/empty) = groq (key set) -> gemini
    (SDK+key) -> whisper. The chain ALWAYS ends with whisper so a missing or
    quota-exhausted cloud key can never make the call permanently deaf."""
    forced = (os.environ.get("VOBIZ_STT", "") or "").strip().lower()
    if forced in ("groq", "gemini", "whisper"):
        return [forced]
    chain: List[str] = []
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
        wf.setsampwidth(2)      # 16-bit
        wf.setframerate(rate)   # 16000 Hz
        wf.writeframes(pcm16)
    return buf.getvalue()


def _gemini_stt_sync(client: Any, model: str, wav_bytes: bytes) -> str:
    """Blocking Gemini audio transcription (runs in executor). Raises on API
    error — async caller catch karke "" return karta hai (whisper fallback)."""
    from google.genai import types  # type: ignore

    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            _GEMINI_STT_PROMPT,
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
# Pre-synthesized audio caches (PCM16 @16 kHz) — shared across calls per worker.
# Greeting: keyed by exact opener text+voice (niche/client embedded in text, so
# a stale entry can never play the WRONG greeting). Fillers: short "Hmm/Achha"
# acknowledgments played the instant STT text aata hai (perceived-latency fix).
# --------------------------------------------------------------------------- #
_GREET_CACHE: Dict[str, bytes] = {}
_GREET_CACHE_MAX = 64
_FILLER_TEXTS = ("Hmm...", "Achha...", "Ji...")
_FILLER_PCM: List[bytes] = []
_FILLER_STARTED = False   # synth fillers once per worker (first session does it)


# --------------------------------------------------------------------------- #
# Per-call session — one instance per WebSocket (per Vobiz docs).
# --------------------------------------------------------------------------- #
class VobizStreamSession:
    """Drives one streamed phone call: listen -> understand -> reply -> speak,
    with energy-VAD turn-taking and barge-in. Never raises out of handle()."""

    def __init__(self, websocket: Any, niche: str = "general",
                 client_id: Optional[str] = None, client_name: str = "Demo Co",
                 voice: str = "hi-IN-SwaraNeural") -> None:
        self.ws = websocket
        self.niche = (niche or "general").strip() or "general"
        self.client_id = client_id
        self.client_name = client_name or "Demo Co"
        self.voice = voice

        self.stream_sid: Optional[str] = None
        self.hist: List[Dict[str, str]] = []   # {role: user|assistant, content}
        self._closed = False
        self._started_at = datetime.now(timezone.utc)          # transcript meta
        self._stt_counts: Dict[str, int] = {"groq": 0, "gemini": 0, "whisper": 0}

        # turn-taking / VAD state
        self._speech_buf: List[bytes] = []
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._had_speech = False
        self._vad_rms = _VAD_RMS

        # playback / barge-in state
        self._speaking = False
        self._play_task: Optional[asyncio.Task] = None
        self._barge_frames = 0
        self._thinking = False
        self._bg_tasks: set = set()   # keep refs so tasks aren't GC'd mid-run

        # instant-greeting state (pre-synthesized at WS open, before 'start')
        self._greet_pcm: Optional[bytes] = None
        self._pregen_task: Optional[asyncio.Task] = None

        # lazy helpers
        self._telecaller = None   # TelecallerBrain — lean phone-tuned (primary)
        self._telecaller_tried = False
        self._brain = None
        self._brain_tried = False
        self._ndm = None          # NaturalDialogManager fallback (cached — heavy)
        self._ndm_tried = False

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
            data.get("streamId") or data.get("streamSid") or data.get("stream_sid")
            or start.get("streamId") or start.get("streamSid") or start.get("stream_sid")
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
            logger.info(f"[vobiz-stream] start streamId={self.stream_sid} niche={self.niche}")
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
        rms = _pcm_rms(pcm16)
        is_speech = rms >= self._vad_rms
        dur_ms = (len(pcm16) / 2) / SAMPLE_RATE * 1000.0  # 640 bytes == 20 ms

        # While we're speaking: only watch for barge-in.
        if self._speaking:
            if is_speech:
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
            self._speech_buf.append(pcm16)
            self._speech_ms += dur_ms
            self._silence_ms = 0.0
            self._had_speech = True
        elif self._had_speech:
            self._speech_buf.append(pcm16)  # keep a little trailing silence
            self._silence_ms += dur_ms

        ended = self._had_speech and self._silence_ms >= SILENCE_MS and self._speech_ms >= MIN_SPEECH_MS
        too_long = self._speech_ms >= MAX_UTTER_MS
        if ended or too_long:
            utt = b"".join(self._speech_buf)
            self._reset_speech()
            self._spawn(self._on_utterance(utt))

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

    async def _on_utterance(self, pcm16: bytes) -> None:
        if self._thinking:
            return
        self._thinking = True
        try:
            text = await self._stt(pcm16)
            if not text:
                return
            logger.info(f"[vobiz-stream {self.stream_sid}] user: {text}")
            self.hist.append({"role": "user", "content": text})
            # SPONTANEITY: LLM+TTS se pehle turant cached "Hmm/Achha" filler
            # bajao — 1-3s ki think-window me line dead na lage. Inline await
            # (~0.5s, acceptable); _run_play har frame pe _speaking check karta
            # hai, isliye barge-in (jo flag girata hai) filler ko bhi kaat deta.
            try:
                if _FILLER_PCM and TTS_AVAILABLE and not self._speaking:
                    self._stop_play()
                    self._speaking = True
                    self._barge_frames = 0
                    await self._run_play(random.choice(_FILLER_PCM))
            except Exception as e:
                logger.debug(f"[vobiz-stream] filler play failed: {e}")
            reply = await self._think(text)
            if reply:
                logger.info(f"[vobiz-stream {self.stream_sid}] bot: {reply}")
                self.hist.append({"role": "assistant", "content": reply})
                await self._say(reply)
        except Exception as e:
            logger.warning(f"[vobiz-stream] utterance handling failed: {e}")
        finally:
            self._thinking = False

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
            text, _provider = await transcribe_audio(wav, language=lang)
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
            from app.voice_agent.gemini_keys import active_key, advance_key, is_quota_error, key_count
        except Exception:  # pool unavailable — single-key, no rotation
            active_key = lambda: ""            # noqa: E731
            advance_key = lambda bad="": ""    # noqa: E731
            is_quota_error = lambda e: False   # noqa: E731
            key_count = lambda: 1              # noqa: E731

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
                    loop.run_in_executor(None, _gemini_stt_sync, client, model, wav),
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
    # Thinking (LLM) — niche-aware Hinglish reply, defensive fallbacks.
    # ------------------------------------------------------------------ #
    async def _think(self, text: str) -> str:
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

    def _get_ndm(self):
        if self._ndm_tried:
            return self._ndm
        self._ndm_tried = True
        try:
            from app.voice_agent.natural_dialog import NaturalDialogManager

            # brain=False sentinel keeps it rule-based (None would auto-build LLM).
            self._ndm = NaturalDialogManager(
                niche=self.niche, client_name=self.client_name,
                client_service=self.niche, brain=False,
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
                niche=self.niche, client_name=self.client_name,
                client_id=self.client_id,
            )
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
        """PURELY STATIC permission-based opener (Gong: ~11% vs 2.3% generic) —
        NICHES pitch_hook template only. NO TelecallerBrain/LLM/genai-import
        here: opener instant + WS-open par pre-synthesizable hona chahiye.
        (TelecallerBrain sirf _think replies ke liye hai.)"""
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
            return (f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                    f"Aapke kaam ki ek choti si baat hai — {hook} — kya main tees second me bata doon?")
        return (f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                "Kya main do minute le sakti hoon?")

    def _greet_key(self) -> str:
        """Cache key = voice + exact opener text (niche/client embedded) —
        wrong-greeting collisions impossible by construction."""
        return f"{self.voice}|{self._opening_line()}"

    async def _pregen_greeting(self) -> None:
        """Synthesize the opener PCM at WS open (Vobiz 'start' se PEHLE) so
        _greet() can play it instantly. Cache hit (same niche+client+voice on a
        later call) => zero synth at all."""
        if not TTS_AVAILABLE:
            return
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
        _FILLER_STARTED = True   # set first — concurrent sessions double-synth na karein
        for t in _FILLER_TEXTS:
            try:
                pcm = await self._synth_pcm(t)
                if pcm:
                    _FILLER_PCM.append(pcm)
            except Exception as e:
                logger.debug(f"[vobiz-stream] filler synth failed ({t!r}): {e}")

    async def _greet(self) -> None:
        line = self._opening_line()
        self.hist.append({"role": "assistant", "content": line})
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
        await self._say(line)   # fallback: synth now (pregen failed/missing)

    async def _say(self, text: str) -> None:
        if not text or not text.strip():
            return
        if not TTS_AVAILABLE:
            logger.warning("[vobiz-stream] TTS unavailable (edge-tts/pydub) — skipping speak")
            return
        self._stop_play()
        self._speaking = True       # set early so synth window also detects barge-in
        self._barge_frames = 0
        try:
            pcm = await self._synth_pcm(text)
        except Exception as e:
            logger.warning(f"[vobiz-stream] TTS synth failed: {e}")
            self._speaking = False
            return
        if not pcm or not self._speaking:   # barged-in during synthesis
            self._speaking = False
            return
        self._play_task = asyncio.create_task(self._run_play(pcm))

    async def _synth_pcm(self, text: str) -> bytes:
        """EdgeTTS MP3 -> raw PCM16 16k mono (L16) bytes. Heavy decode in executor.
        NO µ-law, NO 8k — Vobiz playAudio takes L16 @16 kHz directly."""
        import edge_tts  # lazy

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

    async def _run_play(self, pcm: bytes) -> None:
        try:
            for i in range(0, len(pcm), FRAME_PCM):
                if not self._speaking:
                    break   # barge-in flipped the flag (covers inline filler play too)
                frame = pcm[i:i + FRAME_PCM]
                if len(frame) < FRAME_PCM:
                    frame = frame + PCM_SILENCE * (FRAME_PCM - len(frame))
                # Vobiz playAudio: L16 @16k, base64 payload, NO streamSid field.
                await self._send({
                    "event": "playAudio",
                    "media": {
                        "contentType": "audio/x-l16",
                        "sampleRate": SAMPLE_RATE,
                        "payload": base64.b64encode(frame).decode("ascii"),
                    },
                })
                await asyncio.sleep(0.02)  # pace at ~real-time (20 ms/frame)
        except asyncio.CancelledError:
            pass  # barge-in
        except Exception as e:
            logger.debug(f"[vobiz-stream] playback error: {e}")
        finally:
            self._speaking = False

    def _stop_play(self) -> None:
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
        self._play_task = None

    async def _barge_in(self) -> None:
        """User started talking over us — stop playback and flush Vobiz buffer."""
        self._barge_frames = 0
        self._stop_play()
        self._speaking = False
        await self._send({"event": "clearAudio"})
        logger.debug("[vobiz-stream] barge-in: playback cleared (clearAudio)")

    # ------------------------------------------------------------------ #
    async def _send(self, obj: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self.ws.send_text(json.dumps(obj))
        except Exception as e:
            logger.debug(f"[vobiz-stream] send failed: {e}")
            self._closed = True

    async def _cleanup(self) -> None:
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
        self._persist_transcript(ended, dur, turns)

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
                "messages": self.hist,
            }
            out_dir = os.path.join("data", "call_transcripts")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, ended.strftime("%Y-%m-%d") + ".jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            logger.info(f"[vobiz-stream] transcript saved -> {path} ({len(self.hist)} msgs)")
        except Exception as e:
            logger.warning(f"[vobiz-stream] transcript persist failed: {e}")


# --------------------------------------------------------------------------- #
# Module-level STT warmup — model load (10-30s) WORKER START par hi shuru ho,
# pehli call ke dauran nahi. Plain daemon thread (import par event loop nahi
# hota); _get_stt lock-protected hai so per-WS warmup/first call safely wait
# karte hain. Opt-out: VOBIZ_STT_WARMUP=0 (e.g. tests/CI).
# --------------------------------------------------------------------------- #
if _LOCAL_STT_OK and os.environ.get("VOBIZ_STT_WARMUP", "1") != "0":
    try:  # pragma: no cover - environment dependent
        threading.Thread(target=_get_stt, daemon=True, name="vobiz-stt-warmup").start()
    except Exception:
        pass


__all__ = ["VobizStreamSession", "STT_AVAILABLE", "TTS_AVAILABLE"]
