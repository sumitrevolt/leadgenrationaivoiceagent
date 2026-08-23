"""
Today Overview — "Aaj kya hua?" plain-Hinglish admin snapshot (NO LLM, instant).
================================================================================

PROBLEM (user feedback 2026-06-12): automation command center technical tha —
heartbeat tables, flag names, job keys. Admin ko ek nazar me samajh nahi aata
tha ki (a) automations chal rahe hain ya nahi, (b) agents ne aaj kya kiya,
(c) kya tootha hai aur kaise theek karein.

YEH MODULE existing data ko (automation_health + team.team_status + llm_metrics
+ flags) PLAIN HINGLISH sentences me aggregate karta hai. Koi naya store nahi,
koi LLM call nahi (instant + free), kabhi raise nahi karta.

API: GET /api/growth/overview/today (growth.py) → /app/automation "🏠 Aaj" tab.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# weekday() 0=Mon … 6=Sun — weekly staff jobs (baaki daily = har din due)
_WEEKLY_ON: dict[str, int] = {
    "weekly_marketing": 2,  # Budh
    "saturday_hygiene": 5,  # Shani
    "kb_refresh": 6,  # Ravi
    "engineer_deps": 6,  # Ravi
}
_DAY_HI = ("Som", "Mangal", "Budh", "Guru", "Shukr", "Shani", "Ravi")

# First expected run time in IST. Before this time, a never-run job is simply
# scheduled later, not a problem. Hourly/5-min jobs are intentionally omitted.
_DUE_AFTER_IST: dict[str, tuple[int, int]] = {
    "revenue_snapshot": (0, 15),
    "obsidian_push": (2, 15),
    "qa": (2, 30),
    "trainer": (3, 0),
    "content_approval_sweep": (4, 30),
    "saturday_hygiene": (4, 0),
    "engineer_deps": (4, 30),
    "kb_refresh": (5, 0),
    "blog": (6, 30),
    "content": (7, 0),
    "standup": (8, 0),
    "daily_owner_brief": (8, 10),
    "hot_queue_brief": (8, 15),
    "digest": (8, 30),
    "readiness_digest": (8, 30),
    "engineer_finops": (9, 0),
    "prospect": (9, 30),
    "engineer_security": (9, 30),
    "engineer_dbre": (10, 0),
    "engineer_dataquality": (10, 30),
    "pipeline": (11, 0),
    "process_autostart": (11, 30),
    "weekly_marketing": (12, 30),
    "midday_prospect": (14, 30),
    "afternoon_content": (15, 0),
    "evening_prospect": (17, 0),
    "evening_wrap": (18, 30),
}


def _ist_now(now: datetime | None = None) -> datetime:
    """Resolve ONE IST timestamp for a scheduling decision.

    ``now`` is threaded from the caller so a single logical evaluation cannot mix
    an injected timestamp with an independent wall-clock read. Callers that pass
    nothing keep the previous behaviour exactly.

    A naive ``now`` is rejected rather than silently compared: mixing naive and
    aware datetimes here would produce a wrong schedule decision, not an error.
    """
    if now is not None:
        if now.tzinfo is None:
            raise ValueError("scheduling decisions require a timezone-aware timestamp")
        try:
            from zoneinfo import ZoneInfo

            return now.astimezone(ZoneInfo("Asia/Kolkata"))
        except Exception:
            return now.astimezone(timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        return datetime.now(timezone.utc)


def _job_due_today(job: str, *, now: datetime | None = None) -> bool:
    wd = _ist_now(now).weekday()
    if job not in _WEEKLY_ON:
        return True
    return wd == _WEEKLY_ON[job]


def _job_due_yet(job: str, *, now: datetime | None = None) -> bool:
    """True only when today's scheduled window has started in IST."""
    # Reuse the SAME resolved instant for both the weekday and the window check —
    # resolving twice could straddle midnight and answer for two different days.
    current = _ist_now(now)
    if not _job_due_today(job, now=current):
        return False
    due = _DUE_AFTER_IST.get(job)
    if not due:
        return True
    return (current.hour, current.minute) >= due


# Har scheduled job ka insaani naam + "yeh kya karta hai" — admin-friendly.
JOB_INFO: dict[str, dict[str, str]] = {
    "growth": {
        "label": "Growth pulse (har 15 min)",
        "kya": "Funnel ki sehat check karke chhote auto-fix karta hai",
    },
    "ops": {
        "label": "Kavya — system health (hourly)",
        "kya": "Server/DB/queue sab theek hai ya nahi",
    },
    "reply_triage": {
        "label": "Reply agent (hourly)",
        "kya": "Aaye hue email replies padh ke hot leads flag + jawab draft karta hai",
    },
    "watchdog": {
        "label": "Ops watchdog (hourly)",
        "kya": "Kuch critical toote to Sumit ko email alert",
    },
    "onboard": {
        "label": "Auto onboarding (hourly)",
        "kya": "Naye paid client ka setup khud kar deta hai",
    },
    "qa": {"label": "Arjun — QA (raat 2:30)", "kya": "Voice agent ki quality test karta hai"},
    "trainer": {"label": "Meera — trainer (raat 3)", "kya": "Agents ko naya seekhata hai"},
    "blog": {"label": "SEO blog (subah 6:30)", "kya": "Roz ek SEO blog post banata hai"},
    "content": {
        "label": "Isha — content (subah 7)",
        "kya": "Apne + clients ke social posts/captions banata hai",
    },
    "hot_queue_brief": {
        "label": "Hot Queue revenue brief (subah 8:15)",
        "kya": "Garam replies ka read-only brief banata hai; action /app/inbox me human karta hai",
    },
    "digest": {"label": "Daily digest (subah 8:30)", "kya": "Din ka summary email Sumit ko"},
    "prospect": {
        "label": "Rohan — prospect scrape (subah 9:30)",
        "kya": "Naye business prospects dhundta hai (42 niches rotation)",
    },
    "email_outreach": {
        "label": "Rohan — cold email (subah 10:30)",
        "kya": "Roz 25 tak personalized cold emails + follow-ups bhejta hai",
    },
    "pipeline": {
        "label": "Neha — pipeline (11:00)",
        "kya": "Leads rescore + hot leads Rohan ko surface",
    },
    "midday_prospect": {
        "label": "Rohan — midday harvest (14:30)",
        "kya": "Dusra free lead-supply pass (websearch/opendata)",
    },
    "email_followup": {
        "label": "Rohan — afternoon followup (16:00)",
        "kya": "Day-3/Day-7 email follow-ups (naya cold batch nahi)",
    },
    "evening_wrap": {
        "label": "Boss — evening wrap (18:30)",
        "kya": "Din ka summary + hot leads EOD recap",
    },
    "afternoon_content": {
        "label": "Isha — afternoon content (15:00)",
        "kya": "Dusra content-gen pass (gated AFTERNOON_CONTENT)",
    },
    "evening_prospect": {
        "label": "Rohan — evening harvest (17:00)",
        "kya": "Teesra free lead-harvest pass (gated EVENING_PROSPECT)",
    },
    "obsidian_push": {
        "label": "Obsidian sync (raat 2:15)",
        "kya": "Second-brain notes compact + nightly git push (gated OBSIDIAN_SYNC)",
    },
    "weekly_marketing": {
        "label": "Isha — weekly packs (Wed 12:30)",
        "kya": "S-tier niche marketing content bank top-up",
    },
    "kb_refresh": {
        "label": "Dev — KB refresh (Sun 05:00)",
        "kya": "Client websites se contextual KB re-ingest",
    },
    "saturday_hygiene": {
        "label": "Kavya — Sat hygiene (04:00)",
        "kya": "DLQ sweep + stale celery queue trim",
    },
    "standup": {
        "label": "Boss standup (08:00)",
        "kya": "Team priorities plan (gated AGENT_STANDUP)",
    },
    "engineer_sre": {"label": "Pranav SRE (hourly)", "kya": "Backup/DR/capacity score"},
    "engineer_finops": {"label": "Vidya FinOps (09:00)", "kya": "Margin + LLM cost digest"},
    "engineer_security": {"label": "Arnav security (09:30)", "kya": "Compliance posture"},
    "engineer_dbre": {
        "label": "Kabir DB reliability (10:00)",
        "kya": "Postgres query/index/connection health check",
    },
    "engineer_dataquality": {
        "label": "Diya data quality (10:30)",
        "kya": "Lead/CRM duplicate aur missing-contact scan",
    },
    "engineer_deps": {
        "label": "Aryan dependency audit (Sun 04:30)",
        "kya": "Dependency/CVE hygiene report",
    },
    "mcp_engineer": {
        "label": "Arya — MCP engineer (hourly :40)",
        "kya": "MCP health score + quota pressure + 90-din key rotation check",
    },
    "readiness_digest": {
        "label": "Activation digest (08:30)",
        "kya": "First-paid-customer readiness ntfy",
    },
    "revenue_snapshot": {
        "label": "Revenue snapshot (raat 00:15)",
        "kya": "Roz ka MRR/churn record karta hai (admin revenue chart ke liye)",
    },
    "gsc_rank": {
        "label": "GSC rank snapshot (raat 00:30)",
        "kya": "Google Search Console se clicks/impressions/position roz record karta hai (gated GSC_ENABLED, off by default)",
    },
    "trial_nudge": {
        "label": "Trial nudge email (subah 09:50)",
        "kya": "Trial khatam hone wale/khatam hue users ko Starter UPI upgrade email bhejta hai (gated TRIAL_NUDGE_ENABLED, off by default)",
    },
    "meter_watch": {
        "label": "Billing meter-watch (har ghante :55)",
        "kya": "Minute-billing meter fail ho to alert",
    },
    "process_autostart": {
        "label": "Process auto-start (~11:30)",
        "kya": "Process-engine workflows auto-shuru karta hai (gated)",
    },
    "flow_cron": {
        "label": "Flow runner cron (har 5 min)",
        "kya": "Customer/admin flows ke due cron triggers scan karta hai (gated)",
    },
    "call_kpi_digest": {
        "label": "Call KPI digest (raat 02:30)",
        "kya": "AI calls ke conversions/dispositions analysis",
    },
    "daily_video": {
        "label": "Roz ka video (09:45)",
        "kya": "Har marketing client ke liye roz 1 naya AI video ad banata hai (approval ke liye bhejta hai)",
    },
    "platform_dial": {
        "label": "Platform auto-dialer (11:30)",
        "kya": "Outbound campaign auto-dial loop",
    },
    # ADR-104 Phase F (2026-07-15): these two jobs existed in team_scheduler's
    # _last_ran (so they DO run) but had no JOB_INFO entry -- the Aaj tab
    # would have shown a raw job-key instead of a Hinglish label the moment
    # either job ran for the first time. Caught by the existing
    # test_job_info_covers_every_scheduled_job parity guard.
    "product_one_health": {
        "label": "Product 1 customer health (hourly :20)",
        "kya": "Paid customer health + approval-reminder + SLA-recovery safety-net sweep",
    },
    "approval_email_sweep": {
        "label": "Approval email sweep (hourly :40)",
        "kya": "Pending-approval email reminders bhejta hai (gated APPROVAL_EMAIL_NOTIFY, off by default)",
    },
    "social_drain": {
        "label": "Social queue drain (hourly :10)",
        "kya": "Queued social posts Postiz/X pe publish karta hai (gated SOCIAL_ENGINE)",
    },
    "sales_autopilot": {
        "label": "Sales Autopilot canary (hourly :25)",
        "kya": "Policy-driven sales tick — dry-run default, calling HARD OFF, INERT jab SALES_AUTOPILOT_ENABLED off",
    },
    "task_lease_reap": {
        "label": "Agent-task lease close-out (hourly :05)",
        "kya": "Jo agent-task apne worker ke marne se claimed/running me atak gaya use terminally failed mark karta hai (re-assign human karta hai, auto-retry NAHI). INERT jab AGENT_TASK_LEASE_REAP off",
    },
    "hq_auto_chase": {
        "label": "Hot Queue auto-chase email (hourly :28)",
        "kya": "Unactioned inquiry cards pe automated EMAIL follow-up (gated HQ_AUTO_CHASE, default OFF). WhatsApp/call 1-click human rehte hain",
    },
    "reply_auto_send": {
        "label": "Safe known-prospect auto-reply (hourly :30)",
        "kya": "Guarded known-prospect email auto-reply sweep (gated REPLY_AUTO_SEND). HARD_OFF override hamesha jeetta hai",
    },
    "content_approval_sweep": {
        "label": "Orphan approval sweep (subah 4:30)",
        "kya": "Dead-client pending approvals ko expire mark karta hai — dry_run default, live tabhi jab CONTENT_APPROVAL_SWEEP_LIVE",
    },
    "daily_owner_brief": {
        "label": "Owner brief + ntfy push (subah 8:10)",
        "kya": "P0/P1 exceptions pe owner ko ntfy push — gated DAILY_OWNER_BRIEF_NTFY. data/daily_owner_brief.txt hamesha save hota hai",
    },
}

# Important flags jo OFF hon to admin ko batana chahiye (flag -> Hinglish reason).
# RULE: sirf woh flags jo prod me ON HONE chahiye (CLAUDE.md "=1 ON") — warna
# OFF-by-default flag yahan add karne se "Aaj" tab pe false-alarm noise aayega.
_IMPORTANT_FLAGS = {
    "AUTO_EMAIL_OUTREACH": "Cold email outreach band hai — naye leads ko mail nahi ja raha",
    "NICHE_ROTATION": "42-niche scraping rotation band hai — sirf default niches scrape ho rahe",
    "REPLY_AGENT": "Email replies koi nahi padh raha (hot leads miss ho sakte)",
    "OPS_WATCHDOG": "System toote to alert nahi aayega",
    "SELF_IMPROVE_LOOP": "Self-improve loop band hai — agents khud kaam nahi uthayenge",
    "DUNNING_ENGINE": "Payment fail hone par recovery emails nahi jayenge",
    "LEAD_HARVESTER": "Lead harvester band hai — naye prospects ki free supply nahi aa rahi",
    "SALES_ENGINE": "Sales pipeline automation band hai — deals + next-action auto nahi ban rahe",
    "CADENCE_ENGINE": "Omnichannel follow-up sequences band hain — leads ko auto touch/reminder nahi ja rahe",
    "GROWTH_OPTIMIZER": "Funnel ka auto-optimizer band hai — leaks khud theek nahi ho rahe",
    "CHANNEL_EXPERIMENTS": "Channel A/B bandit band hai — best outreach channel auto-pick nahi ho raha",
    "AUTO_ONBOARD": "Naye paid client ka auto-setup band hai — manually karna padega",
}

# Flags jo ON hon to KHATARNAK — admin ko turant batao (problems[] me, kya+fix).
# Normal prod me ye sab OFF rehte hain → koi false-alarm nahi; koi ON ho to genuine.
_DANGER_ON_FLAGS: dict[str, dict[str, str]] = {
    "LLM_BUDGET_HARD_KILL": {
        "kya": "🚨 Emergency LLM kill-switch ON hai — saara AI band hai (replies/calls/content kuch nahi chalega)",
        "fix": "Jaan-boojh ke nahi kiya to .env me LLM_BUDGET_HARD_KILL=0 karke app recreate karo",
    },
    "WHATSAPP_AUTO_SEND": {
        "kya": "WhatsApp auto-send ON hai — bulk par number-ban ka risk",
        "fix": "Sirf approved-template + kam volume safe; sure nahi to WHATSAPP_AUTO_SEND off karo",
    },
    "REPLY_AUTO_SEND": {
        "kya": "Email auto-reply ON hai — interested replies bina review ja rahe (ban/galti risk)",
        "fix": "Draft-review safe hai — confidence nahi to REPLY_AUTO_SEND off rakho",
    },
}


def _flag_on(name: str) -> bool:
    return (os.environ.get(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _pending_decisions() -> int:
    """Kitne kaam SACH me boss ki manzoori maangte hain (agentic-draft queue).

    Canonical source = approvals_bridge (same count owner_home + Mission Control
    dikhate hain). Import-safe + never-raise: creds/store na ho to 0 (fail-open,
    kabhi false-alarm nahi). Yeh 'events_today' (jo agents AAJ kar CHUKE hain) se
    alag hai — yeh asli 'boss decision chahiye' backlog hai."""
    try:
        from app.platform import approvals_bridge

        d = approvals_bridge.list_drafts(include_decided=False) or {}
        return int((d.get("counts") or {}).get("pending") or 0)
    except Exception as e:
        logger.debug(f"[today] pending_decisions failed: {e}")
        return 0


def _customer_approval_backlog() -> dict[str, Any]:
    """Work the CUSTOMER has not decided on yet — a DIFFERENT queue from
    ``_pending_decisions()``.

    `approvals_bridge` (the source of `needs_decision`) covers the agentic-draft
    queue and contains no reference to `content_approval` at all, so customer-
    facing content/video approvals were counted by nothing on this page. That is
    how 32 of 39 video records sat at `pending` on prod for weeks with only 4 ever
    published, while the Aaj tab reported no problem (verified 2026-08-09).

    Delivery only happens after the customer clicks approve, so an ageing pile
    here means the product is generating work nobody ever receives. Never raises;
    an unreadable store contributes nothing rather than a false alarm.
    """
    out: dict[str, Any] = {"total": 0, "oldest_days": 0, "by_type": {}, "oldest_client": ""}
    try:
        from datetime import datetime as _dt

        from app.marketing import content_approval

        rows = content_approval.pending() or []
        out["total"] = len(rows)
        oldest_days = 0
        oldest_client = ""
        for r in rows:
            kind = str(((r.get("content") or {}) or {}).get("type") or "content")
            out["by_type"][kind] = out["by_type"].get(kind, 0) + 1
            raw = str(r.get("created_at") or "").strip()
            if not raw:
                continue
            try:
                created = _dt.fromisoformat(raw.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age = int((datetime.now(timezone.utc) - created).total_seconds() // 86400)
                if age > oldest_days:
                    oldest_days = age
                    oldest_client = str(r.get("client_id") or "")
            except Exception:
                continue
        out["oldest_days"] = oldest_days
        out["oldest_client"] = oldest_client
    except Exception as e:
        logger.debug(f"[today] customer approval backlog skip: {e}")
    return out


def _env_tri_state(name: str) -> str:
    """Boolean env → on/off/unset. Kabhi raw value return nahi (secrets-safe)."""
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return "unset"
    if raw in ("0", "false", "no", "off"):
        return "off"
    return "on"


def _upi_owner_queue() -> dict[str, int]:
    """Manual-UPI owner queue + aaj ke /start intents. Read-only, fail-open zeros."""
    out = {
        "upi_pending": 0,
        "upi_needs_owner": 0,
        "upi_needs_bind": 0,
        "upi_starts_today": 0,
    }
    try:
        from app.billing.paid_activations import _ist_day, today_ist
        from app.platform import upi_payments

        day = today_ist()
        rows = upi_payments.list_payments() or []
        actionable = upi_payments.list_actionable() or []
        out["upi_needs_owner"] = len(actionable)
        out["upi_pending"] = sum(1 for r in actionable if r.get("status") == "pending")
        out["upi_needs_bind"] = sum(
            1
            for r in actionable
            if r.get("status") == "approved" and not str(r.get("client_id") or "").strip()
        )
        out["upi_starts_today"] = sum(1 for r in rows if _ist_day(r.get("created_at")) == day)
    except Exception as e:
        logger.debug(f"[today] upi owner queue skip: {e}")
    return out


def _onboard_factory_counts() -> dict[str, int]:
    """Staged onboarding factory snapshot. Flag OFF / Redis miss = honest zeros."""
    out = {"onboard_waiting": 0, "onboard_running": 0, "onboard_failed": 0}
    try:
        from app.marketing.onboarding_factory import get_all_pipelines

        for pipeline in (get_all_pipelines() or [])[:200]:
            stages = pipeline.get("stages") or {}
            failed = any((v or {}).get("status") == "failed" for v in stages.values())
            if failed or pipeline.get("status") == "failed":
                out["onboard_failed"] += 1
            elif pipeline.get("status") == "in_progress":
                out["onboard_running"] += 1
            elif pipeline.get("status") != "completed":
                out["onboard_waiting"] += 1
    except Exception as e:
        logger.debug(f"[today] onboard factory skip: {e}")
    return out


def _marketing_feature_totals() -> dict[str, Any]:
    """Read-only marketing-feature JSONL ledgers. Fail-open zeros; never fabricate.

    Numbers are store counts, not live Google/Meta pixels. ``drip_emails_opened``
    is 0 until a run row actually has ``opened`` (EMAIL_TRACKING). Flag OFF +
    empty file = honest zero, not a success claim.
    """
    out: dict[str, Any] = {
        "reviews_sent": 0,
        "drip_emails_sent": 0,
        "drip_emails_opened": 0,
        "forms_submitted": 0,
        "proposals_accepted": 0,
        "reminders_sent": 0,
        "health_at_risk": 0,
        "review_monitor": _env_tri_state("REVIEW_MONITOR"),
        "form_builder": _env_tri_state("FORM_BUILDER"),
        "proposal_builder": _env_tri_state("PROPOSAL_BUILDER"),
        "booking_reminders": _env_tri_state("BOOKING_REMINDERS"),
        "client_health_alerts": _env_tri_state("CLIENT_HEALTH_ALERTS"),
        "email_tracking": _env_tri_state("EMAIL_TRACKING"),
    }
    try:
        from app.marketing.review_automation import get_sequence_stats

        s = get_sequence_stats() or {}
        out["reviews_sent"] = int(s.get("sent") or 0)
    except Exception as e:
        logger.debug(f"[today] review stats skip: {e}")
    try:
        from app.marketing.email_drips import get_drip_stats

        s = get_drip_stats() or {}
        out["drip_emails_sent"] = int(s.get("total_emails_sent") or 0)
        out["drip_emails_opened"] = int(s.get("opened") or 0)
    except Exception as e:
        logger.debug(f"[today] drip stats skip: {e}")
    try:
        from app.marketing.form_builder import get_form_stats

        s = get_form_stats() or {}
        out["forms_submitted"] = int(s.get("total_responses") or 0)
    except Exception as e:
        logger.debug(f"[today] form stats skip: {e}")
    try:
        from app.marketing.proposal_builder import get_proposal_stats

        s = get_proposal_stats() or {}
        out["proposals_accepted"] = int(s.get("accepted") or 0)
    except Exception as e:
        logger.debug(f"[today] proposal stats skip: {e}")
    try:
        from app.marketing.appointment_reminders import get_reminder_stats

        s = get_reminder_stats() or {}
        out["reminders_sent"] = int(s.get("sent") or 0)
    except Exception as e:
        logger.debug(f"[today] reminder stats skip: {e}")
    try:
        from app.marketing.customer_health import get_health_summary

        s = get_health_summary() or {}
        out["health_at_risk"] = int(s.get("at_risk") or 0)
    except Exception as e:
        logger.debug(f"[today] health stats skip: {e}")
    return out


def _paid_activations_today() -> dict[str, Any]:
    """Aaj ke Product-1 (Marketing) paid activations — ledger-backed, IST din.

    ``docs/gtm/PRODUCT1_50_PAID_DAY_90D.md`` ka north-star KPI hai, par owner ke
    home snapshot pe iska koi number tha hi nahi: sirf MRR snapshot delta tha, jo
    price/plan edit se bhi hilta hai. Ab invoice + UPI ledger se seedha count aata
    hai. Read-only — kuch activate/approve nahi hota. Never raises; store na
    padhe to zeroes (fail-open, kabhi fabricated paid count nahi).
    """
    try:
        from app.billing import paid_activations

        return paid_activations.daily_paid_activations() or {}
    except Exception as e:
        logger.debug(f"[today] paid activations skip: {e}")
        return {}


def _ago_minutes(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))
    except Exception:
        return None


def _ago_str(mins: int | None) -> str:
    if mins is None:
        return "kabhi nahi"
    if mins < 2:
        return "abhi-abhi"
    if mins < 60:
        return f"{mins} min pehle"
    if mins < 60 * 24:
        return f"{mins // 60} ghante pehle"
    return f"{mins // (60 * 24)} din pehle"


def build() -> dict[str, Any]:
    """Poora 'Aaj' snapshot — headline, problems[], staff[], jobs[], flags_off[].
    Har item plain Hinglish. Kabhi raise nahi karta (partial data theek hai)."""
    problems: list[dict[str, str]] = []
    jobs_out: list[dict[str, Any]] = []
    staff_out: list[dict[str, Any]] = []
    flags_off: list[dict[str, str]] = []
    # events_today = agents ne AAJ kitne kaam KIYE (done, DB event count) — NOT pending.
    # needs_decision = asli boss-decision backlog (pending agentic approvals).
    totals = {"events_today": 0, "working": 0, "staff": 0, "needs_decision": 0, "hot_queue": 0}

    # ---- 1) Scheduled jobs (dead-man heartbeats) -> Hinglish status ----
    try:
        from app.platform import automation_health

        h = automation_health.health()
        for j in h.get("jobs", []):
            key = j.get("job", "")
            info = JOB_INFO.get(key, {"label": key, "kya": ""})
            mins = _ago_minutes(j.get("last_run"))
            status = j.get("status", "unknown")
            if status == "ok":
                line = f"✅ Chal raha hai — pichhli baar {_ago_str(mins)}"
            elif status == "overdue":
                if _job_due_today(key):
                    line = f"⚠️ Time par nahi chala (pichhli baar {_ago_str(mins)})"
                    problems.append(
                        {
                            "kya": f"{info['label']} time par nahi chala",
                            "fix": "Worker/scheduler container check karo — /app/ops me ya 'docker ps' se",
                        }
                    )
                else:
                    line = f"📅 Weekly job — agle din schedule ({_DAY_HI[_WEEKLY_ON[key]]})"
                    status = "scheduled_off"
            elif status == "last_failed":
                line = f"❌ Pichhla run FAIL hua ({_ago_str(mins)})"
                problems.append(
                    {
                        "kya": f"{info['label']} pichhli baar fail hua",
                        "fix": "Events tab me error dekho",
                    }
                )
            elif status == "never_ran":
                if not _job_due_today(key):
                    line = f"📅 Aaj schedule nahi — har {_DAY_HI[_WEEKLY_ON[key]]} ko chalega"
                    status = "scheduled_off"
                elif not _job_due_yet(key):
                    line = "📅 Aaj baad me chalega — scheduled time abhi nahi aaya"
                    status = "scheduled_off"
                else:
                    line = "⏳ Abhi tak nahi chala — deploy ke baad pehli run pending"
                    problems.append(
                        {
                            "kya": f"{info['label']} abhi tak heartbeat nahi mila",
                            "fix": "Scheduler/worker up hai? Mission Control se manual trigger ya worker logs dekho",
                        }
                    )
            elif status == "scheduled_off":
                day = _DAY_HI[_WEEKLY_ON[key]] if key in _WEEKLY_ON else "?"
                line = f"📅 Aaj schedule nahi — har {day} ko chalega"
            else:
                line = "❓ Status pata nahi"
            jobs_out.append({**info, "job": key, "status": status, "line": line})
        q = h.get("queue") or {}
        if h.get("queue_backlogged"):
            problems.append(
                {
                    "kya": f"Task queue me kaam atka hai (celery={q.get('celery')}, dlq={q.get('dlq')})",
                    "fix": "Worker container restart karo ya DLQ retry (Upgrader tab)",
                }
            )
        # ADR-104 Phase F (2026-07-15): this function only ever checked
        # queue_backlogged (live celery/heavy depth) -- dead_tasks_present and
        # retryable_failed_present (Phase B authoritative fields, same
        # automation_health.health() call above) were never read, so this
        # "Aaj" snapshot (feeds BOTH /app/control-center's Problems panel AND
        # /app/automation's Aaj tab) could say "Koi problem nahi mili" while
        # dlq:dead held retry-exhausted tasks.
        # 2026-08-09: a mega-job that runs out of its wall-clock budget DROPS the
        # engines queued behind it. Prod ran `content` over its 420s budget on 15
        # consecutive days with zero visible signal — the "Aaj" tab happily said
        # sab theek while engines behind it never ran. Surface it in the owner's
        # own words, with the actual engine names.
        # A producer that still reports green but has stopped producing. The
        # liveness dead-man cannot see this — it only knows the job ran and did
        # not raise, which stayed true for all 15 days of the video outage.
        for _o in h.get("stale_outputs") or []:
            if _o.get("status") != "stale":
                continue
            problems.append(
                {
                    "kya": (
                        f"{_o.get('producer')} chal to raha hai par {_o.get('age_days')} din se "
                        f"kuch bana hi nahi ({_o.get('why')})"
                    ),
                    "fix": _o.get("owner_hint")
                    or "Engine ka flag aur uska last output dono check karo",
                    "href": "/app/automation",
                }
            )
        _skips = h.get("engine_skips") or {}
        if _skips.get("total"):
            _names = ", ".join(sorted((_skips.get("by_engine") or {}).keys())[:4]) or "kuch engines"
            problems.append(
                {
                    "kya": (
                        f"{_skips.get('total')} baar kaam chhoda gaya — time khatam hone se yeh "
                        f"engines chale hi nahi: {_names}"
                    ),
                    "fix": (
                        "Job ka time budget badhao (CONTENT_TIME_BUDGET_S) ya bhaari engine ko "
                        "apne alag job me nikalo — jaise daily video ke liye kiya gaya"
                    ),
                    "href": "/app/automation",
                }
            )
        # Customer-side approval pile. Nothing on this page counted it before
        # (see _customer_approval_backlog), which is how 32 of 39 video records
        # sat pending on prod while the tab said sab theek. A generated video the
        # customer never approves is never delivered — so it is a REVENUE problem,
        # not a queue statistic. Threshold 3 keeps normal same-day review quiet.
        _appr = _customer_approval_backlog()
        if _appr.get("total", 0) >= 3 or _appr.get("oldest_days", 0) >= 3:
            _kinds = ", ".join(f"{k}×{v}" for k, v in sorted((_appr.get("by_type") or {}).items()))
            _age = _appr.get("oldest_days") or 0
            problems.append(
                {
                    "kya": (
                        f"{_appr.get('total')} cheezein customer ki approval ka intezaar kar rahi "
                        f"hain{f' (sabse purani {_age} din se)' if _age else ''}"
                        f"{f' — {_kinds}' if _kinds else ''}. Approve nahi hui to customer tak "
                        f"kuch nahi pahunchta."
                    ),
                    "fix": (
                        "Customer ko yaad dilao ya unki taraf se approve karo — "
                        "roz ka video bhi backlog wale client ke liye ruk jayega"
                    ),
                    "href": "/app/automation",
                }
            )
        if h.get("dead_tasks_present"):
            problems.append(
                {
                    "kya": (
                        f"{q.get('dead')} failed kaam stuck hain — system ne retry band kar diya "
                        f"(dead/exhausted)"
                    ),
                    "fix": "Stuck tasks dekho, root-cause fix karo, phir retry/clear",
                    "href": "/app/office#reliability",
                }
            )
        if h.get("retryable_failed_present") and not h.get("queue_backlogged"):
            problems.append(
                {
                    "kya": (
                        f"{q.get('dlq')} failed tasks dubara try ke liye wait kar rahe hain "
                        f"(DLQ, retry-able)"
                    ),
                    "fix": "Thodi der auto-retry ka wait karo, ya Reliability se manual retry",
                    "href": "/app/office#reliability",
                }
            )
    except Exception as e:
        logger.debug(f"[today] automation_health failed: {e}")

    # ---- 2) Staff — aaj kisne kya kiya ----
    try:
        from app.platform.team import team_status

        ts = team_status()
        members = ts.get("members") or []
        totals["staff"] = len(members)
        for m in members:
            today = int(m.get("today_actions") or 0)
            state = str(m.get("state") or "")
            le = m.get("last_activity") or {}
            last = ""
            if isinstance(le, dict) and (le.get("action") or le.get("detail")):
                last = f"{le.get('action', '')}: {le.get('detail', '')}".strip(": ")
            if state == "working":
                totals["working"] += 1
                line = "🟢 Abhi kaam kar raha hai"
            elif state == "active":
                line = "🔵 Aaj active tha"
            else:
                line = "⚪ Kaafi der se kuch nahi kiya"
            totals["events_today"] += today
            staff_out.append(
                {
                    "member": m.get("key", ""),
                    "name": m.get("name", ""),
                    "emoji": m.get("emoji", "🤖"),
                    "role": m.get("title", ""),
                    "today": today,
                    "line": line,
                    "last": str(last)[:140],
                }
            )
        staff_out.sort(key=lambda x: -x["today"])
    except Exception as e:
        logger.debug(f"[today] team_status failed: {e}")

    # ---- 3) LLM brain health (free providers) ----
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(1000) or {}
        fb = float(st.get("fallback_or_fail_rate") or 0)
        if int(st.get("total_calls") or 0) >= 20 and fb > 0.5:
            problems.append(
                {
                    "kya": f"AI brain struggle kar raha hai ({round(fb * 100)}% calls fail/fallback)",
                    "fix": "Free LLM quota khatam ho sakta hai — kal tak rukna ya naya key add karna",
                }
            )
    except Exception as e:
        logger.debug(f"[today] llm_metrics failed: {e}")

    # ---- 4) Important flags OFF ----
    for flag, reason in _IMPORTANT_FLAGS.items():
        if not _flag_on(flag):
            flags_off.append({"flag": flag, "matlab": reason})

    # ---- 4b) Khatarnak flags jo ON hain (kill/ban risk) -> problems ----
    for flag, info in _DANGER_ON_FLAGS.items():
        if _flag_on(flag):
            problems.append({"kya": info["kya"], "fix": info["fix"]})

    # ---- 5) Asli boss-decision backlog (pending agentic approvals) ----
    # events_today = auto ho-CHUKA kaam; needs_decision = boss pe atka kaam.
    # Isse admin ka "841 pending?" wala confusion door hota hai (truth: 841 done).
    totals["needs_decision"] = _pending_decisions()
    # Separate counter on purpose: needs_decision is what the OWNER must decide,
    # this is what the CUSTOMER has not decided. Collapsing them would hide a
    # delivery blocker inside an ops number.
    _appr_totals = _customer_approval_backlog()
    totals["customer_approvals_pending"] = _appr_totals.get("total", 0)
    totals["customer_approvals_oldest_days"] = _appr_totals.get("oldest_days", 0)

    # ---- 5b) Aaj ke paid activations (Product-1 north-star, ledger-backed) ----
    # paid_today = aaj koi bhi paid event (naya + renewal); activations_today =
    # sirf woh clients jinka pehla paid event bhi aaj hai (asli "naya paid").
    _paid = _paid_activations_today()
    totals["paid_today"] = int(_paid.get("paid_today") or 0)
    totals["activations_today"] = int(_paid.get("activations_today") or 0)
    totals["paid_gross_today_inr"] = float(_paid.get("gross_inr_today") or 0)

    # ---- 6) Hot Queue (GTM bottleneck) — owner 15-min sprint, never auto-send ----
    try:
        from app.platform import reply_agent

        hq_n = len(reply_agent.hot_queue(limit=50, scope="boss") or [])
        totals["hot_queue"] = hq_n
        if hq_n > 0:
            problems.insert(
                0,
                {
                    "kya": (
                        f"{hq_n} garam replies Hot Queue me wait kar rahe hain — "
                        "15 min sprint se next paid customer"
                    ),
                    "fix": "/app/inbox kholo, top card pe Call/WA draft, phir Done (auto-send nahi)",
                    "href": "/app/inbox",
                },
            )
    except Exception as e:
        logger.debug(f"[today] hot_queue failed: {e}")
        totals["hot_queue"] = 0

    # ---- 7) Owner money-path + control-plane chips (admin-only; keys/counts, no PII)
    _upi = _upi_owner_queue()
    totals.update(_upi)
    totals.update(_onboard_factory_counts())
    totals.update(_marketing_feature_totals())
    totals["dsh_runtime"] = _env_tri_state("DSH_RUNTIME_ENABLED")
    totals["dsh_shadow"] = _env_tri_state("DSH_SHADOW_ENABLED")
    totals["staff_bus"] = _env_tri_state("STAFF_BUS_ENABLED")
    totals["delivery_at_risk"] = int(totals.get("customer_approvals_pending") or 0)
    totals["automation_failures"] = sum(
        1
        for p in problems
        if any(tok in (p.get("kya") or "").lower() for tok in ("fail", "stuck", "exhausted", "dlq"))
    )
    if totals.get("upi_needs_owner"):
        totals["top_blocker"] = "upi_pending_unactioned"
    elif totals.get("hot_queue"):
        totals["top_blocker"] = "hot_queue"
    elif totals.get("onboard_failed"):
        totals["top_blocker"] = "onboard_failed"
    elif totals.get("delivery_at_risk"):
        totals["top_blocker"] = "delivery_approvals"
    else:
        totals["top_blocker"] = ""

    if int(totals.get("upi_needs_owner") or 0) > 0:
        already = any("upi" in (p.get("kya") or "").lower() for p in problems)
        if not already:
            insert_at = 1 if int(totals.get("hot_queue") or 0) > 0 else 0
            problems.insert(
                insert_at,
                {
                    "kya": (
                        f"{totals['upi_needs_owner']} UPI claim owner action maangte hain "
                        f"(pending={totals['upi_pending']}, bind={totals['upi_needs_bind']})"
                    ),
                    "fix": (
                        "Bind/Re-Approve tabhi jab bank credit sach me aaya ho — "
                        "auto-confirm mat karo"
                    ),
                    "href": "/app/admin#sec-upi-selfserve",
                },
            )

    # ---- Headline ----
    if problems:
        headline = f"⚠️ {len(problems)} cheez dhyan maangti hai — neeche dekho"
    elif totals["events_today"] > 0:
        nd = totals["needs_decision"]
        tail = (
            f" · {nd} kaam aapki manzoori maang raha hai"
            if nd > 0
            else " · kuch bhi aapki manzoori pe atka nahi (sab auto)"
        )
        headline = (
            f"✅ Sab theek chal raha hai — aaj team ne {totals['events_today']} kaam KIYE"
            f" ({totals['working']} agent abhi active){tail}"
        )
    else:
        headline = "🌅 Aaj abhi tak koi kaam log nahi hua (subah ke jobs ka time dekho)"

    return {
        "headline": headline,
        "problems": problems,
        "staff": staff_out,
        "jobs": jobs_out,
        "flags_off": flags_off,
        "totals": totals,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


__all__ = ["build", "JOB_INFO"]
