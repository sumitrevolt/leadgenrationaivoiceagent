"""DLQ auto-retry sweep (failed Celery staff-jobs ko khud dobara chalao).

PROBLEM: worker.py `on_task_failure` failed tasks ko Redis `dlq:failed_tasks`
me record karta hai — par wahan se nikaalna MANUAL tha (`POST /infra/dlq/retry`).
Koi dekhe hi nahi to failed job pade-pade automation gap ban jata.

YEH MODULE: watchdog job (hourly) me wired sweep —
  - DLQ se items pop karo, sirf STAFF_JOBS parse karo (side-effect-safe:
    legacy/unknown tasks blindly retry NAHI hote → `dlq:dead` me move).
  - Per-job attempt count Redis key `dlq:retry:{job}` me (12h TTL) —
    MAX_ATTEMPTS ke baad job `dlq:dead` me + (gated) email alert.
    (Shared-hash TTL hata diya — kisi job ka incr doosri job ka cap reset na kare.)
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
COUNTS_KEY = "dlq:retry_counts"  # legacy shared-hash (unused for writes; kept for ops grep)
COUNT_KEY_PREFIX = "dlq:retry:"  # per-job key → deterministic TTL / MAX_ATTEMPTS
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
            if isinstance(parsed, list | tuple) and parsed:
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
    try:
        from app.platform.owner_os import record_scheduler_skip, scheduler_dispatch_allowed

        allowed, reason = scheduler_dispatch_allowed(job=job)
        if not allowed:
            record_scheduler_skip(job, reason, source="dlq_retry._dispatch")
            return "skipped_owner_schedulers"
    except Exception:
        pass
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
            count_key = f"{COUNT_KEY_PREFIX}{job}"
            attempts = int(r.incr(count_key) or 1)
            r.expire(count_key, COUNTS_TTL_S)
            if attempts >= MAX_ATTEMPTS:
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


RESOLVED_KEY = "dlq:resolved"
_RESOLUTIONS = frozenset(
    {
        "RECOVERED",
        "ALREADY_COMPLETED",
        "SUPERSEDED",
        "STALE_EXPIRED",
        "NON_RETRYABLE",
        "MANUAL_REVIEW_REQUIRED",
    }
)


def resolve_from_list(
    *,
    source_key: str,
    resolution: str,
    job: str | None = None,
    note: str = "",
    max_items: int = 50,
    r=None,
) -> dict[str, Any]:
    """Move matching DLQ records to ``dlq:resolved`` with audited resolution.

    Does NOT blind-purge: every moved record keeps original fields + resolution
    metadata. Physical source list shrinks only for matched items; unmatched stay.
    Never raises.
    """
    out: dict[str, Any] = {"moved": 0, "kept": 0, "resolution": resolution, "source": source_key}
    if resolution not in _RESOLUTIONS:
        out["error"] = f"invalid_resolution:{resolution}"
        return out
    if source_key not in (DLQ_KEY, DEAD_KEY):
        out["error"] = f"invalid_source:{source_key}"
        return out
    try:
        r = r or _redis()
        n = int(r.llen(source_key) or 0)
        kept: list[str] = []
        moved_jobs: list[str] = []
        for _ in range(min(n, max(1, max_items))):
            raw = r.rpop(source_key)
            if not raw:
                break
            try:
                rec = json.loads(raw)
            except Exception:
                kept.append(raw if isinstance(raw, str) else raw.decode("utf-8", "ignore"))
                out["kept"] += 1
                continue
            job_name = parse_staff_job(rec) or ""
            if job and job_name != job:
                kept.append(json.dumps(rec, ensure_ascii=False))
                out["kept"] += 1
                continue
            rec["resolution"] = resolution
            rec["resolved_at"] = (
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            )
            if note:
                rec["resolution_note"] = str(note)[:200]
            r.lpush(RESOLVED_KEY, json.dumps(rec, ensure_ascii=False))
            out["moved"] += 1
            moved_jobs.append(job_name or "?")
        for item in reversed(kept):
            r.lpush(source_key, item)
        r.ltrim(RESOLVED_KEY, 0, 999)
        out["moved_jobs"] = moved_jobs
        if out["moved"]:
            logger.info(f"[dlq_retry] resolve {source_key}: {out}")
    except Exception as e:
        out["error"] = str(e)[:160]
        logger.warning(f"[dlq_retry] resolve failed: {e}")
    return out


__all__ = [
    "parse_staff_job",
    "run_sweep",
    "resolve_from_list",
    "DLQ_KEY",
    "DEAD_KEY",
    "RESOLVED_KEY",
]
