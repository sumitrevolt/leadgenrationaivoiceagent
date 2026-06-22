"""Kokoro TTS — self-hosted FREE fallback for EdgeTTS (resilience + tail-latency).

EdgeTTS (`hi-IN-SwaraNeural`) is network-dependent and occasionally 403s. Kokoro
(82M params, Apache-2.0, runs on CPU) is a self-hosted floor used ONLY when the
primary TTS fails/times out AND `USE_KOKORO_TTS=1`.

INERT by design: `available()` is False until the `kokoro` package + model are
baked into the image (Dockerfile.lock) — exactly the Smart Turn pattern. So this
module ships safe (zero behaviour change) and activates only after the dep bake +
flag flip. Never-raise: `synthesize()` returns b"" on any failure so callers can
fall through cleanly.

Caveats (documented for the voice-path owner): Kokoro outputs ~24 kHz; the live
Vobiz stream needs L16/16 kHz, so adoption there needs a resample step. Hindi
naturalness < EdgeTTS → keep EdgeTTS primary, Kokoro = failover only.
"""

from __future__ import annotations

import os

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PIPELINE = None
_TRIED = False


def enabled() -> bool:
    return os.environ.get("USE_KOKORO_TTS", "0").strip().lower() in ("1", "true", "yes", "on")


def _get_pipeline():
    """Lazily build the Kokoro pipeline once. Returns None if dep/model absent."""
    global _PIPELINE, _TRIED
    if _PIPELINE is not None or _TRIED:
        return _PIPELINE
    _TRIED = True
    try:
        from kokoro import KPipeline  # type: ignore

        _PIPELINE = KPipeline(lang_code=os.environ.get("KOKORO_LANG", "h"))  # 'h' = Hindi
        logger.info("[kokoro] pipeline ready")
    except Exception as e:  # dep not baked yet → stay inert
        logger.debug("[kokoro] unavailable: %s", e)
        _PIPELINE = None
    return _PIPELINE


def available() -> bool:
    """True only when flag on AND the kokoro pipeline actually loaded."""
    return enabled() and _get_pipeline() is not None


def synthesize(text: str, voice: str | None = None, sample_rate: int = 24000) -> bytes:
    """PCM16 mono WAV bytes for `text`, or b"" if unavailable/failed. NEVER raises.

    Synchronous + CPU-bound — call via asyncio.to_thread from async paths.
    """
    if not text or not text.strip():
        return b""
    pipe = _get_pipeline() if enabled() else None
    if pipe is None:
        return b""
    try:
        import io
        import wave

        import numpy as np

        v = voice or os.environ.get("KOKORO_VOICE", "hf_alpha")  # Hindi female default
        chunks = []
        for _gs, _ps, audio in pipe(text, voice=v):
            chunks.append(audio)
        if not chunks:
            return b""
        samples = np.concatenate(chunks)
        pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(pcm16)
        return buf.getvalue()
    except Exception as e:  # pragma: no cover — never-raise
        logger.debug("[kokoro] synth failed: %s", e)
        return b""


__all__ = ["enabled", "available", "synthesize"]
