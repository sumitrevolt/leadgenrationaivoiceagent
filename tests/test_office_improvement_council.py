"""F6 "Team Improvement Council" — office HQ snapshot-grounded AgentVerse discussion.

Bars:
- POST /api/platform/office/improve is admin-gated.
- improvement_council() always calls coordinator.coordinate_agentverse with
  execute=False (draft-safe — a discussion, not an action run).
- Empty topic falls back to the default project-improvement question.
- Contributions carry {staff, staff_name, dispatchable} so the admin can
  1-click dispatch through the EXISTING run_agent_task() path.
- Timeout/failure paths degrade honestly (never-raise).
"""

from __future__ import annotations

import asyncio

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


def test_improve_endpoint_requires_admin():
    saved_admin = app.dependency_overrides.pop(require_admin, None)
    saved_user = app.dependency_overrides.pop(get_current_user, None)
    try:
        r = client.post("/api/platform/office/improve", json={"topic": "kya improve karein?"})
        assert r.status_code in (401, 403)
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user


def test_improve_endpoint_happy_path(monkeypatch):
    async def _fake_agentverse(goal, execute=False, max_rounds=1, quality_bar=0.75, team_size=3):
        return {
            "ok": True,
            "run_id": "abc",
            "final_score": 0.8,
            "experts": [{"role": "Growth Lead", "expertise": "revenue", "staff": "rohan"}],
            "contributions": [
                {
                    "role": "Growth Lead",
                    "staff": "rohan",
                    "output": "Follow-up cadence tighten karo",
                }
            ],
            "solution": "Follow-up cadence tighten karo",
            "summary": "Rohan follow-up cadence pe focus kare",
        }

    monkeypatch.setattr("app.agents.coordinator.coordinate_agentverse", _fake_agentverse)
    r = client.post("/api/platform/office/improve", json={"topic": "revenue kaise badhaye?"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["contributions"][0]["staff_name"]  # resolved from STAFF
    assert d["contributions"][0]["dispatchable"] is True


def test_default_topic_used_when_empty(monkeypatch):
    captured = {}

    async def _fake_agentverse(goal, execute=False, max_rounds=1, quality_bar=0.75, team_size=3):
        captured["goal"] = goal
        captured["execute"] = execute
        return {"ok": True, "experts": [], "contributions": [], "solution": "", "summary": ""}

    monkeypatch.setattr("app.agents.coordinator.coordinate_agentverse", _fake_agentverse)
    out = _run(office_hq.improvement_council("", 4, 1))
    assert out["ok"] is True
    assert out["topic"] == office_hq._DEFAULT_COUNCIL_TOPIC
    assert captured["execute"] is False  # always draft-safe
    assert office_hq._DEFAULT_COUNCIL_TOPIC in captured["goal"]


def test_unknown_staff_contribution_not_dispatchable(monkeypatch):
    async def _fake_agentverse(goal, execute=False, max_rounds=1, quality_bar=0.75, team_size=3):
        return {
            "ok": True,
            "experts": [],
            "contributions": [
                {"role": "Freelance Consultant", "staff": "", "output": "generic idea"}
            ],
            "solution": "",
            "summary": "",
        }

    monkeypatch.setattr("app.agents.coordinator.coordinate_agentverse", _fake_agentverse)
    out = _run(office_hq.improvement_council("kuch bhi", 2, 1))
    assert out["contributions"][0]["dispatchable"] is False
    assert out["contributions"][0]["staff_name"] == ""


def test_coordinator_raises_yields_ok_false(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("LLM chain down")

    monkeypatch.setattr("app.agents.coordinator.coordinate_agentverse", _boom)
    out = _run(office_hq.improvement_council("topic", 3, 1))
    assert out["ok"] is False
    assert "LLM chain down" in out["error"]


def test_timeout_yields_honest_note(monkeypatch):
    async def _slow(*a, **k):
        await asyncio.sleep(999)

    monkeypatch.setattr("app.agents.coordinator.coordinate_agentverse", _slow)
    monkeypatch.setattr(office_hq, "_COUNCIL_TIMEOUT", 0.05)
    out = _run(office_hq.improvement_council("topic", 2, 1))
    assert out["ok"] is True
    assert out["status"] == "timeout"


def test_coordinator_ok_false_propagates(monkeypatch):
    async def _fake_agentverse(goal, execute=False, max_rounds=1, quality_bar=0.75, team_size=3):
        return {"ok": False, "error": "goal bahut chhota hai"}

    monkeypatch.setattr("app.agents.coordinator.coordinate_agentverse", _fake_agentverse)
    out = _run(office_hq.improvement_council("x", 2, 1))
    assert out["ok"] is False
    assert "chhota" in out["error"]


def test_team_size_and_rounds_are_clamped(monkeypatch):
    captured = {}

    async def _fake_agentverse(goal, execute=False, max_rounds=1, quality_bar=0.75, team_size=3):
        captured["max_rounds"] = max_rounds
        captured["team_size"] = team_size
        return {"ok": True, "experts": [], "contributions": [], "solution": "", "summary": ""}

    monkeypatch.setattr("app.agents.coordinator.coordinate_agentverse", _fake_agentverse)
    _run(office_hq.improvement_council("x", team_size=99, max_rounds=99))
    assert captured["team_size"] == 4  # clamped to max 4
    assert captured["max_rounds"] == 2  # clamped to max 2
