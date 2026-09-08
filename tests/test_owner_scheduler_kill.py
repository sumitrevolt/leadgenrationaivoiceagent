"""owner_schedulers kill — real dispatch boundary (apply_async + _run_job)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app.platform.owner_os as owner_os
import app.platform.owner_os_store as store
import app.platform.scheduler_config as scheduler_config
from app.tasks import staff_jobs


def _patch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OWNER_OS_STORAGE", "jsonl")
    store.reset_storage_mode()
    monkeypatch.setattr(owner_os, "_CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(owner_os, "_KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(owner_os, "_AUDIT_STORE", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(store, "CMD_STORE", str(tmp_path / "cmds.jsonl"))
    monkeypatch.setattr(store, "KILL_STORE", str(tmp_path / "kills.jsonl"))
    monkeypatch.setattr(store, "AUDIT_STORE", str(tmp_path / "audit.jsonl"))


def test_dispatch_allowed_when_disengaged(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    ok, reason = owner_os.scheduler_dispatch_allowed()
    assert ok is True
    assert reason == ""


def test_dispatch_skipped_when_engaged(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    ok, reason = owner_os.scheduler_dispatch_allowed()
    assert ok is False
    assert reason == "owner_schedulers_kill_switch"
    skip = owner_os.record_scheduler_skip("ops", reason, source="unit")
    assert skip["skipped"] is True
    assert skip["reason"] == "owner_schedulers_kill_switch"
    audit = owner_os.recent_audit(20)
    assert any(a.get("action") == "scheduler_dispatch_skipped" for a in audit)


def test_apply_async_does_not_enqueue_when_engaged(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    enqueued = {"n": 0}

    def _parent_apply(self, args=None, kwargs=None, **options):
        enqueued["n"] += 1
        return MagicMock(id="real")

    monkeypatch.setattr(staff_jobs.Task, "apply_async", _parent_apply)
    result = staff_jobs.run_staff_job.apply_async(args=["ops"])
    assert enqueued["n"] == 0
    assert getattr(result, "id", None) == "owner-schedulers-skipped"
    payload = result.get()
    assert payload["skipped"] is True
    assert payload["reason"] == "owner_schedulers_kill_switch"


def test_manual_header_bypasses_guard(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    enqueued = {"n": 0}

    def _parent_apply(self, args=None, kwargs=None, **options):
        enqueued["n"] += 1
        return MagicMock(id="manual")

    monkeypatch.setattr(staff_jobs.Task, "apply_async", _parent_apply)
    result = staff_jobs.run_staff_job.apply_async(args=["ops"], headers={"owner_os_manual": True})
    assert enqueued["n"] == 1
    assert result.id == "manual"


def test_scheduler_config_dispatch_skipped(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    called = {"delay": 0}

    class _Fake:
        def delay(self, job):
            called["delay"] += 1

        def apply_async(self, *a, **k):
            called["delay"] += 1

    monkeypatch.setattr("app.tasks.staff_jobs.run_staff_job", _Fake())
    via = scheduler_config._dispatch("ops", manual=False)
    assert via == "skipped_owner_schedulers"
    assert called["delay"] == 0


def test_scheduler_config_run_now_manual_still_dispatches(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    called = {"n": 0}

    class _Fake:
        def apply_async(self, args=None, kwargs=None, **options):
            called["n"] += 1
            assert (options.get("headers") or {}).get("owner_os_manual") is True
            return MagicMock(id="m")

        def delay(self, job):
            called["n"] += 1

    monkeypatch.setattr("app.tasks.staff_jobs.run_staff_job", _Fake())
    out = scheduler_config.run_now("ops", by="admin")
    assert out["ok"] is True
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_run_job_skips_when_engaged(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    from app.platform import team_scheduler

    inner_called = {"n": 0}

    async def _inner(job):
        inner_called["n"] += 1
        return True

    monkeypatch.setattr(team_scheduler, "_run_job_inner", _inner)
    ok = await team_scheduler._run_job("ops")
    assert ok is True
    assert inner_called["n"] == 0


def test_resume_allows_future_dispatch(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    assert owner_os.scheduler_dispatch_allowed()[0] is False
    owner_os.set_kill_switch("owner_schedulers", False, by="test", reason="resume")
    assert owner_os.scheduler_dispatch_allowed()[0] is True


def test_calling_remains_hard_off_during_scheduler_test(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    owner_os.set_kill_switch("owner_schedulers", True, by="test", reason="unit")
    plan = owner_os.parse_intent("platform_dial calling enable karo")
    assert plan["intent"] == "enable_calling"
    assert plan["safe_to_execute"] is False
    refused = owner_os.set_kill_switch("platform_dial", False, by="test")
    assert refused.get("ok") is False
