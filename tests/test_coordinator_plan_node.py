"""COORD_PLAN_NODE flag contract on coordinator.plan().

INERT by default (flag OFF => plan_node never invoked, legacy `_extract_list`
path + hardcoded fallback byte-identical). Flag ON => plan_node is the canary;
on any plan_node failure the legacy path still runs. No real network anywhere —
`_llm` is monkeypatched.
"""

from __future__ import annotations

import asyncio

from app.agents import coordinator
from app.agents.harness import plan_node


def _counting(invoked: dict):
    async def f(*a, **k):
        invoked["n"] += 1
        return None

    return f


def test_flag_off_plan_node_never_invoked(tmp_path, monkeypatch):
    monkeypatch.delenv("COORD_PLAN_NODE", raising=False)
    monkeypatch.setattr(coordinator, "_RUNS", str(tmp_path / "c.jsonl"))

    invoked = {"n": 0}
    monkeypatch.setattr(plan_node, "structured_plan", _counting(invoked))

    async def _fake_chat(system, messages, **kw):
        return "", "none"  # LLM empty -> legacy fallback chain

    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", _fake_chat)

    steps = asyncio.run(coordinator.plan("leads 2x karo", max_steps=3))
    assert steps and all(s["agent"] in coordinator._agent_keys() for s in steps)
    assert invoked["n"] == 0  # INERT contract: flag OFF => zero plan_node involvement


def test_flag_on_valid_plan_uses_structured(tmp_path, monkeypatch):
    monkeypatch.setenv("COORD_PLAN_NODE", "1")
    monkeypatch.setattr(coordinator, "_RUNS", str(tmp_path / "c2.jsonl"))

    async def fake_llm(system, user, max_tokens=260, temperature=0.4):
        return '[{"agent":"dev","task":"research"},{"agent":"isha","task":"post"}]', "none"

    monkeypatch.setattr(coordinator, "_llm", fake_llm)

    steps = asyncio.run(coordinator.plan("nikal ke leads", max_steps=3))
    assert steps == [{"agent": "dev", "task": "research"}, {"agent": "isha", "task": "post"}]


def test_flag_on_invalid_falls_back_to_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("COORD_PLAN_NODE", "1")
    monkeypatch.setenv("COORD_PLAN_NODE_REVIEWS", "0")
    monkeypatch.setattr(coordinator, "_RUNS", str(tmp_path / "c3.jsonl"))

    calls = {"n": 0}

    async def fake_llm(system, user, max_tokens=260, temperature=0.4):
        calls["n"] += 1
        return "garbage not json", "none"

    monkeypatch.setattr(coordinator, "_llm", fake_llm)

    steps = asyncio.run(coordinator.plan("nikal ke leads", max_steps=3))
    assert steps  # legacy fallback chain (dev -> rohan -> isha)
    assert all(s["agent"] in coordinator._agent_keys() for s in steps)
    # plan_node fill (1) failed, then legacy call (1) failed -> hardcoded fallback.
    assert calls["n"] == 2


def test_flag_on_review_rounds_recover(tmp_path, monkeypatch):
    monkeypatch.setenv("COORD_PLAN_NODE", "1")
    monkeypatch.setattr(coordinator, "_RUNS", str(tmp_path / "c4.jsonl"))

    calls = {"n": 0}

    async def flaky(system, user, max_tokens=260, temperature=0.4):
        calls["n"] += 1
        if calls["n"] == 1:
            return '[{"agent":"nope","task":"x"}]', "none"  # fill invalid
        return '[{"agent":"dev","task":"research"}]', "none"  # review round fixes

    monkeypatch.setattr(coordinator, "_llm", flaky)

    steps = asyncio.run(coordinator.plan("nikal ke leads", max_steps=3))
    assert steps == [{"agent": "dev", "task": "research"}]
    assert calls["n"] == 2  # fill + one review round, legacy never called
