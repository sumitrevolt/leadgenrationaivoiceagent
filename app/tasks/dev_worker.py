"""INERT-by-default Celery entrypoint for the dev-task runner (Phase 3).

Registering this task does nothing on its own. It only executes work when
DEV_ORCHESTRATOR=1 AND DEV_WORKER_ENABLED=1, it is never on a beat schedule
(so it never self-fires), and it delegates to the draft-only ``run_dev_task``
which never applies a patch, commits, or deploys.
"""

from __future__ import annotations

import os

from app.platform.celery_async import run as run_async
from app.utils.logger import setup_logger
from app.worker import celery_app

logger = setup_logger(__name__)


def _enabled() -> bool:
    from app.dev_control.runner import worker_enabled

    return worker_enabled()


@celery_app.task(name="app.tasks.dev_worker.run_dev_task", bind=True, max_retries=2)
def run_dev_task_task(self, task_id: str, worker_id: str = "celery-dev-worker"):
    if not _enabled():
        return {"skipped": "disabled", "task_id": task_id}
    from app.dev_control.runner import run_dev_task
    from app.models.base import get_async_session

    async def _go():
        async with get_async_session() as db:
            return await run_dev_task(
                db,
                task_id,
                worker_id=worker_id,
                proposals_root=os.getenv("DEV_PROPOSALS_DIR", "data/dev_tasks"),
            )

    try:
        return run_async(_go())
    except Exception as exc:  # noqa: BLE001 — bounded retry, DLQ records the failure
        logger.error("dev_worker run failed for %s: %s", task_id, exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.tasks.dev_worker.reconcile_leases", bind=True)
def reconcile_leases_task(self):
    """Reclaim dead leases. INERT unless the worker feature is enabled."""
    if not _enabled():
        return {"skipped": "disabled"}
    from app.dev_control.reconcile import reconcile_leases
    from app.models.base import get_async_session

    async def _go():
        async with get_async_session() as db:
            return await reconcile_leases(db)

    return run_async(_go())
