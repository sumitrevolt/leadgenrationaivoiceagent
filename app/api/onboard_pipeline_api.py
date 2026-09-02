"""
Onboarding Pipeline Admin API
=============================
GET  /api/admin/onboard-pipeline/status           → all pipelines + metrics
GET  /api/admin/onboard-pipeline/status/{cid}     → single client pipeline
POST /api/admin/onboard-pipeline/run              → trigger pipeline for a client
POST /api/admin/onboard-pipeline/retry/{cid}/{stage} → retry a failed stage
GET  /api/admin/onboard-pipeline/metrics          → capacity metrics (p50/p95/failure)

Auth: require_admin (Bearer JWT from /app/admin-login).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/admin/onboard-pipeline", tags=["Onboarding Pipeline"])


# -----------------------------------------------------------------------
# Response models
# -----------------------------------------------------------------------


class PipelineStageResult(BaseModel):
    status: str
    duration_s: float | None = None
    error: str | None = None


class PipelineStatus(BaseModel):
    cid: str
    status: str
    progress: str = ""
    pct: int = 0
    stages: dict[str, Any] = {}
    stages_list: list[str] = []
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str | None = None


class PipelineMetrics(BaseModel):
    stages: dict[str, Any] = {}
    summary: dict[str, Any] = {}


class RunRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=100)
    force: bool = False
    send_welcome: bool = True
    start_from: str | None = None


class RetryRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=100)
    stage: str = Field(..., min_length=1, max_length=50)


# -----------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------


@router.get("/status")
async def list_pipelines(
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    """List all pipeline states + capacity metrics."""
    from app.marketing.onboarding_factory import get_all_pipelines, get_capacity_metrics

    try:
        pipelines = get_all_pipelines()
        metrics = get_capacity_metrics(hours=24)
        return {
            "ok": True,
            "pipelines": pipelines,
            "total": len(pipelines),
            "in_progress": sum(1 for p in pipelines if p.get("status") == "in_progress"),
            "completed": sum(1 for p in pipelines if p.get("status") == "completed"),
            "capacity": metrics,
        }
    except Exception as exc:
        logger.warning("[onboard_pipeline_api] status error: %s", exc)
        return {"ok": False, "error": str(exc)[:200]}


@router.get("/status/{cid}")
async def get_pipeline_status(
    cid: str,
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Get pipeline status for a specific client."""
    from app.marketing.onboarding_factory import get_pipeline_status

    try:
        status = get_pipeline_status(cid)
        return {"ok": True, **status}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@router.post("/run")
async def trigger_pipeline(
    req: RunRequest,
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Trigger onboarding pipeline for a client."""
    from app.marketing.onboarding_factory import check_backpressure
    from app.tasks.onboard_pipeline import run_onboard_pipeline

    # Backpressure check
    ok, reason = check_backpressure()
    if not ok:
        raise HTTPException(status_code=429, detail=f"Backpressure: {reason}")

    try:
        result = run_onboard_pipeline.delay(
            req.client_id,
            force=req.force,
            send_welcome=req.send_welcome,
            start_from=req.start_from,
        )
        return {
            "ok": True,
            "task_id": result.id,
            "client_id": req.client_id,
            "message": "Pipeline task queued",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@router.post("/retry/{cid}/{stage}")
async def retry_stage(
    cid: str,
    stage: str,
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Retry a specific failed pipeline stage."""
    from app.tasks.onboard_pipeline import run_single_stage

    try:
        result = run_single_stage.delay(cid, stage)
        return {
            "ok": True,
            "task_id": result.id,
            "client_id": cid,
            "stage": stage,
            "message": f"Stage {stage} retry queued",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@router.get("/metrics")
async def capacity_metrics(
    hours: int = Query(24, ge=1, le=168),
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Get capacity metrics for the onboarding pipeline."""
    from app.marketing.onboarding_factory import get_capacity_metrics

    try:
        return get_capacity_metrics(hours=hours)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@router.get("/backpressure")
async def backpressure_status(
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Check current backpressure status."""
    from app.marketing.onboarding_factory import check_backpressure

    try:
        ok, reason = check_backpressure()
        return {"ok": True, "backpressure_free": ok, "reason": reason}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
