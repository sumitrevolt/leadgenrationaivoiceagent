"""Draft-only worktree runner for the engineering control plane (Phase 3).

HARD GATES (never relaxed by this module):
  * INERT unless DEV_ORCHESTRATOR=1 AND DEV_WORKER_ENABLED=1 (checked by the
    Celery wrapper, not here — this function is the pure orchestration core).
  * The runner produces a REVIEW-ONLY patch PROPOSAL artifact. It NEVER writes
    that patch into the working tree, commits, pushes, or deploys. ``apply_patch``
    below unconditionally refuses; patch application is a separate future phase.
  * File-ownership locks prevent two workers touching the same files.
  * All provider spend flows through the budget-admitting gateway + usage ledger.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.dev_control import locks
from app.dev_control.gateway import invoke
from app.dev_control.service import _TRANSITIONS, TaskState
from app.dev_control.usage import record_gateway_result


def _flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def auto_apply_enabled() -> bool:
    return _flag("AUTO_APPLY_PATCH")


def worker_enabled() -> bool:
    return _flag("DEV_ORCHESTRATOR") and _flag("DEV_WORKER_ENABLED")


def apply_patch(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Patch application boundary — DISABLED. Even with AUTO_APPLY_PATCH=1 the
    Phase-3 runner never mutates the working tree. Returns a refusal so callers
    have explicit evidence the gate held."""
    return {"applied": False, "refused": True, "reason": "auto_apply_forbidden_phase3"}


def _json_list(value: str | None) -> list[str]:
    try:
        out = json.loads(value or "[]")
        return [str(x) for x in out] if isinstance(out, list) else []
    except Exception:
        return []


def _can(state_value: str, target: TaskState) -> bool:
    try:
        return target in _TRANSITIONS[TaskState(state_value)]
    except Exception:
        return False


def _write_proposal(proposals_root: str, task_id: str, text: str) -> str:
    safe_id = "".join(ch for ch in task_id if ch.isalnum() or ch in "-_")[:64] or "task"
    d = Path(proposals_root) / safe_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"proposal-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}.md"
    header = (
        "# REVIEW-ONLY PATCH PROPOSAL\n"
        "> This artifact was NOT applied to the working tree. A human must review,\n"
        "> and application happens only through the separately-gated deploy path.\n\n"
    )
    path.write_text(header + (text or "(empty proposal)"), encoding="utf-8")
    return str(path)


async def run_dev_task(
    db,
    task_id: str,
    *,
    worker_id: str = "dev-worker-1",
    provider_call: Any = None,
    proposals_root: str = "data/dev_tasks",
    lock: Any = None,
    task_budget_usd: str | float = "0.50",
    daily_remaining_usd: str | float = "5.00",
) -> dict[str, Any]:
    """Run one claimed task to a review-required proposal. Draft-only."""
    from app.models.dev_task import DevTask

    task = await db.get(DevTask, task_id)
    if task is None:
        return {"ok": False, "reason": "task_not_found"}
    if task.state != TaskState.CLAIMED.value:
        return {"ok": False, "reason": "not_claimed", "state": task.state}

    lock = lock or locks.default_lock()
    owned = _json_list(task.file_ownership)
    acq = lock.acquire(worker_id, owned)
    if not acq["acquired"]:
        if _can(task.state, TaskState.BLOCKED):
            task.state = TaskState.BLOCKED.value
        task.blocked_reason = "file_ownership_conflict: " + ",".join(acq["conflict"])[:400]
        task.updated_at = datetime.utcnow()
        await db.commit()
        return {"ok": False, "reason": "file_ownership_conflict", "conflict": acq["conflict"]}

    try:
        task.state = TaskState.RUNNING.value
        task.lease_owner = worker_id
        task.updated_at = datetime.utcnow()
        await db.commit()

        acceptance = _json_list(task.acceptance_criteria)
        system = (
            "You are a senior engineer producing a REVIEW-ONLY unified-diff patch "
            "PROPOSAL plus a short rationale. Do not assume it will be auto-applied."
        )
        user = (task.parent_objective or "").strip()
        if acceptance:
            user += "\n\nAcceptance criteria:\n- " + "\n- ".join(acceptance)

        result = await invoke(
            task_id=task_id, task_type="code", sensitivity="normal", complexity="high",
            system=system, messages=[{"role": "user", "content": user}], max_tokens=1200,
            task_budget_usd=Decimal(str(task_budget_usd)),
            daily_remaining_usd=Decimal(str(daily_remaining_usd)),
            provider_call=provider_call,
        )
        try:
            await record_gateway_result(db, task_id, result, scope=f"dev-task:{task_id}")
        except Exception:
            pass  # ledger failure must never crash the runner

        if not result.get("ok"):
            if _can(task.state, TaskState.BLOCKED):
                task.state = TaskState.BLOCKED.value
            task.blocked_reason = ("provider_unavailable: " + str(result.get("reason")))[:400]
            task.updated_at = datetime.utcnow()
            await db.commit()
            return {"ok": False, "reason": result.get("reason"), "stage": "invoke"}

        artifact = _write_proposal(proposals_root, task_id, result.get("text") or "")
        task.worker_report = json.dumps({
            "proposal_artifact": artifact,
            "provider": result.get("provider"),
            "model": result.get("model"),
            "applied": False,
            "auto_apply_enabled": auto_apply_enabled(),
            "note": "review-only; patch NOT applied to the working tree",
        })
        task.selected_provider = result.get("provider")
        task.selected_model = result.get("model")
        if _can(task.state, TaskState.REVIEW_REQUIRED):
            task.state = TaskState.REVIEW_REQUIRED.value
        task.updated_at = datetime.utcnow()
        await db.commit()
        return {"ok": True, "state": task.state, "proposal_artifact": artifact, "applied": False}
    finally:
        lock.release(worker_id, owned)
