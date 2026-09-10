"""Restart reconciliation + read-only status for the control plane (Phase 4).

The DATABASE is the single source of truth for task state — never tmux, never a
worker's memory. On restart (or on a cadence) ``reconcile_leases`` reclaims tasks
whose worker died mid-flight: an expired lease moves the task out of the in-flight
states and either requeues it (under the retry cap) or fails it. All transitions
below are legal per the control-plane state machine (CLAIMED/RUNNING -> BLOCKED ->
QUEUED|FAILED).

Two entrypoints, one policy:
  * ``reconcile_leases``            — async, caller owns the session (API route).
  * ``reconcile_expired_leases_sync`` — blocking, opens its own session, NEVER
    raises. Safe for app startup and Celery beat (see
    ``app/tasks/dev_task_reconcile.py``).

Both are bounded (``limit`` rows per call) and idempotent: a second call finds no
expired in-flight row and does nothing. Requeued tasks get
``next_eligible_at = now + backoff`` (60s * 2^retry_count, 15m cap, jitter — see
``app.dev_control.lease_policy``) so a poison task cannot be re-claimed in a hot
loop. The decision itself is the pure function ``plan_lease_reclaim``.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.dev_control.lease_policy import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RECONCILE_LIMIT,
    plan_lease_reclaim,
)
from app.dev_control.service import _TRANSITIONS, TaskState

_IN_FLIGHT = (TaskState.CLAIMED.value, TaskState.RUNNING.value)


def _can(state_value: str, target: TaskState) -> bool:
    try:
        return target in _TRANSITIONS[TaskState(state_value)]
    except Exception:
        return False


async def reconcile_leases(
    db,
    *,
    now: datetime | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    limit: int = DEFAULT_RECONCILE_LIMIT,
) -> dict[str, Any]:
    """Reclaim in-flight tasks whose lease has expired. Idempotent + bounded.

    ``limit`` caps the rows touched per call so a beat tick can never block the
    app on a huge backlog; the next tick picks up the rest. Requeued tasks are
    given ``next_eligible_at`` (exponential backoff + jitter) which
    ``claims.claim_next`` honours.
    """
    from app.models.dev_task import DevTask

    now = now or datetime.utcnow()
    bounded_limit = max(1, int(limit or DEFAULT_RECONCILE_LIMIT))
    stmt = (
        select(DevTask)
        .where(
            DevTask.state.in_(_IN_FLIGHT),
            DevTask.lease_until.is_not(None),
            DevTask.lease_until < now,
        )
        .order_by(DevTask.lease_until.asc())
        .limit(bounded_limit)
    )
    rows = (await db.scalars(stmt)).all()
    requeued = failed = 0
    for task in rows:
        plan = plan_lease_reclaim(
            state=task.state,
            retry_count=task.retry_count,
            max_retries=max_retries,
            now=now,
        )
        # First leave the in-flight state legally (BLOCKED hop), then resolve.
        if plan["intermediate_state"]:
            task.state = plan["intermediate_state"]
        task.state = plan["state"]
        task.blocked_reason = plan["blocked_reason"]
        task.retry_count = plan["retry_count"]
        task.lease_owner = plan["lease_owner"]
        task.lease_until = plan["lease_until"]
        task.next_eligible_at = plan["next_eligible_at"]
        task.updated_at = now
        if plan["outcome"] == "failed":
            failed += 1
        else:
            requeued += 1
    await db.commit()
    return {
        "scanned": len(rows),
        "requeued": requeued,
        "failed": failed,
        "at": now.isoformat(),
        "limit": bounded_limit,
        "capped": len(rows) >= bounded_limit,
    }


def _sync_session_ctx(session_factory=None):
    """Context manager yielding a SYNC session (caller-supplied or default)."""
    if session_factory is not None:

        @contextlib.contextmanager
        def _from_factory():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        return _from_factory()

    from app.models.base import get_db_session

    return get_db_session()


def reconcile_expired_leases_sync(
    *,
    now: datetime | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    limit: int = DEFAULT_RECONCILE_LIMIT,
    session_factory=None,
) -> dict[str, Any]:
    """Blocking, never-raising entrypoint for app startup / Celery beat.

    Opens its own short-lived session (unless ``session_factory`` is given),
    applies exactly the same ``plan_lease_reclaim`` policy as the async path, and
    returns ``{"ok": ..., ...}``. A reconciliation hiccup must never stop a boot
    or kill a beat tick, so every exception is caught and reported as
    ``ok=False`` with a ``reason``.
    """
    from app.models.dev_task import DevTask

    now = now or datetime.utcnow()
    bounded_limit = max(1, int(limit or DEFAULT_RECONCILE_LIMIT))
    result: dict[str, Any] = {
        "ok": True,
        "scanned": 0,
        "requeued": 0,
        "failed": 0,
        "at": now.isoformat(),
        "limit": bounded_limit,
        "capped": False,
    }
    try:
        with _sync_session_ctx(session_factory) as session:
            stmt = (
                select(DevTask)
                .where(
                    DevTask.state.in_(_IN_FLIGHT),
                    DevTask.lease_until.is_not(None),
                    DevTask.lease_until < now,
                )
                .order_by(DevTask.lease_until.asc())
                .limit(bounded_limit)
            )
            rows = list(session.execute(stmt).scalars().all())
            requeued = failed = 0
            for task in rows:
                plan = plan_lease_reclaim(
                    state=task.state,
                    retry_count=task.retry_count,
                    max_retries=max_retries,
                    now=now,
                )
                if plan["intermediate_state"]:
                    task.state = plan["intermediate_state"]
                task.state = plan["state"]
                task.blocked_reason = plan["blocked_reason"]
                task.retry_count = plan["retry_count"]
                task.lease_owner = plan["lease_owner"]
                task.lease_until = plan["lease_until"]
                task.next_eligible_at = plan["next_eligible_at"]
                task.updated_at = now
                if plan["outcome"] == "failed":
                    failed += 1
                else:
                    requeued += 1
            session.commit()
            result.update(
                {
                    "scanned": len(rows),
                    "requeued": requeued,
                    "failed": failed,
                    "capped": len(rows) >= bounded_limit,
                }
            )
            return result
    except Exception as exc:  # never propagate — startup/beat must survive this
        result.update({"ok": False, "reason": f"{type(exc).__name__}: {exc}"})
        return result


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
