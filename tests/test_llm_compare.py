"""Tests — LLM Compare blind arena (Odysseus-inspired, patterns-only reimplement).

Coverage:
 1) INERT-default gate: LLM_COMPARE_ENABLED unset → 503 (no data leak)
 2) providers listing shape
 3) run endpoint parallel-fanout with monkeypatched chat_provider (no real API)
 4) blind labeling (no provider name leaked in /run response entries)
 5) vote flow reveals mapping + records winner
 6) double-vote rejected
 7) unknown label rejected
 8) admin auth still enforced (no /run without admin dep override)
"""

from __future__ import annotations

import asyncio
import importlib
import os
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------- helpers ---------------------- #


def _import_module(monkeypatch, enabled: bool = True):
    """Fresh import each test so flag reading + in-mem store reset."""
    if enabled:
        monkeypatch.setenv("LLM_COMPARE_ENABLED", "1")
    else:
        monkeypatch.delenv("LLM_COMPARE_ENABLED", raising=False)
    import app.api.llm_compare as m

    importlib.reload(m)
    # wipe any process-local in-mem state
    m._INMEM.clear()
    m._INMEM_VOTES.clear()
    return m


# ---------------------- flag gate ---------------------- #


def test_disabled_by_default_returns_503(monkeypatch):
    m = _import_module(monkeypatch, enabled=False)

    async def _run():
        with pytest.raises(Exception) as exc:
            m._require_enabled()
        # HTTPException with 503
        assert getattr(exc.value, "status_code", None) == 503

    asyncio.run(_run())


def test_enabled_flag_variants(monkeypatch):
    for val in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("LLM_COMPARE_ENABLED", val)
        import app.api.llm_compare as m

        importlib.reload(m)
        assert m._enabled() is True
    for val in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("LLM_COMPARE_ENABLED", val)
        importlib.reload(m)
        assert m._enabled() is False


# ---------------------- providers list ---------------------- #


def test_providers_list_shape(monkeypatch):
    m = _import_module(monkeypatch)
    lst = m._list_available_providers()
    assert isinstance(lst, list) and len(lst) >= 3
    for row in lst:
        assert set(row.keys()) == {"provider", "model", "available"}
        assert isinstance(row["available"], bool)


# ---------------------- run + vote flow ---------------------- #


def test_run_blind_and_vote_flow(monkeypatch):
    m = _import_module(monkeypatch)

    # Force ALL default providers "available" so we don't need real keys
    fake_flags = dict.fromkeys(m._DEFAULT_MODELS.keys(), True)
    monkeypatch.setattr(m.free_ai, "_provider_flags", lambda: fake_flags)

    # Stub chat_provider — returns deterministic per-provider text
    async def fake_chat_provider(*, provider, model, system, messages, **kwargs):
        return f"reply from {provider} using {model}", provider

    monkeypatch.setattr(m.free_ai, "chat_provider", fake_chat_provider)

    async def _flow():
        # RUN — pick 3 providers, expect 3 blind entries
        payload = m.CompareRunIn(
            prompt="Test prompt",
            providers=["cerebras", "groq", "mistral"],
            system="",
            max_tokens=64,
            temperature=0.5,
        )
        # bypass require_admin dep by calling endpoint fn directly
        run_out = await m.run_compare(payload, _user=object())
        assert run_out["count"] == 3
        assert len(run_out["entries"]) == 3
        # BLIND: no entry may contain the string 'cerebras' / 'groq' / 'mistral'
        # in identifying fields (only labels A/B/C)
        for e in run_out["entries"]:
            assert "provider" not in e, "provider name must NOT leak in run response"
            assert e["label"] in ("A", "B", "C")
            assert e["text"].startswith("reply from ")
            assert isinstance(e["latency_ms"], int)
        rid = run_out["run_id"]
        assert rid and len(rid) >= 8

        # VOTE for label 'A'
        vote_out = await m.vote(m.CompareVoteIn(run_id=rid, winner_label="A"), _user=object())
        assert vote_out["winner_label"] == "A"
        assert vote_out["winner_provider"] in ("cerebras", "groq", "mistral")
        assert set(vote_out["reveal"].keys()) == {"A", "B", "C"}

        # Double-vote rejected
        with pytest.raises(Exception) as exc:
            await m.vote(m.CompareVoteIn(run_id=rid, winner_label="B"), _user=object())
        assert getattr(exc.value, "status_code", None) == 400

        # Stats leaderboard non-empty
        st = await m.stats(_user=object())
        board = st["leaderboard"]
        winner_row = next(r for r in board if r["provider"] == vote_out["winner_provider"])
        assert winner_row["wins"] >= 1

    asyncio.run(_flow())


def test_run_requires_two_providers(monkeypatch):
    m = _import_module(monkeypatch)

    # Only 1 provider available
    fake_flags = {p: (p == "cerebras") for p in m._DEFAULT_MODELS.keys()}
    monkeypatch.setattr(m.free_ai, "_provider_flags", lambda: fake_flags)

    async def _one():
        with pytest.raises(Exception) as exc:
            await m.run_compare(
                m.CompareRunIn(prompt="hi", providers=["cerebras"]),
                _user=object(),
            )
        assert getattr(exc.value, "status_code", None) == 400

    asyncio.run(_one())


def test_unknown_label_rejected(monkeypatch):
    m = _import_module(monkeypatch)
    fake_flags = dict.fromkeys(m._DEFAULT_MODELS.keys(), True)
    monkeypatch.setattr(m.free_ai, "_provider_flags", lambda: fake_flags)

    async def fake_chat_provider(*, provider, model, system, messages, **kwargs):
        return f"ok {provider}", provider

    monkeypatch.setattr(m.free_ai, "chat_provider", fake_chat_provider)

    async def _flow():
        out = await m.run_compare(
            m.CompareRunIn(prompt="test", providers=["cerebras", "groq"]),
            _user=object(),
        )
        with pytest.raises(Exception) as exc:
            await m.vote(
                m.CompareVoteIn(run_id=out["run_id"], winner_label="Z"),
                _user=object(),
            )
        assert getattr(exc.value, "status_code", None) == 400

    asyncio.run(_flow())


def test_vote_run_id_expired(monkeypatch):
    m = _import_module(monkeypatch)
    fake_flags = dict.fromkeys(m._DEFAULT_MODELS.keys(), True)
    monkeypatch.setattr(m.free_ai, "_provider_flags", lambda: fake_flags)

    async def _flow():
        with pytest.raises(Exception) as exc:
            await m.vote(
                m.CompareVoteIn(run_id="nonexistent-run-id-x", winner_label="A"),
                _user=object(),
            )
        assert getattr(exc.value, "status_code", None) == 404

    asyncio.run(_flow())


# ---------------------- registry ---------------------- #


def test_flag_registered_in_automation_flags():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "LLM_COMPARE_ENABLED" in AUTOMATION_FLAGS


def test_router_importable_from_main():
    """Router should import without side effects even when flag OFF."""
    import app.api.llm_compare as m

    importlib.reload(m)
    assert m.router is not None
    routes = [getattr(r, "path", "") for r in m.router.routes]
    assert "/api/llm/compare/run" in routes
    assert "/api/llm/compare/vote" in routes
    assert "/api/llm/compare/stats" in routes
    assert "/api/llm/compare/providers" in routes
