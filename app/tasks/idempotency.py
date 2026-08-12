"""Celery task idempotency — prevent duplicate side effects on retry.

Usage: wrap any task function with @idempotent_task(task_name, ttl=3600)
Redis setnx with task_id = dedup. TTL = window jisme retry acceptable.
"""

from __future__ import annotations

import functools
import hashlib
import os
from typing import Any, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _redis_client():
    try:
        import redis as _redis

        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        return _redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def idempotent_task(task_name: str, ttl: int = 3600) -> Callable:
    """Decorator: Celery task ko idempotent banao (Redis setnx dedup)."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            task_id = (
                kwargs.get("task_id")
                or getattr(self, "request", None)
                and getattr(self.request, "id", None)
            )
            if not task_id:
                task_id = f"{task_name}:{hashlib.sha1(str(args).encode()).hexdigest()[:16]}"

            # Include the retry count: a genuine self.retry() reuses the same task_id,
            # so without this the retry hits the live key and is skipped as a "duplicate"
            # — silently swallowing the failure (never re-runs, never reaches the DLQ).
            # True redeliveries of the SAME attempt keep the same retries → still deduped.
            retries = getattr(getattr(self, "request", None), "retries", 0) or 0
            key = f"celery:idem:{task_name}:{task_id}:{retries}"
            r = _redis_client()
            if r:
                try:
                    if not r.set(key, "1", nx=True, ex=ttl):
                        logger.info(f"[idempotency] skip duplicate: {key}")
                        return {"ok": True, "skipped": "duplicate", "task": task_name}
                except Exception as e:
                    logger.warning(f"[idempotency] redis check failed: {e}")

            return fn(self, *args, **kwargs)

        return wrapper

    return decorator
