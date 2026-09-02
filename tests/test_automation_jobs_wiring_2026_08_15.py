"""New automation jobs wiring contracts — 2026-08-15 revenue automation batch.

Verifies the three new jobs (``hq_auto_chase``, ``reply_auto_send``,
``content_approval_sweep``) are registered in every scheduler surface a dead
in-process-only job previously slipped through: STAFF_JOBS, team_scheduler
dispatcher + windows, Celery beat, scheduler_config JOB_META, and the flag
registry. Also verifies content_approval_sweep stays dry-run by default.
"""

from __future__ import annotations

from app.platform import scheduler_config, team_scheduler
from app.tasks import staff_jobs

NEW_JOBS = ("hq_auto_chase", "reply_auto_send", "content_approval_sweep")


def test_new_jobs_registered_in_staff_jobs():
    for job in NEW_JOBS:
        assert job in staff_jobs.STAFF_JOBS, f"{job} missing from STAFF_JOBS"


def test_new_jobs_registered_in_scheduler_dispatcher():
    src = team_scheduler.__file__
    with open(src, encoding="utf-8") as f:
        text = f.read()
    for job in NEW_JOBS:
        assert f'job == "{job}"' in text, f"{job} dispatcher branch missing"


def test_new_jobs_registered_in_scheduler_last_ran_map():
    # team_scheduler._last_ran dict has an entry per job (the in-process guard)
    assert hasattr(team_scheduler, "_last_ran")
    for job in NEW_JOBS:
        assert job in team_scheduler._last_ran, f"{job} missing from _last_ran map"


def test_new_jobs_registered_in_scheduler_config():
    for job in NEW_JOBS:
        assert job in scheduler_config.JOB_META, f"{job} missing from JOB_META"


def test_new_jobs_registered_in_celery_beat():
    # Celery beat schedule keys are staff-<job>-<cadence>; job name is the args[0]
    beat_args = set()
    for key, entry in _beat_schedule().items():
        args = entry.get("args") or ()
        if args:
            beat_args.add(args[0])
    for job in NEW_JOBS:
        assert job in beat_args, f"{job} missing from Celery beat"


def test_content_approval_sweep_dry_run_default():
    """Sweep job must be dry-run by default — CONTENT_APPROVAL_SWEEP_LIVE actuates."""
    src = team_scheduler.__file__
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "CONTENT_APPROVAL_SWEEP_LIVE" in text
    assert "dry_run=not live" in text


def test_flags_registered():
    from app.api import automation_flags

    for flag in ("HQ_AUTO_CHASE", "CONTENT_APPROVAL_SWEEP"):
        assert flag in automation_flags.AUTOMATION_FLAGS, f"{flag} not in AUTOMATION_FLAGS"


def test_new_jobs_in_job_info_and_deadman():
    from app.platform.automation_health import EXPECTED_GAP_MIN
    from app.platform.today_overview import JOB_INFO

    for job in NEW_JOBS:
        assert job in JOB_INFO, f"{job} missing JOB_INFO Hinglish label"
        assert job in EXPECTED_GAP_MIN, f"{job} missing EXPECTED_GAP_MIN dead-man"


def _beat_schedule():
    """Import app.worker lazily (heavy app import) and read beat schedule."""
    import app.worker as worker_mod

    return worker_mod.celery_app.conf.beat_schedule
