"""Automation health / dead-man switch (Cronitor/healthchecks.io-pattern, free).

PROBLEM: koi scheduled job chupchaap chalna band ho jaye (jaise scheduler bug,
worker crash, import error) to pata hi nahi chalta — automation "chal raha
hoga" maan ke baith jaate hain. Yeh module har job-run HEARTBEAT record karta
(team_scheduler._run_job wrapper se — in-process YA Celery dono path cover) aur
expected cadence se compare karke OVERDUE jobs pakadta.

`run_watch()` watchdog-job me wired: overdue mile to email alert (gated
`AUTOMATION_HEALTH_ALERTS=1`; off = sirf log). Store: data/job_runs.jsonl
(latest-per-job snapshot data/job_heartbeats.json). Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

from app.platform.today_overview import _WEEKLY_ON, _job_due_today, _job_due_yet  # noqa: E402

_RUNS = os.path.join("data", "job_runs.jsonl")
_BEATS = os.path.join("data", "job_heartbeats.json")

# job -> max-gap (minutes) jiske baad OVERDUE (cadence + generous grace)
EXPECTED_GAP_MIN = {
    "growth": 60,  # 15-min job, 1h grace
    "ops": 180,  # hourly
    "reply_triage": 180,
    "watchdog": 180,
    "onboard": 180,
    "standup": 30 * 60,  # daily 08:00 IST
    "engineer_sre": 180,  # hourly :45
    "mcp_engineer": 180,  # hourly :40 (gated MCP_ENGINEER) — dead-man parity with STAFF_JOBS
    "engineer_finops": 30 * 60,
    "engineer_security": 30 * 60,
    "engineer_dbre": 30 * 60,
    "engineer_dataquality": 30 * 60,
    "engineer_deps": 8 * 24 * 60,
    "readiness_digest": 30 * 60,
    "qa": 30 * 60,  # daily (30h)
    "trainer": 30 * 60,
    "blog": 30 * 60,
    "content": 30 * 60,
    "digest": 30 * 60,
    "prospect": 30 * 60,
    "email_outreach": 24 * 60,  # hourly 9am-7pm; overnight ~14h gap → 24h grace (90h was a dead-man blind spot)
    "pipeline": 30 * 60,
    "email_followup": 24 * 60,  # hourly 9am-7pm; overnight ~14h gap → 24h grace
    "kb_refresh": 8 * 24 * 60,  # weekly Sun
    "midday_prospect": 30 * 60,  # daily 14:30
    "evening_wrap": 30 * 60,
    "weekly_marketing": 8 * 24 * 60,
    "saturday_hygiene": 8 * 24 * 60,
    "meter_watch": 180,  # hourly :55 (gated METER_ALERTS), 3h grace
    "process_autostart": 30 * 60,  # daily ~11:30 IST (gated PROCESS_AUTOSTART)
    "obsidian_push": 30 * 60,  # daily ~02:15 IST: second-brain compact + git push (_run_job heartbeats daily; job body no-ops unless OBSIDIAN_SYNC=1)
    "revenue_snapshot": 30 * 60,  # daily ~00:15 IST: B1 MRR/churn snapshot (gated REVENUE_TRENDS)
    "flow_cron": 30,  # every 5 min: Flow Runner cron scan (self-gates; beat always heartbeats)
    "afternoon_content": 30 * 60,  # daily 15:00 IST: 2nd content-gen pass (gated AFTERNOON_CONTENT)
    "evening_prospect": 30 * 60,  # daily 17:00 IST: 3rd free lead-harvest pass (gated EVENING_PROSPECT)
    "self_improve": 30,  # ~20-min tick; 30-min grace — watchdog now flags stale loop (dead-man trio complete)
    "platform_dial": 30 * 60,  # daily 11:30 IST: self-sale AI cold-call batch (gated PLATFORM_DIAL_DAILY)
    "call_kpi_digest": 30 * 60,  # daily 19:30 IST: Lekha call-KPI digest
    "product_one_health": 180,  # hourly :20 (2026-07-08): Product 1 Customer Health/Approval Reminder/SLA Recovery sweep, 3h grace like meter_watch
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _alerts_enabled() -> bool:
    return os.environ.get("AUTOMATION_HEALTH_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def record_run(
    job: str,
    ok: bool = True,
    seconds: float = 0.0,
    note: str = "",
    error_class: str = "",
    correlation_id: str = "",
) -> None:
    """Job-run heartbeat (scheduler wrapper se). KABHI raise nahi, fast.

    `error_class`/`correlation_id` additive 2026-07-07 (job-log schema audit
    finding) — optional, existing callers untouched. `error_class` = the
    exception TYPE name when `ok=False` and the caller actually has an
    exception object at this level (most jobs swallow+return False internally
    per sub-engine, so this stays "" for those — same honest partial coverage
    the audit found, just no longer silently discarded when the outer
    wrapper genuinely does have one)."""
    try:  # W1.13: per-job Prometheus counters (independent try — heartbeat pe asar na ho)
        from app.platform import job_metrics

        job_metrics.record(job, ok, seconds)
    except Exception:
        pass
    try:
        rec = {
            "job": (job or "?")[:30],
            "ok": bool(ok),
            "s": round(float(seconds), 2),
            "duration_ms": round(float(seconds) * 1000),
            "note": (note or "")[:120],
            "error_class": (error_class or "")[:60],
            "correlation_id": (correlation_id or "")[:60],
            "at": _now().isoformat(timespec="seconds"),
        }
        os.makedirs(os.path.dirname(_RUNS) or ".", exist_ok=True)
        with open(_RUNS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # latest-per-job snapshot (fast reads) — READ-MODIFY-WRITE, isliye
        # cross-process lock + atomic replace (web 2 workers + celery workers
        # ek saath record_run kar sakte = snapshot corrupt ho sakta tha).
        from app.utils.file_lock import file_lock

        with file_lock(_BEATS):
            beats: dict[str, Any] = {}
            try:
                if os.path.exists(_BEATS):
                    with open(_BEATS, encoding="utf-8") as f:
                        beats = json.load(f) or {}
            except Exception:
                beats = {}
            beats[rec["job"]] = rec
            tmp = f"{_BEATS}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(beats, f, ensure_ascii=False)
            os.replace(tmp, _BEATS)
    except Exception:
        pass


def queue_depth() -> dict[str, Any]:
    """Celery queue backlog (Redis llen). Backlog badhta jaye = worker mar gaya/slow.
    Redis na ho to {-1} (unknown). Kabhi raise nahi."""
    out = {"celery": -1, "heavy": -1, "dlq": -1, "dead": -1}
    try:
        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
        out["celery"] = int(r.llen("celery") or 0)
        out["heavy"] = int(r.llen("heavy") or 0)  # heavy staff-jobs queue (CELERY_HEAVY_QUEUE)
        out["dlq"] = int(r.llen("dlq:failed_tasks") or 0)
        out["dead"] = int(r.llen("dlq:dead") or 0)  # dlq_retry: retry-exhausted/unknown
    except Exception:
        pass
    return out


QUEUE_BACKLOG_ALERT = 50  # itne pending tasks = worker problem


def health() -> dict[str, Any]:
    """Per-job: last run, ok, overdue? + overall status. Kabhi raise nahi."""
    beats: dict[str, Any] = {}
    try:
        if os.path.exists(_BEATS):
            with open(_BEATS, encoding="utf-8") as f:
                beats = json.load(f) or {}
    except Exception:
        beats = {}
    jobs: list[dict[str, Any]] = []
    overdue: list[str] = []
    never_ran: list[str] = []
    for job, gap_min in EXPECTED_GAP_MIN.items():
        b = beats.get(job)
        if not b and (not _job_due_today(job) or not _job_due_yet(job)):
            jobs.append(
                {
                    "job": job,
                    "last_run": None,
                    "status": "scheduled_off",
                }
            )
            continue
        if not b:
            never_ran.append(job)
            jobs.append({"job": job, "last_run": None, "status": "never_ran"})
            continue
        try:
            last = datetime.fromisoformat(str(b.get("at")))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            is_over = _now() - last > timedelta(minutes=gap_min)
            status = "overdue" if is_over else ("ok" if b.get("ok") else "last_failed")
            if is_over:
                overdue.append(job)
            jobs.append(
                {
                    "job": job,
                    "last_run": b.get("at"),
                    "last_ok": b.get("ok"),
                    "duration_s": b.get("s"),
                    "status": status,
                }
            )
        except Exception:
            jobs.append({"job": job, "status": "unknown"})
    q = queue_depth()
    backlogged = (
        q.get("celery", -1) > QUEUE_BACKLOG_ALERT or q.get("heavy", -1) > QUEUE_BACKLOG_ALERT
    )
    # Obsidian staging health
    _obs_ok = False
    _obs_detail = "OBSIDIAN_SYNC not enabled"
    try:
        from pathlib import Path
        if os.getenv("OBSIDIAN_SYNC", "0") in ("1", "true"):
            _vault = Path("data/obsidian_staging")
            if _vault.exists():
                _files = list(_vault.rglob("*.md"))
                _obs_ok = len(_files) > 0
                _obs_detail = f"{len(_files)} notes in staging"
            else:
                _obs_detail = "staging dir missing"
    except Exception as e:
        _obs_detail = str(e)[:100]
    return {
        "status": (
            "degraded" if (overdue or backlogged) else ("warming_up" if never_ran else "healthy")
        ),
        # Explicit boolean truth for consumers — pehle sirf `status` string tha, jisse
        # `h.get("ok")` KABHI None deta tha (team_pulse._kavya `h.get("ok", True)` = hamesha
        # "OK" bolta tha even jab jobs overdue/queue-backlogged the → false-healthy). Ab
        # additive `ok` = degraded ka inverse (warming_up abhi-boot = ok, alarm nahi).
        "ok": not (overdue or backlogged),
        "overdue": overdue,
        "never_ran": never_ran,
        "queue": q,
        "queue_backlogged": backlogged,
        "jobs": jobs,
        "obsidian_sync": {"ok": _obs_ok, "detail": _obs_detail},
        "at": _now().isoformat(timespec="seconds"),
    }


async def run_watch() -> dict[str, Any]:
    """Watchdog hook: overdue jobs → (gated) email alert. Kabhi raise nahi."""
    try:
        h = health()
        if h.get("queue_backlogged") and _alerts_enabled():
            notify = os.environ.get("NOTIFY_EMAIL", "").strip()
            if notify:
                try:
                    from app.integrations.email_sender import email_sender

                    await email_sender.send_email(
                        [notify],
                        f"⚠️ Celery backlog: {h['queue'].get('celery')} tasks pending",
                        "Worker slow/mar gaya lagta hai. Check: docker logs leadgen_worker (automation_health)",
                    )
                except Exception:
                    pass
        if h["overdue"] and _alerts_enabled():
            notify = os.environ.get("NOTIFY_EMAIL", "").strip()
            if notify:
                try:
                    from app.integrations.email_sender import email_sender

                    await email_sender.send_email(
                        [notify],
                        f"⚠️ Automation DEAD-MAN alert: {len(h['overdue'])} job(s) overdue",
                        "Yeh scheduled jobs expected time pe NAHI chale:\n\n- "
                        + "\n- ".join(h["overdue"])
                        + "\n\nCelery worker/scheduler containers check karo: docker ps | grep leadgen. "
                        "(automation_health dead-man switch)",
                    )
                except Exception as e:
                    logger.warning(f"[automation_health] alert failed: {e}")
        try:
            from app.platform import team

            team.log_event(
                "kavya",
                "automation_health",
                f"{h['status']}: {len(h['overdue'])} overdue, {len(h['never_ran'])} never-ran",
                status="ok" if h["status"] == "healthy" else "warn",
            )
        except Exception:
            pass
        return h
    except Exception as e:
        logger.warning(f"[automation_health] run_watch failed: {e}")
        return {"error": str(e)}
