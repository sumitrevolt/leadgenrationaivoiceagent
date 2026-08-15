"""Celery tasks for the onboarding factory pipeline.

Each stage is a Celery task with:
  - Per-stage retry with exponential backoff
  - DLQ on permanent failure (stage executor returns ok=False)
  - Idempotency via Redis setnx (skip duplicate runs of same stage)
  - Backpressure check before starting
  - Capacity metrics recording

Feature flag: ONBOARDING_PIPELINE=0 (default OFF)

Usage:
    # Run full pipeline for a client
    run_onboard_pipeline.delay("client_id")

    # Run from a specific stage (resume)
    run_onboard_pipeline.delay("client_id", start_from="content_pack")
"""

from __future__ import annotations

import os
from typing import Any

from celery import shared_task

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _run_async(coro):
    """Run async function from sync Celery task."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=600)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@shared_task(
    bind=True,
    name="app.tasks.onboard_pipeline.run_onboard_pipeline",
    max_retries=2,
    default_retry_delay=60,
    acks_late=False,
    soft_time_limit=540,
    time_limit=600,
)
def run_onboard_pipeline(
    self,
    cid: str,
    *,
    force: bool = False,
    send_welcome: bool = True,
    start_from: str | None = None,
    _attempt: int = 0,
) -> dict[str, Any]:
    """Run the full onboarding pipeline for one client.

    Each invocation runs all pending stages. If a stage fails, the task
    retries (up to max_retries=2) from the failed stage. After exhausting
    retries, the failure is recorded and the stage remains in 'failed' state
    in Redis so it can be picked up by DLQ retry sweep.

    Backpressure: checks active pipeline count before starting.
    Idempotency: completed stages are skipped on re-run.
    Never raises — returns result dict.
    """
    if not _flag("ONBOARDING_PIPELINE"):
        return {"ok": False, "client_id": cid, "skipped": "flag_off"}

    from app.marketing.onboarding_factory import (
        check_backpressure,
        decrement_active,
        get_pipeline_status,
        increment_active,
        run_pipeline,
    )

    # Backpressure check
    ok, reason = check_backpressure()
    if not ok:
        logger.warning("[onboard_pipeline] backpressure: %s for client %s", reason, cid)
        # Retry with backoff (30s × attempt)
        return {
            "ok": False,
            "client_id": cid,
            "skipped": "backpressure",
            "reason": reason,
            "retry_scheduled": True,
        }

    # Idempotency: check if pipeline already completed
    status = get_pipeline_status(cid)
    if status.get("status") == "completed" and not force:
        return {"ok": True, "client_id": cid, "skipped": "pipeline_already_completed"}

    increment_active()
    try:
        result = _run_async(
            run_pipeline(
                cid,
                force=force,
                send_welcome=send_welcome,
                start_from=start_from,
            )
        )

        # If pipeline failed at a stage, retry from that stage
        if not result.get("overall_ok") and _attempt < self.max_retries:
            failed_at = result.get("failed_at")
            if failed_at:
                logger.info(
                    "[onboard_pipeline] stage %s failed for %s, retrying (attempt %d)",
                    failed_at,
                    cid,
                    _attempt + 1,
                )
                raise self.retry(
                    kwargs={
                        "cid": cid,
                        "force": force,
                        "send_welcome": send_welcome,
                        "start_from": failed_at,
                        "_attempt": _attempt + 1,
                    },
                    countdown=60 * (_attempt + 1),  # exponential: 60s, 120s
                )

        return result

    except self.MaxRetriesExceededError:
        logger.warning(
            "[onboard_pipeline] max retries exceeded for %s, stage %s",
            cid,
            status.get("failed_at", "unknown"),
        )
        return {"ok": False, "client_id": cid, "error": "max_retries_exceeded"}
    except Exception as exc:
        # Unexpected error — don't retry, record to DLQ
        logger.warning("[onboard_pipeline] unexpected error for %s: %s", cid, exc)
        return {"ok": False, "client_id": cid, "error": str(exc)[:200]}
    finally:
        decrement_active()


@shared_task(
    bind=True,
    name="app.tasks.onboard_pipeline.run_single_stage",
    max_retries=3,
    default_retry_delay=30,
    acks_late=False,
    soft_time_limit=180,
    time_limit=210,
)
def run_single_stage(
    self,
    cid: str,
    stage: str,
    *,
    _attempt: int = 0,
) -> dict[str, Any]:
    """Run a single pipeline stage (for manual retry from admin UI).

    Used when admin clicks 'Retry' on a failed stage in the dashboard.
    """
    if not _flag("ONBOARDING_PIPELINE"):
        return {"ok": False, "client_id": cid, "skipped": "flag_off"}

    from app.marketing.onboarding_factory import (
        STAGE_EXECUTORS,
        PipelineState,
        Stage,
        _redis,
        record_stage_metrics,
    )

    executor = STAGE_EXECUTORS.get(Stage(stage) if stage in [s.value for s in Stage] else stage)
    if not executor:
        return {"ok": False, "error": f"unknown_stage: {stage}"}

    r = _redis()
    state = PipelineState(cid, r)
    state.mark_stage(stage, "running")

    import time as _time

    t0 = _time.monotonic()
    try:
        result = _run_async(executor(cid, force=True, send_welcome=True))
        elapsed = _time.monotonic() - t0

        if result.get("ok") is False and result.get("error"):
            state.mark_stage(stage, "failed", result=result, error=result["error"])
            record_stage_metrics(stage, elapsed, False, r)
            if _attempt < self.max_retries:
                raise self.retry(
                    kwargs={"cid": cid, "stage": stage, "_attempt": _attempt + 1},
                    countdown=30 * (_attempt + 1),
                )
            return {"ok": False, "client_id": cid, "stage": stage, "error": result["error"]}

        state.mark_stage(stage, "done", result=result)
        record_stage_metrics(stage, elapsed, True, r)
        return {"ok": True, "client_id": cid, "stage": stage, "result": result}

    except self.MaxRetriesExceededError:
        return {"ok": False, "client_id": cid, "stage": stage, "error": "max_retries_exceeded"}
    except Exception as exc:
        elapsed = _time.monotonic() - t0
        state.mark_stage(stage, "failed", error=str(exc)[:500])
        record_stage_metrics(stage, elapsed, False, r)
        return {"ok": False, "client_id": cid, "stage": stage, "error": str(exc)[:200]}


@shared_task(
    bind=True,
    name="app.tasks.onboard_pipeline.batch_onboard",
    max_retries=0,
    acks_late=False,
    soft_time_limit=540,
    time_limit=600,
)
def batch_onboard(
    self,
    client_ids: list[str],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Onboard multiple clients sequentially with time budget.

    Used by the hourly sweep (AUTO_ONBOARD) and admin bulk-onboard.
    Respects ONBOARD_TIME_BUDGET_S. Each client runs through the pipeline.
    """
    if not _flag("ONBOARDING_PIPELINE"):
        return {"ok": False, "skipped": "flag_off", "count": len(client_ids)}

    from app.platform.job_time_budget import JobBudget

    budget = JobBudget.from_env("ONBOARD_TIME_BUDGET_S", label="onboard_pipeline")

    results: list[dict] = []
    onboarded = 0
    failed = 0
    skipped = 0

    for cid in client_ids:
        if not budget.ok(need=25.0):
            results.append({"client_id": cid, "skipped": "time_budget"})
            skipped += 1
            continue

        try:
            result = run_onboard_pipeline(cid, force=force)
            if isinstance(result, dict):
                if result.get("overall_ok") or result.get("ok"):
                    onboarded += 1
                elif result.get("skipped"):
                    skipped += 1
                else:
                    failed += 1
                results.append(result)
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            results.append({"client_id": cid, "error": str(exc)[:200]})

    return {
        "ok": True,
        "total": len(client_ids),
        "onboarded": onboarded,
        "failed": failed,
        "skipped": skipped,
        "budget": budget.snapshot(),
        "results": results[:10],  # cap response size
    }
