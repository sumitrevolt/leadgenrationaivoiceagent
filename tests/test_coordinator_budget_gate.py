"""Coordinator swarm paths respect the per-agent budget governor (2026-07-31).

`agent_budget.check()` was wired into `staff.run_member` only, so the coordinator's
fan_out / agentverse / debate / council paths issued one LLM call per agent per round with
no daily ceiling — `_llm_rate_ok()` caps burst-per-minute, not the day's total. On a
free-tier provider chain that lets a swarm eat the quota the voice path shares.
"""

from __future__ import annotations

import pytest

from app.agents import coordinator as co


@pytest.fixture()
def spy_llm(monkeypatch):
    """Record whether the draft branch reached the LLM."""
    calls: list[tuple[str, str]] = []

    async def _fake(system, user, max_tokens=260, temperature=0.4):
        calls.append((system, user))
        return "draft output", "fake-provider"

    monkeypatch.setattr(co, "_llm", _fake)
    return calls


@pytest.mark.asyncio
async def test_blocked_agent_skips_the_llm_entirely(monkeypatch, spy_llm):
    monkeypatch.setattr(
        "app.platform.agent_budget.check",
        lambda agent_id: {"allowed": False, "tier": 3, "usage": 120, "limit": 100},
    )

    out = await co._run_agent("isha", "content banao", {"goal": "g", "results": []}, execute=False)

    assert out["mode"] == "skipped"
    assert out["reason"] == "budget_exceeded"
    assert out["budget"]["tier"] == 3
    assert spy_llm == []  # the whole point: no tokens burned


@pytest.mark.asyncio
async def test_allowed_agent_runs_normally(monkeypatch, spy_llm):
    monkeypatch.setattr(
        "app.platform.agent_budget.check", lambda agent_id: {"allowed": True, "tier": 1}
    )

    out = await co._run_agent("isha", "content banao", {"goal": "g", "results": []}, execute=False)

    assert out["mode"] == "draft"
    assert out["output"] == "draft output"
    assert len(spy_llm) == 1


@pytest.mark.asyncio
async def test_disabled_budget_is_a_behavioural_no_op(monkeypatch, spy_llm):
    # AGENT_BUDGET_ENABLED off is the DEFAULT — check() short-circuits to allowed=True,
    # so arming nothing must leave the coordinator exactly as it was.
    monkeypatch.setenv("AGENT_BUDGET_ENABLED", "0")

    out = await co._run_agent("isha", "content banao", {"goal": "g", "results": []}, execute=False)

    assert out["mode"] == "draft"
    assert len(spy_llm) == 1


@pytest.mark.asyncio
async def test_budget_subsystem_failure_fails_open(monkeypatch, spy_llm):
    def _boom(agent_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.platform.agent_budget.check", _boom)

    out = await co._run_agent("isha", "content banao", {"goal": "g", "results": []}, execute=False)

    assert out["mode"] == "draft"  # agent still runs
    assert len(spy_llm) == 1


@pytest.mark.asyncio
async def test_execute_branch_is_untouched_by_the_gate(monkeypatch):
    """The tool branch already ran under staff's governance — don't double-gate it."""
    monkeypatch.setattr(
        "app.platform.agent_budget.check",
        lambda agent_id: {"allowed": False, "tier": 3},
    )

    async def _tool(task, goal):
        return {"ok": True, "tool": "isha"}

    monkeypatch.setitem(co._TOOLS, "isha", _tool)

    out = await co._run_agent("isha", "content banao", {"goal": "g", "results": []}, execute=True)

    assert out["mode"] == "executed"
    assert out["output"] == {"ok": True, "tool": "isha"}
