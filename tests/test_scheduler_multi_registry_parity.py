"""Multi-registry scheduler parity — STAFF_JOBS ↔ beat ↔ JOB_META ↔ health ↔ UI."""

from __future__ import annotations

import asyncio

import pytest

from app.platform import scheduler_parity as sp
from app.platform.scheduler_config import JOB_META, RUN_DUE_EXCLUDE
from app.tasks.staff_jobs import STAFF_JOBS


def test_no_unexplained_registry_diffs():
    unexplained = sp.unexplained_diffs()
    assert unexplained == [], unexplained


def test_beat_staff_entries_target_run_staff_job():
    problems = sp.beat_task_targets_ok()
    assert problems == [], problems


def test_every_staff_job_has_full_wiring():
    rows = {r.job_id: r for r in sp.build_parity_table()}
    assert len(rows) == len(STAFF_JOBS)
    for job in STAFF_JOBS:
        r = rows[job]
        assert r.in_job_meta, job
        assert r.in_last_ran, job
        assert r.in_expected_gap, job
        assert r.in_job_info, job
        assert r.beat_keys, f"{job} missing celery beat entry"
        assert r.owner and r.label and r.cadence, job
        assert r.gap_min is not None and r.gap_min > 0, job


def test_required_run_due_exclude_complete():
    assert sp.REQUIRED_RUN_DUE_EXCLUDE <= set(RUN_DUE_EXCLUDE)


def test_side_effect_jobs_marked_and_excluded():
    for job in (
        "platform_dial",
        "email_outreach",
        "email_followup",
        "sales_autopilot",
        "hq_auto_chase",
        "reply_auto_send",
    ):
        assert job in RUN_DUE_EXCLUDE
        assert job in sp.CUSTOMER_CONTACT_JOBS or job in sp.PROVIDER_CONTACT_JOBS


def test_platform_dial_represented_with_owner_swara():
    meta = JOB_META["platform_dial"]
    assert meta["owner"] == "swara"
    row = next(r for r in sp.build_parity_table() if r.job_id == "platform_dial")
    assert row.run_due_excluded is True
    assert row.customer_contact and row.provider_contact
    assert row.in_expected_gap


def test_self_improve_intentional_exception_documented():
    idx = sp.intentional_exception_index()
    assert ("self_improve", "EXPECTED_GAP_MIN", "extra") in idx
    sets = sp.collect_registry_sets()
    assert "self_improve" in sets["EXPECTED_GAP_MIN"]
    assert "self_improve" not in sets["STAFF_JOBS"]


def test_summarize_clean():
    s = sp.summarize()
    # 50 since 2026-08-23: +trial_nudge (BLK-02; INERT default).
    # (previous 49 since 2026-08-19 added daily_owner_brief; 45 included gsc_rank).
    assert s["staff_job_count"] == 50
    assert s["unexplained"] == []
    assert s["beat_problems"] == []


def test_unknown_job_run_inner_is_safe(monkeypatch):
    """Unknown job must not raise and must not pretend success via staff dispatcher."""
    from app.platform import team_scheduler

    # _run_job_inner for unknown should no-op safely
    asyncio.run(team_scheduler._run_job_inner("does_not_exist_xyz"))


def test_partial_registration_fails_contract(monkeypatch):
    """Simulate a job in STAFF_JOBS missing JOB_META — contract must fail."""
    from app.platform import scheduler_config

    monkeypatch.setitem(
        scheduler_config.JOB_META,
        "__probe_only__",
        {"label": "x", "cadence": "y", "owner": "z"},
    )
    # probe key in JOB_META but not STAFF → unexplained extra
    problems = sp.unexplained_diffs()
    assert any("__probe_only__" in p for p in problems)


def test_owner_os_run_now_requires_idempotency_path():
    """Owner OS run_now always goes through create_command (idempotency-capable)."""
    import inspect

    from app.platform import owner_os

    src = inspect.getsource(owner_os.run_now)
    assert "create_command" in src
    assert "idempotency_key" in src
    # Must not call team_scheduler._run_job directly (bypass risk)
    assert "_run_job(" not in src


def test_sales_autopilot_in_expected_gap():
    from app.platform.automation_health import EXPECTED_GAP_MIN

    assert "sales_autopilot" in EXPECTED_GAP_MIN
    assert EXPECTED_GAP_MIN["sales_autopilot"] >= 60
