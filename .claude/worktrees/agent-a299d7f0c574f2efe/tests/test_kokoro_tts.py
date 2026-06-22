"""Tests for Kokoro TTS fallback — inert-safety + tts.py facade failover.

No network, no real kokoro dep: we exercise the inert path and monkeypatch the
fallback into the TextToSpeech facade.
"""

from __future__ import annotations

import asyncio


def test_inert_without_flag(monkeypatch):
    from app.voice_agent import kokoro_tts

    monkeypatch.delenv("USE_KOKORO_TTS", raising=False)
    assert kokoro_tts.enabled() is False
    assert kokoro_tts.available() is False
    # never-raise + empty when unavailable
    assert kokoro_tts.synthesize("namaste") == b""


def test_synthesize_empty_text_is_empty(monkeypatch):
    from app.voice_agent import kokoro_tts

    monkeypatch.setenv("USE_KOKORO_TTS", "1")
    assert kokoro_tts.synthesize("") == b""
    assert kokoro_tts.synthesize("   ") == b""


def test_tts_facade_falls_back_to_kokoro(monkeypatch):
    from app.voice_agent import kokoro_tts
    from app.voice_agent.tts import TextToSpeech

    tts = TextToSpeech(provider="edge")  # no API key required

    async def _boom(*_a, **_k):
        raise RuntimeError("primary TTS down")

    monkeypatch.setattr(tts._provider, "synthesize", _boom, raising=False)
    monkeypatch.setattr(kokoro_tts, "available", lambda: True, raising=False)
    monkeypatch.setattr(kokoro_tts, "synthesize", lambda text, *a, **k: b"WAVDATA", raising=False)

    out = asyncio.run(tts.synthesize("namaste ji"))
    assert out == b"WAVDATA"


def test_tts_facade_reraises_when_kokoro_unavailable(monkeypatch):
    from app.voice_agent import kokoro_tts
    from app.voice_agent.tts import TextToSpeech

    tts = TextToSpeech(provider="edge")

    async def _boom(*_a, **_k):
        raise RuntimeError("primary TTS down")

    monkeypatch.setattr(tts._provider, "synthesize", _boom, raising=False)
    monkeypatch.setattr(kokoro_tts, "available", lambda: False, raising=False)

    # No fallback available → original failure propagates (caller handles).
    try:
        asyncio.run(tts.synthesize("namaste"))
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
