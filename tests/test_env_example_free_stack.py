"""W3.6 — .env.example must advertise the real FREE stack, not stale PAID providers.

The template shipped `DEFAULT_STT=deepgram`, `DEFAULT_LLM=gemini-1.5-flash`, and
ElevenLabs/Azure TTS blocks — all paid and none part of the actual stack (Groq STT /
Mistral+Groq+Cerebras+Gemini LLM / EdgeTTS, free-only per user mandate). That misleads
onboarding. This guards the corrected defaults against re-drift.
"""

from __future__ import annotations

from pathlib import Path

_ENV = Path(__file__).resolve().parent.parent / ".env.example"


def test_env_example_is_free_stack():
    txt = _ENV.read_text(encoding="utf-8")
    # stale PAID defaults must be gone
    assert "DEFAULT_STT=deepgram" not in txt, "STT default must be free Groq, not Deepgram"
    assert "DEFAULT_LLM=gemini-1.5-flash" not in txt, "LLM default must be the free stack"
    assert "DEEPGRAM_API_KEY" not in txt, "stale paid Deepgram key must be removed"
    assert "ELEVENLABS_API_KEY" not in txt, "stale paid ElevenLabs key must be removed"
    # free defaults present
    assert "DEFAULT_STT=groq" in txt
    assert "DEFAULT_TTS=edge" in txt
