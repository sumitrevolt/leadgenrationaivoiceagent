"""Gate-off must never read as "work done" (Day-0 audit 2026-09-14, item B).

A staff job whose master flag is OFF still RUNS: the beat fires, the body
no-ops and returns, and ``team_scheduler._run_job_direct`` recorded a plain
``ok=True`` heartbeat. So "gate off" and "job ran fine" produced the SAME
record, and ``health()`` reported ``ok`` for a job that had done nothing.

Fix: the wrapper consults the job's OWN gate accessor (``gated_inert``) and
records an explicit ``status="gated_inert"`` with ``ok=False``. ``health()``
surfaces that explicit status ahead of the ok-derived one, and ``run_history``
keeps the marker out of its ``failed`` view — so the false green is not traded
for a false red.

Also covers item C: the render-plane lease maintenance had TWO beat entries
running identical work every 5 minutes.
"""

from __future__ import annotations

import asyncio
import json

import pytest


@pytest.fixture()
def ah(tmp_path, monkeypatch):
    """automation_health with isolated jsonl + snapshot paths (no real data/ writes)."""
    from app.platform import automation_health as _ah

    monkeypatch.setattr(_ah, "_RUNS", lambda: str(tmp_path / "job_runs.jsonl"))
    monkeypatch.setattr(_ah, "_BEATS", lambda: str(tmp_path / "job_heartbeats.json"))
    return _ah


def _health_hermetic(ah, monkeypatch) -> dict:
    """health() reaches for Redis (queue_depth) and the beat registry — stub both
    so the classification can be asserted without any external service."""
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0})
    monkeypatch.setattr(ah, "wiring_gaps", lambda: [])
    return ah.health()


def _job_row(health_out: dict, name: str) -> dict:
    return next(j for j in health_out["jobs"] if j["job"] == name)


# ---------------------------------------------------------------------------
# record_run — the additive `status` field
# ---------------------------------------------------------------------------


def test_record_run_status_round_trips_to_jsonl_and_snapshot(ah):
    ah.record_run("gsc_rank", False, 0.1, status="gated_inert")
    rec = json.loads(open(ah._RUNS(), encoding="utf-8").read().splitlines()[-1])
    assert rec["ok"] is False and rec["status"] == "gated_inert"
    # latest-per-job snapshot carries it too (health() reads the snapshot)
    beats = json.load(open(ah._BEATS(), encoding="utf-8"))
    assert beats["gsc_rank"]["status"] == "gated_inert"


def test_record_run_without_status_stays_old_shape(ah):
    """Old callers must not gain a `status` key (records stay readable)."""
    ah.record_run("growth", True, 1.0)
    rec = json.loads(open(ah._RUNS(), encoding="utf-8").read().splitlines()[-1])
    assert "status" not in rec


# ---------------------------------------------------------------------------
# health() — the explicit marker wins over the ok-derived status
# ---------------------------------------------------------------------------


def test_health_reports_gated_inert_not_ok(ah, monkeypatch):
    """The whole point: a gated-off run must not surface as `ok`."""
    ah.record_run("gsc_rank", False, 0.1, status="gated_inert")
    h = _health_hermetic(ah, monkeypatch)
    row = _job_row(h, "gsc_rank")
    assert row["status"] == "gated_inert"
    # ...and NOT as a failure either (it ran on schedule; the gate is off by design)
    assert row["status"] != "last_failed"
    assert "gsc_rank" not in h["overdue"]


def test_health_without_marker_still_uses_ok(ah, monkeypatch):
    """Regression guard: the new branch must not swallow normal classification."""
    ah.record_run("gsc_rank", True, 0.1)
    h = _health_hermetic(ah, monkeypatch)
    assert _job_row(h, "gsc_rank")["status"] == "ok"


# ---------------------------------------------------------------------------
# _run_job_direct — the choke point that records the marker
# ---------------------------------------------------------------------------


def _capture(monkeypatch, inner, gated: bool):
    """Run one `_run_job` tick with record_run captured; return the records."""
    from app.platform import automation_health, scheduler_config, team_scheduler

    records: list[dict] = []

    def _fake_record(job, ok=True, seconds=0.0, note="", **kw):
        records.append({"job": job, "ok": ok, "note": note, **kw})

    async def _inner(job):
        return inner

    monkeypatch.setattr(scheduler_config, "is_enabled", lambda job: True)
    monkeypatch.setattr(team_scheduler, "_run_job_inner", _inner)
    monkeypatch.setattr(automation_health, "record_run", _fake_record)
    monkeypatch.setattr(automation_health, "gated_inert", lambda job: gated)
    # Keep the tick off the DB/agent-task ledger (not under test here).
    from app.platform import agent_task_queue

    monkeypatch.setattr(agent_task_queue, "routine_ledger_enabled", lambda: False)
    return records


def test_gate_off_records_gated_inert_not_success(monkeypatch):
    """The defect: gate OFF + body no-op used to record ok=True."""
    from app.platform import team_scheduler

    records = _capture(monkeypatch, True, gated=True)
    asyncio.run(team_scheduler._run_job("gsc_rank"))

    last = records[-1]
    assert last["status"] == "gated_inert"
    assert last["ok"] is False, "a gated-off run must not record success"


def test_gate_on_records_plain_success(monkeypatch):
    from app.platform import team_scheduler

    records = _capture(monkeypatch, True, gated=False)
    asyncio.run(team_scheduler._run_job("gsc_rank"))

    last = records[-1]
    assert last["ok"] is True
    assert last.get("status", "") == ""


def test_failed_job_is_not_relabelled_gated(monkeypatch):
    """A real failure must stay a failure — the gate check only runs on success."""
    from app.platform import team_scheduler

    records = _capture(monkeypatch, False, gated=False)
    asyncio.run(team_scheduler._run_job("gsc_rank"))

    last = records[-1]
    assert last["ok"] is False
    assert last.get("status", "") == ""
    assert last["error_class"] == "job_reported_failure"


# ---------------------------------------------------------------------------
# gated_inert — registry hygiene + fail-open
# ---------------------------------------------------------------------------


def test_registry_accessors_resolve():
    """Pins the registry: every entry must be a real, callable accessor, and the
    job must be one health() actually tracks (a typo would silently disable the
    guard for that job)."""
    import importlib

    from app.platform import automation_health as ah

    for job, (mod_name, attr) in ah._GATED_JOB_ACCESSORS.items():
        assert job in ah.EXPECTED_GAP_MIN, f"{job} not tracked by health()"
        fn = getattr(importlib.import_module(mod_name), attr)
        assert callable(fn), f"{mod_name}.{attr} not callable"
        assert isinstance(fn(), bool)


def test_gated_inert_true_when_accessor_false(monkeypatch):
    from app.platform import automation_health as ah

    # Point the registry at a real, patchable accessor and drive its verdict.
    monkeypatch.setattr(
        ah, "_GATED_JOB_ACCESSORS", {"j": ("app.platform.automation_health", "_env_on")}
    )
    monkeypatch.setattr(ah, "_env_on", lambda *a, **k: False)
    assert ah.gated_inert("j") is True
    monkeypatch.setattr(ah, "_env_on", lambda *a, **k: True)
    assert ah.gated_inert("j") is False


def test_gated_inert_fails_open(monkeypatch):
    """A broken accessor must NEVER label a job inert (that would mask real runs)."""
    from app.platform import automation_health as ah

    monkeypatch.setattr(ah, "_GATED_JOB_ACCESSORS", {"j": ("app.does.not.exist", "enabled")})
    assert ah.gated_inert("j") is False
    monkeypatch.setattr(ah, "_GATED_JOB_ACCESSORS", {"j": ("app.utils.logger", "nope_attr")})
    assert ah.gated_inert("j") is False
    assert ah.gated_inert("job_not_in_registry") is False


# ---------------------------------------------------------------------------
# run_history — the marker must not become a new false RED
# ---------------------------------------------------------------------------


def test_run_history_keeps_gated_inert_out_of_failed(ah):
    ah.record_run("gsc_rank", False, 0.1, status="gated_inert")
    ah.record_run("content", False, 0.1, error_class="ValueError")
    ah.record_run("blog", True, 0.1)

    failed = ah.run_history(status="failed")
    assert [r["job"] for r in failed] == ["content"], "inert is not a failure"
    ok_only = ah.run_history(status="ok")
    assert [r["job"] for r in ok_only] == ["blog"], "inert is not a success"


def test_run_history_failures_first_orders_inert_last(ah):
    ah.record_run("content", False, 0.1, error_class="ValueError")
    ah.record_run("gsc_rank", False, 0.1, status="gated_inert")

    runs = ah.run_history(failures_first=True)
    assert runs[0]["job"] == "content", "the real failure must lead"


# ---------------------------------------------------------------------------
# Item C — one render-plane lease maintenance, not two
# ---------------------------------------------------------------------------


def test_render_plane_lease_has_exactly_one_beat_entry():
    """`render_plane.lease_maintenance` duplicated `staff-render-plane-lease-5m`:
    both hit `_render_plane_lease_async(max_retries=3, limit=200, enqueue=True)`
    every 5 minutes (288 redundant sweeps/day). The direct-task entry was added
    AFTER the ENABLE_LEGACY_BEAT strip, so it really did fire in production."""
    from app.worker import celery_app

    beat = celery_app.conf.beat_schedule or {}
    assert "render_plane.lease_maintenance" not in beat

    def _reaches_lease_maintenance(entry: dict) -> bool:
        if entry.get("task") == "app.tasks.video_jobs.render_plane_lease_task":
            return True
        args = entry.get("args") or ()
        return entry.get("task") == "app.tasks.staff_jobs.run_staff_job" and args == (
            "render_plane_lease",
        )

    entries = [k for k, v in beat.items() if _reaches_lease_maintenance(v)]
    assert entries == ["staff-render-plane-lease-5m"], entries
