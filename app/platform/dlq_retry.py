"""DLQ auto-retry sweep (failed Celery staff-jobs ko khud dobara chalao).

PROBLEM: worker.py `on_task_failure` failed tasks ko Redis `dlq:failed_tasks`
me record karta hai — par wahan se nikaalna MANUAL tha (`POST /infra/dlq/retry`).
Koi dekhe hi nahi to failed job pade-pade automation gap ban jata.

YEH MODULE: watchdog job (hourly) me wired sweep —
  - DLQ se items pop karo, sirf STAFF_JOBS parse karo (side-effect-safe:
    legacy/unknown tasks blindly retry NAHI hote → `dlq:dead` me move).
  - Per-job attempt count Redis hash `dlq:retry_counts` me (6h TTL) —
    MAX_ATTEMPTS (2) ke baad job `dlq:dead` me + (gated) email alert.
  - Re-dispatch: Celery owner ho (RUN_IN_PROCESS_SCHEDULER=0) to
    `run_staff_job.apply_async(countdown=backoff)`; warna direct in-process
    `team_scheduler._run_job` await.

GATED `DLQ_AUTO_RETRY=1` (default OFF = aaj jaisa, sirf record). Import-safe,
kabhi raise nahi, Redis down = silent skip. (automation_health pattern.)
"""

from __future__ import annotations

import ast
import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

DLQ_KEY = "dlq:failed_tasks"
DEAD_KEY = "dlq:dead"
COUNTS_KEY = "dlq:retry_counts"
COUNTS_TTL_S = 12 * 3600  # attempt-counts 12h baad reset (transient-failure count zinda rahe)
MAX_ATTEMPTS = 3  # 3 auto-retries before dead-queue — transient 429/500/timeout ko recover hone ka extra chance (tha 2)
BACKOFF_BASE_S = 120  # attempt n → n*120s countdown (celery path)


def _enabled() -> bool:
    return os.environ.get("DLQ_AUTO_RETRY", "0").strip().lower() in ("1", "true", "yes")


def _celery_owns_jobs() -> bool:
    """RUN_IN_PROCESS_SCHEDULER=0 = celery worker/beat owner (live default ab yahi)."""
    return os.environ.get("RUN_IN_PROCESS_SCHEDULER", "1").strip().lower() in ("0", "false", "no")


def _redis():
    import redis as _redis

    from app.config import settings

    return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)


def parse_staff_job(rec: dict[str, Any]) -> str | None:
    """DLQ record ke `args` str se staff-job naam nikaalo (warna None).
    on_task_failure args ko str() karke save karta — e.g. "('content',)"."""
    try:
        from app.tasks.staff_jobs import STAFF_JOBS

        raw = rec.get("args") or ""
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, (list, tuple)) and parsed:
                cand = str(parsed[0])
                if cand in STAFF_JOBS:
                    return cand
        except Exception:
            pass
        # fallback: substring match (args format badle to bhi pakde)
        for job in STAFF_JOBS:
            if f"'{job}'" in raw or f'"{job}"' in raw:
                return job
    except Exception:
        pass
    return None


async def _dispatch(job: str, attempt: int) -> str:
    """Job dobara chalao. Return: 'celery' ya 'inprocess' (kaise dispatch hua)."""
    if _celery_owns_jobs():
        from app.tasks.staff_jobs import run_staff_job

        run_staff_job.apply_async(args=(job,), countdown=attempt * BACKOFF_BASE_S)
        return "celery"
    # in-process mode: seedha chalao (defensive — _run_job kabhi raise nahi karta
    # except job-level, jo heartbeat me dikh jata)
    from app.platform import team_scheduler

    try:
        await team_scheduler._run_job(job)
    except Exception as e:
        logger.warning(f"[dlq_retry] in-process retry of '{job}' failed: {e}")
    return "inprocess"


async def _alert_dead(dead_jobs: list[str]) -> None:
    notify = os.environ.get("NOTIFY_EMAIL", "").strip()
    if not notify or not dead_jobs:
        return
    try:
        from app.integrations.email_sender import email_sender

        await email_sender.send_email(
            [notify],
            f"⚠️ DLQ: {len(dead_jobs)} job(s) retry ke baad bhi FAIL — manual dekho",
            "Yeh jobs auto-retry (max "
            + str(MAX_ATTEMPTS)
            + " attempts) ke baad bhi fail rahe — ab `dlq:dead` me hain:\n\n- "
            + "\n- ".join(dead_jobs)
            + "\n\nInspect: GET /api/growth/infra/dlq?key=dead · logs: docker logs leadgen_worker (dlq_retry)",
        )
    except Exception as e:
        logger.warning(f"[dlq_retry] dead-alert email failed: {e}")


def _queue_flooded(r=None) -> bool:
    """D3: celery queue depth cap se zyada hai? Tab DLQ retry-sweep DEFER karo —
    flooded queue pe rpop+re-enqueue = retry-storm (known 'llen celery >500 = del'
    gotcha). Items DLQ me rehte (no loss), agla sweep retry karega. Gated
    QUEUE_DEPTH_BACKPRESSURE; INERT (False) unset pe. Best-effort — error = not flooded."""
    if os.environ.get("QUEUE_DEPTH_BACKPRESSURE", "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    try:
        cap = int(os.environ.get("QUEUE_DEPTH_CAP", "800") or "800")
        r = r or _redis()
        if r is None:
            return False
        depth = int(r.llen("celery") or 0)
        if depth > cap:
            logger.warning(
                f"[dlq_retry] queue backpressure: celery depth {depth} > {cap} — DLQ sweep deferred"
            )
            return True
    except Exception:
        return False
    return False


async def run_sweep(max_items: int = 20, r=None, force: bool = False) -> dict[str, Any]:
    """DLQ sweep: staff-jobs retry (backoff), exhausted/unknown → dlq:dead.
    KABHI raise nahi. Flag off = no-op summary (force=True manual API ke liye)."""
    out: dict[str, Any] = {"enabled": _enabled(), "retried": [], "dead": [], "skipped": 0}
    if not (_enabled() or force):
        return out
    try:
        r = r or _redis()
        # D3: agar celery queue flooded hai to retry-storm mat banao — DLQ items
        # rehne do (no loss), manual force=True isko bypass karta.
        if not force and _queue_flooded(r):
            out["deferred"] = "queue_flooded"
            return out
        dead_alerts: list[str] = []
        for _ in range(max(1, min(max_items, 100))):
            raw = r.rpop(DLQ_KEY)
            if not raw:
                break
            try:
                rec = json.loads(raw)
            except Exception:
                r.lpush(DEAD_KEY, raw)
                out["skipped"] += 1
                continue
            job = parse_staff_job(rec)
            if not job:
                # legacy/unknown task — blind retry side-effect risk (calls/emails) → dead
                r.lpush(DEAD_KEY, json.dumps(rec, ensure_ascii=False))
                out["skipped"] += 1
                continue
            attempts = int(r.hincrby(COUNTS_KEY, job, 1) or 1)
            r.expire(COUNTS_KEY, COUNTS_TTL_S)
            if attempts > MAX_ATTEMPTS:
                rec["dead_reason"] = f"max {MAX_ATTEMPTS} auto-retries exhausted"
                r.lpush(DEAD_KEY, json.dumps(rec, ensure_ascii=False))
                out["dead"].append(job)
                dead_alerts.append(f"{job} ({rec.get('error', '')[:80]})")
                continue
            how = await _dispatch(job, attempts)
            out["retried"].append({"job": job, "attempt": attempts, "via": how})
        r.ltrim(DEAD_KEY, 0, 499)
        if dead_alerts:
            await _alert_dead(dead_alerts)
        if out["retried"] or out["dead"]:
            logger.info(f"[dlq_retry] sweep: {out}")
            try:
                from app.platform import team

                team.log_event(
                    "kavya",
                    "dlq_retry",
                    f"retried {len(out['retried'])}, dead {len(out['dead'])}, skipped {out['skipped']}",
                    status="ok" if not out["dead"] else "warn",
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[dlq_retry] sweep failed: {e}")
        out["error"] = str(e)[:120]
    return out
