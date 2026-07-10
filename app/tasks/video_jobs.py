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
