"""Agent-task lease reclaim (2026-07-31).

`agent_task_queue.stale_tasks()` deliberately only SURFACES stuck work, so a worker that
dies between `claim_next()` and `complete()`/`fail()` strands its lease forever and the task
can never be picked up again. `reap_stale_leases()` is the bounded reclaim path.

These tests drive a REAL in-memory sqlite session (not a mock) so the optimistic-lock
UPDATE and the status/`checkout_version` filters are actually exercised.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.agent_task import AgentTask
from app.models.base import Base
from app.platform import agent_task_queue as atq


@pytest.fixture()
def seed(monkeypatch):
    """Real sqlite-memory session patched in place of `get_db_session`.

    Returns a `(add, rows)` pair: `add(**overrides)` inserts one AgentTask, `rows()`
    re-reads every row so a test can assert on what the reaper actually committed.
    """
    engine = create_engine("sqlite://")
    AgentTask.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)

    @contextlib.contextmanager
    def _session():
        db = Session()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    monkeypatch.setattr("app.models.base.get_db_session", _session)

    counter = {"n": 0}

    def add(*, minutes_ago: int = 90, status: str = "claimed", version: int = 1, **kw):
        counter["n"] += 1
        tid = f"t{counter['n']}"
        with _session() as db:
            db.add(
                AgentTask(
                    id=tid,
                    agent_id=kw.get("agent_id", "rohan"),
                    status=status,
                    goal=kw.get("goal", "follow up hot leads"),
                    # claim_next() writes an aware UTC `claimed_at`; mirror that exactly so
                    # the cutoff comparison here matches production, not a naive variant.
                    claimed_at=atq._now() - timedelta(minutes=minutes_ago),
                    checkout_version=version,
                )
            )
        return tid

    def rows():
        # Snapshot to plain dicts INSIDE the session — ORM instances detach on close.
        with _session() as db:
            return {
                r.id: {
                    "status": r.status,
                    "claimed_at": r.claimed_at,
                    "completed_at": r.completed_at,
                    "result_summary": r.result_summary,
                    "checkout_version": r.checkout_version,
                }
                for r in db.query(AgentTask).all()
            }

    # Base is imported so the model's metadata is registered; assert it to keep linters
    # and future refactors honest about the dependency.
    assert AgentTask.__table__ in Base.metadata.tables.values()
    return add, rows


@pytest.mark.asyncio
async def test_dry_run_reports_but_mutates_nothing(seed):
    add, rows = seed
    tid = add(version=1)

    out = await atq.reap_stale_leases()  # dry_run=True is the DEFAULT

    assert out["dry_run"] is True
    assert out["scanned"] == 1 and out["failed"] == 1
    assert rows()[tid]["status"] == "claimed"  # untouched
    assert rows()[tid]["claimed_at"] is not None


@pytest.mark.asyncio
async def test_expired_lease_is_closed_terminally_not_requeued(seed):
    """NOT a requeue — see the reap docstring. `pending` would allow a double-run."""
    add, rows = seed
    tid = add(version=1, status="running")

    out = await atq.reap_stale_leases(dry_run=False)

    assert out["failed"] == 1
    row = rows()[tid]
    assert row["status"] == "failed"
    assert row["status"] != "pending"  # explicitly NOT reclaimable by another agent
    assert "lease_expired_after_1_attempts" in (row["result_summary"] or "")
    assert row["completed_at"] is not None


@pytest.mark.asyncio
async def test_a_reaped_task_cannot_be_reclaimed_or_overwritten(seed):
    """The safety property terminal-fail buys us.

    `complete()`/`fail()` match on id+status only — NEITHER guards on `checkout_version`.
    So if the reap had requeued to `pending`, a second agent could claim the same row while
    the original slow-but-alive worker was still running, and that worker's late
    `complete()` would silently overwrite the second run. These leases wrap real
    side-effecting work, so that is a customer-visible double-execution, not a nit.
    """
    add, rows = seed
    tid = add(version=1, status="running")
    await atq.reap_stale_leases(dry_run=False)

    # (a) no other agent can pick it up — the queue no longer offers it
    assert await atq.claim_next("rohan") is None

    # (b) the original worker's late completion cannot resurrect or overwrite it
    late = await atq.complete(tid, result="finished after the reap")
    assert late["ok"] is False

    row = rows()[tid]
    assert row["status"] == "failed"
    assert "lease_expired" in (row["result_summary"] or "")  # reap's reason survives


@pytest.mark.asyncio
async def test_leaves_fresh_and_finished_tasks_alone(seed):
    add, rows = seed
    fresh = add(minutes_ago=1)  # inside the threshold
    done = add(minutes_ago=999, status="done")
    pending = add(minutes_ago=999, status="pending")

    out = await atq.reap_stale_leases(threshold_minutes=30, dry_run=False)

    assert out["scanned"] == 0
    after = rows()
    assert after[fresh]["status"] == "claimed"
    assert after[done]["status"] == "done"
    assert after[pending]["status"] == "pending"


@pytest.mark.asyncio
async def test_limit_bounds_the_scan(seed):
    add, _rows = seed
    for _ in range(5):
        add()

    out = await atq.reap_stale_leases(limit=2, dry_run=False)

    assert out["scanned"] == 2


@pytest.mark.asyncio
async def test_never_raises_when_the_db_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.models.base.get_db_session",
        lambda: (_ for _ in ()).throw(Exception("no DB")),
    )

    out = await atq.reap_stale_leases(dry_run=False)

    assert out["failed"] == 0
    assert "error" in out


def test_job_is_registered_in_every_registry():
    """A scheduled job must land in SIX registries here, not one.

    Review of this PR caught it missing from `JOB_META`, and comparing against
    `sales_autopilot`/`social_drain` then caught it missing from `STAFF_JOBS` and the Celery
    beat schedule too. That second gap is the serious one: production runs
    `celery -A app.worker beat` with `RUN_IN_PROCESS_SCHEDULER=0`, so a job wired ONLY into
    `team_scheduler.scheduler_loop` never fires in prod — exactly the fault `call_kpi_digest`
    hit (audit 2026-07-04). This test exists so the next person cannot repeat it.

    `JOB_INFO` is asserted here too. It is *also* covered transitively by
    `test_today_overview.py::test_job_info_covers_every_scheduled_job`, but a reader of this
    test should not have to know that to trust the name on the tin.
    """
    from app.platform import automation_health, scheduler_config, team_scheduler, today_overview
    from app.tasks.staff_jobs import STAFF_JOBS
    from app.worker import celery_app

    assert "task_lease_reap" in STAFF_JOBS
    assert "task_lease_reap" in scheduler_config.JOB_META
    assert "task_lease_reap" in team_scheduler._last_ran
    assert "task_lease_reap" in automation_health.EXPECTED_GAP_MIN
    assert "task_lease_reap" in today_overview.JOB_INFO
    # Light, idempotent (optimistic-lock update → a re-reap of the same row is a no-op), and
    # sends nothing → recovery SHOULD be allowed to catch it up.
    assert "task_lease_reap" not in scheduler_config.RUN_DUE_EXCLUDE

    beat = celery_app.conf.beat_schedule
    assert "staff-task-lease-reap-hourly" in beat
    # A bare ("task_lease_reap") would be a plain string, not a 1-tuple, and would pass the
    # wrong args to run_staff_job. Assert the tuple, not just presence.
    assert beat["staff-task-lease-reap-hourly"]["args"] == ("task_lease_reap",)


def test_flag_is_inert_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_TASK_LEASE_REAP", raising=False)
    assert atq.lease_reap_enabled() is False

    monkeypatch.setenv("AGENT_TASK_LEASE_REAP", "0")
    assert atq.lease_reap_enabled() is False

    for on in ("1", "true", "YES", "on"):
        monkeypatch.setenv("AGENT_TASK_LEASE_REAP", on)
        assert atq.lease_reap_enabled() is True
