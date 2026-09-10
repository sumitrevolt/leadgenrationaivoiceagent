"""Celery entrypoint for canonical-DevTask lease reconciliation (INERT by default).

This module is NOT in ``app.worker.celery_app`` include list yet, so importing
it has no runtime effect today — it exists so the beat entry is a one-line
change when we are ready:

    # app/worker.py
    include=[..., "app.tasks.dev_task_reconcile", ...]
    celery_app.conf.beat_schedule["dev-tasks-reconcile"] = {
        "task": "dev_tasks.reconcile_leases",
        "schedule": 60.0,          # every minute
        "kwargs": {"max_retries": 3, "limit": 200},
    }

The task body only calls ``reconcile_expired_leases_sync``, which is bounded,
idempotent and never raises — a beat tick can therefore never wedge the
scheduler, and a reconcile hiccup can never mark a task FAILED spuriously.

Gates untouched: no deployment, no WhatsApp, no payments, no compliance logic.
"""

from __future__ import annotations

import logging
from typing import Any

from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="dev_tasks.reconcile_leases", bind=True, max_retries=0)
def reconcile_leases_task(
    self=None, *, max_retries: int = 3, limit: int = 200
) -> dict[str, Any]:
    """Reclaim expired DevTask leases. Safe to run on a beat; never raises."""
    from app.dev_control.reconcile import reconcile_expired_leases_sync

    result = reconcile_expired_leases_sync(max_retries=max_retries, limit=limit)
    if not result.get("ok"):
        logger.warning("dev_tasks.reconcile_leases degraded: %s", result.get("reason"))
    return result
