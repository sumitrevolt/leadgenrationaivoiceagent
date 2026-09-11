"""Worker-facing render-plane API (T02).

Routes (mounted at ``/api/render-plane``)::

    POST /lease              lease the next queued job
    POST /heartbeat          extend a lease the caller owns
    POST /complete           record a finished artifact (idempotent)
    POST /fail               fail / requeue a job
    GET  /status/{job_id}    read one job (tenant-scoped)
    GET  /fetch/{job_id}     fetch the render inputs (spec descriptor)

Security: every route requires the shared worker token in the
``X-Render-Plane-Token`` header, compared in constant time. If the token is
**unset**, the plane is REFUSED (503) — an unauthenticated render plane is worse
than a disabled one. The token is never logged and never echoed. The whole plane
is off unless ``CREATIVE_RENDER_PLANE_ENABLED=1`` (fail-closed).

``app/main.py`` mounts this router in T04; T02 does not edit ``main.py``.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import get_async_db
from app.render_plane import jobstore
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/render-plane", tags=["Render Plane"])

FLAG_ENV = "CREATIVE_RENDER_PLANE_ENABLED"
TOKEN_ENV = "RENDER_PLANE_WORKER_TOKEN"
TOKEN_HEADER = "X-Render-Plane-Token"


# --------------------------------------------------------------------- gates
def _env_on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _enabled() -> bool:
    return _env_on(FLAG_ENV, "0")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(status_code=503, detail=f"{FLAG_ENV} is disabled")


def _worker_token() -> str:
    return (os.getenv(TOKEN_ENV) or "").strip()


def _require_worker_token(x_render_plane_token: str = Header(default="")) -> None:
    """Constant-time token gate. Unset token => the plane is refused."""
    expected = _worker_token()
    if not expected:
        raise HTTPException(status_code=503, detail=f"{TOKEN_ENV} is not configured")
    if not hmac.compare_digest(expected, str(x_render_plane_token or "")):
        # Never echo the presented value.
        raise HTTPException(status_code=401, detail="invalid render-plane token")


def _log_ledger(tenant_id: str, event: str, detail: str = "") -> None:
    """Best-effort render-plane ledger event. Never raises, never blocks a route."""
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.log_event(
            str(tenant_id or ""), event, detail=str(detail or "")[:200]
        )
    except Exception as exc:
        logger.warning("[render_plane] ledger event %s skipped: %s", event, type(exc).__name__)


# --------------------------------------------------------------------- models
class LeaseRequest(BaseModel):
    worker: str = Field(..., min_length=1, max_length=120)
    lease_seconds: int | None = Field(None, ge=30, le=86_400)
    scan_limit: int = Field(10, ge=1, le=100)


class HeartbeatRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=180)
    worker: str = Field(..., min_length=1, max_length=120)
    attempt: int = Field(0, ge=0)
    lease_token: str = Field("", max_length=128)


class CompleteRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=180)
    worker: str = Field(..., min_length=1, max_length=120)
    revision: int = Field(0, ge=0)
    attempt: int = Field(0, ge=0)
    sha256: str = Field("", max_length=64)
    manifest_hash: str = Field("", max_length=64)
    artifact_path: str = Field("", max_length=500)
    artifact_bytes: int = Field(0, ge=0)
    network_isolation: dict[str, Any] = Field(default_factory=dict)
    lease_token: str = Field("", max_length=128)


class FailRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=180)
    worker: str = Field("", max_length=120)
    error: str = Field("", max_length=400)
    retryable: bool = False


# -------------------------------------------------------------------- routes
@router.post("/lease")
async def lease(
    body: LeaseRequest,
    db: AsyncSession = Depends(get_async_db),
    _token: None = Depends(_require_worker_token),
) -> dict[str, Any]:
    _require_enabled()
    result = await jobstore.claim_next_job(
        db,
        str(body.worker),
        lease_seconds_=body.lease_seconds,
        scan_limit=body.scan_limit,
    )
    job = result.get("job") or {}
    if result.get("ok") and job:
        _log_ledger(
            job.get("tenant_id"),
            "render_plane_leased",
            f"{job.get('creative_id')}:rev{job.get('revision')}",
        )
    return result


@router.post("/heartbeat")
async def heartbeat(
    body: HeartbeatRequest,
    db: AsyncSession = Depends(get_async_db),
    _token: None = Depends(_require_worker_token),
) -> dict[str, Any]:
    _require_enabled()
    if body.lease_token and not jobstore.verify_lease_token(
        body.job_id, body.worker, body.attempt, body.lease_token
    ):
        return {"ok": False, "error": "invalid_lease_token"}
    return await jobstore.heartbeat_job(db, body.job_id, body.worker)


@router.post("/complete")
async def complete(
    body: CompleteRequest,
    db: AsyncSession = Depends(get_async_db),
    _token: None = Depends(_require_worker_token),
) -> dict[str, Any]:
    _require_enabled()
    if body.lease_token and not jobstore.verify_lease_token(
        body.job_id, body.worker, body.attempt, body.lease_token
    ):
        return {"ok": False, "error": "invalid_lease_token"}
    result = await jobstore.complete_job(
        db,
        job_id=body.job_id,
        worker=body.worker,
        revision=body.revision,
        attempt=body.attempt,
        sha256=body.sha256,
        manifest_hash=body.manifest_hash,
        artifact_path=body.artifact_path,
        artifact_bytes=body.artifact_bytes,
        network_isolation=body.network_isolation,
    )
    job = result.get("job") or {}
    if result.get("ok") and not result.get("idempotent"):
        _log_ledger(
            job.get("tenant_id"),
            "render_plane_completed",
            f"{job.get('creative_id')}:rev{job.get('revision')}",
        )
    return result


@router.post("/fail")
async def fail(
    body: FailRequest,
    db: AsyncSession = Depends(get_async_db),
    _token: None = Depends(_require_worker_token),
) -> dict[str, Any]:
    _require_enabled()
    result = await jobstore.fail_job(
        db,
        job_id=body.job_id,
        worker=body.worker,
        error=body.error,
        retryable=body.retryable,
    )
    if result.get("ok"):
        job = result.get("job") or {}
        _log_ledger(
            job.get("tenant_id"),
            "render_plane_failed",
            f"{job.get('creative_id')}:rev{job.get('revision')}:{body.error}"[:200],
        )
    return result


@router.get("/status/{job_id}")
async def status(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    _token: None = Depends(_require_worker_token),
) -> dict[str, Any]:
    _require_enabled()
    return await jobstore.get_job(db, job_id)


@router.get("/fetch/{job_id}")
async def fetch(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    _token: None = Depends(_require_worker_token),
) -> dict[str, Any]:
    """Return the render inputs for one job (descriptor + resolved spec).

    The worker fetches inputs BEFORE rendering, so the render step itself needs
    no egress. Never raises; a missing spec degrades to an empty dict.
    """
    _require_enabled()
    got = await jobstore.get_job(db, job_id)
    if not got.get("ok"):
        return got
    job = got.get("job") or {}
    spec: dict[str, Any] = {}
    try:
        from app.marketing.creative_os.service import get_record

        rec = get_record(str(job.get("tenant_id") or ""), str(job.get("creative_id") or ""))
        if rec.get("ok"):
            spec = (rec.get("record") or {}).get("spec") or {}
    except Exception as exc:  # never blocks the worker; it can retry /fail
        logger.warning("[render_plane] fetch spec lookup failed: %s", type(exc).__name__)
    return {
        "ok": True,
        "job_id": job_id,
        "tenant_id": job.get("tenant_id"),
        "creative_id": job.get("creative_id"),
        "revision": job.get("revision"),
        "spec_hash": job.get("spec_hash"),
        "template_id": job.get("template_id"),
        "aspect_ratio": job.get("aspect_ratio"),
        "spec": spec,
    }


__all__ = ["FLAG_ENV", "TOKEN_ENV", "TOKEN_HEADER", "router"]
