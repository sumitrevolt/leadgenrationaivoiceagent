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

_RUNS = os.path.join("data", "job_runs.jsonl")
_BEATS = os.path.join("data", "job_heartbeats.json")

# job -> max-gap (minutes) jiske baad OVERDUE (cadence + generous grace)
EXPECTED_GAP_MIN = {
    "growth": 60,            # 15-min job, 1h grace
    "ops": 180,              # hourly
    "reply_triage": 180,
    "watchdog": 180,
    "onboard": 180,
    "qa": 30 * 60,           # daily (30h)
    "trainer": 30 * 60,
    "blog": 30 * 60,
    "content": 30 * 60,
    "digest": 30 * 60,
    "prospect": 30 * 60,
    "email_outreach": 30 * 60,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _alerts_enabled() -> bool:
    return os.environ.get("AUTOMATION_HEALTH_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def record_run(job: str, ok: bool = True, seconds: float = 0.0, note: str = "") -> None:
    """Job-run heartbeat (scheduler wrapper se). KABHI raise nahi, fast."""
    try:
        rec = {
            "job": (job or "?")[:30],
            "ok": bool(ok),
            "s": round(float(seconds), 2),
            "note": (note or "")[:120],
            "at": _now().isoformat(timespec="seconds"),
        }
        os.makedirs(os.path.dirname(_RUNS) or ".", exist_ok=True)
        with open(_RUNS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # latest-per-job snapshot (fast reads)
        beats: dict[str, Any] = {}
        try:
            if os.path.exists(_BEATS):
                with open(_BEATS, encoding="utf-8") as f:
                    beats = json.load(f) or {}
        except Exception:
            beats = {}
        beats[rec["job"]] = rec
        with open(_BEATS, "w", encoding="utf-8") as f:
            json.dump(beats, f, ensure_ascii=False)
    except Exception:
        pass


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
    return {
        "status": "degraded" if overdue else ("warming_up" if never_ran else "healthy"),
        "overdue": overdue,
        "never_ran": never_ran,
        "jobs": jobs,
        "at": _now().isoformat(timespec="seconds"),
    }


async def run_watch() -> dict[str, Any]:
    """Watchdog hook: overdue jobs → (gated) email alert. Kabhi raise nahi."""
    try:
        h = health()
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
