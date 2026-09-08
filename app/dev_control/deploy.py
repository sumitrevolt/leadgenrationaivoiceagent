"""Staged promotion + human production-approval gate (Phase 5).

This module NEVER executes a deployment. Production deploys on this project are
MANUAL (Hostinger runbook; CI is gate-only). Here we only:
  * drive the legal state progression review -> tests -> staging,
  * require an explicit human approval carrying a fail-closed token before a task
    may enter PRODUCTION_DEPLOYED, and
  * record immutable approval/deployment evidence.
The actual "git pull && docker compose ... up" step is still run by a human per
`memory/playbooks.md`. AUTO_DEPLOY is reported for transparency but is never
acted upon by code.
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime
from typing import Any

from app.dev_control.governor_reviews import review_gate_status
from app.dev_control.service import _TRANSITIONS, TaskState


def _flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def auto_deploy_enabled() -> bool:
    """Reported for transparency only — code never auto-deploys regardless."""
    return _flag("AUTO_DEPLOY")


def _approval_token() -> str:
    return os.getenv("DEV_DEPLOY_APPROVAL_TOKEN", "").strip()


def verify_approval_token(provided: str | None) -> bool:
    """Fail-closed: no configured token, or a mismatch, means NO approval."""
    token = _approval_token()
    if not token or not provided:
        return False
    return hmac.compare_digest(token, str(provided).strip())


def _can(state_value: str, target: TaskState) -> bool:
    try:
        return target in _TRANSITIONS[TaskState(state_value)]
    except Exception:
        return False


def approval_gate_status() -> dict[str, Any]:
    return {
        "auto_deploy": auto_deploy_enabled(),
        "auto_deploy_executed_by_code": False,
        "approval_token_configured": bool(_approval_token()),
        "deploy_mode": "manual_hostinger_runbook",
        "runbook": "memory/playbooks.md",
    }


async def promote_to_staging(
    db, task_id: str, *, tests_passed: bool, test_evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Legal REVIEW/RUNNING -> TESTS_RUNNING -> STAGING_READY|TESTS_FAILED."""
    from app.models.dev_task import DevTask

    task = await db.get(DevTask, task_id)
    if task is None:
        return {"ok": False, "reason": "task_not_found"}
    review_gate = review_gate_status(task.worker_report)
    if not review_gate["approved"]:
        return {
            "ok": False,
            "reason": "dual_governor_review_required",
            "review_gate": review_gate,
        }
    if not _can(task.state, TaskState.TESTS_RUNNING):
        return {"ok": False, "reason": "illegal_state", "state": task.state}
    task.state = TaskState.TESTS_RUNNING.value
    task.test_evidence = json.dumps({"passed": bool(tests_passed), **(test_evidence or {})})[:8000]
    if tests_passed:
        task.state = TaskState.STAGING_READY.value
        outcome = "staging_ready"
    else:
        task.state = TaskState.TESTS_FAILED.value
        outcome = "tests_failed"
    task.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "state": task.state, "outcome": outcome, "review_gate": review_gate}


async def request_production_approval(
    db, task_id: str, *, requested_by: str, staging_evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    from app.models.dev_task import DevTask

    task = await db.get(DevTask, task_id)
    if task is None:
        return {"ok": False, "reason": "task_not_found"}
    review_gate = review_gate_status(task.worker_report)
    if not review_gate["approved"]:
        return {
            "ok": False,
            "reason": "dual_governor_review_required",
            "review_gate": review_gate,
        }
    if not _can(task.state, TaskState.PRODUCTION_APPROVAL_REQUIRED):
        return {"ok": False, "reason": "illegal_state", "state": task.state}
    task.state = TaskState.PRODUCTION_APPROVAL_REQUIRED.value
    task.deployment_evidence = json.dumps(
        {
            "stage": "awaiting_human_approval",
            "requested_by": requested_by,
            "staging_evidence": staging_evidence or {},
            "requested_at": datetime.utcnow().isoformat(),
        }
    )[:8000]
    task.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "state": task.state}


async def approve_production(
    db, task_id: str, *, approver: str, token: str | None, commit_hash: str = ""
) -> dict[str, Any]:
    """Human approval gate. Records PRODUCTION_DEPLOYED evidence but runs NO deploy."""
    from app.models.dev_task import DevTask

    if not verify_approval_token(token):
        return {"ok": False, "reason": "approval_token_invalid_or_unconfigured"}
    task = await db.get(DevTask, task_id)
    if task is None:
        return {"ok": False, "reason": "task_not_found"}
    if not _can(task.state, TaskState.PRODUCTION_DEPLOYED):
        return {"ok": False, "reason": "illegal_state", "state": task.state}
    task.state = TaskState.PRODUCTION_DEPLOYED.value
    task.deployment_evidence = json.dumps(
        {
            "stage": "approved_pending_manual_deploy",
            "approved_by": approver,
            "approved_at": datetime.utcnow().isoformat(),
            "commit_hash": commit_hash,
            "auto_deploy_executed_by_code": False,
            "note": "human-approved; operator runs the Hostinger runbook — code did not deploy",
        }
    )[:8000]
    task.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "state": task.state, "deployed_by_code": False}


async def reject_production(db, task_id: str, *, approver: str, reason: str) -> dict[str, Any]:
    from app.models.dev_task import DevTask

    task = await db.get(DevTask, task_id)
    if task is None:
        return {"ok": False, "reason": "task_not_found"}
    if not _can(task.state, TaskState.CANCELLED):
        return {"ok": False, "reason": "illegal_state", "state": task.state}
    task.state = TaskState.CANCELLED.value
    task.blocked_reason = f"production_rejected_by:{approver}: {reason}"[:400]
    task.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "state": task.state}
