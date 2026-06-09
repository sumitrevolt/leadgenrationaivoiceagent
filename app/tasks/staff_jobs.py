"""Durable Celery wrappers for the AI-staff periodic jobs.

WHY: aaj AI-staff automation (content, outreach, onboarding, watchdog, etc.)
in-process APScheduler loop (`app/platform/team_scheduler.py`) pe chalti hai —
ek hi process, app restart pe job miss/double ho sakta. Yeh module wahi jobs
Celery beat ke through **durable** chalata hai: dedicated worker, restart-safe
schedule, retry, aur dead-letter (worker.py `on_task_failure` -> Redis DLQ).

DORMANT by default — koi behaviour change nahi:
  - Yeh beat entries SIRF tab fire hote jab `celery beat` process chale
    (compose `--profile celery`). Default deployment me beat nahi chalta.
  - Default path aaj jaisa hi: in-process APScheduler (RUN_IN_PROCESS_SCHEDULER=1).

DURABLE path pe switch (double-run avoid):
    RUN_IN_PROCESS_SCHEDULER=0   # in-process loop band
    docker compose -f docker-compose.vps.yml --profile celery up -d
    # ab celery worker + celery beat owner; web process scheduler nahi chalata

Har job internally defensive hai (team_scheduler._run_job kabhi raise nahi karta);
Celery retry sirf invoke-level failure (import/loop) pe lagta hai.
"""

from __future__ import annotations

import asyncio

from celery import shared_task

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Same job names as team_scheduler._run_job dispatcher.
STAFF_JOBS = (
    "growth",
    "ops",
    "qa",
    "trainer",
    "digest",
    "content",
    "blog",
    "prospect",
    "email_outreach",
    "reply_triage",
    "watchdog",
    "onboard",
)


def _run_async(coro):
    """Async coroutine ko sync Celery task ke andar safely chalao (apna loop)."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass


@shared_task(
    bind=True,
    name="app.tasks.staff_jobs.run_staff_job",
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
def run_staff_job(self, job: str):
    """Ek AI-staff job durably chalao (team_scheduler._run_job ka Celery wrapper)."""
    if job not in STAFF_JOBS:
        logger.warning(f"[staff_jobs] unknown job '{job}' — skip")
        return {"ok": False, "job": job, "reason": "unknown"}
    try:
        from app.platform import team_scheduler

        _run_async(team_scheduler._run_job(job))
        return {"ok": True, "job": job}
    except Exception as e:  # invoke-level failure -> retry, fir DLQ
        logger.warning(f"[staff_jobs] job '{job}' invoke failed: {e}")
        raise self.retry(exc=e)
