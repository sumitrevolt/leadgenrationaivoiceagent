"""Pure control-plane rules; persistence adapters can call these functions."""

from __future__ import annotations

import uuid

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"
    CHANGES_REQUESTED = "changes_requested"
    TESTS_RUNNING = "tests_running"
    TESTS_FAILED = "tests_failed"
    STAGING_READY = "staging_ready"
    STAGING_DEPLOYED = "staging_deployed"
    PRODUCTION_APPROVAL_REQUIRED = "production_approval_required"
    PRODUCTION_DEPLOYED = "production_deployed"
    DELIVERY_VERIFICATION = "delivery_verification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


IDEMPOTENCY_REUSE = "reused"

_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PROPOSED: {TaskState.APPROVED, TaskState.CANCELLED},
    TaskState.APPROVED: {TaskState.QUEUED, TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.QUEUED: {TaskState.CLAIMED, TaskState.BLOCKED, TaskState.CANCELLED},
    TaskState.CLAIMED: {TaskState.RUNNING, TaskState.BLOCKED, TaskState.FAILED},
    TaskState.RUNNING: {
        TaskState.REVIEW_REQUIRED,
        TaskState.TESTS_RUNNING,
        TaskState.BLOCKED,
        TaskState.FAILED,
    },
    TaskState.BLOCKED: {TaskState.QUEUED, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.REVIEW_REQUIRED: {
        TaskState.CHANGES_REQUESTED,
        TaskState.TESTS_RUNNING,
        TaskState.FAILED,
    },
    TaskState.CHANGES_REQUESTED: {TaskState.QUEUED, TaskState.CANCELLED},
    TaskState.TESTS_RUNNING: {TaskState.STAGING_READY, TaskState.TESTS_FAILED, TaskState.FAILED},
    TaskState.TESTS_FAILED: {TaskState.QUEUED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.STAGING_READY: {
        TaskState.STAGING_DEPLOYED,
        TaskState.PRODUCTION_APPROVAL_REQUIRED,
        TaskState.FAILED,
    },
    TaskState.STAGING_DEPLOYED: {TaskState.PRODUCTION_APPROVAL_REQUIRED, TaskState.FAILED},
    TaskState.PRODUCTION_APPROVAL_REQUIRED: {TaskState.PRODUCTION_DEPLOYED, TaskState.CANCELLED},
    TaskState.PRODUCTION_DEPLOYED: {TaskState.DELIVERY_VERIFICATION, TaskState.FAILED},
    TaskState.DELIVERY_VERIFICATION: {TaskState.COMPLETED, TaskState.FAILED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


class InvalidTransition(ValueError):
    """Raised when a task attempts to skip a required control-plane gate."""


def _normalise_idempotency_key(idempotency_key: str) -> str:
    """Trim the key; empty keys never reach the DB (behaviour preserved)."""
    key = (idempotency_key or "").strip()
    if not key:
        raise ValueError("idempotency_key is required")
    return key


def _row_to_record(task: Any, *, reused: bool) -> dict[str, Any]:
    """Project a DevTask row onto the public record dict."""
    return {
        "task_id": task.id,
        "idempotency_key": task.idempotency_key,
        "objective": task.parent_objective,
        "state": task.state,
        "lease_until": task.lease_until,
        "retry_count": int(task.retry_count or 0),
        "next_eligible_at": getattr(task, "next_eligible_at", None),
        "parent_id": getattr(task, "parent_id", None),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "reused": reused,
    }


def _build_task(objective: str, key: str, *, customer_id: str | None, priority: int, now: datetime):
    """Build (not persist) a DevTask. Model import stays lazy on purpose."""
    from app.models.dev_task import DevTask

    return DevTask(
        id=str(uuid.uuid4()),
        idempotency_key=key,
        parent_objective=(objective or "").strip()[:4000],
        customer_id=customer_id,
        priority=int(priority),
        state=TaskState.PROPOSED.value,
        retry_count=0,
        created_at=now,
        updated_at=now,
    )


def create_task_record(
    objective: str,
    idempotency_key: str,
    *,
    db=None,
    customer_id: str | None = None,
    priority: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    """SYNC durable create. Idempotency is enforced by the DATABASE.

    The old implementation kept a process-local ``_IDEMPOTENCY`` dict, which
    made idempotency a lie for a 24x7 system: every restart (or every second
    uvicorn worker) forgot every key and happily created duplicate tasks. The
    guarantee now comes from the UNIQUE column ``dev_tasks.idempotency_key``:
    an existing row is returned (``reused=True``), and if two writers race, the
    loser's INSERT hits the unique constraint and the committed winner is
    returned — never a second row, never a 500.

    ``db`` may be any sync SQLAlchemy Session. When it is None a short-lived
    session is opened via ``app.models.base.get_db_session``.
    """
    # Validate BEFORE importing SQLAlchemy: a bad key must fail fast, and this
    # keeps the guard testable on a bare interpreter.
    key = _normalise_idempotency_key(idempotency_key)
    now = now or datetime.utcnow()

    if db is None:
        from app.models.base import get_db_session

        with get_db_session() as session:
            return _create_task_sync(
                session,
                objective,
                key,
                customer_id=customer_id,
                priority=priority,
                now=now,
            )

    return _create_task_sync(
        db,
        objective,
        key,
        customer_id=customer_id,
        priority=priority,
        now=now,
    )


def _create_task_sync(
    db,
    objective: str,
    key: str,
    *,
    customer_id: str | None,
    priority: int,
    now: datetime,
) -> dict[str, Any]:
    """Session-owning body of the sync durable create (see create_task_record)."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models.dev_task import DevTask

    existing = db.execute(select(DevTask).where(DevTask.idempotency_key == key)).scalars().first()
    if existing is not None:
        return _row_to_record(existing, reused=True)
    task = _build_task(objective, key, customer_id=customer_id, priority=priority, now=now)
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = (
            db.execute(select(DevTask).where(DevTask.idempotency_key == key)).scalars().first()
        )
        if winner is not None:
            return _row_to_record(winner, reused=True)
        raise
    return _row_to_record(task, reused=False)


async def create_task_record_async(
    db,
    objective: str,
    idempotency_key: str,
    *,
    customer_id: str | None = None,
    priority: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    """ASYNC durable create (FastAPI layer). Same DB-level idempotency."""
    key = _normalise_idempotency_key(idempotency_key)
    now = now or datetime.utcnow()

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models.dev_task import DevTask

    existing = (
        (await db.execute(select(DevTask).where(DevTask.idempotency_key == key))).scalars().first()
    )
    if existing is not None:
        return _row_to_record(existing, reused=True)
    task = _build_task(objective, key, customer_id=customer_id, priority=priority, now=now)
    db.add(task)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        winner = (
            (await db.execute(select(DevTask).where(DevTask.idempotency_key == key)))
            .scalars()
            .first()
        )
        if winner is not None:
            return _row_to_record(winner, reused=True)
        raise
    return _row_to_record(task, reused=False)


def transition(record: dict[str, Any], target: TaskState) -> dict[str, Any]:
    current = TaskState(record["state"])
    if target not in _TRANSITIONS[current]:
        raise InvalidTransition(f"{current.value} -> {target.value} is not allowed")
    record["state"] = target.value
    return record


def admit_cost(
    *,
    provider: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    task_budget_usd: Decimal,
    daily_remaining_usd: Decimal,
) -> dict[str, Any]:
    from app.dev_control.registry import MODEL_CATALOG

    meta = MODEL_CATALOG.get(provider)
    if not meta:
        return {"allowed": False, "reason": "unknown_provider", "estimated_cost_usd": Decimal("0")}
    cost = (
        Decimal(estimated_input_tokens) * Decimal(str(meta["cost_input_usd_per_million"]))
        + Decimal(estimated_output_tokens) * Decimal(str(meta["cost_output_usd_per_million"]))
    ) / Decimal(1_000_000)
    if cost > task_budget_usd:
        return {"allowed": False, "reason": "task_budget_exceeded", "estimated_cost_usd": cost}
    if cost > daily_remaining_usd:
        return {"allowed": False, "reason": "daily_budget_exceeded", "estimated_cost_usd": cost}
    return {"allowed": True, "reason": "within_budget", "estimated_cost_usd": cost}
