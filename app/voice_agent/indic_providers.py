"""
Indian-Language Voice Providers — Sarvam AI + AI4Bharat (the project's edge).

Retell / Vapi / Bland are English-first. THIS module is what makes the LeadGen
voice agent actually good at Hindi, Marathi, Tamil, Telugu, Bengali and 17 more
scheduled Indian languages — including Hindi-English code-switching mid-sentence
(very common on real B2B sales calls in India).

It plugs straight into the existing BYOK registry (app/voice_agent/providers.py)
by implementing the SAME interfaces:

    STTProvider.transcribe(audio: bytes, **kwargs) -> str    (+ transcribe_stream)
    TTSProvider.synthesize(text: str, voice_id=None) -> bytes (+ synthesize_stream)

Providers added (registered names):
    "sarvam"    -> SarvamSTT (Saaras v3) + SarvamTTS (Bulbul v3)   [API, BYOK]
    "ai4bharat" -> Ai4BharatSTT + Ai4BharatTTS (self-host stubs)  [optional]

How a user switches to Sarvam (no code change, just env)::

    SARVAM_API_KEY=sk_...        # your Sarvam subscription key
    STT_PROVIDER=sarvam
    TTS_PROVIDER=sarvam
    DEFAULT_LANGUAGE=hi-IN

Then the existing pipeline (`get_registry().get_stt()/.get_tts()`) automatically
returns the Sarvam-backed providers. Without a key everything degrades to the
free Vosk / EdgeTTS defaults — nothing crashes.

DESIGN RULES (defensive by contract):
    * httpx imported lazily inside methods — module import never fails.
    * Any API/network/parse error => log + return "" (STT) / b"" (TTS).
    * Unknown endpoint shape => graceful empty result, never an exception bubble.
    * is_available() is the single source of truth for "configured?".
"""

import base64
import os
from collections.abc import AsyncGenerator

from app.utils.logger import setup_logger
from app.voice_agent.providers import (
    STTProvider,
    TTSProvider,
    get_registry,
)

logger = setup_logger(__name__)


# =============================================================================
# SCHEDULED INDIAN LANGUAGES (Sarvam Saaras / Bulbul coverage target)
# =============================================================================
# 22 official scheduled languages of India (BCP-47 "<lang>-IN" codes used by
# the Sarvam API as `language_code` / `target_language_code`). English (India)
# is included for code-switching.

INDIAN_LANGUAGES: dict[str, str] = {
    "hi-IN": "Hindi",
    "en-IN": "English (India)",
    "bn-IN": "Bengali",
    "mr-IN": "Marathi",
    "te-IN": "Telugu",
    "ta-IN": "Tamil",
    "gu-IN": "Gujarati",
    "ur-IN": "Urdu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "or-IN": "Odia",
    "pa-IN": "Punjabi",
    "as-IN": "Assamese",
    "mai-IN": "Maithili",
    "sat-IN": "Santali",
    "ks-IN": "Kashmiri",
    "ne-IN": "Nepali",
    "sd-IN": "Sindhi",
    "doi-IN": "Dogri",
    "kok-IN": "Konkani",
    "mni-IN": "Manipuri (Meitei)",
    "brx-IN": "Bodo",
    "sa-IN": "Sanskrit",
}

# Default language used when none is supplied (overridable via DEFAULT_LANGUAGE).
DEFAULT_LANGUAGE = "hi-IN"

# Sarvam API constants.
_SARVAM_BASE_URL = "https://api.sarvam.ai"
_SARVAM_AUTH_HEADER = "api-subscription-key"
_SARVAM_STT_MODEL = "saaras:v3"  # Saaras v3 — speech-to-text-translate / STT
_SARVAM_TTS_MODEL = "bulbul:v3"  # Bulbul v3 — streaming TTS
_SARVAM_DEFAULT_SPEAKER = "anushka"  # safe default voice; overridable via voice_id


def _sarvam_key() -> str:
    """Read the Sarvam subscription key from env (empty string if unset)."""
    return (os.getenv("SARVAM_API_KEY") or "").strip()


def _default_language() -> str:
    """Resolve the default language code from env, falling back to hi-IN."""
    code = (os.getenv("DEFAULT_LANGUAGE") or DEFAULT_LANGUAGE).strip()
    return code or DEFAULT_LANGUAGE


# =============================================================================
# LANGUAGE DETECTION (cheap unicode-range heuristic)
# =============================================================================

# (lang_code, (start, end)) unicode block ranges. First block that has a hit
# wins. Latin is treated as English-India only if nothing Indic matched.
_SCRIPT_RANGES = [
    ("bn-IN", (0x0980, 0x09FF)),  # Bengali (also Assamese)
    ("gu-IN", (0x0A80, 0x0AFF)),  # Gujarati
    ("pa-IN", (0x0A00, 0x0A7F)),  # Gurmukhi (Punjabi)
    ("ta-IN", (0x0B80, 0x0BFF)),  # Tamil
    ("te-IN", (0x0C00, 0x0C7F)),  # Telugu
    ("kn-IN", (0x0C80, 0x0CFF)),  # Kannada
    ("ml-IN", (0x0D00, 0x0D7F)),  # Malayalam
    ("or-IN", (0x0B00, 0x0B7F)),  # Odia
    ("ur-IN", (0x0600, 0x06FF)),  # Arabic block (Urdu)
    ("hi-IN", (0x0900, 0x097F)),  # Devanagari (Hindi/Marathi/Sanskrit/etc.)
]


def detect_language(text: str) -> str:
    """
    Quick heuristic language detection from unicode script ranges.

    Returns a BCP-47 "<lang>-IN" code from INDIAN_LANGUAGES. Devanagari maps to
    Hindi (covers the most common case); pure-Latin text maps to en-IN. On any
    issue, falls back to the configured default language. Never raises.
    """
    if not text:
        return _default_language()
    try:
        counts: dict[str, int] = {}
        for ch in text:
            cp = ord(ch)
            for code, (lo, hi) in _SCRIPT_RANGES:
                if lo <= cp <= hi:
                    counts[code] = counts.get(code, 0) + 1
                    break
        if counts:
            # Most-represented Indic script wins.
            return max(counts, key=counts.get)
        # No Indic script chars at all -> assume English (India).
        # (Latin letters present?)
        if any(("a" <= c.lower() <= "z") for c in text):
            return "en-IN"
        return _default_language()
    except Exception as e:  # pragma: no cover - heuristic must never crash
        logger.debug(f"detect_language fallback ({e})")
        return _default_language()


# =============================================================================
# SARVAM AI — SaaaS providers (Saaras v3 STT + Bulbul v3 TTS)
# =============================================================================


class SarvamSTT(STTProvider):
    """
    Sarvam AI Speech-to-Text (Saaras v3).

    22 Indian languages + English, Hindi-English code-switching mid-sentence,
    tuned for 8 kHz call audio. Uses the documented multipart upload endpoint.

    Defensive: on missing key / network / parse error returns "" and logs.
    """

    name = "sarvam-stt"

    def __init__(self) -> None:
        self.api_key = _sarvam_key()
        if not self.api_key:
            logger.warning(
                "SarvamSTT constructed without SARVAM_API_KEY — will return "
                "empty transcripts until a key is set."
            )

    def is_available(self) -> bool:
        """True only if a Sarvam subscription key is configured."""
        return bool(self.api_key)

    async def transcribe(self, audio: bytes, language: str = None, **kwargs) -> str:
        """
        Transcribe call audio to text via Sarvam Saaras v3.

        Args:
            audio: raw audio bytes (wav/pcm/mp3; call audio typically 8 kHz wav).
            language: BCP-47 code, e.g. "hi-IN". None => auto-detect by Sarvam
                      (Saaras supports language auto-detection / code-switching).

        Returns:
            Transcript string, or "" on any failure.
        """
        if not self.is_available():
            logger.debug("SarvamSTT.transcribe skipped — no API key.")
            return ""
        if not audio:
            return ""

        lang = (language or kwargs.get("language_code") or "").strip()

        try:
            import httpx
        except Exception as e:
            logger.warning(f"SarvamSTT: httpx not available ({e}); returning ''.")
            return ""

        url = f"{_SARVAM_BASE_URL}/speech-to-text"
        headers = {_SARVAM_AUTH_HEADER: self.api_key}
        # Sarvam STT takes a multipart file plus form fields. We keep field names
        # defensive: "file" is the documented audio part; model + language_code
        # are optional hints.
        files = {"file": ("audio.wav", audio, "audio/wav")}
        data = {"model": _SARVAM_STT_MODEL}
        if lang and lang.lower() not in ("auto", "unknown"):
            data["language_code"] = lang

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code >= 400:
                logger.warning(f"SarvamSTT HTTP {resp.status_code}: {resp.text[:200]}")
                return ""
            payload = resp.json()
        except Exception as e:
            logger.warning(f"SarvamSTT request failed ({e}); returning ''.")
            return ""

        return self._extract_transcript(payload)

    @staticmethod
    def _extract_transcript(payload) -> str:
        """Pull the transcript out of various plausible response shapes."""
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("transcript", "text", "transcription", "output"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            # Some APIs nest under "data" or a list of segments.
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("transcript", "text"):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        return ""


class SarvamTTS(TTSProvider):
    """
    Sarvam AI Text-to-Speech (Bulbul v3).

    Streaming, 30+ voices, emotion control, native Indian-language prosody.
    POSTs text + target_language_code + speaker, returns base64 audio.

    Defensive: on missing key / network / parse error returns b"" and logs.
    """

    name = "sarvam-tts"

    def __init__(self) -> None:
        self.api_key = _sarvam_key()
        if not self.api_key:
            logger.warning(
                "SarvamTTS constructed without SARVAM_API_KEY — will return "
                "empty audio until a key is set."
            )

    def is_available(self) -> bool:
        """True only if a Sarvam subscription key is configured."""
        return bool(self.api_key)

    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        language: str = None,
        **kwargs,
    ) -> bytes:
        """
        Synthesize Indian-language speech via Sarvam Bulbul v3.

        Args:
            text: text to speak (may contain Hindi-English code-switching).
            voice_id: Sarvam speaker name (e.g. "anushka"); defaults to a safe one.
            language: target BCP-47 code, e.g. "hi-IN". None => auto-detect from
                      the text via detect_language(), else DEFAULT_LANGUAGE.

        Returns:
            Audio bytes (decoded from Sarvam's base64), or b"" on any failure.
        """
        if not self.is_available():
            logger.debug("SarvamTTS.synthesize skipped — no API key.")
            return b""
        if not text or not text.strip():
            return b""

        lang = (language or kwargs.get("target_language_code") or "").strip()
        if not lang:
            lang = detect_language(text)
        speaker = (voice_id or kwargs.get("speaker") or _SARVAM_DEFAULT_SPEAKER).strip()

        try:
            import httpx
        except Exception as e:
            logger.warning(f"SarvamTTS: httpx not available ({e}); returning b''.")
            return b""

        url = f"{_SARVAM_BASE_URL}/text-to-speech"
        headers = {
            _SARVAM_AUTH_HEADER: self.api_key,
            "Content-Type": "application/json",
        }
        body = {
            "text": text,
            "target_language_code": lang,
            "speaker": speaker,
            "model": _SARVAM_TTS_MODEL,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=body)
            if resp.status_code >= 400:
                logger.warning(f"SarvamTTS HTTP {resp.status_code}: {resp.text[:200]}")
                return b""
            payload = resp.json()
        except Exception as e:
            logger.warning(f"SarvamTTS request failed ({e}); returning b''.")
            return b""

        return self._extract_audio(payload)

    @staticmethod
    def _extract_audio(payload) -> bytes:
        """Decode base64 audio out of various plausible response shapes."""
        if payload is None:
            return b""

        def _decode(b64: str) -> bytes:
            try:
                return base64.b64decode(b64)
            except Exception as e:
                logger.warning(f"SarvamTTS base64 decode failed ({e}).")
                return b""

        if isinstance(payload, str):
            return _decode(payload)
        if isinstance(payload, dict):
            # Common shape: {"audios": ["<base64>", ...]}
            audios = payload.get("audios")
            if isinstance(audios, list) and audios:
                first = audios[0]
                if isinstance(first, str) and first:
                    return _decode(first)
            # Alternatives: {"audio": "<base64>"} / {"audio_base64": "..."} etc.
            for key in ("audio", "audio_base64", "audio_content", "output"):
                val = payload.get(key)
                if isinstance(val, str) and val:
                    return _decode(val)
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("audio", "audio_base64"):
                    val = data.get(key)
                    if isinstance(val, str) and val:
                        return _decode(val)
        return b""

    async def synthesize_stream(
        self, text: str, voice_id: str | None = None, **kwargs
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesized audio. Bulbul v3 supports true streaming; here we use
        the simple, robust path (full synth, single yield) so the pipeline's
        streaming contract is satisfied without depending on the streaming
        endpoint's exact framing. Degrades to nothing-yielded on failure.
        """
        audio = await self.synthesize(text, voice_id=voice_id, **kwargs)
        if audio:
            yield audio


# =============================================================================
# AI4BHARAT — open-source Indic models (self-host) — optional adapters
# =============================================================================
# These are lightweight stubs. They document how to self-host AI4Bharat's
# open models and stay "not available" unless explicitly configured, so the
# heavy models are NEVER a hard dependency.


def _ai4bharat_endpoint() -> str:
    """Self-hosted AI4Bharat inference base URL, if the user configured one."""
    return (os.getenv("AI4BHARAT_ENDPOINT") or "").strip()


class Ai4BharatSTT(STTProvider):
    """
    AI4Bharat IndicConformer (ASR) adapter — open-source, self-hosted.

    To enable: deploy AI4Bharat's IndicConformer / Indic-Whisper model behind an
    HTTP endpoint (e.g. a small FastAPI wrapper or their NeMo server) and set:

        AI4BHARAT_ENDPOINT=http://your-host:port

    The endpoint is expected to accept a multipart audio "file" and return JSON
    with a "transcript"/"text" field. Until configured, is_available() is False
    and transcribe() returns "" (so the registry falls back to free Vosk).

    Repo: https://github.com/AI4Bharat/IndicConformerASR
    """

    name = "ai4bharat-stt"

    def __init__(self) -> None:
        self.endpoint = _ai4bharat_endpoint()

    def is_available(self) -> bool:
        return bool(self.endpoint)

    async def transcribe(self, audio: bytes, language: str = None, **kwargs) -> str:
        if not self.is_available():
            logger.debug(
                "Ai4BharatSTT not configured (set AI4BHARAT_ENDPOINT to self-host). Returning ''."
            )
            return ""
        if not audio:
            return ""
        try:
            import httpx
        except Exception as e:
            logger.warning(f"Ai4BharatSTT: httpx unavailable ({e}); returning ''.")
            return ""
        url = self.endpoint.rstrip("/") + "/transcribe"
        files = {"file": ("audio.wav", audio, "audio/wav")}
        data = {}
        lang = (language or kwargs.get("language_code") or "").strip()
        if lang:
            data["language"] = lang
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, files=files, data=data)
            if resp.status_code >= 400:
                logger.warning(f"Ai4BharatSTT HTTP {resp.status_code}.")
                return ""
            payload = resp.json()
        except Exception as e:
            logger.warning(f"Ai4BharatSTT request failed ({e}); returning ''.")
            return ""
        if isinstance(payload, dict):
            for key in ("transcript", "text", "transcription"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return ""


class Ai4BharatTTS(TTSProvider):
    """
    AI4Bharat IndicTTS (Indic-Parler / FastPitch+HiFiGAN) adapter — self-hosted.

    To enable: deploy AI4Bharat's IndicTTS model behind an HTTP endpoint and set:

        AI4BHARAT_ENDPOINT=http://your-host:port

    The endpoint is expected to accept JSON {"text", "language"} and return JSON
    with base64 "audio"/"audio_base64". Until configured, is_available() is False
    and synthesize() returns b"" (registry falls back to free EdgeTTS).

    Repo: https://github.com/AI4Bharat/Indic-TTS
    """

    name = "ai4bharat-tts"

    def __init__(self) -> None:
        self.endpoint = _ai4bharat_endpoint()

    def is_available(self) -> bool:
        return bool(self.endpoint)

    async def synthesize(
        self, text: str, voice_id: str | None = None, language: str = None, **kwargs
    ) -> bytes:
        if not self.is_available():
            logger.debug(
                "Ai4BharatTTS not configured (set AI4BHARAT_ENDPOINT to self-host). Returning b''."
            )
            return b""
        if not text or not text.strip():
            return b""
        try:
            import httpx
        except Exception as e:
            logger.warning(f"Ai4BharatTTS: httpx unavailable ({e}); returning b''.")
            return b""
        lang = (language or kwargs.get("language") or "").strip() or detect_language(text)
        url = self.endpoint.rstrip("/") + "/tts"
        body = {"text": text, "language": lang}
        if voice_id:
            body["speaker"] = voice_id
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                logger.warning(f"Ai4BharatTTS HTTP {resp.status_code}.")
                return b""
            payload = resp.json()
        except Exception as e:
            logger.warning(f"Ai4BharatTTS request failed ({e}); returning b''.")
            return b""
        if isinstance(payload, dict):
            for key in ("audio", "audio_base64", "audio_content"):
                val = payload.get(key)
                if isinstance(val, str) and val:
                    try:
                        return base64.b64decode(val)
                    except Exception as e:
                        logger.warning(f"Ai4BharatTTS base64 decode failed ({e}).")
                        return b""
        return b""


# =============================================================================
# REGISTRATION
# =============================================================================


def register_indic_providers(registry=None) -> None:
    """
    Register Sarvam + AI4Bharat providers into the BYOK ProviderRegistry.

    After calling this, users can select them purely via env:
        STT_PROVIDER=sarvam   TTS_PROVIDER=sarvam   (or =ai4bharat)

    Args:
        registry: a ProviderRegistry. If None, the process-wide singleton from
                  get_registry() is used.

    Idempotent + defensive: registration failures are logged, never raised.
    """
    reg = registry if registry is not None else get_registry()
    try:
        # Sarvam (API, BYOK) — the flagship Indian-language path.
        reg.register("stt", "sarvam", SarvamSTT)
        reg.register("tts", "sarvam", SarvamTTS)

        # AI4Bharat (open-source, self-hosted) — optional.
        reg.register("stt", "ai4bharat", Ai4BharatSTT)
        reg.register("tts", "ai4bharat", Ai4BharatTTS)

        logger.info("Registered Indian-language providers: sarvam (stt+tts), ai4bharat (stt+tts).")
    except Exception as e:  # pragma: no cover - registration must never crash app
        logger.warning(f"register_indic_providers failed ({e}); skipping.")


# Auto-register on import so a simple `import app.voice_agent.indic_providers`
# makes "sarvam"/"ai4bharat" selectable. Safe + idempotent.
try:
    register_indic_providers()
except Exception as _e:  # pragma: no cover
    logger.debug(f"Indic provider auto-registration skipped: {_e}")
