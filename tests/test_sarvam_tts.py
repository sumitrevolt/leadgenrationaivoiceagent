"""Sarvam TTS optional-premium-voice guards — INERT without key, cap-safe.

These lock the safety contract: no key = None (EdgeTTS floor), over monthly
char-cap = None, and no network call on either path. Happy-path (real API) is
verified by in-container smoke once a SARVAM_API_KEY is configured.
"""

import asyncio

from app.voice_agent import sarvam_tts


def test_inert_without_key(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.setattr(sarvam_tts, "_api_key", lambda: "")
    assert sarvam_tts.is_enabled() is False
    # No key → None instantly (caller falls back to EdgeTTS), never raises.
    assert asyncio.run(sarvam_tts.synth_mp3_b64("namaste sir")) is None


def test_enabled_with_key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test_dummy")
    monkeypatch.setattr(sarvam_tts.settings, "sarvam_api_key", "", raising=False)
    assert sarvam_tts.is_enabled() is True


def test_over_cap_returns_none_no_network(monkeypatch):
    monkeypatch.setattr(sarvam_tts, "_api_key", lambda: "sk_test_dummy")
    monkeypatch.setattr(sarvam_tts, "_cap", lambda: 10)
    monkeypatch.setattr(sarvam_tts, "_usage_read", lambda: {sarvam_tts._month_key(): 100})

    # If the network were hit this would error/hang; instead it must short-circuit.
    def _boom(*a, **k):
        raise AssertionError("must not call API when over cap")

    monkeypatch.setattr(sarvam_tts.asyncio, "wait_for", _boom)
    assert asyncio.run(sarvam_tts.synth_mp3_b64("a long enough text over the cap")) is None


def test_cap_zero_means_unlimited(monkeypatch):
    monkeypatch.setattr(sarvam_tts, "_cap", lambda: 0)
    assert sarvam_tts._over_cap(10_000_000) is False
