"""Agent Scheduler — runtime job control (admin UI se, no-restart).

KYA: AI-staff scheduled jobs ka single registry (label/cadence/owner) + per-job
runtime enable/disable override + "run-due" recovery dispatch. Overrides
`data/scheduler_overrides.json` me rehte (bind-mounted => container rebuild
NAHI chahiye; admin toggle turant live).

KAHAN GATE LAGTA: `team_scheduler._run_job` (single choke-point — in-process
loop AUR Celery `staff_jobs.run_staff_job` DONO isi se guzarte). Isliye toggle
dono paths pe kaam karta hai; beat entry fire hoti hai par job body skip.

SAFETY:
- FAIL-OPEN: overrides file missing/corrupt/error => job ENABLED (aaj jaisa).
- Compliance gates (TRAI/DND/calling-window) job body ke ANDAR hain — yeh
  module unhe kabhi touch nahi karta, sirf staff-job dispatch skip karta hai.
- Import-safe, koi function kabhi raise nahi karta (record/log style).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OVERRIDES = os.path.join("data", "scheduler_overrides.json")

# ---------------------------------------------------------------------------
# Registry: har job jo team_scheduler._run_job dispatch karta hai.
# cadence = IST human string (source: team_scheduler.scheduler_loop windows +
# worker.py beat crontabs). Yeh DISPLAY-only hai — actual timing wahi 2 sources.
# ---------------------------------------------------------------------------
JOB_META: dict[str, dict[str, str]] = {
    "growth": {
        "label": "Growth pulse — funnel check + auto-action",
        "cadence": "har 15 min",
        "owner": "boss",
    },
    "flow_cron": {"label": "Flow Runner cron scan", "cadence": "har 5 min", "owner": "platform"},
    "ops": {"label": "System health check", "cadence": "hourly :05", "owner": "kavya"},
    "reply_triage": {
        "label": "Email replies padh ke draft jawab",
        "cadence": "hourly :20",
        "owner": "rohan",
    },
    "watchdog": {"label": "Kuch toota to email alert", "cadence": "hourly :35", "owner": "kavya"},
    "onboard": {
        "label": "Naye paid client ka auto-setup",
        "cadence": "hourly :50",
        "owner": "platform",
    },
    "mcp_engineer": {"label": "MCP health pulse (Arya)", "cadence": "hourly :40", "owner": "arya"},
    "engineer_sre": {
        "label": "Reliability score (Pranav SRE)",
        "cadence": "hourly :45",
        "owner": "pranav",
    },
    "meter_watch": {
        "label": "Billing meter-failure watcher",
        "cadence": "hourly :55",
        "owner": "platform",
    },
    "email_outreach": {
        "label": "Cold emails + warmup (cap 25/din)",
        "cadence": "9am-7pm hourly :05",
        "owner": "rohan",
    },
    "email_followup": {
        "label": "Day-3/7 follow-ups",
        "cadence": "9am-7pm hourly :20",
        "owner": "rohan",
    },
    "revenue_snapshot": {
        "label": "MRR/churn snapshot",
        "cadence": "daily 00:15",
        "owner": "platform",
    },
    "gsc_rank": {
        "label": "Google Search Console rank snapshot",
        "cadence": "daily 00:30",
        "owner": "platform",
    },
    "trial_nudge": {
        "label": "Trial expiry/expired Starter UPI nudge email",
        "cadence": "daily 09:50",
        "owner": "platform",
    },
    "obsidian_push": {
        "label": "Second-brain compact + git push",
        "cadence": "daily 02:15",
        "owner": "platform",
    },
    "qa": {"label": "Voice-agent quality test (Arjun)", "cadence": "daily 02:30", "owner": "arjun"},
    "trainer": {
        "label": "AI brain training/tuning (Meera)",
        "cadence": "daily 03:00",
        "owner": "meera",
    },
    "blog": {"label": "SEO blog post generate", "cadence": "daily 06:30", "owner": "isha"},
    "content": {
        "label": "Self + clients ke social posts",
        "cadence": "daily 07:00",
        "owner": "isha",
    },
    "standup": {"label": "Boss team standup", "cadence": "daily 08:00", "owner": "boss"},
    "digest": {"label": "Daily business summary email", "cadence": "daily 08:30", "owner": "boss"},
    "readiness_digest": {
        "label": "Activation-readiness ntfy digest",
        "cadence": "daily 08:30",
        "owner": "platform",
    },
    "engineer_finops": {
        "label": "Margin score (Vidya FinOps)",
        "cadence": "daily 09:00",
        "owner": "vidya",
    },
    "prospect": {
        "label": "Naye prospects dhoondna (niches rotation)",
        "cadence": "daily 09:30",
        "owner": "rohan",
    },
    "engineer_security": {
        "label": "Compliance posture (Arnav)",
        "cadence": "daily 09:30",
        "owner": "arnav",
    },
    "engineer_dbre": {
        "label": "Postgres reliability (Kabir)",
        "cadence": "daily 10:00",
        "owner": "kabir",
    },
    "engineer_dataquality": {
        "label": "Lead/CRM integrity (Diya)",
        "cadence": "daily 10:30",
        "owner": "diya",
    },
    "pipeline": {
        "label": "Lead rescore + hot-lead surfacing (Neha)",
        "cadence": "daily 11:00",
        "owner": "neha",
    },
    "daily_video": {
        "label": "Daily per-client video producer (gated DAILY_VIDEO_ENABLED; enqueue-only)",
        "cadence": "daily 09:45",
        "owner": "isha",
    },
    "platform_dial": {
        "label": "Self-sale AI cold-call batch",
        "cadence": "daily 11:30",
        "owner": "swara",
    },
    "process_autostart": {
        "label": "Process-engine auto-start",
        "cadence": "daily 11:30",
        "owner": "platform",
    },
    "midday_prospect": {
        "label": "2nd lead-supply pass",
        "cadence": "daily 14:30",
        "owner": "rohan",
    },
    "afternoon_content": {
        "label": "2nd content-gen pass",
        "cadence": "daily 15:00",
        "owner": "isha",
    },
    "evening_prospect": {
        "label": "3rd lead-harvest pass",
        "cadence": "daily 17:00",
        "owner": "rohan",
    },
    "evening_wrap": {"label": "EOD summary + hot recap", "cadence": "daily 18:30", "owner": "boss"},
    "call_kpi_digest": {
        "label": "Call-KPI digest (Lekha)",
        "cadence": "daily 19:30",
        "owner": "lekha",
    },
    "weekly_marketing": {
        "label": "S-tier niche marketing packs",
        "cadence": "Wed 12:30",
        "owner": "isha",
    },
    "engineer_deps": {
        "label": "Dependency CVE audit (Aryan)",
        "cadence": "Sun 04:30",
        "owner": "aryan",
    },
    "kb_refresh": {"label": "Contextual KB re-ingest", "cadence": "Sun 05:00", "owner": "meera"},
    "saturday_hygiene": {"label": "DLQ + celery trim", "cadence": "Sat 04:00", "owner": "kavya"},
    "hot_queue_brief": {
        "label": "Office HQ revenue brief (health-gated)",
        "cadence": "daily 08:15",
        "owner": "platform",
    },
    "product_one_health": {
        "label": "Product 1 Customer Health + SLA Recovery",
        "cadence": "hourly :20",
        "owner": "platform",
    },
    "approval_email_sweep": {
        "label": "Pending-approval email sweep (gated APPROVAL_EMAIL_NOTIFY)",
        "cadence": "hourly :40",
        "owner": "platform",
    },
    "social_drain": {
        "label": "Social queue drain (Postiz/X — gated SOCIAL_ENGINE)",
        "cadence": "hourly :10",
        "owner": "isha",
    },
    "sales_autopilot": {
        "label": "Sales Autopilot canary tick (gated SALES_AUTOPILOT_ENABLED)",
        "cadence": "hourly :25",
        "owner": "platform",
    },
    "task_lease_reap": {
        "label": "Expired agent-task lease close-out (gated AGENT_TASK_LEASE_REAP)",
        "cadence": "hourly :05",
        "owner": "platform",
    },
    "hq_auto_chase": {
        "label": "Hot Queue auto-chase EMAIL (gated HQ_AUTO_CHASE)",
        "cadence": "hourly :28",
        "owner": "platform",
    },
    "reply_auto_send": {
        "label": "Safe known-prospect auto-reply sweep (gated REPLY_AUTO_SEND)",
        "cadence": "hourly :30",
        "owner": "platform",
    },
    "content_approval_sweep": {
        "label": "Orphaned-pending approval retirement (dry_run default)",
        "cadence": "daily 04:30",
        "owner": "platform",
    },
    "daily_owner_brief": {
        "label": "Owner brief + ntfy push (P0/P1 blockers)",
        "cadence": "daily 08:10",
        "owner": "platform",
    },
}


# Jobs jinhe run-due recovery kabhi auto-enqueue NAHI karega (side-effect heavy:
# outbound calls/emails apni window ke bahar dobara nahi bhejne chahiye).
# "digest" bhi: uske summary-email step me per-day dedupe nahi hai — recovery
# double-fire = duplicate internal digest email (audit 2026-07-04).
RUN_DUE_EXCLUDE = {
    "platform_dial",
    "email_outreach",
    "email_followup",
    "digest",
    "sales_autopilot",
    "hq_auto_chase",
    "reply_auto_send",
    "trial_nudge",  # outbound customer email — no catch-up flood (BLK-02 2026-08-23)
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_overrides() -> dict[str, Any]:
    try:
        if os.path.exists(_OVERRIDES):
            with open(_OVERRIDES, encoding="utf-8") as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning(f"[scheduler-config] overrides read failed (FAIL-OPEN): {e}")
    return {}


def is_enabled(job: str) -> bool:
    """Job admin-disabled hai kya? FAIL-OPEN: kisi bhi error/unknown pe True."""
    try:
        ov = _read_overrides().get(str(job)) or {}
        return bool(ov.get("enabled", True))
    except Exception:
        return True


def set_enabled(job: str, enabled: bool, by: str = "admin", note: str = "") -> dict[str, Any]:
    """Per-job toggle persist karo (atomic, cross-process lock). Unknown job = reject."""
    job = str(job or "").strip()
    if job not in JOB_META:
        return {"ok": False, "error": f"unknown job '{job}'"}
    try:
        from app.utils.file_lock import file_lock

        os.makedirs(os.path.dirname(_OVERRIDES) or ".", exist_ok=True)
        with file_lock(_OVERRIDES):
            data = _read_overrides()
            data[job] = {
                "enabled": bool(enabled),
                "by": str(by)[:40],
                "note": str(note)[:120],
                "at": _now_iso(),
            }
            tmp = f"{_OVERRIDES}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, _OVERRIDES)
        try:
            from app.platform import team

            team.log_event(
                "manager",
                "task_assigned",
                f"scheduler {'ON' if enabled else 'PAUSE'}: {job} (by {by})",
            )
        except Exception:
            pass
        return {"ok": True, "job": job, "enabled": bool(enabled)}
    except Exception as e:
        logger.warning(f"[scheduler-config] set_enabled failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


def list_jobs() -> dict[str, Any]:
    """Merged view: registry + runtime toggle + heartbeat health (UI ke liye)."""
    health: dict[str, Any] = {}
    try:
        from app.platform import automation_health

        health = automation_health.health() or {}
    except Exception as e:
        logger.warning(f"[scheduler-config] health merge failed: {e}")
    beats = {str(j.get("job")): j for j in (health.get("jobs") or []) if isinstance(j, dict)}
    ov = _read_overrides()
    jobs: list[dict[str, Any]] = []
    for job, meta in JOB_META.items():
        b = beats.get(job) or {}
        o = ov.get(job) or {}
        enabled = bool(o.get("enabled", True))
        jobs.append(
            {
                "job": job,
                "label": meta["label"],
                "cadence": meta["cadence"],
                "owner": meta["owner"],
                "enabled": enabled,
                "paused_by": (None if enabled else o.get("by")),
                "last_run": b.get("last_run"),
                "duration_s": b.get("duration_s"),
                "status": ("admin_paused" if not enabled else b.get("status", "unknown")),
            }
        )
    return {
        "status": health.get("status", "unknown"),
        "overdue": health.get("overdue", []),
        "queue": health.get("queue", {}),
        "jobs": jobs,
        "at": _now_iso(),
    }


def _dispatch(job: str, *, manual: bool = False) -> str:
    """Job ko background me chalao — Celery prefer (durable, web-process block
    nahi hota; idempotent_task ttl=3600 double-enqueue dedupe karta). Broker na
    mile to in-process create_task fallback (rollback mode).

    Scheduled paths (manual=False) honor owner_schedulers kill via
    OwnerSchedulerGuardedTask.apply_async. Admin run_now sets manual=True.
    """
    if not manual:
        try:
            from app.platform.owner_os import record_scheduler_skip, scheduler_dispatch_allowed

            allowed, reason = scheduler_dispatch_allowed(job=job)
            if not allowed:
                record_scheduler_skip(job, reason, source="scheduler_config._dispatch")
                return "skipped_owner_schedulers"
        except Exception:
            pass
    try:
        from app.tasks.staff_jobs import run_staff_job

        if manual:
            run_staff_job.apply_async(args=[job], headers={"owner_os_manual": True})
        else:
            run_staff_job.delay(job)
        return "celery"
    except Exception as e:
        logger.warning(f"[scheduler-config] celery dispatch failed ({e}) — inline fallback")
    try:
        import asyncio

        from app.platform import team_scheduler

        asyncio.get_running_loop().create_task(team_scheduler._run_job(job))
        return "inline"
    except Exception as e:
        logger.warning(f"[scheduler-config] inline dispatch failed: {e}")
        return "failed"


def run_now(job: str, by: str = "admin") -> dict[str, Any]:
    """Ek job ABHI chalao (background dispatch — HTTP request block nahi hota)."""
    job = str(job or "").strip()
    if job not in JOB_META:
        return {"ok": False, "error": f"unknown job '{job}'"}
    try:
        from app.platform import team

        team.log_event("manager", "task_assigned", f"manual job run: {job} (by {by})")
    except Exception:
        pass
    via = _dispatch(job, manual=True)
    return {"ok": via != "failed", "job": job, "started_via": via}


def run_due(max_jobs: int = 3) -> dict[str, Any]:
    """Dead-man RECOVERY tick: overdue/never_ran jobs (enabled + non-excluded)
    ko re-dispatch karo. Idempotent-ish: heartbeat run ke baad update hota,
    isliye double-fire pe wahi job dobara due nahi dikhega + Celery-side
    idempotent_task (1h ttl) duplicate enqueue bhi rokta. Bounded max_jobs."""
    max_jobs = max(1, min(int(max_jobs or 3), 5))
    health: dict[str, Any] = {}
    try:
        from app.platform import automation_health

        health = automation_health.health() or {}
    except Exception as e:
        return {"ok": False, "error": f"health unavailable: {e}"}
    due_all = [
        j
        for j in list(health.get("overdue") or []) + list(health.get("never_ran") or [])
        if j in JOB_META and is_enabled(j)
    ]
    due = [j for j in due_all if j not in RUN_DUE_EXCLUDE]
    picked = due[:max_jobs]
    started = {j: _dispatch(j) for j in picked}
    return {
        "ok": True,
        "due": due,
        "started": started,
        "skipped_excluded": [j for j in due_all if j in RUN_DUE_EXCLUDE],
        "at": _now_iso(),
    }


__all__ = [
    "JOB_META",
    "is_enabled",
    "set_enabled",
    "list_jobs",
    "run_now",
    "run_due",
]
