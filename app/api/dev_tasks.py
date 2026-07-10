"""Admin-only Claude-managed engineering task ledger API (draft-safe)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import require_admin
from app.dev_control.registry import MODEL_CATALOG, route_preview
from app.dev_control.service import TaskState
from app.models.base import get_async_db
from app.models.dev_task import DevTask
from app.models.dev_usage import DevTaskUsage
from app.dev_control import deploy as _deploy, delivery as _delivery, reconcile as _reconcile

router = APIRouter(prefix="/dev-tasks", tags=["Dev Task Control Plane"])


def _enabled() -> bool:
    return os.getenv("DEV_ORCHESTRATOR", "0").strip().lower() in {"1", "true", "yes", "on"}


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=503, detail="DEV_ORCHESTRATOR is disabled")


class CreateTaskRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=180)
    parent_objective: str = Field(..., min_length=3, max_length=4000)
    customer_id: str | None = Field(None, max_length=36)
    priority: int = Field(50, ge=1, le=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=20)
    file_ownership: list[str] = Field(default_factory=list, max_length=100)
    dependencies: list[str] = Field(default_factory=list, max_length=50)


class RoutePreviewRequest(BaseModel):
    task_type: str = Field("code", min_length=2, max_length=40)
    sensitivity: str = Field("normal", min_length=2, max_length=30)
    complexity: str = Field("medium", min_length=2, max_length=30)


class TransitionRequest(BaseModel):
    state: TaskState
    reason: str = Field("", max_length=1000)


class WorkerReportRequest(BaseModel):
    files_changed: list[str] = Field(default_factory=list, max_length=200)
    summary: str = Field("", max_length=4000)
    tests_executed: list[str] = Field(default_factory=list, max_length=100)
    test_result: str = Field("", max_length=1000)
    unresolved_risks: list[str] = Field(default_factory=list, max_length=30)
    commit_hash: str = Field("", max_length=80)
    recommended_next_action: str = Field("", max_length=1000)


def _row(task: DevTask) -> dict[str, Any]:
    def _json(value: str | None, fallback: Any) -> Any:
        try:
            return json.loads(value or "")
        except Exception:
            return fallback

    return {
        "task_id": task.id,
        "idempotency_key": task.idempotency_key,
        "objective": task.parent_objective,
        "customer_id": task.customer_id,
        "priority": task.priority,
        "state": task.state,
        "selected_provider": task.selected_provider,
        "selected_model": task.selected_model,
        "fallback_models": _json(task.fallback_models, []),
        "worktree_path": task.worktree_path,
        "branch_name": task.branch_name,
        "file_ownership": _json(task.file_ownership, []),
        "dependencies": _json(task.dependencies, []),
        "acceptance_criteria": _json(task.acceptance_criteria, []),
        "retry_count": task.retry_count,
        "lease_owner": task.lease_owner,
        "lease_until": task.lease_until.isoformat() if task.lease_until else None,
        "test_evidence": task.test_evidence,
        "deployment_evidence": task.deployment_evidence,
        "delivery_evidence": task.delivery_evidence,
        "worker_report": _json(task.worker_report, {}),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.get("/models")
async def list_models(_user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    return {"models": [{"alias": k, **val} for k, val in MODEL_CATALOG.items()]}


@router.post("/route-preview")
async def preview_route(body: RoutePreviewRequest, _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    return route_preview(task_type=body.task_type, sensitivity=body.sensitivity, complexity=body.complexity)


@router.post("")
async def create_task(body: CreateTaskRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    existing = await db.scalar(select(DevTask).where(DevTask.idempotency_key == body.idempotency_key))
    if existing:
        return {"reused": True, "task": _row(existing)}
    now = datetime.utcnow()
    task = DevTask(
        id=str(uuid.uuid4()), idempotency_key=body.idempotency_key,
        parent_objective=body.parent_objective, customer_id=body.customer_id,
        priority=body.priority, state=TaskState.PROPOSED.value,
        acceptance_criteria=json.dumps(body.acceptance_criteria),
        file_ownership=json.dumps(body.file_ownership), dependencies=json.dumps(body.dependencies),
        retry_count=0, created_at=now, updated_at=now,
    )
    db.add(task)
    try:
        await db.commit()
    except IntegrityError:
        # Two manager retries can race on the unique idempotency key. The
        # losing transaction is discarded and the committed winner is returned.
        await db.rollback()
        winner = await db.scalar(select(DevTask).where(DevTask.idempotency_key == body.idempotency_key))
        if winner:
            return {"reused": True, "task": _row(winner)}
        raise HTTPException(status_code=503, detail="task ledger temporarily unavailable")
    await db.refresh(task)
    return {"reused": False, "task": _row(task)}


@router.get("")
async def list_tasks(state: str | None = Query(None, max_length=40), limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    stmt = select(DevTask).order_by(DevTask.created_at.desc()).limit(limit)
    if state:
        stmt = stmt.where(DevTask.state == state)
    return {"tasks": [_row(x) for x in (await db.scalars(stmt)).all()]}


@router.post("/{task_id}/transition")
async def transition_task(task_id: str, body: TransitionRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    task = await db.get(DevTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    from app.dev_control.service import InvalidTransition, transition
    record = {"state": task.state}
    try:
        transition(record, body.state)
    except (InvalidTransition, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task.state = record["state"]
    if body.reason and body.state == TaskState.BLOCKED:
        task.blocked_reason = body.reason
    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return {"task": _row(task)}


@router.post("/claim-next")
async def claim_next_task(worker: str = Query(..., min_length=2, max_length=120), db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    """Atomically claim the highest-priority QUEUED task (worker poll surface)."""
    _require_enabled()
    from app.dev_control.claims import claim_next

    won = await claim_next(db, worker)
    if not won:
        return {"task": None, "reason": "no_eligible_task"}
    return {"task": _row(won["task"])}


@router.post("/{task_id}/claim")
async def claim_task(task_id: str, worker: str = Query(..., min_length=2, max_length=120), db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    """Claim one queued task with a bounded lease; tmux is never the source of truth.

    The claim is a single conditional UPDATE (state must still be QUEUED), so two
    workers racing on the same task get exactly one winner -- the loser gets 409.
    """
    _require_enabled()
    task = await db.get(DevTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    from app.dev_control.claims import atomic_claim

    if not await atomic_claim(db, task_id, worker):
        raise HTTPException(status_code=409, detail=f"task not claimable from state '{task.state}' (already claimed or not queued)")
    await db.refresh(task)
    return {"task": _row(task)}


@router.post("/{task_id}/heartbeat")
async def heartbeat_task(task_id: str, worker: str = Query(..., min_length=2, max_length=120), db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    """Extend a lease the caller owns; a non-owner heartbeat is refused (no lease steal)."""
    _require_enabled()
    task = await db.get(DevTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    from app.dev_control.claims import atomic_heartbeat

    if not await atomic_heartbeat(db, task_id, worker):
        raise HTTPException(status_code=409, detail="lease not owned by this worker (or task not in flight)")
    await db.refresh(task)
    return {"task_id": task.id, "lease_owner": task.lease_owner, "lease_until": task.lease_until.isoformat() if task.lease_until else None}


@router.post("/{task_id}/report")
async def record_report(task_id: str, body: WorkerReportRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    task = await db.get(DevTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    task.worker_report = json.dumps(body.model_dump())
    task.test_evidence = json.dumps({"commands": body.tests_executed, "result": body.test_result})
    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return {"task": _row(task)}


# ---------------------------------------------------------------------------
# Phase 3-6 lifecycle endpoints (all admin-gated + DEV_ORCHESTRATOR-gated).
# None of these apply a patch, run a shell command, deploy, or message a
# customer. Runner dispatch is separately gated by DEV_WORKER_ENABLED.
# ---------------------------------------------------------------------------


class PromoteStagingRequest(BaseModel):
    tests_passed: bool = True
    evidence: dict[str, Any] = Field(default_factory=dict)


class RequestApprovalRequest(BaseModel):
    staging_evidence: dict[str, Any] = Field(default_factory=dict)


class ApproveProductionRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=200)
    commit_hash: str = Field("", max_length=80)


class RejectProductionRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


@router.get("/status")
async def dev_status(db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    snap = await _reconcile.status_snapshot(db)
    return {"status": snap, "line": _reconcile.render_status_line(snap), "deploy_gate": _deploy.approval_gate_status()}


@router.get("/{task_id}/usage")
async def task_usage(task_id: str, db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    rows = (await db.scalars(select(DevTaskUsage).where(DevTaskUsage.task_id == task_id).order_by(DevTaskUsage.attempt_no))).all()
    return {"task_id": task_id, "usage": [{
        "attempt_no": r.attempt_no, "provider": r.provider, "model": r.model,
        "outcome": r.outcome, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
        "cost_usd": str(r.cost_usd) if r.cost_usd is not None else None,
        "estimated": r.estimated, "detail": r.detail,
    } for r in rows]}


@router.post("/reconcile")
async def reconcile(db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    return await _reconcile.reconcile_leases(db)


@router.post("/{task_id}/run")
async def run_task(task_id: str, _user=Depends(require_admin)) -> dict[str, Any]:
    """Enqueue the draft-only runner. 503 unless DEV_WORKER_ENABLED (INERT default)."""
    _require_enabled()
    from app.dev_control.runner import worker_enabled

    if not worker_enabled():
        raise HTTPException(status_code=503, detail="DEV_WORKER_ENABLED is disabled")
    try:
        from app.tasks.dev_worker import run_dev_task_task

        async_result = run_dev_task_task.delay(task_id)
        return {"enqueued": True, "task_id": task_id, "job_id": getattr(async_result, "id", None)}
    except Exception as exc:  # broker down etc. — never 500 the admin API
        raise HTTPException(status_code=503, detail=f"worker unavailable: {str(exc)[:120]}") from exc


@router.post("/{task_id}/promote-staging")
async def promote_staging(task_id: str, body: PromoteStagingRequest, db: AsyncSession = Depends(get_async_db), _user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    out = await _deploy.promote_to_staging(db, task_id, tests_passed=body.tests_passed, test_evidence=body.evidence)
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=out.get("reason", "cannot_promote"))
    return out


@router.post("/{task_id}/request-approval")
async def request_approval(task_id: str, body: RequestApprovalRequest, db: AsyncSession = Depends(get_async_db), user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    out = await _deploy.request_production_approval(db, task_id, requested_by=str(getattr(user, "email", "admin")), staging_evidence=body.staging_evidence)
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=out.get("reason", "cannot_request"))
    return out


@router.post("/{task_id}/approve-production")
async def approve_production(task_id: str, body: ApproveProductionRequest, db: AsyncSession = Depends(get_async_db), user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    out = await _deploy.approve_production(db, task_id, approver=str(getattr(user, "email", "admin")), token=body.token, commit_hash=body.commit_hash)
    if not out.get("ok"):
        raise HTTPException(status_code=403 if "token" in out.get("reason", "") else 409, detail=out.get("reason", "cannot_approve"))
    return out


@router.post("/{task_id}/reject-production")
async def reject_production(task_id: str, body: RejectProductionRequest, db: AsyncSession = Depends(get_async_db), user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    out = await _deploy.reject_production(db, task_id, approver=str(getattr(user, "email", "admin")), reason=body.reason)
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=out.get("reason", "cannot_reject"))
    return out


@router.post("/{task_id}/finalize-delivery")
async def finalize_delivery(task_id: str, db: AsyncSession = Depends(get_async_db), user=Depends(require_admin)) -> dict[str, Any]:
    _require_enabled()
    out = await _delivery.finalize_delivery(db, task_id, verified_by=str(getattr(user, "email", "admin")))
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=out.get("reason", "cannot_finalize"))
    return out
