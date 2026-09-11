"""Celery task wrapper for the video-creative pipeline — routes to the
dedicated 'video' queue when CELERY_VIDEO_QUEUE=1 (app/worker.py
_route_video_task), falls back to the default queue otherwise. HEAVY
(ffmpeg) — never call render_creative_video directly from a web request."""

from __future__ import annotations

import asyncio
from typing import Any

from app.utils.logger import setup_logger
from app.worker import celery_app

logger = setup_logger(__name__)


@celery_app.task(name="app.tasks.video_jobs.build_creative_video_task")
def build_creative_video_task(
    recipe: str = "generic",
    *,
    business_name: str,
    niche: str = "general",
    slides: list[str] | None = None,
    offer: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    from app.marketing import video_pipeline

    try:
        return asyncio.run(
            video_pipeline.render_creative_video(
                recipe=recipe,
                business_name=business_name,
                niche=niche,
                slides=slides,
                offer=offer,
                client_id=client_id,
            )
        )
    except Exception as e:
        logger.warning(f"[video_jobs] build_creative_video_task unexpected failure: {e}")
        return {"error": str(e)[:200]}


def _render_soft_limit() -> int:
    """Celery deadline — must be the OUTERMOST of the three nested timeouts.

    Inward ordering: hyperframes subprocess < creative_os worker_timeout_s <
    THIS. A full-HD HyperFrames render takes ~2 min, far beyond the 300s that
    sufficed for the deterministic FFmpeg provider, and if Celery fires first the
    provider's Chrome children are orphaned instead of reaped.
    """
    import os

    try:
        return max(120, min(3600, int(os.getenv("CREATIVE_VIDEO_SOFT_TIME_LIMIT_S", "1200"))))
    except Exception:
        return 1200


@celery_app.task(
    name="app.tasks.video_jobs.daily_video_client_task",
    bind=True,
    max_retries=1,
    soft_time_limit=_render_soft_limit(),
    time_limit=_render_soft_limit() + 120,
)
def daily_video_client_task(self, *, client_id: str) -> dict[str, Any]:
    """One client's DAILY classic (deterministic ffmpeg) video ad.

    Enqueued by ``app.marketing.daily_video.run_daily`` with
    ``task_id=daily_video:{client_id}:{YYYY-MM-DD}`` so a re-fired beat cannot
    render the same client twice in a day. HEAVY — never called from the web
    process; the producer only dispatches.
    """
    from app.tasks.idempotency import idempotent_task

    @idempotent_task("daily_video_client", ttl=20 * 3600)
    def _guarded(task_self, cid: str) -> dict[str, Any]:
        from app.marketing import video_ad_cycle

        return asyncio.run(video_ad_cycle.generate_for_client(cid))

    try:
        return _guarded(self, str(client_id))
    except Exception as e:
        logger.warning(f"[video_jobs] daily_video_client_task failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


@celery_app.task(
    name="app.tasks.video_jobs.render_creative_os_task",
    bind=True,
    max_retries=1,
    soft_time_limit=_render_soft_limit(),
    time_limit=_render_soft_limit() + 120,
)
def render_creative_os_task(
    self,
    *,
    tenant_id: str,
    creative_id: str,
    revision: int = 0,
) -> dict[str, Any]:
    """Creative Automation OS worker — heavy render + QA for one creative revision.

    Idempotent via Celery task_id ``creative_os:{id}:rev{N}`` set by the enqueue path.
    Never invoked from the FastAPI web process for production traffic.
    """
    try:
        from app.marketing.creative_os.service import process_generation

        return process_generation(str(tenant_id), str(creative_id))
    except Exception as e:
        logger.warning(f"[video_jobs] render_creative_os_task failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


# --------------------------------------------------------------------------- #
# Render plane (T02) — VPS-side lease maintenance + completion bridge.
# --------------------------------------------------------------------------- #
@celery_app.task(
    name="app.tasks.video_jobs.render_plane_lease_task",
    bind=True,
    max_retries=0,
)
def render_plane_lease_task(
    self=None,
    *,
    max_retries: int = 3,
    limit: int = 200,
    enqueue: bool = True,
) -> dict[str, Any]:
    """VPS-side render-plane maintenance + completion bridge (safe on a beat).

    Bounded, idempotent and never raises:
      1. reclaim expired render leases (the SAME pure ``lease_policy`` decision
         the control plane uses);
      2. optionally create render jobs for creatives still ``queued`` so the local
         worker has something to lease (idempotent by ``job_id``);
      3. bridge completed render jobs back into ``service.process_generation`` so
         a finished local render enters QA exactly once.
    """
    try:
        return asyncio.run(
            _render_plane_lease_async(max_retries=max_retries, limit=limit, enqueue=enqueue)
        )
    except Exception as e:
        logger.warning(f"[video_jobs] render_plane_lease_task failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def _render_plane_lease_async(
    *, max_retries: int, limit: int, enqueue: bool
) -> dict[str, Any]:
    from app.models.base import get_async_session
    from app.render_plane import jobstore

    out: dict[str, Any] = {"ok": True, "queued": 0, "bridged": 0}
    async with get_async_session() as db:
        out["reclaimed"] = await jobstore.reclaim_render_leases(
            db, max_retries=max_retries, limit=limit
        )
        if enqueue:
            out["queued"] = await _enqueue_render_jobs(db, jobstore, limit=limit)
        out["bridged"] = await _bridge_done_jobs(db, jobstore, limit=limit)
    return out


async def _enqueue_render_jobs(db, jobstore, *, limit: int) -> int:
    """Create render jobs for creatives still `queued`. Returns how many were new."""
    from app.marketing import delivery_ledger
    from app.marketing.creative_os.store import list_records

    created = 0
    try:
        listed = list_records("", status="queued", limit=limit)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[video_jobs] render_plane enqueue scan failed: {e}")
        return 0
    for item in (listed.get("items") or [])[:limit]:
        tid = str(item.get("tenant_id") or "")
        cid = str(item.get("creative_id") or "")
        rev = int(item.get("approval_revision") or 0)
        if not tid or not cid:
            continue
        res = await jobstore.create_job(db, tenant_id=tid, creative_id=cid, revision=rev)
        if res.get("ok") and res.get("created"):
            created += 1
            try:
                delivery_ledger.log_event(
                    tid, "render_plane_queued", detail=f"{cid}:rev{rev}"
                )
            except Exception:
                pass
    return created


async def _bridge_done_jobs(db, jobstore, *, limit: int) -> int:
    """Feed finished render jobs into `process_generation` (idempotent)."""
    from app.marketing.creative_os.store import get_record

    bridged = 0
    try:
        listed = await jobstore.list_jobs(db, state="done", limit=limit)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[video_jobs] render_plane bridge scan failed: {e}")
        return 0
    for job in listed.get("items") or []:
        tid = str(job.get("tenant_id") or "")
        cid = str(job.get("creative_id") or "")
        rev = int(job.get("revision") or 0)
        if not tid or not cid:
            continue
        try:
            rec = get_record(tid, cid)
        except Exception:
            continue
        if not rec.get("ok"):
            continue
        status = str((rec.get("record") or {}).get("status") or "")
        # process_generation is idempotent for terminal states; only a creative
        # that has NOT advanced yet needs the bridge.
        if status not in ("queued", "generating"):
            continue
        try:
            # Reuse the existing dispatch seam (idempotency key + eager fallback).
            from app.marketing.creative_os import service as _creative_service

            _creative_service._enqueue_celery(tid, cid, rev)
            bridged += 1
        except Exception:
            continue
    return bridged


# --------------------------------------------------------------------------- #
# Delivery (T03 implementation) — thin one-line delegations, sole-writer T02.
# --------------------------------------------------------------------------- #
@celery_app.task(
    name="app.tasks.video_jobs.video_delivery_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
)
def video_delivery_task(
    self,
    *,
    tenant_id: str,
    creative_id: str,
    revision: int = 0,
    caption: str = "",
) -> dict[str, Any]:
    """Durable async send of ONE approved video to Telegram (customer + ops).

    Idempotent by construction: deliver_video skips any target already holding a
    `deliver:<creative>:rev<N>:<target>` receipt, so a redelivery cannot
    double-message. Fail-closed: flag off / no token => honest no-op, never a
    raise.
    """
    from app.marketing import video_delivery

    try:
        return video_delivery.deliver_video(
            str(tenant_id),
            str(creative_id),
            caption=str(caption or ""),
            revision=int(revision or 0),
            actor="celery",
        )
    except Exception as e:
        logger.warning(f"[video_jobs] video_delivery_task failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


@celery_app.task(
    name="app.tasks.video_jobs.video_delivery_retry_task",
    bind=True,
    max_retries=1,
    soft_time_limit=600,
    time_limit=720,
)
def video_delivery_retry_task(self, *, limit: int = 20) -> dict[str, Any]:
    """Drain the per-tenant delivery retry queue (bounded, exponential backoff)."""
    from app.marketing import video_delivery

    try:
        return video_delivery.process_retries(limit=int(limit or 20))
    except Exception as e:
        logger.warning(f"[video_jobs] video_delivery_retry_task failed: {e}")
        return {"ok": False, "error": str(e)[:200]}
