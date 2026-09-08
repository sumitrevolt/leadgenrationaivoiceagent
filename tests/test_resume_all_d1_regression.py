"""D1 regression: board_governance.resume_all() must clear alias-keyed pause
records too and report honest still_paused/ok (guardian FAIL verdict 2026-08-25).

Run with a temp CWD so data/agent_pause_state.jsonl writes stay sandboxed
(agent_controls uses relative data/ paths).
"""

import json
import os

import pytest


@pytest.fixture()
def controls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.platform import agent_controls

    agent_controls._STORE = str(tmp_path / "data" / "agent_pause_state.jsonl")
    return agent_controls


def test_resume_all_clears_alias_keyed_pauses(controls, tmp_path):
    from app.platform import board_governance

    # Simulate an emergency stop that wrote records under ALIAS keys,
    # exactly the shape the guardian E2E run produced.
    for key in ["qa", "trainer", "ops", "digest", "content"]:
        controls.pause(key, by="e2e", note="EMERGENCY STOP")
    assert controls.list_paused(), "precondition: paused set non-empty"

    out = board_governance.resume_all(by="test")

    assert out["ok"] is True, f"resume_all not ok: {out}"
    assert out["still_paused"] == [], f"agents left paused: {out['still_paused']}"
    assert controls.list_paused() == {}


def test_resume_all_reports_false_when_pause_persists(controls, monkeypatch):
    from app.platform import board_governance

    controls.pause("arjun", by="e2e", note="stop")
    # Sabotage resume writes so the record cannot clear.
    monkeypatch.setattr(controls, "_append", lambda rec: None)
    # resume() also logs to team — stub it out.
    class _FakeTeam:
        @staticmethod
        def log_event(*a, **k):
            pass

    import sys

    fake_team = type(sys)("fake_team_mod")
    fake_team.STAFF = {"arjun": {}}
    monkeypatch.setitem(sys.modules, "app.platform.team", fake_team)

    out = board_governance.resume_all(by="test")
    assert out["ok"] is False or out["still_paused"], (
        "must NOT report ok=True while agents remain paused"
    )


def test_resume_all_on_clean_board_is_ok(controls):
    from app.platform import board_governance

    out = board_governance.resume_all(by="test")
    assert out["ok"] is True
    assert out["still_paused"] == []
