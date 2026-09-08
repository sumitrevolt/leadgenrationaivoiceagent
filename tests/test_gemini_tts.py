"""Gemini-TTS premium-voice guards — INERT without key/flag, valid WAV, no network.

Locks the safety contract: no Gemini key OR GEMINI_TTS=0 → None (EdgeTTS floor);
PCM→WAV wrapper produces a valid RIFF header; empty text short-circuits. Happy-path
(real API) is verified by in-container smoke once a GEMINI_API_KEY is present.
"""

import asyncio

from app.voice_agent import gemini_tts


def test_inert_without_key(monkeypatch):
    monkeypatch.setattr(gemini_tts, "_key", lambda: "")
    assert gemini_tts.is_enabled() is False
    assert asyncio.run(gemini_tts.synth_wav_b64("namaste sir")) is None


def test_flag_off_disables(monkeypatch):
    monkeypatch.setattr(gemini_tts, "_key", lambda: "AIza_dummy")
    monkeypatch.setenv("GEMINI_TTS", "0")
    assert gemini_tts.is_enabled() is False


def test_enabled_with_key_and_flag(monkeypatch):
    monkeypatch.setattr(gemini_tts, "_key", lambda: "AIza_dummy")
    monkeypatch.setenv("GEMINI_TTS", "1")
    assert gemini_tts.is_enabled() is True


def test_pcm_to_wav_valid_riff_header():
    wav = gemini_tts._pcm_to_wav(b"\x00\x01" * 100)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert b"data" in wav[:64]
    # base64 of a RIFF WAV must start with the "UklGR" magic the frontend detects.
    import base64

    assert base64.b64encode(wav).decode("ascii").startswith("UklGR")


def test_empty_text_returns_none(monkeypatch):
    monkeypatch.setattr(gemini_tts, "_key", lambda: "AIza_dummy")
    monkeypatch.setenv("GEMINI_TTS", "1")
    assert asyncio.run(gemini_tts.synth_wav_b64("   ")) is None
