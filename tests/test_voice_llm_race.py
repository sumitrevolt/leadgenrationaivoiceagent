"""Unit tests for VOICE_LLM_RACE — parallel LLM backend race in TelecallerBrain.

Diagnosed 2026-06-26 from live-prod agent_tester scorecard: sequential
Gemini → free_ai with each capped at _REPLY_TIMEOUT_S=8s gave a 7-17s tail
plus 2× NO-REPLY at 12s ("atak jata" symptom). The race fires both backends
in parallel; first non-empty wins; loser is cancelled. Default OFF =
byte-identical sequential behaviour (regression-safe rollout)."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.voice_agent.telecaller_brain import TelecallerBrain


def _make_brain(monkeypatch: pytest.MonkeyPatch) -> TelecallerBrain:
    monkeypatch.setenv("VOICE_LLM_RACE", "1")
    return TelecallerBrain(niche="solar_residential", client_name="Test Co")


@pytest.mark.asyncio
async def test_race_returns_fastest_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whoever returns first non-empty wins; slower path is cancelled."""
    brain = _make_brain(monkeypatch)

    async def _slow_gemini(_p: str) -> str:
        await asyncio.sleep(0.6)
        return "GEMINI_REPLY"

    async def _fast_free(_p: str) -> str:
        await asyncio.sleep(0.05)
        return "FREE_AI_REPLY"

    monkeypatch.setattr(brain, "_gemini_reply", _slow_gemini)
    monkeypatch.setattr(brain, "_free_llm", _fast_free)

    text, provider = await brain._generate("hello")
    assert text == "FREE_AI_REPLY"
    assert provider == "free_ai"


@pytest.mark.asyncio
async def test_race_skips_empty_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the fastest returns empty, the race waits for the other backend."""
    brain = _make_brain(monkeypatch)

    async def _fast_empty(_p: str) -> str:
        await asyncio.sleep(0.05)
        return ""

    async def _slow_good(_p: str) -> str:
        await asyncio.sleep(0.2)
        return "GEMINI_REPLY"

    monkeypatch.setattr(brain, "_free_llm", _fast_empty)
    monkeypatch.setattr(brain, "_gemini_reply", _slow_good)

    text, provider = await brain._generate("hello")
    assert text == "GEMINI_REPLY"
    assert provider == "gemini"


@pytest.mark.asyncio
async def test_race_returns_empty_when_both_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both empty → caller falls to script_fallback (returns ("","")) — never crashes."""
    brain = _make_brain(monkeypatch)

    async def _empty(_p: str) -> str:
        await asyncio.sleep(0.05)
        return ""

    monkeypatch.setattr(brain, "_gemini_reply", _empty)
    monkeypatch.setattr(brain, "_free_llm", _empty)

    text, provider = await brain._generate("hello")
    assert text == ""
    assert provider == ""


@pytest.mark.asyncio
async def test_race_survives_one_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """If one backend raises, race still returns the other's non-empty reply."""
    brain = _make_brain(monkeypatch)

    async def _boom(_p: str) -> str:
        raise RuntimeError("simulated provider crash")

    async def _good(_p: str) -> str:
        await asyncio.sleep(0.1)
        return "SURVIVOR_REPLY"

    monkeypatch.setattr(brain, "_gemini_reply", _boom)
    monkeypatch.setattr(brain, "_free_llm", _good)

    text, provider = await brain._generate("hello")
    assert text == "SURVIVOR_REPLY"
    assert provider == "free_ai"


@pytest.mark.asyncio
async def test_race_disabled_by_default_preserves_sequential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VOICE_LLM_RACE unset → existing sequential behaviour byte-identical."""
    monkeypatch.delenv("VOICE_LLM_RACE", raising=False)
    monkeypatch.delenv("VOICE_GEMINI_PRIMARY", raising=False)
    monkeypatch.delenv("GEMINI_PRIMARY", raising=False)
    brain = TelecallerBrain(niche="solar_residential", client_name="Test Co")

    gemini_called: list[bool] = []
    free_called: list[bool] = []

    async def _gemini(_p: str) -> str:
        gemini_called.append(True)
        return "GEM"

    async def _free(_p: str) -> str:
        free_called.append(True)
        return "FREE"

    monkeypatch.setattr(brain, "_gemini_reply", _gemini)
    monkeypatch.setattr(brain, "_free_llm", _free)

    text, provider = await brain._generate("hello")
    # Default (no flags) = free_ai first, returns immediately, Gemini never called.
    assert text == "FREE"
    assert provider == "free_ai"
    assert free_called == [True]
    assert gemini_called == []
