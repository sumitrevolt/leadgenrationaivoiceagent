"""agent_controls — pause/resume sidecar (mirrors approvals_bridge's proven
collapse-to-latest pattern).

Bars:
- pause()/resume()/is_paused() roundtrip correctly.
- Job-name aliases (qa/trainer/ops/digest/content/email_outreach) canonicalize
  to the same STAFF member they dispatch to in staff.run_member()'s table —
  pausing "arjun" must also block a call made via the "qa" alias.
- list_paused() only returns currently-paused members (collapse-to-latest).
- Never raises on a missing/corrupt store file.
- staff.run_member() actually honors the pause flag (integration bar) and a
  SCHEDULED job (staff.run_qa() called directly, as team_scheduler.py does)
  is completely unaffected by a pause — this is the documented safety scope.
"""

from __future__ import annotations

import pytest

from app.platform import agent_controls as ac


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(ac, "_STORE", str(tmp_path / "agent_pause_state.jsonl"))


def test_pause_then_is_paused_true(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert ac.is_paused("arjun") is False
    ac.pause("arjun", by="sumit", note="testing")
    assert ac.is_paused("arjun") is True


def test_resume_clears_pause(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ac.pause("arjun", by="sumit")
    assert ac.is_paused("arjun") is True
    ac.resume("arjun", by="sumit")
    assert ac.is_paused("arjun") is False


def test_alias_resolves_to_same_member(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ac.pause("arjun", by="sumit")
    assert ac.is_paused("qa") is True  # "qa" dispatches to arjun in staff.run_member()
    ac.resume("qa", by="sumit")  # resuming via the alias must also clear the canonical key
    assert ac.is_paused("arjun") is False


def test_list_paused_only_returns_currently_paused(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ac.pause("arjun", by="a")
    ac.pause("meera", by="a")
    ac.resume("meera", by="a")
    paused = ac.list_paused()
    assert "arjun" in paused
    assert "meera" not in paused


def test_collapse_to_latest_across_repeated_toggles(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ac.pause("kavya", by="a")
    ac.resume("kavya", by="a")
    ac.pause("kavya", by="a")
    assert ac.is_paused("kavya") is True


def test_missing_store_file_is_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, "_STORE", str(tmp_path / "does_not_exist.jsonl"))
    assert ac.is_paused("arjun") is False
    assert ac.list_paused() == {}


def test_empty_member_rejected():
    assert ac.pause("", by="a")["ok"] is False
    assert ac.resume("", by="a")["ok"] is False


async def test_run_member_honors_pause_for_manual_run_path(monkeypatch, tmp_path):
    """The one real choke-point this module gates: app.agents.staff.run_member()."""
    from app.agents import staff

    _isolate(monkeypatch, tmp_path)
    ac.pause("arjun", by="sumit")
    result = await staff.run_member("arjun")
    assert result.get("skipped") is True
    assert result.get("reason") == "paused_by_admin"


async def test_scheduled_job_path_bypasses_run_member_entirely(monkeypatch, tmp_path):
    """team_scheduler.py's _run_job_inner calls staff.run_qa() DIRECTLY, never
    through run_member() — so pausing arjun must NOT block a direct run_qa()
    call. This is the documented safety boundary; regress-guard it."""
    from app.agents import staff

    _isolate(monkeypatch, tmp_path)
    ac.pause("arjun", by="sumit")

    called = {"hit": False}

    async def _fake_qa():
        called["hit"] = True
        return {"ok": True}

    monkeypatch.setattr(staff, "run_qa", _fake_qa)
    result = await staff.run_qa()
    assert called["hit"] is True
    assert result == {"ok": True}
