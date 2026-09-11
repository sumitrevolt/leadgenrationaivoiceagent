"""T03 video-job wiring contract — the 4 delivery/lifecycle/health jobs must be
reachable from EVERY scheduler surface.

WHY: T03 (2026-09-11) registered ``video_delivery``, ``video_delivery_retry``,
``video_health`` and ``video_lifecycle_reconcile`` in
``scheduler_config.JOB_META`` but gave them NO dispatch path — they were absent
from ``STAFF_JOBS`` (so ``run_staff_job`` rejected them as ``"unknown job"``),
had no ``team_scheduler._run_job_inner`` branch, and had no Celery beat entry.
Production runs ``celery -A app.worker beat`` with ``RUN_IN_PROCESS_SCHEDULER=0``,
so a job wired only into an in-process surface never fires — the exact fault
``call_kpi_digest`` hit (audit 2026-07-04). This test pins all SIX registries so
the gap cannot reopen.

Run::

    python -m unittest tests.test_video_jobs_wiring

Env note: the test is self-contained. If ``celery`` is not importable it installs
a minimal stub so the REAL ``app.worker`` / ``app.tasks.staff_jobs`` modules load
and their registries can be inspected. In a full environment the real celery is
used and no stub is installed.
"""

from __future__ import annotations

import sys
import types
import unittest


def _ensure_celery() -> None:
    """Install a minimal celery stub ONLY when celery is genuinely missing."""
    try:
        import celery  # noqa: F401
        import celery.exceptions  # noqa: F401
        import celery.schedules  # noqa: F401

        return
    except Exception:  # noqa: BLE001
        pass

    cel = types.ModuleType("celery")

    class _Conf:
        def __init__(self) -> None:
            object.__setattr__(self, "_d", {})

        def update(self, *a, **k):
            self._d.update(dict(*a, **k))

        def __getattr__(self, k):
            return self._d.get(k)

        def __setattr__(self, k, v):
            self._d[k] = v

    class _Celery:
        def __init__(self, *a, **k):
            self.conf = _Conf()
            self.tasks: dict = {}
            self.conf.include = list(k.get("include") or [])

        def task(self, *a, **k):
            def deco(fn):
                self.tasks[getattr(fn, "__name__", "t")] = fn
                return fn

            return deco

        def __getattr__(self, k):
            raise AttributeError(k)

    class _Task:
        abstract = True

    def _shared_task(*a, **k):
        def deco(fn):
            return fn

        return deco

    def _identity_connect(*a, **k):
        def deco(fn):
            return fn

        return deco

    cel.Celery = _Celery
    cel.Task = _Task
    cel.shared_task = _shared_task
    cel.signals = types.SimpleNamespace(
        **{
            n: types.SimpleNamespace(connect=_identity_connect)
            for n in (
                "worker_process_init",
                "worker_ready",
                "worker_shutting_down",
                "task_prerun",
                "task_postrun",
                "task_failure",
                "task_retry",
            )
        }
    )
    sys.modules.setdefault("celery", cel)

    sched = types.ModuleType("celery.schedules")
    sched.crontab = lambda *a, **k: ("crontab", a, k)
    sys.modules.setdefault("celery.schedules", sched)

    exc = types.ModuleType("celery.exceptions")

    class _SoftTimeLimitExceeded(Exception):
        pass

    class _CeleryError(Exception):
        pass

    exc.SoftTimeLimitExceeded = _SoftTimeLimitExceeded
    exc.CeleryError = _CeleryError
    sys.modules.setdefault("celery.exceptions", exc)


_ensure_celery()

import app.worker as worker  # noqa: E402
from app.platform import (  # noqa: E402
    automation_health,
    owner_agent_execution,
    scheduler_config,
    scheduler_parity,
    team_scheduler,
    today_overview,
)
from app.tasks import staff_jobs  # noqa: E402

# The four T03 jobs — the exact set JOB_META shipped without a dispatch path.
T03_JOBS = (
    "video_delivery",
    "video_delivery_retry",
    "video_health",
    "video_lifecycle_reconcile",
)

# Pre-existing (NOT T03) staff jobs that intentionally have no `_run_job_inner`
# body: `heartbeat` is a pure liveness tick (its only effect is the run-record
# heartbeat emitted by `_run_job_direct`); `content_approval_notify` is a
# beat-only entry that predates this change. Excluded here so this guard targets
# genuinely missing dispatch branches (the T03 bug class) without re-litigating
# pre-existing wiring.
_BRANCHLESS_STAFF_JOBS = frozenset({"heartbeat", "content_approval_notify"})


def _beat_jobs() -> set[str]:
    """Job ids dispatched by ``staff-*`` beat entries (``run_staff_job`` args[0])."""
    out: set[str] = set()
    for key, entry in (worker.celery_app.conf.beat_schedule or {}).items():
        if not str(key).startswith("staff-"):
            continue
        if str((entry or {}).get("task") or "") != "app.tasks.staff_jobs.run_staff_job":
            continue
        args = (entry or {}).get("args") or ()
        if args:
            out.add(str(args[0]))
    return out


class VideoJobsWiringTest(unittest.TestCase):
    """Six-registry reachability for the T03 video jobs."""

    def test_all_six_registries(self) -> None:
        beat = _beat_jobs()
        for job in T03_JOBS:
            self.assertIn(job, staff_jobs.STAFF_JOBS, f"{job} missing STAFF_JOBS")
            self.assertIn(job, scheduler_config.JOB_META, f"{job} missing JOB_META")
            self.assertIn(job, team_scheduler._last_ran, f"{job} missing _last_ran")
            self.assertIn(
                job, automation_health.EXPECTED_GAP_MIN, f"{job} missing EXPECTED_GAP_MIN"
            )
            self.assertIn(job, today_overview.JOB_INFO, f"{job} missing JOB_INFO")
            self.assertIn(job, beat, f"{job} missing Celery beat entry")

    def test_beat_entries_target_run_staff_job_with_tuple_args(self) -> None:
        """A bare string arg would pass the wrong thing to run_staff_job."""
        for job in T03_JOBS:
            hits = [
                (k, v)
                for k, v in (worker.celery_app.conf.beat_schedule or {}).items()
                if str(k).startswith("staff-")
                and (v or {}).get("task") == "app.tasks.staff_jobs.run_staff_job"
                and ((v or {}).get("args") or ()) == (job,)
            ]
            self.assertTrue(hits, f"{job} has no staff- beat entry with args=({job!r},)")

    def test_dead_man_grace_positive(self) -> None:
        for job in T03_JOBS:
            gap = automation_health.EXPECTED_GAP_MIN.get(job)
            self.assertIsNotNone(gap, job)
            self.assertGreater(gap, 0, job)

    def test_dispatch_branch_present(self) -> None:
        with open(team_scheduler.__file__, encoding="utf-8") as f:
            src = f.read()
        for job in T03_JOBS:
            self.assertIn(f'job == "{job}"', src, f"{job} has no _run_job_inner branch")

    def test_dispatch_branch_reachable_and_returns_true(self) -> None:
        """Each T03 job must dispatch and complete without raising.

        The bodies are gate-safe (delivery pair no-op when
        VIDEO_TELEGRAM_DELIVERY_ENABLED is off; health/reconcile are read-only),
        so every one must return ``True`` — not merely "not raise".
        """
        import asyncio

        for job in T03_JOBS:
            ok = asyncio.run(team_scheduler._run_job_inner(job))
            self.assertIs(ok, True, f"{job} dispatch did not succeed")

    def test_every_job_meta_job_is_dispatchable(self) -> None:
        """JOB_META ⊆ STAFF_JOBS — the T03 gap metric.

        A JOB_META job absent from STAFF_JOBS can NEVER be dispatched:
        ``run_staff_job`` rejects it as ``"unknown job"``. This count was **4**
        (the four T03 video jobs) before the fix and is **0** after.
        """
        undispatchable = sorted(set(scheduler_config.JOB_META) - set(staff_jobs.STAFF_JOBS))
        self.assertEqual(
            undispatchable, [], f"JOB_META jobs with no dispatch path: {undispatchable}"
        )

    def test_no_unexpected_branchless_job_meta_job(self) -> None:
        """Every JOB_META job must have a ``_run_job_inner`` branch, EXCEPT the
        pre-existing branchless liveness jobs below (their only job is the
        run-record heartbeat emitted by ``_run_job_direct``). This is the guard
        that would have caught the T03 gap."""
        with open(team_scheduler.__file__, encoding="utf-8") as f:
            src = f.read()
        missing = [
            j
            for j in scheduler_config.JOB_META
            if j not in _BRANCHLESS_STAFF_JOBS and f'job == "{j}"' not in src
        ]
        self.assertEqual(missing, [], f"JOB_META jobs with no dispatch branch: {missing}")

    def test_isha_owner_control_plane_aligned(self) -> None:
        """AGENT_JOBS[isha] must match JOB_META owner=isha (else pausing Isha
        leaves her video-delivery jobs running — a silent control-plane hole)."""
        isha = set(owner_agent_execution.AGENT_JOBS["isha"])
        meta_isha = {
            j
            for j, meta in scheduler_config.JOB_META.items()
            if str(meta.get("owner") or "") == "isha"
        }
        self.assertEqual(isha, meta_isha, f"AGENT_JOBS drift: {isha ^ meta_isha}")

    def test_registry_parity_clean(self) -> None:
        self.assertEqual(scheduler_parity.unexplained_diffs(), [])
        self.assertEqual(scheduler_parity.beat_task_targets_ok(), [])

    def test_flags_default_inert(self) -> None:
        """Delivery pair must be INERT unless VIDEO_TELEGRAM_DELIVERY_ENABLED=1."""
        import os

        os.environ.pop("VIDEO_TELEGRAM_DELIVERY_ENABLED", None)
        from app.marketing import video_delivery

        self.assertFalse(video_delivery.enabled())


if __name__ == "__main__":
    unittest.main()
