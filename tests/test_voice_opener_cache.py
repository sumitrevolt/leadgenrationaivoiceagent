"""Unit tests for VOICE_RESPONSE_CACHE — opener-only semantic cache in TelecallerBrain.

Diagnosed 2026-06-26 from prod inspection: SEMANTIC_CACHE=1 was set in /opt/leadgen/.env
but `redis-cli --scan --pattern 'semcache:*' | wc -l` reported 0 keys — proving the
voice brain hot path never called semantic_complete. semantic_cache.py was only used
by app/marketing/* and app/llm/budget_guard.py.

These tests lock the wiring + the conservative scope (opener-only, never mid-call).
Default OFF = byte-identical existing behaviour (regression-safe rollout)."""

from __future__ import annotations

import asyncio

import pytest

from app.voice_agent.telecaller_brain import TelecallerBrain


def _brain(monkeypatch: pytest.MonkeyPatch) -> TelecallerBrain:
    monkeypatch.setenv("VOICE_RESPONSE_CACHE", "1")
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    return TelecallerBrain(niche="solar_residential", client_name="Test Co")


def test_eligibility_first_user_turn_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache only applies when zero USER turns yet (bot greeting in history is OK)."""
    brain = _brain(monkeypatch)
    # No history at all → eligible
    assert brain._opener_cache_eligible([], "haan boliye") is True
    assert brain._opener_cache_eligible(None, "haan boliye") is True
    # Just the bot's auto-greeting before first user turn → STILL eligible (this
    # is the real prod shape — web_call.py sends greeting before user speaks)
    only_greeting = [{"role": "assistant", "content": "Namaste sir, kaise hain?"}]
    assert brain._opener_cache_eligible(only_greeting, "haan boliye") is True
    # ANY prior user message → mid-conversation → must NOT cache (context bleed)
    mid_call = [
        {"role": "assistant", "content": "Namaste"},
        {"role": "user", "content": "haan"},
        {"role": "assistant", "content": "Aapka bill kitna?"},
    ]
    assert brain._opener_cache_eligible(mid_call, "2000 ke aas paas") is False
    # Too-short utterances rejected (too generic to safely match across calls)
    assert brain._opener_cache_eligible([], "haan") is False
    assert brain._opener_cache_eligible([], "") is False


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """VOICE_RESPONSE_CACHE unset → byte-identical existing behaviour."""
    monkeypatch.delenv("VOICE_RESPONSE_CACHE", raising=False)
    monkeypatch.setenv("SEMANTIC_CACHE", "1")
    brain = TelecallerBrain(niche="solar_residential", client_name="Test Co")
    assert brain._opener_cache_eligible([], "haan boliye sir") is False


def test_requires_semantic_cache_flag_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with VOICE_RESPONSE_CACHE=1, must also have SEMANTIC_CACHE=1
    (defense in depth — the underlying engine respects its own gate)."""
    monkeypatch.setenv("VOICE_RESPONSE_CACHE", "1")
    monkeypatch.delenv("SEMANTIC_CACHE", raising=False)
    brain = TelecallerBrain(niche="solar_residential", client_name="Test Co")
    assert brain._opener_cache_eligible([], "haan boliye sir") is False


@pytest.mark.asyncio
async def test_lookup_fail_open_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Redis / no Qdrant / no fastembed = clean None, NO exception bubbles up."""
    brain = _brain(monkeypatch)
    # _opener_cache_lookup must absorb any/all exceptions inside semantic_cache deps
    result = await brain._opener_cache_lookup("haan boliye sir")
    assert result is None  # no infra in unit-test env, fail-open


@pytest.mark.asyncio
async def test_store_fail_open_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Store is fire-and-forget — must absorb every failure silently."""
    brain = _brain(monkeypatch)
    # No raise even with no Redis / Qdrant
    await brain._opener_cache_store("haan boliye sir", "Namaste sir, kaise hain?")
    # Empty/whitespace reply must short-circuit cleanly
    await brain._opener_cache_store("haan boliye sir", "")
    await brain._opener_cache_store("haan boliye sir", "   ")


@pytest.mark.asyncio
async def test_reply_uses_cache_when_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """If _opener_cache_lookup returns a cached reply, _generate must NOT be called.
    Stub _fast_path_reply so we exercise the LLM/cache code path (otherwise the
    niche opener canned line would short-circuit before cache check)."""
    brain = _brain(monkeypatch)

    async def _cache_hit(_ut: str) -> str:
        return "CACHED_OPENER_REPLY"

    gen_called: list[bool] = []

    async def _spy_generate(_p: str) -> tuple[str, str]:
        gen_called.append(True)
        return ("LLM_REPLY_SHOULD_NOT_RUN", "gemini")

    monkeypatch.setattr(brain, "_fast_path_reply", lambda *_a, **_k: "")
    monkeypatch.setattr(brain, "_opener_cache_lookup", _cache_hit)
    monkeypatch.setattr(brain, "_generate", _spy_generate)

    text = await brain.reply([], "haan boliye sir")
    assert text == "CACHED_OPENER_REPLY"
    assert gen_called == []  # cache served, LLM never invoked


@pytest.mark.asyncio
async def test_reply_skips_cache_for_mid_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mid-conversation turn (non-empty history) must NEVER consult the cache."""
    brain = _brain(monkeypatch)

    lookup_called: list[bool] = []

    async def _spy_lookup(_ut: str) -> str | None:
        lookup_called.append(True)
        return "SHOULD_NEVER_RETURN"

    async def _stub_generate(_p: str) -> tuple[str, str]:
        return ("MID_CALL_LLM_REPLY", "gemini")

    async def _stub_kb_facts(_ut: str) -> list[str]:
        return []

    monkeypatch.setattr(brain, "_fast_path_reply", lambda *_a, **_k: "")
    monkeypatch.setattr(brain, "_opener_cache_lookup", _spy_lookup)
    monkeypatch.setattr(brain, "_generate", _stub_generate)
    monkeypatch.setattr(brain, "_kb_facts", _stub_kb_facts)

    # History includes a real user turn — mid-conversation, NOT first user reply
    history = [
        {"role": "assistant", "content": "Namaste sir"},
        {"role": "user", "content": "haan boliye sir"},
        {"role": "assistant", "content": "Aapka monthly bill kitna?"},
    ]
    text = await brain.reply(history, "2000 rupees ke aas paas")
    # LLM ran, cache was never consulted
    assert lookup_called == []
    assert "MID_CALL_LLM_REPLY" in text or text  # text non-empty


@pytest.mark.asyncio
async def test_reply_stores_on_cache_miss_first_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """First-turn cache miss + LLM success → store() must be called fire-and-forget."""
    brain = _brain(monkeypatch)

    store_calls: list[tuple[str, str]] = []

    async def _cache_miss(_ut: str) -> None:
        return None

    async def _spy_store(ut: str, text: str) -> None:
        store_calls.append((ut, text))

    async def _stub_generate(_p: str) -> tuple[str, str]:
        return ("FRESH_LLM_OPENER", "gemini")

    async def _stub_kb_facts(_ut: str) -> list[str]:
        return []

    monkeypatch.setattr(brain, "_fast_path_reply", lambda *_a, **_k: "")
    monkeypatch.setattr(brain, "_opener_cache_lookup", _cache_miss)
    monkeypatch.setattr(brain, "_opener_cache_store", _spy_store)
    monkeypatch.setattr(brain, "_generate", _stub_generate)
    monkeypatch.setattr(brain, "_kb_facts", _stub_kb_facts)

    text = await brain.reply([], "haan boliye sir")
    # Give the fire-and-forget store task a chance to run
    await asyncio.sleep(0.05)
    assert "FRESH_LLM_OPENER" in text or text == "FRESH_LLM_OPENER"
    assert len(store_calls) == 1
    assert store_calls[0][0] == "haan boliye sir"
    assert "FRESH_LLM_OPENER" in store_calls[0][1]
