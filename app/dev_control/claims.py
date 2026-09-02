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
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.dev_control.service import TaskState

DEFAULT_LEASE_SECONDS = 600
_HEARTBEAT_STATES = (TaskState.CLAIMED.value, TaskState.RUNNING.value)


async def atomic_claim(
    db,
    task_id: str,
    worker: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Claim one QUEUED task. Returns True only for the single winning worker."""
    from app.models.dev_task import DevTask

    now = now or datetime.utcnow()
    result = await db.execute(
        update(DevTask)
        .where(DevTask.id == task_id, DevTask.state == TaskState.QUEUED.value)
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
    """
    from app.models.dev_task import DevTask

    stmt = (
        select(DevTask.id)
        .where(DevTask.state == TaskState.QUEUED.value)
        .order_by(DevTask.priority.desc(), DevTask.created_at.asc())
        .limit(max(1, scan_limit))
    )
    for candidate_id in (await db.scalars(stmt)).all():
        if await atomic_claim(db, candidate_id, worker, lease_seconds=lease_seconds, now=now):
            task = await db.get(DevTask, candidate_id)
            return {"task_id": candidate_id, "task": task}
    return None
