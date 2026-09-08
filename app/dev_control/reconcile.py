"""Restart reconciliation + read-only status for the control plane (Phase 4).

The DATABASE is the single source of truth for task state — never tmux, never a
worker's memory. On restart (or on a cadence) ``reconcile_leases`` reclaims tasks
whose worker died mid-flight: an expired lease moves the task out of the in-flight
states and either requeues it (under the retry cap) or fails it. All transitions
below are legal per the control-plane state machine (CLAIMED/RUNNING -> BLOCKED ->
QUEUED|FAILED).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.dev_control.service import _TRANSITIONS, TaskState

_IN_FLIGHT = (TaskState.CLAIMED.value, TaskState.RUNNING.value)


def _can(state_value: str, target: TaskState) -> bool:
    try:
        return target in _TRANSITIONS[TaskState(state_value)]
    except Exception:
        return False


async def reconcile_leases(
    db, *, now: datetime | None = None, max_retries: int = 3
) -> dict[str, Any]:
    """Reclaim in-flight tasks whose lease has expired. Idempotent + bounded."""
    from app.models.dev_task import DevTask

    now = now or datetime.utcnow()
    stmt = select(DevTask).where(
        DevTask.state.in_(_IN_FLIGHT),
        DevTask.lease_until.is_not(None),
        DevTask.lease_until < now,
    )
    rows = (await db.scalars(stmt)).all()
    requeued = failed = 0
    for task in rows:
        # First leave the in-flight state legally.
        if _can(task.state, TaskState.BLOCKED):
            task.state = TaskState.BLOCKED.value
        task.retry_count = (task.retry_count or 0) + 1
        task.lease_owner = None
        task.lease_until = None
        if task.retry_count > max_retries:
            task.state = TaskState.FAILED.value
            task.blocked_reason = f"lease_expired_max_retries({max_retries})"
            failed += 1
        else:
            task.state = TaskState.QUEUED.value
            task.blocked_reason = "lease_expired_reclaimed"
            requeued += 1
        task.updated_at = now
    await db.commit()
    return {"scanned": len(rows), "requeued": requeued, "failed": failed, "at": now.isoformat()}


async def status_snapshot(db) -> dict[str, Any]:
    """Read-only rollup for tmux/admin observation — no mutations."""
    from app.models.dev_task import DevTask

    by_state: dict[str, int] = {}
    for state, count in (
        await db.execute(select(DevTask.state, func.count()).group_by(DevTask.state))
    ).all():
        by_state[str(state)] = int(count)
    total = sum(by_state.values())
    total_cost = await db.scalar(select(func.coalesce(func.sum(DevTask.actual_cost_usd), 0)))
    in_flight = by_state.get("claimed", 0) + by_state.get("running", 0)
    return {
        "total": total,
        "by_state": by_state,
        "in_flight": in_flight,
        "queued": by_state.get("queued", 0),
        "review_required": by_state.get("review_required", 0),
        "production_approval_required": by_state.get("production_approval_required", 0),
        "failed": by_state.get("failed", 0),
        "completed": by_state.get("completed", 0),
        "actual_cost_usd": str(Decimal(str(total_cost or "0"))),
    }


def render_status_line(snapshot: dict[str, Any]) -> str:
    """One-line tmux status string from a snapshot."""
    return (
        f"devtasks total={snapshot.get('total', 0)} "
        f"inflight={snapshot.get('in_flight', 0)} "
        f"queued={snapshot.get('queued', 0)} "
        f"review={snapshot.get('review_required', 0)} "
        f"prod_approval={snapshot.get('production_approval_required', 0)} "
        f"failed={snapshot.get('failed', 0)} "
        f"cost=${snapshot.get('actual_cost_usd', '0')}"
    )
