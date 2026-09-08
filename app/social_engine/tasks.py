"""social_engine.tasks — Celery (Redis) drain task. Worker isse import kare to register
hota; warna scheduler `process_queue()` direct drain karta (guaranteed). NEVER breaks import."""

from __future__ import annotations

import asyncio

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

drain_social_queue = None

try:
    from app.worker import celery_app

    @celery_app.task(name="social_engine.drain", bind=True, max_retries=2)
    def drain_social_queue(self, limit: int = 50):  # noqa: F811
        from app.social_engine import engine

        try:
            return asyncio.run(engine.process_queue(limit))
        except Exception as e:  # pragma: no cover
            logger.warning(f"[social_engine.task] drain failed: {e}")
            return {"error": str(e)[:150]}

except Exception as e:  # celery app unavailable at import (web-only / tests) — fine
    logger.debug(f"[social_engine] celery task not registered: {e}")
