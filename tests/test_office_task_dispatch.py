"""F3 "Kaam Do" — office HQ map task dispatch.

Bars:
- POST /api/platform/office/agents/{member}/task is admin-gated (401 w/o auth).
- run_agent_task() is DRAFT-SAFE: team scope calls coordinator.coordinate with
  execute=False (never a real side-effect), solo scope calls fan_out for that
  single member only.
- Goal validation: empty -> ok:False; >500 chars capped (not rejected).
- Failure path: coordinator raising -> ok:False, HTTP still 200 (never-raise).
- Timeout path: primitive hitting the budget -> ok:True, status:"timeout" with
  an honest note (coroutine cancelled, NOT backgrounded).
- Unknown member -> ok:False.
- Contract: success always returns {ok, summary, run_id} regardless of primitive.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient

from app.api.auth_deps import get_current_user, require_admin
from app.main import app
from app.platform import office_hq

client = TestClient(app)


def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        return asyncio.get_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------- #
# HTTP: admin gate
#
# conftest.py globally overrides require_admin/get_current_user with a mock
# admin for the whole suite (so most tests run auth-open). To genuinely test
# the gate we temporarily REMOVE those overrides so the real dependency runs
# and rejects a no-token request — then restore them (else we'd break sibling
# tests, the documented "mocked-open auth = false confidence" lesson).
# --------------------------------------------------------------------------- #
def test_task_endpoint_requires_admin():
    """No auth + real dependency -> 401/403, never reaches the coordinator."""
    saved_admin = app.dependency_overrides.pop(require_admin, None)
    saved_user = app.dependency_overrides.pop(get_current_user, None)
    try:
        r = client.post(
            "/api/platform/office/agents/isha/task",
            json={"goal": "test goal jo lamba hai", "scope": "solo"},
        )
        assert r.status_code in (401, 403)
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user


def test_task_endpoint_happy_path(monkeypatch):
    """Admin authed (conftest global mock super-admin) + coordinator mocked ->
    200 with {ok, summary}. We do NOT touch dependency_overrides here — conftest
    already hands the client a super-admin, and popping it in a finally would
    delete the global override for every sibling test."""

    async def _fake_fanout(goal, agents=None, max_agents=4):
        return {"ok": True, "summary": "isha ne plan bana diya", "agents": agents}

    monkeypatch.setattr("app.agents.coordinator.fan_out", _fake_fanout)
    r = client.post(
        "/api/platform/office/agents/isha/task",
        json={"goal": "content plan banao", "scope": "solo"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "summary" in d and "plan bana diya" in d["summary"]


# --------------------------------------------------------------------------- #
# Unit: run_agent_task validation + never-raise contract
# --------------------------------------------------------------------------- #
def test_empty_goal_rejected():
    out = _run(office_hq.run_agent_task("isha", "   ", "solo"))
    assert out["ok"] is False
    assert "goal" in out["error"].lower()


def test_unknown_member_rejected():
    out = _run(office_hq.run_agent_task("__nobody__", "kuch kaam karo", "solo"))
    assert out["ok"] is False
    assert "unknown agent" in out["error"].lower()


def test_bad_scope_rejected():
    out = _run(office_hq.run_agent_task("isha", "kuch kaam karo", "everyone"))
    assert out["ok"] is False
    assert "scope" in out["error"].lower()


def test_solo_scope_calls_fanout_single_agent(monkeypatch):
    captured = {}

    async def _fake_fanout(goal, agents=None, max_agents=4):
        captured["goal"] = goal
        captured["agents"] = agents
        captured["max_agents"] = max_agents
        return {"ok": True, "summary": "done", "agents": agents}

    # If coordinate is called instead, this test must fail loudly.
    async def _boom_coordinate(*a, **k):
        raise AssertionError("solo scope must NOT call coordinate()")

    monkeypatch.setattr("app.agents.coordinator.fan_out", _fake_fanout)
    monkeypatch.setattr("app.agents.coordinator.coordinate", _boom_coordinate)
    out = _run(office_hq.run_agent_task("rohan", "leads follow up karo", "solo"))
    assert out["ok"] is True
    assert captured["agents"] == ["rohan"]  # only that one member
    assert captured["max_agents"] == 1
    assert out["summary"] == "done"


def test_team_scope_calls_coordinate_draft_safe(monkeypatch):
    """team scope must call coordinate with execute=False (draft-safe)."""
    captured = {}

    async def _fake_coordinate(goal, execute=False, max_steps=5):
        captured["execute"] = execute
        captured["max_steps"] = max_steps
        return {"ok": True, "run_id": "abc123", "summary": "team plan ready"}

    async def _boom_fanout(*a, **k):
        raise AssertionError("team scope must NOT call fan_out()")

    monkeypatch.setattr("app.agents.coordinator.coordinate", _fake_coordinate)
    monkeypatch.setattr("app.agents.coordinator.fan_out", _boom_fanout)
    out = _run(office_hq.run_agent_task("isha", "poori team se campaign", "team"))
    assert out["ok"] is True
    assert captured["execute"] is False  # DRAFT-SAFE — no side effects
    assert out["run_id"] == "abc123"
    assert out["summary"] == "team plan ready"


def test_goal_over_500_chars_capped(monkeypatch):
    captured = {}

    async def _fake_fanout(goal, agents=None, max_agents=4):
        captured["goal"] = goal
        return {"ok": True, "summary": "ok"}

    monkeypatch.setattr("app.agents.coordinator.fan_out", _fake_fanout)
    out = _run(office_hq.run_agent_task("isha", "x" * 900, "solo"))
    assert out["ok"] is True
    assert len(captured["goal"]) == 500  # capped, not rejected


def test_coordinator_raises_yields_ok_false(monkeypatch):
    """Never-raise: coordinator blowing up -> {ok:False}, function returns."""

    async def _boom(*a, **k):
        raise RuntimeError("LLM chain down")

    monkeypatch.setattr("app.agents.coordinator.fan_out", _boom)
    out = _run(office_hq.run_agent_task("isha", "kuch karo", "solo"))
    assert out["ok"] is False
    assert "LLM chain down" in out["error"]


def test_timeout_yields_honest_background_note(monkeypatch):
    """Budget exceeded -> ok:True + status:timeout + honest note (not fabricated)."""

    async def _slow(*a, **k):
        await asyncio.sleep(999)

    monkeypatch.setattr("app.agents.coordinator.fan_out", _slow)
    monkeypatch.setattr(office_hq, "_TASK_TIMEOUT", 0.05)
    out = _run(office_hq.run_agent_task("isha", "lamba kaam", "solo"))
    assert out["ok"] is True
    assert out["status"] == "timeout"
    assert "events" in out["note"].lower() or "ticker" in out["note"].lower()


def test_coordinator_ok_false_propagates(monkeypatch):
    """Primitive returning ok:False (e.g. goal too short) surfaces honestly."""

    async def _fake_fanout(goal, agents=None, max_agents=4):
        return {"ok": False, "error": "goal bahut chhota hai"}

    monkeypatch.setattr("app.agents.coordinator.fan_out", _fake_fanout)
    out = _run(office_hq.run_agent_task("isha", "abc", "solo"))
    assert out["ok"] is False
    assert "chhota" in out["error"]
