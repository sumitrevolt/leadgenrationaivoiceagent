"""Atomic task claiming for the engineering control plane.

The API-layer claim (read -> validate -> write) had a lost-update race: two
workers could both read state=queued, both pass the transition check, and both
commit -- the second silently overwriting the first worker's lease. These
helpers replace that with a single conditional UPDATE whose rowcount proves
exactly one winner (works on Postgres and SQLite alike; no advisory locks
needed). tmux/worker memory is never the source of truth -- the DB row is.

Design rules (mirrors reconcile.py):
  * claim only from QUEUED -- expired in-flight leases are reclaimed by
    ``reconcile.reconcile_leases``, not stolen here.
  * heartbeat only extends a lease the caller actually owns.
  * ``claim_next`` scans a bounded candidate window in priority order and
    atomically claims the first winnable row (loser rows are simply skipped).
  * a task serving an exponential-backoff delay (``next_eligible_at`` set by
    reconcile) is NOT claimable until that timestamp passes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update

from app.dev_control.service import TaskState

DEFAULT_LEASE_SECONDS = 600
_HEARTBEAT_STATES = (TaskState.CLAIMED.value, TaskState.RUNNING.value)


def _backoff_predicate(now: datetime):
    """TRUE when a task is not currently serving an exponential-backoff delay.

    ``next_eligible_at`` is set by ``reconcile.reconcile_leases`` when an expired
    lease is requeued. NULL means "eligible immediately", so every task created
    before the column existed (and every never-retried task) stays claimable --
    the predicate is backwards compatible by construction.
    """
    from app.models.dev_task import DevTask

    return or_(DevTask.next_eligible_at.is_(None), DevTask.next_eligible_at <= now)


async def atomic_claim(
    db,
    task_id: str,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
    respect_backoff: bool = False,
) -> bool:
    """Claim one QUEUED task. Returns True only for the single winning worker.

    ``respect_backoff`` defaults to False so the explicit-by-id admin claim
    (``POST /dev-tasks/{id}/claim``) keeps its historical behaviour; the scanner
    ``claim_next`` opts in so a backed-off task cannot be picked up early. When
    enabled, the predicate rides on the SAME conditional UPDATE -- still a
    single statement, never a read-then-write.
    """
    from app.models.dev_task import DevTask

    now = now or datetime.utcnow()
    conditions = [DevTask.id == task_id, DevTask.state == TaskState.QUEUED.value]
    if respect_backoff:
        conditions.append(_backoff_predicate(now))
    result = await db.execute(
        update(DevTask)
        .where(*conditions)
        .values(
            state=TaskState.CLAIMED.value,
            lease_owner=worker,
            lease_until=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )
    await db.commit()
    return bool(result.rowcount or 0)


async def atomic_heartbeat(
    db,
    task_id: str,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Extend a lease the caller owns. Returns False on steal attempts."""
    from app.models.dev_task import DevTask

    now = now or datetime.utcnow()
    result = await db.execute(
        update(DevTask)
        .where(
            DevTask.id == task_id,
            DevTask.lease_owner == worker,
            DevTask.state.in_(_HEARTBEAT_STATES),
        )
        .values(lease_until=now + timedelta(seconds=lease_seconds), updated_at=now)
    )
    await db.commit()
    return bool(result.rowcount or 0)


async def claim_next(
    db,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    scan_limit: int = 10,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Atomically claim the highest-priority QUEUED task; None when idle.

    Candidates are scanned oldest-first within descending priority; each
    candidate is claimed with the same conditional UPDATE, so a concurrent
    worker taking a row just moves us to the next candidate.

    Backoff is honoured twice: once in the candidate SELECT (so a backed-off
    task does not waste a scan slot) and once inside the claim UPDATE (so a
    task that becomes backed-off between SELECT and UPDATE still cannot be
    taken). NULL ``next_eligible_at`` always stays eligible.
    """
    from app.models.dev_task import DevTask

    now = now or datetime.utcnow()
    stmt = (
        select(DevTask.id)
        .where(DevTask.state == TaskState.QUEUED.value, _backoff_predicate(now))
        .order_by(DevTask.priority.desc(), DevTask.created_at.asc())
        .limit(max(1, scan_limit))
    )
    for candidate_id in (await db.scalars(stmt)).all():
        if await atomic_claim(
            db,
            candidate_id,
            worker,
            lease_seconds=lease_seconds,
            now=now,
            respect_backoff=True,
        ):
            task = await db.get(DevTask, candidate_id)
            return {"task_id": candidate_id, "task": task}
    return None
