"""Pure control-plane rules; persistence adapters can call these functions."""

from __future__ import annotations

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


_IDEMPOTENCY: dict[str, dict[str, Any]] = {}


def create_task_record(objective: str, idempotency_key: str) -> dict[str, Any]:
    key = idempotency_key.strip()
    if not key:
        raise ValueError("idempotency_key is required")
    if key in _IDEMPOTENCY:
        out = dict(_IDEMPOTENCY[key])
        out["reused"] = True
        return out
    import uuid

    record = {
        "task_id": str(uuid.uuid4()),
        "objective": objective.strip()[:4000],
        "state": TaskState.PROPOSED.value,
        "lease_until": None,
        "reused": False,
    }
    _IDEMPOTENCY[key] = record
    return dict(record)


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
