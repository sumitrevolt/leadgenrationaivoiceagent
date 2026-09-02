"""Tests for the honest non-voice agent-health resolver
(app/platform/agent_status.py).

Uses the REAL canonical registry (23 non-voice contracts) with the live runtime
signals (team_status / automation_health / owner_os kill / env flags) monkeypatched,
so the honest-health computation is exercised deterministically without a DB or app.
"""

from __future__ import annotations

import pytest

from app.platform import agent_status as asx
from app.platform import automation_health, owner_os, team


def _wire(monkeypatch, members=None, overdue=None, killed=None):
    monkeypatch.setattr(team, "team_status", lambda: {"members": members or []})
    monkeypatch.setattr(automation_health, "health", lambda: {"overdue": overdue or []})
    monkeypatch.setattr(owner_os, "kill_engaged", lambda k: bool(killed and k in killed))


def test_fleet_health_excludes_voice(monkeypatch):
    _wire(monkeypatch)
    fh = asx.fleet_health()
    assert fh["scope"] == "non_voice"
    teams = {a["team"] for a in fh["agents"]}
    assert teams <= {"platform", "marketing"}
    assert "voice" not in teams
    assert fh["total"] == 23
    ids = {a["id"] for a in fh["agents"]}
    for v in ("swara", "ananya", "riya", "arjun", "meera", "lekha", "raksha", "tara"):
        assert v not in ids


def test_disabled_when_flag_off(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.delenv("SRE_AGENT", raising=False)
    h = asx.agent_health("pranav")  # gated by SRE_AGENT
    assert h["enabled"] is False
    assert h["health"] == "disabled"


def test_healthy_when_recent_activity(monkeypatch):
    _wire(
        monkeypatch,
        members=[
            {
                "key": "neha",
                "state": "working",
                "last_active_mins": 10,
                "today_actions": 3,
                "today_errors": 0,
            }
        ],
    )
    h = asx.agent_health("neha")  # core (ungated), periodic
    assert h["enabled"] is True
    assert h["health"] == "healthy"
    assert h["runtime_state"] == "working"


def test_stale_when_periodic_no_activity(monkeypatch):
    _wire(monkeypatch)  # neha absent from team feed
    h = asx.agent_health("neha")
    assert h["enabled"] is True
    assert h["health"] == "stale"


def test_idle_when_event_driven_no_work(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setenv("JOURNEY_ENGINE", "1")
    h = asx.agent_health("ira")  # event-driven (useful_work_gap None), now enabled
    assert h["enabled"] is True
    assert h["health"] == "idle"  # ready/subscribed, NOT offline/stale


def test_overdue_job_marks_stale(monkeypatch):
    _wire(
        monkeypatch,
        members=[{"key": "neha", "last_active_mins": 5, "today_actions": 1, "today_errors": 0}],
        overdue=["pipeline"],
    )
    h = asx.agent_health("neha")
    assert h["health"] == "stale"
    assert "pipeline" in h["overdue_jobs"]


def test_killed_when_kill_switch_engaged(monkeypatch):
    _wire(monkeypatch, killed={"owner_all_agents"})
    h = asx.agent_health("neha")
    assert h["health"] == "killed"
    assert h["killed_by"] == "owner_all_agents"


def test_failed_when_errors_dominate(monkeypatch):
    _wire(
        monkeypatch,
        members=[{"key": "neha", "last_active_mins": 5, "today_actions": 2, "today_errors": 3}],
    )
    h = asx.agent_health("neha")
    assert h["health"] == "failed"


def test_never_raises_on_signal_failure(monkeypatch):
    def _boom():
        raise RuntimeError("team feed down")

    monkeypatch.setattr(team, "team_status", _boom)
    monkeypatch.setattr(automation_health, "health", lambda: {})
    monkeypatch.setattr(owner_os, "kill_engaged", lambda k: False)
    fh = asx.fleet_health()
    assert fh["total"] == 23  # still computed from registry with empty signals


def test_counts_and_attention_shape(monkeypatch):
    _wire(monkeypatch)
    fh = asx.fleet_health()
    assert isinstance(fh["counts"], dict)
    assert isinstance(fh["needs_attention"], list)
    assert sum(fh["counts"].values()) == fh["total"]
    # runtime_state (process) is reported separately from health (useful-work)
    assert all("runtime_state" in a and "health" in a for a in fh["agents"])
