"""LeadGenAI Operating HQ — business-command-center aggregator behind /app/office.

Extends the existing 4-room virtual office (team.py STAFF + office_map.html) into
an 8-room read-only command center that shows REAL business signals: lead
pipeline, deals, billing, approvals, system health, next-best-actions.

Hard rules followed here (per user spec + advisor review):
  - READ-ONLY. No new DB models/enums/migrations. Every number is either a
    direct read of an existing table/store, or a thin re-aggregation of an
    existing builder (today_overview.build, automation_health.health,
    _collect_live_stats, sales_pipeline.stats, client_health.health_report,
    approvals_bridge.list_drafts). We do not re-implement any of those.
  - Every pipeline stage carries a `source` tag: "real" (direct query/store),
    "partial" (real data, approximate mapping to the 12-stage model — has a
    `note` explaining the approximation), or "mock" (no backing data at all,
    always empty + clearly labeled — never fabricated numbers).
  - Never raises. Every public function degrades to a safe empty shape on
    any failure so a broken sub-engine can never blank the whole page.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.platform.team import STAFF
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))

# --------------------------------------------------------------------------- #
# 8-room layout — a finer regrouping of the SAME 31 STAFF (team.py), by actual
# duties rather than the coarser 3-bucket `product` field. Pure re-labeling;
# no new agents invented. Anyone not in this dict falls back to their
# `product` bucket (defensive — a future STAFF addition never 404s a room).
# --------------------------------------------------------------------------- #
ROOM_DEFS: list[dict[str, str]] = [
    {
        "id": "coordinator",
        "name": "Coordinator Room",
        "emoji": "🧑‍💼",
        "purpose": "Kaam assign karta, stuck tasks dekhta, next-best-action deta",
    },
    {
        "id": "lead_lab",
        "name": "Data / Lead Lab",
        "emoji": "🧹",
        "purpose": "Lead import, dedupe, validation, enrichment, scoring",
    },
    {
        "id": "sales_crm",
        "name": "Sales / CRM Room",
        "emoji": "🤝",
        "purpose": "Qualified follow-up, deal stages, appointments, CRM sync",
    },
    {
        "id": "voice_team",
        "name": "Voice Team",
        "emoji": "📞",
        "purpose": "AI voice calls, queue, transcripts, appointment outcomes",
    },
    {
        "id": "marketing_team",
        "name": "Marketing Team",
        "emoji": "📣",
        "purpose": "WhatsApp/social/GBP content, offers, campaign creatives",
    },
    {
        "id": "qa_audit",
        "name": "QA / Audit Room",
        "emoji": "🧪",
        "purpose": "Automation quality checks, broken workflows, bad data",
    },
    {
        "id": "platform_engineering",
        "name": "Platform / Engineering",
        "emoji": "🛠️",
        "purpose": "System health, API/provider status, cron, queues, DB",
    },
    {
        "id": "admin_finance",
        "name": "Admin / Finance Room",
        "emoji": "💰",
        "purpose": "Billing, invoices, payments, subscriptions, churn-risk",
    },
]
ROOM_IDS = {r["id"] for r in ROOM_DEFS}

MEMBER_ROOM: dict[str, str] = {
    "manager": "coordinator",
    # Lead Lab — data integrity + pipeline freshness (dedupe/rescore/hot-surface)
    "diya": "lead_lab",
    "neha": "lead_lab",
    # Sales / CRM — follow-up, targeting, CRM push, sequencing
    "rohan": "sales_crm",
    "priya": "sales_crm",
    "anika": "sales_crm",
    "ira": "sales_crm",
    # Voice Team
    "swara": "voice_team",
    "ananya": "voice_team",
    "riya": "voice_team",
    "lekha": "voice_team",
    "raksha": "voice_team",
    # Marketing Team
    "dev": "marketing_team",
    "isha": "marketing_team",
    "ravi": "marketing_team",
    "zara": "marketing_team",
    "kiran": "marketing_team",
    # QA / Audit — voice QA + trainer (existing quality-check duties)
    "arjun": "qa_audit",
    "meera": "qa_audit",
    # Platform / Engineering — infra, code, security, MCP, voice-provider readiness
    "kavya": "platform_engineering",
    "hermes": "platform_engineering",
    "vikram": "platform_engineering",
    "guru": "platform_engineering",
    "pranav": "platform_engineering",
    "arnav": "platform_engineering",
    "kabir": "platform_engineering",
    "aryan": "platform_engineering",
    "arya": "platform_engineering",
    "tara": "platform_engineering",
    # Admin / Finance — revenue + margin
    "nikhil": "admin_finance",
    "vidya": "admin_finance",
}


def coordination_topology() -> dict[str, Any]:
    """Canonical Boss -> domain-team -> STAFF projection.

    This is visibility/routing metadata only.  It never dispatches work and it
    does not change Agent Runtime rollout gates.  Keeping it derived from the
    office room map prevents the coordinator and UI from inventing a second
    workforce taxonomy.
    """
    boss = "manager"
    assigned: list[str] = []
    teams: list[dict[str, Any]] = []
    room_meta = {row["id"]: row for row in ROOM_DEFS}
    for room in ROOM_DEFS:
        room_id = room["id"]
        if room_id == "coordinator":
            continue
        members = sorted(
            key
            for key, mapped_room in MEMBER_ROOM.items()
            if mapped_room == room_id and key != boss
        )
        assigned.extend(members)
        teams.append(
            {
                "id": room_id,
                "name": room["name"],
                "purpose": room["purpose"],
                "members": members,
                "member_count": len(members),
            }
        )

    staff_ids = set(STAFF)
    covered = {boss, *assigned}
    duplicates = sorted({key for key in assigned if assigned.count(key) > 1})
    return {
        "boss": boss,
        "boss_name": STAFF.get(boss, {}).get("name", "Boss"),
        "boss_room": room_meta.get("coordinator", {}).get("name", "Coordinator Room"),
        "teams": teams,
        "team_count": len(teams),
        "staff_count": len(staff_ids),
        "covered_count": len(covered & staff_ids),
        "missing_agents": sorted(staff_ids - covered),
        "unknown_agents": sorted(covered - staff_ids),
        "duplicate_assignments": duplicates,
        "coverage_ok": covered == staff_ids and not duplicates,
        "authority": {
            "default_decision": "boss_within_agent_contract",
            "owner_required": ["manual_upi_credit_confirmation"],
            "system_hard_gates": [
                "dnd_trai_consent_dpdp",
                "kill_switches_and_budgets",
                "red_lane_and_prohibited_actions",
            ],
        },
        "claim_note": (
            "31/31 coordination-ready means Boss can route every profile; "
            "runtime rollout_state still decides whether an action may execute."
        ),
    }


# STAFF keys with a REAL, individually re-triggerable manual-run wired today
# (app/agents/staff.py run_member() dispatch table). All 31 STAFF members now
# have run_* wrappers — Paperclip Plan B expansion (2026-07-19).
RUNNABLE_MEMBERS = set(STAFF.keys())

# Member key -> the single env flag that gates their underlying automation
# engine, for offline_reason classification. Expanded to cover ALL gated agents
# (previously only 5 — many flag-gated agents showed "no_data_today" instead of
# the accurate "flag_off:X" reason).
_MEMBER_GATING_FLAG: dict[str, str] = {
    # Marketing
    "priya": "CRM_SYNC",
    "zara": "SOCIAL_ENGINE",
    "anika": "CADENCE_ENGINE",
    "ira": "JOURNEY_ENGINE",
    "kiran": "CAMPAIGN_OPTIMIZER",
    # Voice
    "raksha": "CALL_TRANSFER",
    # Platform / Engineering
    "hermes": "INFRA_HANDLER",
    "vikram": "CODE_UPGRADER",
    "guru": "SKILL_PACK",
    "pranav": "SRE_AGENT",
    "vidya": "FINOPS_AGENT",
    "arnav": "SECURITY_AGENT",
    "kabir": "DBRE_AGENT",
    "diya": "DATA_INTEGRITY_AGENT",
    "aryan": "DEPS_AGENT",
    "arya": "MCP_ENGINEER",
}


def classify_offline_reason(key: str) -> str:
    """Why a member shows offline — 'flag_off:X' / 'no_data_today' / 'unknown'.

    Never raises (env read wrapped). Pure function, no IO beyond os.environ."""
    try:
        flag = _MEMBER_GATING_FLAG.get(key)
        if flag:
            val = (os.environ.get(flag) or "").strip().lower()
            if val not in ("1", "true", "yes"):
                return f"flag_off:{flag}"
            return "no_data_today"
        if key in STAFF:
            return "no_data_today"
        return "unknown"
    except Exception:
        return "unknown"


# automation_health job-key -> owning room, for blocked/error badges per room.
JOB_ROOM: dict[str, str] = {
    "prospect": "lead_lab",
    "midday_prospect": "lead_lab",
    "evening_prospect": "lead_lab",
    "pipeline": "lead_lab",
    "engineer_dataquality": "lead_lab",
    "reply_triage": "sales_crm",
    "qa": "qa_audit",
    "trainer": "qa_audit",
    "email_outreach": "marketing_team",
    "email_followup": "marketing_team",
    "content": "marketing_team",
    "blog": "marketing_team",
    "afternoon_content": "marketing_team",
    "weekly_marketing": "marketing_team",
    "kb_refresh": "marketing_team",
    "digest": "admin_finance",
    "revenue_snapshot": "admin_finance",
    "meter_watch": "admin_finance",
    "growth": "coordinator",
    "standup": "coordinator",
    "process_autostart": "coordinator",
    "ops": "platform_engineering",
    "watchdog": "platform_engineering",
    "onboard": "platform_engineering",
    "engineer_sre": "platform_engineering",
    "mcp_engineer": "platform_engineering",
    "engineer_finops": "admin_finance",
    "engineer_security": "platform_engineering",
    "engineer_dbre": "platform_engineering",
    "engineer_deps": "platform_engineering",
    "readiness_digest": "platform_engineering",
    "saturday_hygiene": "platform_engineering",
    "obsidian_push": "platform_engineering",
    "flow_cron": "platform_engineering",
    "evening_wrap": "platform_engineering",
    "call_kpi_digest": "voice_team",
}

# approvals_bridge source -> owning room (sales/coordinator/fde are the only
# 3 sources that engine supports today).
APPROVAL_ROOM = {"sales": "sales_crm", "coordinator": "coordinator", "fde": "sales_crm"}

# --------------------------------------------------------------------------- #
# Aaj-ka-Schedule — static mirror of team_scheduler.py's IST job windows so the
# office map can show a real day-plan timeline ("kya kab chalega / chala").
# DISPLAY-ONLY: nothing here triggers a job. Drift-locked by
# tests/test_office_hq.py::test_schedule_defs_windows_match_team_scheduler_source,
# which asserts each window tuple string still exists verbatim in
# team_scheduler.py — change a window there and this list (+ test) fails loudly
# until both are updated together.
#   type "daily":  window = [start_h, start_m, end_h, end_m] (IST)
#   type "weekly": window + weekday (0=Mon .. 6=Sun)
#   type "recurring": cadence = human-readable repeat rule (no single window)
# --------------------------------------------------------------------------- #
SCHEDULE_DEFS: list[dict[str, Any]] = [
    {"job": "revenue_snapshot", "label": "MRR snapshot", "type": "daily", "window": [0, 5, 0, 35]},
    {
        "job": "obsidian_push",
        "label": "Obsidian brain push",
        "type": "daily",
        "window": [2, 15, 3, 0],
    },
    {"job": "qa", "label": "Voice QA (Arjun)", "type": "daily", "window": [2, 30, 4, 0]},
    {"job": "trainer", "label": "Trainer + ML (Meera)", "type": "daily", "window": [3, 0, 4, 30]},
    {"job": "blog", "label": "SEO blog (Dev)", "type": "daily", "window": [6, 30, 8, 30]},
    {
        "job": "content",
        "label": "Content generation (Isha)",
        "type": "daily",
        "window": [7, 0, 9, 0],
    },
    {"job": "standup", "label": "Boss standup", "type": "daily", "window": [8, 0, 9, 30]},
    {"job": "digest", "label": "Morning digest", "type": "daily", "window": [8, 30, 10, 30]},
    {
        "job": "readiness_digest",
        "label": "Readiness digest",
        "type": "daily",
        "window": [8, 30, 9, 30],
    },
    {
        "job": "engineer_finops",
        "label": "FinOps score (Vidya)",
        "type": "daily",
        "window": [9, 0, 10, 0],
    },
    {
        "job": "prospect",
        "label": "Lead prospecting (Rohan)",
        "type": "daily",
        "window": [9, 30, 11, 30],
    },
    {
        "job": "engineer_security",
        "label": "Security posture (Arnav)",
        "type": "daily",
        "window": [9, 30, 10, 30],
    },
    {
        "job": "engineer_dbre",
        "label": "DB reliability (Kabir)",
        "type": "daily",
        "window": [10, 0, 11, 0],
    },
    {
        "job": "engineer_dataquality",
        "label": "Data integrity (Diya)",
        "type": "daily",
        "window": [10, 30, 11, 30],
    },
    {
        "job": "pipeline",
        "label": "Pipeline rescore (Neha)",
        "type": "daily",
        "window": [11, 0, 12, 0],
    },
    {
        "job": "platform_dial",
        "label": "Self-sale cold-call batch",
        "type": "daily",
        "window": [11, 30, 12, 30],
    },
    {
        "job": "process_autostart",
        "label": "Process auto-start",
        "type": "daily",
        "window": [11, 30, 13, 0],
    },
    {
        "job": "midday_prospect",
        "label": "Midday lead harvest",
        "type": "daily",
        "window": [14, 30, 15, 30],
    },
    {
        "job": "afternoon_content",
        "label": "Afternoon content (Isha)",
        "type": "daily",
        "window": [15, 0, 16, 0],
    },
    {
        "job": "evening_prospect",
        "label": "Evening lead harvest",
        "type": "daily",
        "window": [17, 0, 18, 0],
    },
    {"job": "evening_wrap", "label": "Evening wrap", "type": "daily", "window": [18, 30, 19, 30]},
    {
        "job": "call_kpi_digest",
        "label": "Call KPI digest (Lekha)",
        "type": "daily",
        "window": [19, 30, 20, 30],
    },
    {
        "job": "weekly_marketing",
        "label": "Weekly marketing packs",
        "type": "weekly",
        "weekday": 2,
        "window": [12, 30, 13, 30],
    },
    {
        "job": "saturday_hygiene",
        "label": "Hygiene sweep (DLQ+trim)",
        "type": "weekly",
        "weekday": 5,
        "window": [4, 0, 5, 30],
    },
    {
        "job": "kb_refresh",
        "label": "KB refresh",
        "type": "weekly",
        "weekday": 6,
        "window": [5, 0, 6, 30],
    },
    {
        "job": "engineer_deps",
        "label": "Dependency CVE audit (Aryan)",
        "type": "weekly",
        "weekday": 6,
        "window": [4, 30, 5, 0],
    },
    {"job": "growth", "label": "Growth pulse", "type": "recurring", "cadence": "har 15 min"},
    {"job": "flow_cron", "label": "Flow Runner cron", "type": "recurring", "cadence": "har 5 min"},
    {"job": "ops", "label": "Ops health (Kavya)", "type": "recurring", "cadence": "hourly :05"},
    {
        "job": "email_outreach",
        "label": "Email outreach (Rohan)",
        "type": "recurring",
        "cadence": "9am-7pm hourly",
    },
    {
        "job": "email_followup",
        "label": "Email follow-ups",
        "type": "recurring",
        "cadence": "9am-7pm hourly (:20+)",
    },
    {"job": "reply_triage", "label": "Reply triage", "type": "recurring", "cadence": "hourly :20"},
    {"job": "watchdog", "label": "Ops watchdog", "type": "recurring", "cadence": "hourly :35"},
    {
        "job": "mcp_engineer",
        "label": "MCP health (Arya)",
        "type": "recurring",
        "cadence": "hourly :40",
    },
    {
        "job": "engineer_sre",
        "label": "SRE score (Pranav)",
        "type": "recurring",
        "cadence": "hourly :45",
    },
    {"job": "onboard", "label": "Auto onboarding", "type": "recurring", "cadence": "hourly :50"},
    {"job": "meter_watch", "label": "Meter watch", "type": "recurring", "cadence": "hourly :55"},
]


def build_schedule() -> list[dict[str, Any]]:
    """Static day-plan for the office map's "Aaj ka Schedule" panel. Pure data,
    zero IO — run-status (done/overdue/off) is merged CLIENT-side from the
    system_health.jobs beats already present in the same snapshot. Never raises."""
    try:
        return [dict(d) for d in SCHEDULE_DEFS]
    except Exception:
        return []


PIPELINE_STAGE_META: list[dict[str, Any]] = [
    {"id": "lead_source", "name": "Lead Source / Import", "order": 1},
    {"id": "cleaning_enrichment", "name": "Lead Cleaning & Enrichment", "order": 2},
    {"id": "scoring_qualification", "name": "Lead Scoring & Qualification", "order": 3},
    {"id": "campaign_planning", "name": "Campaign Planning", "order": 4},
    {"id": "outreach_queue", "name": "Outreach Queue", "order": 5},
    {"id": "conversation_followup", "name": "Conversation / Follow-up", "order": 6},
    {"id": "appointment_booking", "name": "Appointment / Demo Booking", "order": 7},
    {"id": "deal_conversion", "name": "Deal / Conversion", "order": 8},
    {"id": "customer_onboarding", "name": "Customer Onboarding", "order": 9},
    {"id": "service_delivery", "name": "Service Delivery / Automation", "order": 10},
    {"id": "billing_subscription", "name": "Billing / Subscription", "order": 11},
    {"id": "retention_growth", "name": "Retention / Growth", "order": 12},
]

# Short Redis-backed cache for build_snapshot() — a browser refresh within
# this window returns instantly instead of recomputing (see build_snapshot
# docstring "Perf note #2"). Shared across uvicorn workers (unlike a plain
# in-process dict), invalidated early by any real mutation.
#
# BUG (2026-07-01, found same day): TTL was 15s while office_map.html's
# auto-refresh polled every 25s (setInterval(refreshSnapshot, 25000)) — since
# 25 > 15, the cache had ALREADY expired before every single periodic poll,
# so the auto-refresh never once hit the cache; only a rapid manual
# double-refresh within 15s ever benefited. Fixed same day by raising TTL to
# 35s (comfortably above the then-25s poll interval).
#
# RETUNE (2026-07-02, Task 8 "real-time tightening"): poll interval tightened
# 25s -> 15s. TTL retuned 35s -> 18s to match — same invariant as the
# 2026-07-01 fix above (TTL must stay ABOVE the poll interval, with a
# comfortable margin), just recalibrated to the new faster poll cadence.
# Do NOT drop TTL below the poll interval and rely on build_snapshot()'s
# compute time (~8-9s) as slack to compensate — that coincidence breaks the
# moment compute time is optimized down, silently reintroducing the exact
# 2026-07-01 cache-defeat bug where every poll misses because the cache
# already expired.
_SNAPSHOT_CACHE_KEY = "office_hq:snapshot"
_SNAPSHOT_CACHE_TTL = 18


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today_start_utc() -> datetime:
    n = datetime.now(_IST)
    start_ist = n.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_ist.astimezone(timezone.utc)


async def _safe_collect_live_stats(timeout: float = 8.0) -> dict[str, Any]:
    """`admin_dashboard_builders._collect_live_stats()` is SYNC and, against real
    production data volume, can take 45s+ (confirmed 2026-07-01 prod incident —
    it does a prospector scan + a per-client content-queue file-read loop).
    Calling it directly blocks the event loop AND can hang the whole snapshot
    indefinitely. Run it in a thread with a hard deadline — on timeout/failure
    the snapshot degrades to zeros for these fields rather than never loading.
    Called ONCE per snapshot (not once per build_metrics + once per
    build_pipeline like before) — that alone halved the real cost."""
    try:
        from app.api.admin_dashboard_builders import _collect_live_stats

        return await asyncio.wait_for(asyncio.to_thread(_collect_live_stats), timeout=timeout)
    except Exception as e:
        logger.warning(f"[office_hq] _collect_live_stats timed out/failed ({timeout}s budget): {e}")
        return {}


async def _safe_db_call(coro: Any, timeout: float = 8.0, label: str = "") -> Any:
    """Bound any single DB round-trip so it can never hang the whole snapshot.
    Returns None on timeout/failure (callers already treat None/empty as ok)."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception as e:
        logger.warning(f"[office_hq] db call '{label}' timed out/failed ({timeout}s budget): {e}")
        return None


def room_for_member(key: str, product: str | None = None) -> str:
    r = MEMBER_ROOM.get(key)
    if r:
        return r
    p = (product or "").strip().lower()
    if p == "voice":
        return "voice_team"
    if p == "marketing":
        return "marketing_team"
    return "platform_engineering"


def _enum_value(obj: Any, attr: str) -> str:
    """Read an ORM attribute that may be an Enum member or a plain string and
    return its lowercase VALUE (e.g. "appointment", not "LeadStatus.APPOINTMENT").
    str(SomeEnum.MEMBER) is "ClassName.MEMBER" in Python — a real footgun when
    comparing against plain-string constants. Never raises."""
    try:
        v = getattr(obj, attr, None)
        if v is None:
            return ""
        return str(getattr(v, "value", v)).lower()
    except Exception:
        return ""


def _is_resolved(overrides: dict[str, dict[str, Any]], item_id: Any) -> bool:
    """True if an admin explicitly marked this item's stuck-state resolved
    (app.platform.admin_pipeline_overrides). Never raises."""
    try:
        return bool((overrides.get(str(item_id)) or {}).get("stuck_resolved_at"))
    except Exception:
        return False


def _needs_approval(name: str, approval_titles: list[str]) -> bool:
    """Best-effort real cross-reference: True if this item's name appears as a
    substring of a currently-pending approval draft's title. Not a fabricated
    flag — it only ever fires against REAL pending approvals data."""
    try:
        n = (name or "").strip().lower()
        if not n or len(n) < 3:
            return False
        return any(n in t for t in approval_titles)
    except Exception:
        return False


def _iso(dt: Any) -> str | None:
    try:
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Rooms — merge STAFF+team_status into the 8-room grouping, with per-room
# task/blocked/error/approval counts sourced from automation_health + approvals.
# --------------------------------------------------------------------------- #
def build_rooms_and_agents() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rooms: dict[str, dict[str, Any]] = {
        r["id"]: {
            **r,
            "agent_keys": [],
            "activeTaskCount": 0,
            "blockedTaskCount": 0,
            "errorCount": 0,
            "approvalCount": 0,
            "status": "idle",
        }
        for r in ROOM_DEFS
    }
    agents: list[dict[str, Any]] = []
    try:
        from app.platform import agent_controls
        from app.platform.team import team_status

        ts = team_status() or {}
        members = {m.get("key"): m for m in (ts.get("members") or [])}
        paused_set = set(agent_controls.list_paused().keys())
        for key, meta in STAFF.items():
            room_id = room_for_member(key, meta.get("product"))
            live = members.get(key) or {}
            state = live.get("state", "offline")
            agent = {
                "id": key,
                "key": key,
                "name": meta.get("name", key),
                "emoji": meta.get("emoji", "🤖"),
                "title": meta.get("title", ""),
                "duties": meta.get("duties", ""),
                "room": room_id,
                "status": state,  # working|active|offline (see team.py windows)
                "offline_reason": classify_offline_reason(key) if state == "offline" else None,
                "todayActions": int(live.get("today_actions") or 0),
                "todayErrors": int(live.get("today_errors") or 0),
                "lastActivityAt": live.get("last_activity"),
                "runnable": key in RUNNABLE_MEMBERS,
                "paused": key in paused_set,
            }
            agents.append(agent)
            room = rooms.get(room_id) or rooms["platform_engineering"]
            room["agent_keys"].append(key)
            if state == "working":
                room["activeTaskCount"] += 1
            if agent["todayErrors"] > 0:
                room["errorCount"] += 1
    except Exception as e:
        logger.warning(f"[office_hq] build_rooms_and_agents (staff) failed: {e}")

    # Blocked/error signal from automation_health (job -> owning room).
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        for j in h.get("jobs", []) or []:
            job = j.get("job", "")
            status = j.get("status", "")
            room_id = JOB_ROOM.get(job)
            if not room_id or room_id not in rooms:
                continue
            if status == "overdue":
                rooms[room_id]["blockedTaskCount"] += 1
            elif status == "last_failed":
                rooms[room_id]["errorCount"] += 1
        if (h.get("queue") or {}).get("dlq", 0) and int(h["queue"]["dlq"]) > 0:
            rooms["platform_engineering"]["errorCount"] += 1
    except Exception as e:
        logger.debug(f"[office_hq] automation_health room-mapping skipped: {e}")

    # Approval counts per room.
    try:
        from app.platform import approvals_bridge

        d = approvals_bridge.list_drafts(include_decided=False) or {}
        by_source = (d.get("counts") or {}).get("by_source") or {}
        for source, count in by_source.items():
            room_id = APPROVAL_ROOM.get(source)
            if room_id and room_id in rooms:
                rooms[room_id]["approvalCount"] += int(count or 0)
    except Exception as e:
        logger.debug(f"[office_hq] approvals room-mapping skipped: {e}")

    out_rooms = []
    for r in rooms.values():
        if r["errorCount"] > 0:
            r["status"] = "error"
        elif r["blockedTaskCount"] > 0 or r["approvalCount"] > 0:
            r["status"] = "blocked"
        elif r["activeTaskCount"] > 0:
            r["status"] = "active"
        else:
            r["status"] = "idle"
        out_rooms.append(r)
    out_rooms.sort(key=lambda r: ROOM_DEFS.index(next(x for x in ROOM_DEFS if x["id"] == r["id"])))
    return out_rooms, agents


# --------------------------------------------------------------------------- #
# Metrics summary — reuse the SAME single-source builders the rest of the
# admin surface uses (admin_dashboard._collect_live_stats, sales_pipeline,
# approvals_bridge, automation_health) rather than re-deriving any of them.
# --------------------------------------------------------------------------- #
async def build_metrics(live_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "new_leads_today": 0,
        "qualified_leads_today": 0,
        "calls_completed_today": 0,
        "emails_sent_today": 0,
        "appointments_booked": 0,
        "campaigns_ready": 0,
        "payments_pending": 0,
        "active_customers": 0,
        "failed_automations": 0,
        "approvals_needed": 0,
        "system_issues": 0,
        "mrr": 0,
    }
    try:
        live = live_stats if live_stats is not None else await _safe_collect_live_stats()
        out["calls_completed_today"] = int(live.get("real_calls_today") or 0)
        out["emails_sent_today"] = int(live.get("emails_sent_today") or 0)
        out["campaigns_ready"] = int(live.get("content_items_generated") or 0)
        out["active_customers"] = int(live.get("marketing_clients_active") or 0)
        out["mrr"] = int(live.get("estimated_mrr") or 0)
        out["failed_automations"] = int(live.get("dlq_count") or 0)
    except Exception as e:
        logger.debug(f"[office_hq] metrics live-stats skipped: {e}")

    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.lead import Lead

        async def _q():
            async with get_async_session() as session:  # type: ignore
                res = await session.execute(select(Lead).limit(3000))
                return res.scalars().all()

        rows = await _safe_db_call(_q(), timeout=8.0, label="metrics.lead_select") or []
        today = _today_start_utc().replace(tzinfo=None)
        new_today = 0
        qualified_today = 0
        appts = 0
        for lead in rows:
            created = getattr(lead, "created_at", None)
            if created and created >= today:
                new_today += 1
                if int(getattr(lead, "lead_score", 0) or 0) >= 70:
                    qualified_today += 1
            if _enum_value(lead, "status") == "appointment":
                appts += 1
        out["new_leads_today"] = new_today
        out["qualified_leads_today"] = qualified_today
        out["appointments_booked"] = appts
    except Exception as e:
        logger.debug(f"[office_hq] metrics lead-query skipped: {e}")

    try:
        from app.platform import approvals_bridge

        d = approvals_bridge.list_drafts(include_decided=False) or {}
        out["approvals_needed"] = int((d.get("counts") or {}).get("pending") or 0)
    except Exception as e:
        logger.debug(f"[office_hq] metrics approvals skipped: {e}")

    try:
        from app.billing import dunning

        out["payments_pending"] = int(dunning.stats().get("open") or 0)
    except Exception as e:
        logger.debug(f"[office_hq] metrics dunning skipped: {e}")

    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        out["system_issues"] = len(h.get("overdue") or []) + len(h.get("never_ran") or [])
    except Exception as e:
        logger.debug(f"[office_hq] metrics automation_health skipped: {e}")

    return out


# --------------------------------------------------------------------------- #
# Pipeline board — 12 stages. Each stage: source real|partial|mock + note.
# `items_limit`: the snapshot embeds top-3-per-stage for the board mini-cards;
# the stage-detail drawer (pipeline_stage_detail) asks for a fuller list so its
# filter/search controls have something real to operate on.
# --------------------------------------------------------------------------- #
async def build_pipeline(
    items_limit: int = 3, live_stats: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    stages: dict[str, dict[str, Any]] = {
        m["id"]: {
            **m,
            "count": 0,
            "stuckCount": 0,
            "errorCount": 0,
            "items": [],
            "source": "mock",
            "note": "Backend data not wired yet.",
        }
        for m in PIPELINE_STAGE_META
    }
    try:
        from app.platform import admin_pipeline_overrides

        overrides = admin_pipeline_overrides.read_all_overrides()
    except Exception:
        overrides = {}
    try:
        from app.platform import approvals_bridge

        _appr = approvals_bridge.list_drafts(include_decided=False) or {}
        approval_titles = [str(d.get("title") or "").lower() for d in (_appr.get("drafts") or [])]
    except Exception:
        approval_titles = []

    # 1) Lead Source / Import — real.
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.lead import Lead

        async def _q():
            async with get_async_session() as session:  # type: ignore
                res = await session.execute(
                    select(Lead).order_by(Lead.created_at.desc()).limit(500)
                )
                return list(res.scalars().all())

        rows = await _safe_db_call(_q(), timeout=8.0, label="pipeline.lead_select") or []
        s = stages["lead_source"]
        s["count"] = len(rows)
        s["source"] = "real"
        s["note"] = "Leads table — last 500 rows scanned."
        s["items"] = [
            _lead_item(r, "lead_source", overrides, approval_titles) for r in rows[:items_limit]
        ]

        # 2) Cleaning & Enrichment — PARTIAL: real verification flags, but no
        # dedicated dedupe/enrichment table exists (Diya's dedupe pass is
        # report-only). Approximated via verified/phone_verified flags.
        unverified = [r for r in rows if not getattr(r, "phone_verified", False)]
        s2 = stages["cleaning_enrichment"]
        s2["count"] = len(unverified)
        s2["source"] = "partial"
        s2["note"] = (
            "Approximated via phone_verified flag — no dedicated dedupe/enrichment table yet."
        )

        # 3) Scoring & Qualification — real (lead_score bands + rejection statuses).
        hot = [r for r in rows if int(getattr(r, "lead_score", 0) or 0) >= 70]
        warm = [r for r in rows if 40 <= int(getattr(r, "lead_score", 0) or 0) < 70]
        rejected_st = {"not_interested", "wrong_number", "dnd", "lost"}
        rejected = [r for r in rows if _enum_value(r, "status") in rejected_st]
        s3 = stages["scoring_qualification"]
        s3["count"] = len(hot) + len(warm)
        s3["hot_count"] = len(hot)  # score>=70 (asli hot)
        s3["warm_count"] = len(warm)  # 40-69 (warm — "hot" NAHI)
        s3["stuckCount"] = 0
        s3["source"] = "real"
        s3["note"] = (
            f"{len(hot)} hot (score>=70) · {len(warm)} warm (40-69) · {len(rejected)} rejected."
        )
        s3["items"] = [
            _lead_item(r, "scoring_qualification", overrides, approval_titles)
            for r in hot[:items_limit]
        ]

        # 5) Outreach Queue — PARTIAL: only the voice-call channel is directly
        # queryable via Lead.next_call_at (email/WhatsApp cadence state lives
        # in data/cadence_leads.jsonl, not summarized here for this pass).
        now_dt = datetime.utcnow()
        due = [r for r in rows if getattr(r, "next_call_at", None) and r.next_call_at <= now_dt]
        s5 = stages["outreach_queue"]
        s5["count"] = len(due)
        s5["stuckCount"] = len(
            [
                r
                for r in due
                if r.next_call_at < now_dt - timedelta(hours=24)
                and not _is_resolved(overrides, getattr(r, "id", ""))
            ]
        )
        s5["source"] = "partial"
        s5["note"] = (
            "Voice call queue only (Lead.next_call_at). Email/WhatsApp cadence state not merged in yet."
        )
        s5["items"] = [
            _lead_item(r, "outreach_queue", overrides, approval_titles) for r in due[:items_limit]
        ]

        # 6) Conversation / Follow-up — real (CALLBACK status).
        callback = [r for r in rows if _enum_value(r, "status") == "callback"]
        s6 = stages["conversation_followup"]
        s6["count"] = len(callback)
        s6["stuckCount"] = len(
            [
                r
                for r in callback
                if getattr(r, "next_call_at", None)
                and r.next_call_at < now_dt
                and not _is_resolved(overrides, getattr(r, "id", ""))
            ]
        )
        s6["source"] = "real"
        s6["items"] = [
            _lead_item(r, "conversation_followup", overrides, approval_titles)
            for r in callback[:items_limit]
        ]

        # 7) Appointment / Demo Booking — real.
        appt = [r for r in rows if _enum_value(r, "status") == "appointment"]
        s7 = stages["appointment_booking"]
        s7["count"] = len(appt)
        s7["stuckCount"] = len(
            [
                r
                for r in appt
                if getattr(r, "appointment_date", None)
                and r.appointment_date < now_dt
                and not _is_resolved(overrides, getattr(r, "id", ""))
            ]
        )
        s7["source"] = "real"
        s7["items"] = [
            _lead_item(r, "appointment_booking", overrides, approval_titles)
            for r in appt[:items_limit]
        ]
    except Exception as e:
        logger.warning(f"[office_hq] pipeline lead-stages failed: {e}")

    # 4) Campaign Planning — PARTIAL: total content-queue depth is real
    # (reused from admin_dashboard_builders), per-item drill-down is not
    # cheaply available across all clients in one pass. Reuses the SAME
    # live_stats fetch as build_metrics (see _safe_collect_live_stats) — this
    # used to call _collect_live_stats() a SECOND time here, doubling an
    # already-expensive sync scan (confirmed 2026-07-01 prod timeout).
    try:
        live = live_stats if live_stats is not None else await _safe_collect_live_stats()
        s4 = stages["campaign_planning"]
        s4["count"] = int(live.get("content_items_generated") or 0)
        s4["source"] = "partial"
        s4["note"] = (
            "Total content-queue depth across clients (auto_content). Per-item preview not wired."
        )
    except Exception as e:
        logger.debug(f"[office_hq] campaign_planning skipped: {e}")

    # 8) Deal / Conversion — real (sales_pipeline deals store).
    try:
        from app.marketing import sales_pipeline

        deals = sales_pipeline.list_deals(limit=200) or {}
        st = sales_pipeline.stats() or {}
        s8 = stages["deal_conversion"]
        s8["count"] = int(st.get("open") or 0)
        stuck_cut = _now().replace(tzinfo=None) - timedelta(days=14)
        stuck = 0
        for d in deals:
            if d.get("stage") in ("demo_sent", "proposal_sent", "negotiating") and not _is_resolved(
                overrides, d.get("id")
            ):
                try:
                    upd = datetime.fromisoformat(str(d.get("updated_at")).replace("Z", "+00:00"))
                    if upd.replace(tzinfo=None) < stuck_cut:
                        stuck += 1
                except Exception:
                    pass
        s8["stuckCount"] = stuck
        s8["source"] = "real" if st.get("engine_on") else "partial"
        s8["note"] = (
            "Deals store (data/deals.jsonl) — 8-stage sales funnel."
            if st.get("engine_on")
            else "SALES_ENGINE flag is off — deals store exists but is not being fed automatically."
        )
        s8["items"] = [
            _deal_item(d, overrides, approval_titles, stuck_cut)
            for d in list(reversed(deals))[:items_limit]
        ]
    except Exception as e:
        logger.debug(f"[office_hq] deal_conversion skipped: {e}")

    # 9) Customer Onboarding — PARTIAL: no bulk-queryable JourneyStage table
    # (ClientJourneyTracker is an in-memory/per-lead dataclass, not a DB
    # table) — approximated via Subscription status=TRIAL as "onboarding".
    # Fetched ONCE here and reused by stage 11 (billing_subscription) below —
    # used to be two separate Subscription queries, doubling DB round-trips.
    subs: list[Any] = []
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.payment import Subscription

        async def _subq():
            async with get_async_session() as session:  # type: ignore
                res = await session.execute(select(Subscription).limit(1000))
                return res.scalars().all()

        subs = await _safe_db_call(_subq(), timeout=8.0, label="pipeline.subscription_select") or []
        trial = sum(1 for s in subs if "trial" in str(getattr(s, "status", "")).lower())
        s9 = stages["customer_onboarding"]
        s9["count"] = trial
        s9["source"] = "partial"
        s9["note"] = (
            "Approximated via Subscription.status=trial — no bulk onboarding-checklist table exists yet."
        )
    except Exception as e:
        logger.debug(f"[office_hq] customer_onboarding skipped: {e}")

    # 10) Service Delivery / Automation Running — PARTIAL: job-health proxy.
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        content_jobs = {"content", "blog", "afternoon_content", "weekly_marketing"}
        running = [
            j
            for j in (h.get("jobs") or [])
            if j.get("job") in content_jobs and j.get("status") == "ok"
        ]
        failed = [
            j
            for j in (h.get("jobs") or [])
            if j.get("job") in content_jobs and j.get("status") == "last_failed"
        ]
        s10 = stages["service_delivery"]
        s10["count"] = len(running)
        s10["errorCount"] = len(failed)
        s10["source"] = "partial"
        s10["note"] = (
            "Content-job heartbeat proxy (automation_health) — not a per-customer delivery ledger."
        )
    except Exception as e:
        logger.debug(f"[office_hq] service_delivery skipped: {e}")

    # 11) Billing / Subscription — real (Subscription + dunning). Reuses `subs`
    # fetched once above (stage 9) instead of a second Subscription query.
    try:
        from app.billing import dunning

        active = sum(1 for s in subs if "active" in str(getattr(s, "status", "")).lower())
        past_due = sum(1 for s in subs if "past_due" in str(getattr(s, "status", "")).lower())
        dstats = dunning.stats() or {}
        s11 = stages["billing_subscription"]
        s11["count"] = active
        s11["stuckCount"] = past_due
        s11["errorCount"] = int(dstats.get("open") or 0)
        s11["source"] = "real"
        s11["note"] = (
            f"{active} active subs · {past_due} past_due · {dstats.get('open', 0)} dunning cases open."
        )
        s11["items"] = [
            _dunning_item(c, overrides) for c in (dstats.get("open_cases") or [])[:items_limit]
        ]
    except Exception as e:
        logger.debug(f"[office_hq] billing_subscription skipped: {e}")

    # 12) Retention / Growth — real (client_health).
    try:
        from app.platform import client_health

        rep = (
            await _safe_db_call(
                client_health.health_report(), timeout=8.0, label="pipeline.client_health"
            )
            or []
        )
        red = [r for r in rep if r.get("band") == "red"]
        s12 = stages["retention_growth"]
        s12["count"] = len(rep)
        s12["errorCount"] = len(red)
        s12["source"] = "real"
        s12["items"] = [_health_item(r, overrides) for r in red[:items_limit]]
    except Exception as e:
        logger.debug(f"[office_hq] retention_growth skipped: {e}")

    return [stages[m["id"]] for m in PIPELINE_STAGE_META]


async def warm_lead_sla_nudge() -> dict[str, Any]:
    """W4.1: pipeline me stuck (>24h — build_pipeline ke existing per-stage stuckCount) +
    warm (40-69) leads → FOUNDER ko ntfy nudge (founder-only, koi customer-send NAHI =
    zero §5 ban/deliverability surface). Gated WARM_SLA_NUDGE (default OFF); threshold
    WARM_SLA_MIN (default 3). build_pipeline modify nahi karta — sirf uske counts reuse."""
    import os as _os

    if _os.getenv("WARM_SLA_NUDGE", "").strip().lower() not in ("1", "true", "yes", "on"):
        return {"nudged": False, "reason": "disabled"}
    try:
        stages = await build_pipeline(items_limit=1)
        stuck = sum(int((st or {}).get("stuckCount") or 0) for st in (stages or []))
        warm = sum(int((st or {}).get("warm_count") or 0) for st in (stages or []))
        try:
            thresh = max(1, int(_os.getenv("WARM_SLA_MIN", "3") or 3))
        except Exception:
            thresh = 3
        if stuck >= thresh:
            from app.platform import ops_alerts

            ops_alerts.alert_warm_sla(stuck, warm)
            return {"nudged": True, "stuck": stuck, "warm": warm}
        return {"nudged": False, "stuck": stuck, "warm": warm, "reason": "below_threshold"}
    except Exception as e:
        logger.debug(f"[office_hq] warm_lead_sla_nudge skipped: {e}")
        return {"error": str(e)}


def _apply_override(item: dict[str, Any], overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Merge a persisted admin annotation (owner/next-action/resolved/status)
    onto a freshly-built item. Real, persisted (app.platform.admin_pipeline_overrides)
    — never fabricated. Resolving a stuck item clears its slaRisk badge."""
    try:
        ov = overrides.get(str(item.get("id")) or "") or {}
        if ov.get("owner_agent"):
            item["assignedAgentId"] = ov["owner_agent"]
        if ov.get("next_action"):
            item["nextAction"] = ov["next_action"]
        if ov.get("status_override") and item.get("type") == "lead":
            item["status"] = ov["status_override"]
        if ov.get("stuck_resolved_at"):
            item["slaRisk"] = False
    except Exception:
        pass
    return item


def _lead_item(
    r: Any,
    stage_id: str,
    overrides: dict[str, dict[str, Any]] | None = None,
    approval_titles: list[str] | None = None,
) -> dict[str, Any]:
    name = getattr(r, "company_name", "") or getattr(r, "contact_name", "") or "Lead"
    item = {
        "id": getattr(r, "id", ""),
        "name": name,
        "type": "lead",
        "stageId": stage_id,
        "source": _enum_value(r, "source"),
        "city": getattr(r, "city", "") or "",
        "category": getattr(r, "niche", "") or getattr(r, "category", "") or "",
        "assignedAgentId": None,
        "priority": "hot" if int(getattr(r, "lead_score", 0) or 0) >= 70 else "normal",
        "status": _enum_value(r, "status"),
        "lastActivityAt": _iso(getattr(r, "updated_at", None)),
        "nextAction": (
            "Call karo"
            if stage_id in ("outreach_queue", "conversation_followup")
            else "Review karo"
        ),
        "slaRisk": bool(
            getattr(r, "next_call_at", None)
            and r.next_call_at < datetime.utcnow() - timedelta(hours=24)
        ),
        "needsApproval": _needs_approval(name, approval_titles or []),
    }
    return _apply_override(item, overrides or {})


def _deal_item(
    d: dict[str, Any],
    overrides: dict[str, dict[str, Any]] | None = None,
    approval_titles: list[str] | None = None,
    stuck_cut: datetime | None = None,
) -> dict[str, Any]:
    name = d.get("business_name") or "Deal"
    sla = False
    if stuck_cut is not None and d.get("stage") in ("demo_sent", "proposal_sent", "negotiating"):
        try:
            upd = datetime.fromisoformat(str(d.get("updated_at")).replace("Z", "+00:00"))
            sla = upd.replace(tzinfo=None) < stuck_cut
        except Exception:
            sla = False
    item = {
        "id": d.get("id"),
        "name": name,
        "type": "deal",
        "stageId": "deal_conversion",
        "source": "sales_pipeline",
        "city": d.get("city") or "",
        "category": d.get("niche") or "",
        "assignedAgentId": None,
        "priority": "normal",
        "status": d.get("stage") or "",
        "lastActivityAt": d.get("updated_at"),
        "nextAction": "Next stage push karo" if d.get("stage") not in ("won", "lost") else "Closed",
        "slaRisk": sla,
        "needsApproval": _needs_approval(name, approval_titles or []),
    }
    return _apply_override(item, overrides or {})


def _dunning_item(
    c: dict[str, Any], overrides: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    item = {
        "id": c.get("id") or c.get("client_id"),
        "name": c.get("business_name") or c.get("client_id") or "Client",
        "type": "invoice",
        "stageId": "billing_subscription",
        "source": "dunning",
        "city": "",
        "category": "",
        "assignedAgentId": "nikhil",
        "priority": "high",
        "status": c.get("status") or "open",
        "lastActivityAt": c.get("updated_at") or c.get("created_at"),
        "nextAction": "Payment reminder bhejo",
        "slaRisk": True,
        "needsApproval": False,
    }
    return _apply_override(item, overrides or {})


def _health_item(
    r: dict[str, Any], overrides: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    item = {
        "id": r.get("client_id"),
        "name": r.get("business_name") or r.get("client_id") or "Client",
        "type": "customer",
        "stageId": "retention_growth",
        "source": "client_health",
        "city": "",
        "category": "",
        "assignedAgentId": "nikhil",
        "priority": "high" if r.get("band") == "red" else "normal",
        "status": r.get("band") or "",
        "lastActivityAt": None,
        "nextAction": r.get("action") or "Contact karo",
        "slaRisk": r.get("band") == "red",
        "needsApproval": False,
    }
    return _apply_override(item, overrides or {})


async def build_approvals() -> dict[str, Any]:
    """Approvals section. `drafts`+`counts` keep their original approvals_bridge
    shape (drift-locked consumers: rooms approvalCount, metrics.approvals_needed,
    next_best_actions). ADDITIVE `queue` key = the UNIFIED actionable list the
    Approvals panel renders: bridge drafts + code-upgrader patch proposals +
    self-improve approval gates — every entry decided via its EXISTING admin API
    (documented per-kind in `decide` hints below); nothing new is stored here."""
    out: dict[str, Any] = {"drafts": [], "counts": {"by_source": {}, "pending": 0}}
    try:
        from app.platform import approvals_bridge

        d = approvals_bridge.list_drafts(include_decided=False) or {}
        drafts = d.get("drafts") or []
        for item in drafts:
            item["room"] = APPROVAL_ROOM.get(item.get("source"), "coordinator")
        out["drafts"] = drafts
        out["counts"] = d.get("counts") or {}
    except Exception as e:
        logger.debug(f"[office_hq] build_approvals failed: {e}")
    out["queue"] = build_approval_queue(drafts=out["drafts"])
    try:
        out["counts"]["total_pending"] = len(out["queue"])
    except Exception:
        pass
    # Audit-trail strip — "who decided what, when" right under the panel that
    # decides it, closing the loop visually (2026-07-03).
    try:
        from app.platform import approvals_bridge

        out["recent_decisions"] = approvals_bridge.recent_decisions(limit=8)
    except Exception as e:
        logger.debug(f"[office_hq] recent_decisions skipped: {e}")
        out["recent_decisions"] = []
    return out


def build_approval_queue(drafts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Unified pending-approvals list across the three EXISTING queues.

    Kinds + their existing decide APIs (frontend/boss-review reuse these — no
    parallel approve endpoints were created):
      - draft       -> POST  /api/growth/approvals/drafts/{source}/{id}/decide
      - patch       -> POST  /api/growth/upgrader/patches/{id}/status  (SUPER_ADMIN)
      - selfimprove -> PATCH /api/growth/selfimprove/approval/{id}/approve|reject

    Read-only aggregation; each source degrades to [] independently. Never raises."""
    queue: list[dict[str, Any]] = []
    # 1) approvals_bridge drafts (sales/coordinator/fde)
    try:
        if drafts is None:
            from app.platform import approvals_bridge

            drafts = (approvals_bridge.list_drafts(include_decided=False) or {}).get("drafts") or []
        for d in drafts:
            queue.append(
                {
                    "kind": "draft",
                    "source": d.get("source") or "",
                    "id": str(d.get("id") or ""),
                    "title": str(d.get("title") or d.get("id") or "")[:160],
                    "summary": str(d.get("body") or "")[:400],
                    "created_at": d.get("created_at") or "",
                }
            )
    except Exception as e:
        logger.debug(f"[office_hq] approval_queue drafts skipped: {e}")
    # 2) code-upgrader patch proposals (Vikram) — approve is a MARKER only;
    # patches are NEVER auto-applied (apply stays in the manual deploy loop).
    try:
        from app.agents import code_upgrader

        for p in code_upgrader.list_patches("proposed", 20) or []:
            queue.append(
                {
                    "kind": "patch",
                    "source": "code_upgrader",
                    "id": str(p.get("id") or ""),
                    "title": str(p.get("title") or p.get("issue") or p.get("id") or "")[:160],
                    "summary": str(p.get("rationale") or p.get("issue") or "")[:400],
                    "created_at": p.get("at") or "",
                }
            )
    except Exception as e:
        logger.debug(f"[office_hq] approval_queue patches skipped: {e}")
    # 3) self-improve approval gates (SELF_IMPROVE_APPROVAL)
    try:
        from app.agents import self_improve

        for t in (self_improve.approval_status() or {}).get("pending") or []:
            queue.append(
                {
                    "kind": "selfimprove",
                    "source": "self_improve",
                    "id": str(t.get("id") or ""),
                    "title": str(t.get("task") or t.get("id") or "")[:160],
                    "summary": (
                        str(t.get("reason") or "")
                        + (f" (est. cost ${t.get('cost')})" if t.get("cost") else "")
                    )[:400],
                    "created_at": t.get("timestamp") or "",
                }
            )
    except Exception as e:
        logger.debug(f"[office_hq] approval_queue selfimprove skipped: {e}")
    return [q for q in queue if q["id"]]


def build_coordination(limit: int = 5) -> list[dict[str, Any]]:
    """Last N coordinator/council runs (read-only) from the EXISTING persisted
    run history data/coordination_runs.jsonl (same file approvals_bridge reads).
    Never raises; [] when the file is absent/empty."""
    out: list[dict[str, Any]] = []
    try:
        from app.platform import approvals_bridge

        rows = approvals_bridge._read_jsonl(approvals_bridge._COORD_RUNS)
        for r in rows[-max(1, min(20, limit)) :][::-1]:
            outcome = str(
                r.get("summary")
                or r.get("solution")
                or r.get("design")
                or r.get("implementation_plan")
                or r.get("verdict")
                or ""
            )[:220]
            out.append(
                {
                    "run_id": str(r.get("run_id") or ""),
                    "goal": str(r.get("goal") or r.get("query") or "coordination run")[:140],
                    "mode": str(r.get("pattern") or r.get("mode") or "sequential"),
                    "executed": bool(r.get("execute")),
                    "boss": str(r.get("boss") or "manager"),
                    "assignments": list(r.get("assignments") or [])[:12],
                    "handoffs": list(r.get("handoffs") or [])[:80],
                    "verdict": r.get("verdict")
                    or {
                        "by": "manager",
                        "status": "recorded" if outcome else "incomplete",
                        "summary": outcome,
                    },
                    "coordination_coverage": r.get("coordination_coverage") or {},
                    "outcome": outcome,
                    "at": r.get("at") or "",
                }
            )
    except Exception as e:
        logger.debug(f"[office_hq] build_coordination skipped: {e}")
    return out


# --------------------------------------------------------------------------- #
# Boss Finalizer — the office "manager agent". For each pending approval item
# it asks the FREE LLM chain (same app.voice_agent.free_ai chain the council
# uses) for a short verdict + reason. RECOMMEND-ONLY by design:
#   - stores nothing (verdicts returned in the response only),
#   - never calls any approve/reject API itself — the HUMAN still clicks,
#   - code patches stay NEVER-auto-applied (CLAUDE.md hard rule intact).
# Cap 10 items, one LLM call per item, per-call hard timeout, never raises.
# --------------------------------------------------------------------------- #
_BOSS_SYSTEM = (
    "Tu LeadGenAI platform ka operations Boss hai. Ek pending approval item diya "
    "jayega (type + title + summary). Decide karo: approve ya reject. "
    "Sirf isi format me jawab do, ek line: VERDICT: approve|reject | REASON: <1 short Hinglish sentence>. "
    "Conservative raho — risky/unclear/irreversible lage to reject bolo."
)


def _parse_boss_reply(text: str) -> tuple[str, str]:
    """'VERDICT: approve | REASON: ...' -> ("approve"|"reject", reason). Lenient."""
    t = (text or "").strip()
    low = t.lower()
    verdict = (
        "reject"
        if (
            "reject" in low
            and low.find("reject") < (low.find("approve") if "approve" in low else 10**9)
        )
        else ("approve" if "approve" in low else "")
    )
    reason = t
    if "reason" in low:
        try:
            reason = t[low.index("reason") + len("reason") :].lstrip(":| ").strip()
        except Exception:
            reason = t
    return verdict, reason[:200]


async def boss_review(max_items: int = 10, per_item_timeout: float = 20.0) -> dict[str, Any]:
    """Verdict + reason for each pending approval item (cap `max_items`).
    Read-only, never raises; a failed/timed-out LLM call yields verdict="skip"."""
    items = build_approval_queue()[: max(1, min(10, max_items))]
    if not items:
        return {"ok": True, "verdicts": [], "reviewed": 0, "note": "koi pending approval nahi"}

    async def _one(it: dict[str, Any]) -> dict[str, Any]:
        base = {"kind": it["kind"], "id": it["id"]}
        try:
            from app.voice_agent import free_ai

            user = (
                f"Type: {it['kind']} ({it.get('source')})\nTitle: {it['title']}\n"
                f"Summary: {it.get('summary') or '(none)'}\n"
                + (
                    "NOTE: code patch approve = sirf review-marker; apply hamesha manual deploy-loop me hota hai."
                    if it["kind"] == "patch"
                    else ""
                )
            )
            text, provider = await asyncio.wait_for(
                free_ai.chat(
                    _BOSS_SYSTEM,
                    [{"role": "user", "content": user}],
                    max_tokens=120,
                    temperature=0.3,
                    scope="office_boss",
                ),
                timeout=per_item_timeout,
            )
            verdict, reason = _parse_boss_reply(text)
            if not verdict:
                return {
                    **base,
                    "verdict": "skip",
                    "reason": "LLM se clear verdict nahi mila",
                    "provider": provider,
                }
            return {**base, "verdict": verdict, "reason": reason, "provider": provider}
        except Exception as e:
            logger.debug(f"[office_hq] boss_review item {it.get('id')} skipped: {e}")
            return {**base, "verdict": "skip", "reason": "LLM unavailable/timeout"}

    try:
        results = await asyncio.gather(*[_one(it) for it in items], return_exceptions=True)
        verdicts = [r for r in results if isinstance(r, dict)]
    except Exception as e:
        logger.warning(f"[office_hq] boss_review failed: {e}")
        verdicts = []
    return {
        "ok": True,
        "verdicts": verdicts,
        "reviewed": len(verdicts),
        "note": "Boss sirf RECOMMEND karta hai — final Approve/Reject HUMAN click se hi hota hai.",
        "generated_at": _now().isoformat(),
    }


def build_system_health() -> dict[str, Any]:
    try:
        from app.platform import automation_health

        return automation_health.health() or {}
    except Exception as e:
        logger.debug(f"[office_hq] build_system_health failed: {e}")
        return {"jobs": [], "overdue": [], "never_ran": [], "queue": {}}


def next_best_actions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure function over an assembled snapshot — no IO, easy to test."""
    actions: list[dict[str, Any]] = []
    try:
        metrics = snapshot.get("metrics") or {}
        approvals = snapshot.get("approvals") or {}
        health = snapshot.get("system_health") or {}
        pipeline = {s["id"]: s for s in (snapshot.get("pipeline") or [])}

        pending = int((approvals.get("counts") or {}).get("pending") or 0)
        if pending:
            actions.append(
                {
                    "label": f"🗂️ {pending} draft(s) approval ke liye pending — review karo",
                    "severity": "warning",
                    "cta_target": "approvals",
                }
            )
        overdue = len(health.get("overdue") or [])
        if overdue:
            actions.append(
                {
                    "label": f"⚠️ {overdue} automation job(s) time par nahi chale — check karo",
                    "severity": "warning",
                    "cta_target": "system_health",
                }
            )
        if int(metrics.get("payments_pending") or 0):
            actions.append(
                {
                    "label": f"💳 {metrics['payments_pending']} payment pending — reminder bhejo",
                    "severity": "warning",
                    "cta_target": "billing_subscription",
                }
            )
        retention = pipeline.get("retention_growth") or {}
        if int(retention.get("errorCount") or 0):
            actions.append(
                {
                    "label": f"❤️ {retention['errorCount']} client churn-risk (red) — proactively contact karo",
                    "severity": "error",
                    "cta_target": "retention_growth",
                }
            )
        deal = pipeline.get("deal_conversion") or {}
        if int(deal.get("stuckCount") or 0):
            actions.append(
                {
                    "label": f"🤝 {deal['stuckCount']} deal(s) 14+ din se stuck — follow-up karo",
                    "severity": "warning",
                    "cta_target": "deal_conversion",
                }
            )
        hot = int((pipeline.get("scoring_qualification") or {}).get("count") or 0)
        followup = int((pipeline.get("conversation_followup") or {}).get("stuckCount") or 0)
        if followup:
            actions.append(
                {
                    "label": f"🔥 {followup} follow-up overdue hai — hot leads ko call karo",
                    "severity": "warning",
                    "cta_target": "conversation_followup",
                }
            )
        elif hot:
            actions.append(
                {
                    "label": f"🔥 {hot} hot lead(s) available — outreach shuru karo",
                    "severity": "info",
                    "cta_target": "scoring_qualification",
                }
            )
    except Exception as e:
        logger.debug(f"[office_hq] next_best_actions failed: {e}")
    order = {"error": 0, "warning": 1, "info": 2}
    actions.sort(key=lambda a: order.get(a.get("severity", "info"), 3))
    return actions[:6]


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(value or "low"), 3)


def build_boss_brief(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Pure executive brief for the first viewport of /app/office."""
    try:
        metrics = snapshot.get("metrics") or {}
        pipeline = {s.get("id"): s for s in (snapshot.get("pipeline") or [])}
        approvals = snapshot.get("approvals") or {}
        health = snapshot.get("system_health") or {}
        pending = int(
            (approvals.get("counts") or {}).get("total_pending")
            or (approvals.get("counts") or {}).get("pending")
            or 0
        )
        overdue = len(health.get("overdue") or [])
        dlq = int((health.get("queue") or {}).get("dlq") or 0)
        stuck_followups = int((pipeline.get("conversation_followup") or {}).get("stuckCount") or 0)
        stale_count = len(snapshot.get("stale_tasks") or [])
        s3 = pipeline.get("scoring_qualification") or {}
        hot = int(s3.get("hot_count", s3.get("count") or 0) or 0)  # asli hot (score>=70)
        warm = int(s3.get("warm_count") or 0)  # warm (40-69)
        new_today = int(metrics.get("new_leads_today") or 0)
        qualified_today = int(metrics.get("qualified_leads_today") or 0)
        # Mid-funnel stall: aaj kaafi naye leads aaye par ek bhi qualify nahi hua
        # = qualification/outreach ruka hai (money-funnel band). Pehle yeh "System
        # healthy" ke neeche chhup jaata tha; ab honestly risk me surface hota hai.
        midfunnel_stall = new_today >= 20 and qualified_today == 0

        risk_label = "System healthy"
        risk_target = "systemHealthPanel"
        if dlq:
            risk_label = f"{dlq} DLQ item(s) repair chahiye"
            risk_target = "failureConsoleCard"
        elif midfunnel_stall:
            risk_label = f"Mid-funnel ruka: {new_today} leads aaye, 0 qualified"
            risk_target = "pipelineBoard"
        elif overdue:
            risk_label = f"{overdue} automation job overdue"
            risk_target = "systemHealthPanel"
        elif stale_count:
            risk_label = f"{stale_count} agent task(s) stuck >10min"
            risk_target = "taskQueuePanel"
        elif stuck_followups:
            risk_label = f"{stuck_followups} follow-up stuck"
            risk_target = "pipelineBoard"

        if pending:
            recommendation = {
                "label": f"{pending} approval review karo",
                "cta_target": "approvalsPanel",
            }
        elif midfunnel_stall:
            recommendation = {
                "label": "Mid-funnel dekho: qualify + outreach chalu karo",
                "cta_target": "pipelineBoard",
            }
        elif stuck_followups:
            recommendation = {"label": "Stuck follow-ups clear karo", "cta_target": "pipelineBoard"}
        elif hot:
            recommendation = {"label": "Hot leads pe Rohan ko lagao", "cta_target": "pipelineBoard"}
        elif warm:
            recommendation = {
                "label": f"{warm} warm lead(s) pe outreach/nurture lagao",
                "cta_target": "pipelineBoard",
            }
        else:
            recommendation = {"label": "Office feed monitor karo", "cta_target": "feedCard"}

        # Opportunity honestly: hot (score>=70) aur warm (40-69) alag — pehle dono
        # ko "hot" bola jaa raha tha (0 hot hone par bhi "53 hot ready"). Fix 2026-07-05.
        if hot:
            opp_label = f"{hot} hot lead(s) ready"
        elif warm:
            opp_label = f"{warm} warm lead(s) — nurture/outreach karo"
        else:
            opp_label = "Aaj ka pipeline calm hai"

        # "Aaj" label explicit; hot/warm sahi label ke saath (numbers sahi the,
        # par warm ko "hot" bolna galat tha). Fix 2026-07-05.
        headline = (
            f"Aaj: {new_today} naye leads, {qualified_today} qualified"
            + (f" · {hot} hot ready" if hot else (f" · {warm} warm" if warm else ""))
            + f" · MRR Rs {int(metrics.get('mrr') or 0):,}"
        )
        return {
            "headline": headline,
            "risk": {"label": risk_label, "cta_target": risk_target},
            "opportunity": {"label": opp_label, "cta_target": "pipelineBoard"},
            "recommendation": recommendation,
            "confidence": "high" if snapshot.get("generated_at") else "medium",
            "source": "office_snapshot",
        }
    except Exception as e:
        logger.debug(f"[office_hq] build_boss_brief failed: {e}")
        return {
            "headline": "Office snapshot partial hai",
            "risk": {"label": "Data partial", "cta_target": "systemHealthPanel"},
            "opportunity": {"label": "Snapshot reload karo", "cta_target": "manualRefreshBtn"},
            "recommendation": {"label": "Refresh now", "cta_target": "manualRefreshBtn"},
            "confidence": "low",
            "source": "fallback",
        }


def build_priority_actions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured, ranked action stack for the CEO command center."""
    actions: list[dict[str, Any]] = []
    try:
        approvals = snapshot.get("approvals") or {}
        health = snapshot.get("system_health") or {}
        pipeline = {s.get("id"): s for s in (snapshot.get("pipeline") or [])}
        metrics = snapshot.get("metrics") or {}
        pending = int(
            (approvals.get("counts") or {}).get("total_pending")
            or (approvals.get("counts") or {}).get("pending")
            or 0
        )
        dlq = int((health.get("queue") or {}).get("dlq") or 0)
        overdue = len(health.get("overdue") or [])
        stuck = int((pipeline.get("conversation_followup") or {}).get("stuckCount") or 0)
        _s3 = pipeline.get("scoring_qualification") or {}
        hot = int(_s3.get("hot_count", _s3.get("count") or 0) or 0)
        warm = int(_s3.get("warm_count") or 0)
        new_today = int(metrics.get("new_leads_today") or 0)
        qualified_today = int(metrics.get("qualified_leads_today") or 0)
        retention_red = int((pipeline.get("retention_growth") or {}).get("errorCount") or 0)
        payments = int(metrics.get("payments_pending") or 0)

        if new_today >= 20 and qualified_today == 0:
            actions.append(
                {
                    "id": "midfunnel_stall",
                    "title": f"Mid-funnel ruka: {new_today} leads, 0 qualified",
                    "why": "Qualification/outreach ruka hai — money-funnel band, revenue rok raha.",
                    "severity": "critical",
                    "owner": "rohan",
                    "room": "sales_crm",
                    "age": "",
                    "cta_label": "Open Pipeline",
                    "cta_target": "pipelineBoard",
                }
            )
        if dlq:
            actions.append(
                {
                    "id": "dlq",
                    "title": f"{dlq} failed job(s)",
                    "why": "Failed jobs automation trust block kar sakte hain.",
                    "severity": "critical",
                    "owner": "hermes",
                    "room": "platform_engineering",
                    "age": "",
                    "cta_label": "Open Reliability",
                    "cta_target": "failureConsoleCard",
                }
            )
        if overdue:
            actions.append(
                {
                    "id": "overdue_jobs",
                    "title": f"{overdue} overdue automation job(s)",
                    "why": "Scheduled loops heartbeat miss kar rahe hain.",
                    "severity": "high",
                    "owner": "kavya",
                    "room": "platform_engineering",
                    "age": "",
                    "cta_label": "Open Health",
                    "cta_target": "systemHealthPanel",
                }
            )
        if pending:
            actions.append(
                {
                    "id": "approvals",
                    "title": f"{pending} approval(s) pending",
                    "why": "Human approval output ko block kar raha hai.",
                    "severity": "high",
                    "owner": "manager",
                    "room": "coordinator",
                    "age": "",
                    "cta_label": "Review Approvals",
                    "cta_target": "approvalsPanel",
                }
            )
        if stuck:
            actions.append(
                {
                    "id": "stuck_followups",
                    "title": f"{stuck} follow-up(s) stuck",
                    "why": "Warm leads ki value late follow-up se girti hai.",
                    "severity": "high",
                    "owner": "rohan",
                    "room": "sales_crm",
                    "age": "",
                    "cta_label": "Open Pipeline",
                    "cta_target": "conversation_followup",
                }
            )
        if retention_red:
            actions.append(
                {
                    "id": "retention",
                    "title": f"{retention_red} client(s) churn-risk",
                    "why": "Retention risk direct revenue risk hai.",
                    "severity": "high",
                    "owner": "nikhil",
                    "room": "admin_finance",
                    "age": "",
                    "cta_label": "Open Retention",
                    "cta_target": "retention_growth",
                }
            )
        if payments:
            actions.append(
                {
                    "id": "payments",
                    "title": f"{payments} payment(s) pending",
                    "why": "Cash collection ko operator attention chahiye.",
                    "severity": "medium",
                    "owner": "nikhil",
                    "room": "admin_finance",
                    "age": "",
                    "cta_label": "Open Billing",
                    "cta_target": "billing_subscription",
                }
            )
        if hot:
            actions.append(
                {
                    "id": "hot_leads",
                    "title": f"{hot} hot lead(s) ready",
                    "why": "Yeh immediate sales opportunity hai.",
                    "severity": "medium",
                    "owner": "rohan",
                    "room": "sales_crm",
                    "age": "",
                    "cta_label": "Open Hot Leads",
                    "cta_target": "scoring_qualification",
                }
            )
        elif warm:
            actions.append(
                {
                    "id": "warm_leads",
                    "title": f"{warm} warm lead(s) — nurture/outreach",
                    "why": "Warm leads ko outreach/nurture chahiye warna thande ho jayenge.",
                    "severity": "medium",
                    "owner": "rohan",
                    "room": "sales_crm",
                    "age": "",
                    "cta_label": "Open Pipeline",
                    "cta_target": "scoring_qualification",
                }
            )
    except Exception as e:
        logger.debug(f"[office_hq] build_priority_actions failed: {e}")
    actions.sort(key=lambda a: (_severity_rank(a.get("severity", "low")), a.get("id", "")))
    return actions[:5]


def build_room_workloads(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map action workload into the same room IDs used by the office map."""
    out: dict[str, dict[str, Any]] = {}
    try:
        agents_by_room: dict[str, list[dict[str, Any]]] = {}
        for agent in snapshot.get("agents") or []:
            agents_by_room.setdefault(str(agent.get("room") or "platform_engineering"), []).append(
                agent
            )
        for room in snapshot.get("rooms") or []:
            rid = str(room.get("id") or "")
            out[rid] = {
                "room": rid,
                "name": room.get("name") or rid,
                "owner_count": len(agents_by_room.get(rid, [])),
                "active_agents": [
                    a.get("key") or a.get("id")
                    for a in agents_by_room.get(rid, [])
                    if a.get("status") != "offline"
                ],
                "health": {
                    "active": int(room.get("activeTaskCount") or 0),
                    "blocked": int(room.get("blockedTaskCount") or 0),
                    "errors": int(room.get("errorCount") or 0),
                    "approvals": int(room.get("approvalCount") or 0),
                },
                "work_items": [],
                "source": "snapshot",
            }
        for item in build_priority_actions(snapshot):
            rid = item.get("room") or "coordinator"
            out.setdefault(
                rid,
                {
                    "room": rid,
                    "name": rid,
                    "owner_count": 0,
                    "active_agents": [],
                    "health": {},
                    "work_items": [],
                    "source": "snapshot",
                },
            )
            out[rid]["work_items"].append(item)
        for room in out.values():
            room["work_items"] = room.get("work_items", [])[:3]
    except Exception as e:
        logger.debug(f"[office_hq] build_room_workloads failed: {e}")
    return out


def build_replay(snapshot: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    """Snapshot-derived timeline for the operator replay panel."""
    items: list[dict[str, Any]] = []
    try:
        at = snapshot.get("generated_at") or _now().isoformat()
        for action in build_priority_actions(snapshot):
            items.append(
                {
                    "at": at,
                    "actor": action.get("owner") or "manager",
                    "title": action.get("title") or action.get("id"),
                    "detail": action.get("why") or "",
                    "target": action.get("cta_target") or "",
                    "kind": "priority",
                }
            )
        for run in snapshot.get("coordination") or []:
            items.append(
                {
                    "at": run.get("at") or at,
                    "actor": "manager",
                    "title": str(run.get("goal") or "Coordination run")[:120],
                    "detail": str(run.get("outcome") or "")[:180],
                    "target": "feedCard",
                    "kind": "coordination",
                }
            )
        for stage in snapshot.get("pipeline") or []:
            if int(stage.get("count") or 0):
                items.append(
                    {
                        "at": at,
                        "actor": "pipeline",
                        "title": f"{stage.get('name') or stage.get('id')}: {stage.get('count')} item(s)",
                        "detail": stage.get("note") or "",
                        "target": stage.get("id") or "pipelineBoard",
                        "kind": "pipeline",
                    }
                )
    except Exception as e:
        logger.debug(f"[office_hq] build_replay failed: {e}")
    capped = max(1, min(50, int(limit or 20)))
    return {"source": "snapshot", "items": items[:capped]}


def build_enterprise_features(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Pure feature-readiness matrix for /app/office.

    This is not a fake roadmap card. Every feature listed here is either backed
    by a section already present in the same snapshot, or points to the exact
    panel/action where the operator can use it. No IO, no side effects.
    """
    try:
        metrics = snapshot.get("metrics") or {}
        rooms = snapshot.get("rooms") or []
        agents = snapshot.get("agents") or []
        pipeline = snapshot.get("pipeline") or []
        approvals = snapshot.get("approvals") or {}
        health = snapshot.get("system_health") or {}
        schedule = snapshot.get("schedule") or []
        coordination = snapshot.get("coordination") or []
        nba = snapshot.get("next_best_actions") or []

        active_agents = len([a for a in agents if a.get("status") != "offline"])
        room_issues = sum(
            int(r.get("blockedTaskCount") or 0) + int(r.get("errorCount") or 0) for r in rooms
        )
        pipeline_items = sum(int(s.get("count") or 0) for s in pipeline)
        stuck_items = sum(int(s.get("stuckCount") or 0) for s in pipeline)
        error_items = sum(int(s.get("errorCount") or 0) for s in pipeline)
        pending_approvals = int(
            (approvals.get("counts") or {}).get("total_pending")
            or (approvals.get("counts") or {}).get("pending")
            or 0
        )
        health_jobs = health.get("jobs") or []
        overdue_jobs = len(health.get("overdue") or [])
        never_ran = len(health.get("never_ran") or [])
        queue = health.get("queue") or {}
        dlq_count = int(queue.get("dlq") or 0)

        def status(warn: bool = False, ready: bool = True) -> str:
            if not ready:
                return "action_needed"
            return "attention" if warn else "live"

        features = [
            {
                "id": "office_map",
                "name": "Interactive office map",
                "room": "Coordinator",
                "status": status(ready=bool(rooms and agents)),
                "metric": f"{len(rooms)} rooms / {len(agents)} agents",
                "cta_target": "stageWrap",
            },
            {
                "id": "live_roster",
                "name": "Live AI staff roster",
                "room": "Team",
                "status": status(warn=active_agents == 0, ready=bool(agents)),
                "metric": f"{active_agents}/{len(agents)} active",
                "cta_target": "leaderboardPanel",
            },
            {
                "id": "room_health",
                "name": "Room-level blocked/error signals",
                "room": "Ops",
                "status": status(warn=room_issues > 0, ready=bool(rooms)),
                "metric": f"{room_issues} room issues",
                "cta_target": "stageWrap",
            },
            {
                "id": "kpi_board",
                "name": "Executive KPI board",
                "room": "Finance",
                "status": "live",
                "metric": f"MRR Rs {int(metrics.get('mrr') or 0):,}",
                "cta_target": "kpiRow",
            },
            {
                "id": "next_actions",
                "name": "Next-best-action command strip",
                "room": "Boss",
                "status": status(warn=bool(nba)),
                "metric": f"{len(nba)} actions",
                "cta_target": "nbaCard",
            },
            {
                "id": "lead_pipeline",
                "name": "12-stage lead-to-renewal pipeline",
                "room": "Sales",
                "status": status(ready=bool(pipeline)),
                "metric": f"{pipeline_items} items",
                "cta_target": "pipelineBoard",
            },
            {
                "id": "stage_drilldown",
                "name": "Pipeline drill-down + filters",
                "room": "Sales",
                "status": status(ready=bool(pipeline)),
                "metric": "up to 50 items/stage",
                "cta_target": "pipelineBoard",
            },
            {
                "id": "owner_assignment",
                "name": "Owner assignment sidecar",
                "room": "Sales",
                "status": "live",
                "metric": "assign agent per item",
                "cta_target": "pipelineBoard",
            },
            {
                "id": "sla_repair",
                "name": "SLA stuck-item repair",
                "room": "Ops",
                "status": status(warn=stuck_items > 0),
                "metric": f"{stuck_items} stuck",
                "cta_target": "pipelineBoard",
            },
            {
                "id": "approval_queue",
                "name": "Unified approvals queue",
                "room": "Admin",
                "status": status(warn=pending_approvals > 0),
                "metric": f"{pending_approvals} pending",
                "cta_target": "approvalsPanel",
            },
            {
                "id": "boss_review",
                "name": "Boss review recommendations",
                "room": "Boss",
                "status": "live",
                "metric": "recommend-only",
                "cta_target": "approvalsPanel",
            },
            {
                "id": "system_health",
                "name": "Automation health monitor",
                "room": "Engineering",
                "status": status(warn=(overdue_jobs + never_ran) > 0, ready=bool(health)),
                "metric": f"{overdue_jobs} overdue / {never_ran} never",
                "cta_target": "systemHealthPanel",
            },
            {
                "id": "dlq_console",
                "name": "DLQ retry and repair desk",
                "room": "Reliability",
                "status": status(warn=dlq_count > 0),
                "metric": f"{dlq_count} dlq",
                "cta_target": "failureConsoleCard",
            },
            {
                "id": "hot_queue",
                "name": "Reception hot-reply tray",
                "room": "Sales",
                "status": "live",
                "metric": "reply_agent hot queue",
                "cta_target": "hotQueueCard",
            },
            {
                "id": "schedule",
                "name": "IST automation day-plan",
                "room": "Ops",
                "status": status(ready=bool(schedule)),
                "metric": f"{len(schedule)} jobs",
                "cta_target": "schedulePanel",
            },
            {
                "id": "live_feed",
                "name": "Live automation event feed",
                "room": "Ops",
                "status": "live",
                "metric": "8s event poll",
                "cta_target": "feedCard",
            },
            {
                "id": "coordination_history",
                "name": "Coordinator/council run history",
                "room": "Boss",
                "status": status(warn=not coordination),
                "metric": f"{len(coordination)} recent",
                "cta_target": "feedCard",
            },
            {
                "id": "workflow_runs",
                "name": "Workflow run monitor",
                "room": "Automation",
                "status": "live",
                "metric": "flow-run endpoint",
                "cta_target": "workflowRunsCard",
            },
            {
                "id": "system_map",
                "name": "Expandable system architecture map",
                "room": "Engineering",
                "status": "live",
                "metric": "control-center iframe",
                "cta_target": "systemMapCard",
            },
            {
                "id": "briefing",
                "name": "Swara morning briefing",
                "room": "Voice",
                "status": "live",
                "metric": "text + cached audio",
                "cta_target": "briefingBtn",
            },
        ]

        live_count = len([f for f in features if f["status"] == "live"])
        attention_count = len([f for f in features if f["status"] == "attention"])
        action_needed_count = len([f for f in features if f["status"] == "action_needed"])
        return {
            "title": "Advanced Virtual Office",
            "summary": {
                "total": len(features),
                "live": live_count,
                "attention": attention_count,
                "action_needed": action_needed_count,
                "pipeline_items": pipeline_items,
                "pipeline_errors": error_items,
            },
            "features": features,
        }
    except Exception as e:
        logger.debug(f"[office_hq] build_enterprise_features failed: {e}")
        return {"title": "Advanced Virtual Office", "summary": {"total": 0}, "features": []}


_TRENDS_PATH = os.path.join("data", "office_trends.json")


def build_trends(snapshot: dict[str, Any]) -> dict[str, Any]:
    """W4.2 (advanced Office): pipeline momentum — hot/warm/stuck ka day-over-day delta
    (sabse recent prior-din se aaj). Point-in-time snapshot ko trend-aware banata.
    Derived-metrics history `data/office_trends.json` me (~7 din; revenue_snapshots jaisa
    precedent — koi business-data mutation nahi). FULLY fail-open: kisi bhi error pe {} —
    page kabhi blank nahi (module ka never-raise contract)."""
    try:
        pipeline = (snapshot or {}).get("pipeline") or []
        hot = sum(int((s or {}).get("hot_count") or 0) for s in pipeline)
        warm = sum(int((s or {}).get("warm_count") or 0) for s in pipeline)
        stuck = sum(int((s or {}).get("stuckCount") or 0) for s in pipeline)
        today_vals = {"hot": hot, "warm": warm, "stuck": stuck}
        today = _now().strftime("%Y-%m-%d")

        hist: dict[str, Any] = {}
        try:
            if os.path.isfile(_TRENDS_PATH):
                with open(_TRENDS_PATH, encoding="utf-8") as f:
                    hist = json.load(f) or {}
        except Exception:
            hist = {}

        prior_days = sorted(d for d in hist if isinstance(d, str) and d < today)
        prev = (hist.get(prior_days[-1]) if prior_days else {}) or {}
        day_over_day = {
            k: {"now": v, "prev": int(prev.get(k) or 0), "delta": v - int(prev.get(k) or 0)}
            for k, v in today_vals.items()
        }

        # persist today's latest + prune to last 7 days (best-effort, atomic tmp+replace)
        try:
            hist[today] = today_vals
            for d in sorted(hist)[:-7]:
                hist.pop(d, None)
            os.makedirs(os.path.dirname(_TRENDS_PATH) or ".", exist_ok=True)
            tmp = _TRENDS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(hist, f)
            os.replace(tmp, _TRENDS_PATH)
        except Exception as e:
            logger.debug(f"[office_hq] trends persist skipped: {e}")

        return {"day_over_day": day_over_day, "asof": today}
    except Exception as e:
        logger.debug(f"[office_hq] build_trends skipped: {e}")
        return {}


def build_trend_alerts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """W4.3 (advanced Office): W4.2 trends ke day-over-day deltas se momentum alerts —
    stuck badhna (mid-funnel jam) / hot girna (top-funnel slow) founder ko flag karo.
    Read-only, deterministic, thresholds env-tunable (OFFICE_STUCK_ALERT_DELTA /
    OFFICE_HOT_ALERT_DROP, default 3), never-raise."""
    try:

        def _thr(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, "").strip() or default)
            except Exception:
                return default

        dod = ((snapshot or {}).get("trends") or {}).get("day_over_day") or {}
        alerts: list[dict[str, Any]] = []
        stuck = dod.get("stuck") or {}
        hot = dod.get("hot") or {}
        if int(stuck.get("delta") or 0) >= _thr("OFFICE_STUCK_ALERT_DELTA", 3):
            alerts.append(
                {
                    "level": "warn",
                    "signal": "stuck_rising",
                    "msg": f"⚠️ Stuck leads +{stuck.get('delta')} vs kal ({stuck.get('now')}) — mid-funnel jam, aaj clear karo.",
                }
            )
        if int(hot.get("delta") or 0) <= -_thr("OFFICE_HOT_ALERT_DROP", 3):
            alerts.append(
                {
                    "level": "warn",
                    "signal": "hot_falling",
                    "msg": f"📉 Hot leads {hot.get('delta')} vs kal ({hot.get('now')}) — top-funnel dheema, prospecting/outreach push.",
                }
            )
        return alerts
    except Exception as e:
        logger.debug(f"[office_hq] build_trend_alerts skipped: {e}")
        return []


async def build_snapshot() -> dict[str, Any]:
    """Top-level composer — the ONE call the frontend needs. Never raises.

    Perf note (2026-07-01 prod incident): this used to call build_metrics()
    then build_pipeline() then build_approvals() sequentially, and BOTH
    build_metrics and build_pipeline independently called the slow sync
    `_collect_live_stats()` (confirmed 45s+ against real prod data). Fixed by
    fetching live_stats ONCE and running the three independent sections
    concurrently — wall time is now roughly the slowest single section
    instead of the sum of all of them, and every DB/sync call inside those
    sections is individually timeout-bounded (see _safe_db_call /
    _safe_collect_live_stats) so one slow query degrades that field to a
    default instead of hanging the whole page again.

    Perf note #2 (same day): even at ~8s a browser refresh still felt slow —
    added a short Redis-backed cache (app.cache.cache, shared across all
    uvicorn workers, unlike an in-process dict) so a repeat load within the
    TTL window returns near-instantly instead of recomputing. Mutation
    endpoints (assign/next-action/resolve-stuck/move/pause/resume) call
    invalidate_snapshot_cache() so an admin's own action is reflected on their
    very next fetch rather than waiting out the TTL."""
    try:
        from app.cache import cache

        cached = await cache.get(_SNAPSHOT_CACHE_KEY)
        if cached is not None:
            cached["cached"] = True
            return cached
    except Exception as e:
        logger.debug(f"[office_hq] snapshot cache read skipped: {e}")

    rooms, agents = build_rooms_and_agents()
    live_stats = await _safe_collect_live_stats()
    metrics, pipeline, approvals = await asyncio.gather(
        build_metrics(live_stats=live_stats),
        build_pipeline(items_limit=3, live_stats=live_stats),
        build_approvals(),
    )
    system_health = build_system_health()
    from app.platform.office_schema import UNITY_OFFICE_SCHEMA_VERSION

    snapshot = {
        "ok": True,
        "schema_version": UNITY_OFFICE_SCHEMA_VERSION,
        "rooms": rooms,
        "agents": agents,
        "metrics": metrics,
        "pipeline": pipeline,
        "approvals": approvals,
        "system_health": system_health,
        "schedule": build_schedule(),
        "coordination": build_coordination(),
        "generated_at": _now().isoformat(),
        "cached": False,
    }
    snapshot["next_best_actions"] = next_best_actions(snapshot)
    snapshot["boss_brief"] = build_boss_brief(snapshot)
    snapshot["priority_actions"] = build_priority_actions(snapshot)
    snapshot["room_workloads"] = build_room_workloads(snapshot)
    snapshot["replay"] = build_replay(snapshot)
    snapshot["enterprise_features"] = build_enterprise_features(snapshot)
    snapshot["trends"] = build_trends(snapshot)  # W4.2: day-over-day pipeline momentum
    snapshot["trend_alerts"] = build_trend_alerts(snapshot)  # W4.3: momentum alerts
    # Paperclip-inspired: per-agent cost + task queue depth
    try:
        from app.platform import agent_cost_tracker as act

        snapshot["agent_costs"] = act.today_snapshot()
    except Exception:
        snapshot["agent_costs"] = {}
    try:
        from app.platform import agent_task_queue as atq

        snapshot["task_queue"] = await atq.agent_queue_snapshot()
    except Exception:
        snapshot["task_queue"] = {}

    # Paperclip: stale tasks — surface stuck work (report, don't auto-fix)
    try:
        from app.platform import agent_task_queue as atq2

        snapshot["stale_tasks"] = await atq2.stale_tasks(threshold_minutes=10)
    except Exception:
        snapshot["stale_tasks"] = []

    # Paperclip: budget dashboard
    try:
        from app.platform import agent_budget

        snapshot["budget_dashboard"] = agent_budget.budget_dashboard()
    except Exception:
        snapshot["budget_dashboard"] = {}

    try:
        from app.cache import cache

        await cache.set(_SNAPSHOT_CACHE_KEY, snapshot, ttl=_SNAPSHOT_CACHE_TTL)
    except Exception as e:
        logger.debug(f"[office_hq] snapshot cache write skipped: {e}")

    return snapshot


async def invalidate_snapshot_cache() -> None:
    """Call after any real mutation so the admin's own action shows up on
    their very next fetch instead of waiting out _SNAPSHOT_CACHE_TTL. Never
    raises — a failed invalidation just means the old TTL runs its course."""
    try:
        from app.cache import cache

        await cache.delete(_SNAPSHOT_CACHE_KEY)
    except Exception as e:
        logger.debug(f"[office_hq] snapshot cache invalidate skipped: {e}")


async def pipeline_stage_detail(stage_id: str) -> dict[str, Any]:
    """Full item list for one stage (drill-down, up to 50) — enough for the
    frontend's filter/search controls to operate on real data."""
    stages = await build_pipeline(items_limit=50)
    for s in stages:
        if s["id"] == stage_id:
            return s
    return {
        "id": stage_id,
        "name": stage_id,
        "count": 0,
        "items": [],
        "source": "mock",
        "note": "Unknown stage id.",
    }


# --------------------------------------------------------------------------- #
# Pipeline item mutations — REAL actions, never fabricated:
#   - "move" a DEAL delegates to the existing sales_pipeline.set_stage() (real).
#   - "move" a LEAD writes a bounded, validated status override (real, persisted,
#     surfaced back into _lead_item — see admin_pipeline_overrides docstring for
#     why this is a sidecar override rather than a direct Lead-table write).
#   - assign/next-action/resolve-stuck are sidecar-only (no other backing store
#     exists for these three concepts on either a Lead or a Deal).
# --------------------------------------------------------------------------- #
def assign_item_owner(item_id: str, agent_key: str, by: str = "admin") -> dict[str, Any]:
    from app.platform import admin_pipeline_overrides

    return admin_pipeline_overrides.set_owner(item_id, agent_key, by)


def set_item_next_action(item_id: str, note: str, by: str = "admin") -> dict[str, Any]:
    from app.platform import admin_pipeline_overrides

    return admin_pipeline_overrides.set_next_action(item_id, note, by)


def resolve_item_stuck(item_id: str, by: str = "admin") -> dict[str, Any]:
    from app.platform import admin_pipeline_overrides

    return admin_pipeline_overrides.mark_stuck_resolved(item_id, by)


def move_item(item_id: str, item_type: str, next_stage: str, by: str = "admin") -> dict[str, Any]:
    from app.platform import admin_pipeline_overrides

    if item_type == "deal":
        from app.marketing import sales_pipeline

        if next_stage not in sales_pipeline.STAGES:
            return {"ok": False, "error": f"stage must be one of {sales_pipeline.STAGES}"}
        ok = sales_pipeline.set_stage(item_id, next_stage, allow_reverse=True)
        return {
            "ok": ok,
            "item_id": item_id,
            "stage": next_stage,
            "via": "sales_pipeline.set_stage",
        }
    if item_type == "lead":
        return admin_pipeline_overrides.set_status_override(item_id, next_stage, by)
    return {"ok": False, "error": f"unsupported item_type: {item_type}"}


# --------------------------------------------------------------------------- #
# F3 "Kaam Do" — map se task dispatch. Admin drawer se ek Hinglish goal + scope
# ("solo" = sirf yeh agent / "team" = coordinator) le kar ek BOUNDED, DRAFT-SAFE
# multi-agent run trigger karta hai — bilkul waise jaise POST /api/agents/council
# live endpoint web process me bounded run karta (precedent). Hard rules:
#   - DRAFT-SAFE ONLY: coordinator ko hamesha execute=False pe chalate — koi
#     real side-effect nahi (no auto-send, no DB mutation). Sirf reasoning/draft.
#   - BOUNDED: asyncio.wait_for(TASK_TIMEOUT) — web worker (WEB_CONCURRENCY=2)
#     ko kabhi unbounded heavy job pe hang nahi hone dete. Timeout pe coroutine
#     CANCEL hota (background me chalta NAHI) — isliye response wording HONEST:
#     "time-limit tak complete nahi hua; jitne steps hue woh events me hain"
#     (coordinate/fan_out dono per-step team.log_event karte, so cancel ke
#     baad bhi jo steps complete hue woh agent_events feed/ticker me dikhte).
#   - NEVER-RAISE: har failure -> {"ok": False, "error": ...} (200 OK), office_hq
#     ke baaki functions jaisa.
#   - Contract: helper HAMESHA {"ok", "summary", "run_id"?} shape lautaata hai
#     chahe solo (fan_out) chale ya team (coordinate) — frontend ko guess nahi
#     karna padta kaunsa field padhe.
# --------------------------------------------------------------------------- #
_TASK_TIMEOUT = 90.0  # seconds — bounded, mirrors the council-endpoint budget
_TASK_GOAL_MAX = 500


async def run_agent_task(member: str, goal: str, scope: str = "solo") -> dict[str, Any]:
    """Dispatch a Hinglish goal to one agent (scope="solo") or the coordinator
    team (scope="team"), draft-safe + bounded. Never raises."""
    key = (member or "").strip().lower()
    goal = (goal or "").strip()
    scope = (scope or "solo").strip().lower()

    if not goal:
        return {"ok": False, "error": "goal khaali hai — kuch likho"}
    if len(goal) > _TASK_GOAL_MAX:
        goal = goal[:_TASK_GOAL_MAX]
    if scope not in ("solo", "team"):
        return {"ok": False, "error": f"scope 'solo' ya 'team' hona chahiye (mila: {scope})"}
    if key not in STAFF:
        return {"ok": False, "error": f"unknown agent: {member}"}

    try:
        from app.platform import team

        team.log_event(
            member=key,
            action="task_dispatched",
            detail=f"[{scope}] {goal[:180]}",
            status="ok",
            meta={"scope": scope, "goal": goal[:400]},
        )
    except Exception as e:
        logger.debug(f"[office_hq] run_agent_task log_event skipped: {e}")

    # --- AgentTask queue: create task record ---
    task_id: str | None = None
    try:
        from app.platform import agent_task_queue as atq

        t_res = await atq.assign(key, goal, delegated_by="admin")
        task_id = t_res.get("id") if t_res.get("ok") else None
        if task_id:
            # begin() = pending -> running. Same self-assigned shape as the
            # scheduler routine bridge: the admin dispatch executes the work
            # itself, so claim_next() never runs and start() (which requires
            # `claimed`) silently no-op'd, leaking a pending row on success.
            await atq.begin(task_id)
    except Exception:
        pass

    try:
        from app.agents import coordinator

        if scope == "team":
            coro = coordinator.coordinate(goal, execute=False, max_steps=3)
        else:
            coro = coordinator.fan_out(goal, agents=[key], max_agents=1)
        result = await asyncio.wait_for(coro, timeout=_TASK_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"[office_hq] run_agent_task({key},{scope}) hit {_TASK_TIMEOUT}s budget")
        if task_id:
            try:
                from app.platform import agent_task_queue as atq

                await atq.complete(task_id, result=f"timeout after {int(_TASK_TIMEOUT)}s")
            except Exception:
                pass
        return {
            "ok": True,
            "status": "timeout",
            "member": key,
            "scope": scope,
            "summary": "",
            "note": (
                f"Time-limit ({int(_TASK_TIMEOUT)}s) tak poora nahi hua — jitne step complete "
                "hue woh events/ticker me dikhenge. Halka goal ya solo scope try karo."
            ),
        }
    except Exception as e:
        logger.warning(f"[office_hq] run_agent_task({key},{scope}) failed: {e}")
        if task_id:
            try:
                from app.platform import agent_task_queue as atq

                await atq.fail(task_id, str(e)[:300])
            except Exception:
                pass
        return {"ok": False, "error": str(e)[:300], "member": key, "scope": scope}

    result = result or {}
    # --- AgentTask queue: complete/fail task ---
    if task_id:
        try:
            from app.platform import agent_task_queue as atq

            summary = str(result.get("summary") or "")[:500]
            if result.get("ok", True):
                await atq.complete(task_id, result=summary)
            else:
                await atq.fail(task_id, str(result.get("error") or "failed")[:300])
        except Exception:
            pass

    if not result.get("ok", True):
        return {
            "ok": False,
            "error": str(result.get("error") or "coordinator run failed"),
            "member": key,
            "scope": scope,
        }
    return {
        "ok": True,
        "status": "done",
        "member": key,
        "scope": scope,
        "run_id": result.get("run_id") or "",
        "task_id": task_id or "",
        "summary": str(result.get("summary") or "(summary abhi nahi bana)")[:1200],
        "note": "Pura result agent_events/ticker me bhi aa gaya (draft-safe — koi auto-send nahi).",
    }


# --------------------------------------------------------------------------- #
# HQ Ask — 🤖 copilot ka MAIN entry point (2026-07-03, user: "yaha se jo puchna
# sab coordinate kare"). Ek Hinglish message lo aur:
#   question -> Boss-persona grounded answer (cached snapshot facts, free-LLM)
#   task     -> auto-route: sahi staff member choose karke run_agent_task()
#               (same draft-safe + bounded Kaam-Do path — koi naya side-effect
#               surface NAHI, sirf routing sugar upar).
# Rules (file-convention): NEVER-RAISE, har LLM call wait_for-bounded, numbers
# sirf snapshot se (fabricate nahi). Router-LLM fail -> keyword heuristic.
# --------------------------------------------------------------------------- #
_ASK_Q_MAX = 500
_ASK_ROUTE_TIMEOUT = 12.0
_ASK_ANSWER_TIMEOUT = 25.0

_TASK_VERB_HINTS = (
    "karo",
    "kar do",
    "kardo",
    "banao",
    "bana do",
    "bhejo",
    "bhej do",
    "chalao",
    "run kar",
    "dispatch",
    "draft",
    "likho",
    "likh do",
    "nikalo",
    "dhundo",
    "harvest",
    "scrape",
    "post kar",
    "call kar",
    "schedule kar",
    "start kar",
)

# "sabhi agents ko command" (user-ask 2026-07-03) — broadcast = parallel fan_out
# to the doer-set (RUNNABLE_MEMBERS), capped, draft-safe.
_BROADCAST_HINTS = (
    "sabhi agent",
    "sab agent",
    "sabko",
    "sab ko",
    "all agent",
    "broadcast",
    "puri team",
    "poori team",
    "saari team",
    "sari team",
    "everyone",
    "har agent",
)


def _ask_heuristic_route(q: str) -> dict[str, str]:
    low = q.lower()
    if any(h in low for h in _BROADCAST_HINTS):
        return {"kind": "broadcast", "member": "", "scope": "team"}
    if any(v in low for v in _TASK_VERB_HINTS):
        return {"kind": "task", "member": "manager", "scope": "team"}
    return {"kind": "question", "member": "", "scope": ""}


async def _ask_route(q: str) -> dict[str, str]:
    """Free-LLM intent+staff router (strict-JSON) — fail/timeout = heuristic."""
    roster = "\n".join(
        f"- {k}: {v.get('title', '')} — {str(v.get('duties', ''))[:90]}" for k, v in STAFF.items()
    )
    system = (
        "Tum ek AI-office router ho. User (admin) ka message classify karo.\n"
        "Roster:\n" + roster + "\n\n"
        'STRICT JSON hi lautao: {"kind":"question"|"task"|"broadcast","member":"<roster-key>","scope":"solo"|"team"}\n'
        "task = user kuch KARWANA chahta hai (banao/bhejo/chalao...). member = sabse fit staff-key; "
        'confuse ho to "manager" + scope "team". question = info/status poocha hai. '
        "broadcast = user SABHI/puri team agents ko ek saath command dena chahta hai."
    )
    try:
        import json as _json

        from app.voice_agent import free_ai

        text, _p = await asyncio.wait_for(
            free_ai.chat(
                system,
                [{"role": "user", "content": q}],
                max_tokens=80,
                temperature=0.0,
                scope="office_ask_route",
            ),
            timeout=_ASK_ROUTE_TIMEOUT,
        )
        raw = (text or "").strip()
        raw = raw[raw.find("{") : raw.rfind("}") + 1]
        parsed = _json.loads(raw)
        kind = str(parsed.get("kind") or "").strip().lower()
        member = str(parsed.get("member") or "").strip().lower()
        scope = str(parsed.get("scope") or "solo").strip().lower()
        if kind not in ("question", "task", "broadcast"):
            return _ask_heuristic_route(q)
        if kind == "task" and member not in STAFF:
            member = "manager"
        if scope not in ("solo", "team"):
            scope = "solo"
        return {"kind": kind, "member": member, "scope": scope}
    except Exception as e:
        logger.debug(f"[office_hq] _ask_route LLM fallback -> heuristic: {e}")
        return _ask_heuristic_route(q)


def _ask_context_from_snapshot(snap: dict[str, Any]) -> str:
    """Cached snapshot -> compact REAL-numbers context (cap ~1400 chars)."""
    try:
        parts: list[str] = []
        m = snap.get("metrics") or {}
        if m:
            parts.append("Metrics: " + "; ".join(f"{k}={v}" for k, v in list(m.items())[:12]))
        ap = dict((snap.get("approvals") or {}).get("counts") or {})
        if ap:
            # total pehle — taaki Boss ka jawab Priority-stack ke total se match kare
            tot = ap.pop("total_pending", ap.pop("pending", None))
            items = ([("TOTAL pending", tot)] if tot is not None else []) + list(ap.items())[:7]
            parts.append("Pending approvals: " + "; ".join(f"{k}={v}" for k, v in items))
        nba = snap.get("next_best_actions") or []
        if nba:
            parts.append(
                "Next-best-actions: " + " | ".join(str(x.get("title") or x)[:80] for x in nba[:3])
            )
        sh = snap.get("system_health") or {}
        if sh:
            parts.append("System: " + "; ".join(f"{k}={v}" for k, v in list(sh.items())[:6]))
        agents = snap.get("agents") or []
        if agents:
            active = [
                a.get("name") or a.get("key")
                for a in agents
                if a.get("status") in ("working", "active")
            ]
            parts.append(
                f"Staff active: {len(active)}/{len(agents)}"
                + (f" ({', '.join(map(str, active[:6]))})" if active else "")
            )
        return "\n".join(parts)[:1400]
    except Exception:
        return ""


async def hq_ask(q: str) -> dict[str, Any]:
    """🤖 HQ Copilot brain — question ka grounded jawab ya task ka auto-dispatch.

    Returns {ok, kind, text, member?, scope?, run_id?}. Never raises."""
    q = (q or "").strip()
    if not q:
        return {"ok": False, "kind": "question", "text": "", "error": "message khaali hai"}
    if len(q) > _ASK_Q_MAX:
        q = q[:_ASK_Q_MAX]

    route = await _ask_route(q)

    if route["kind"] == "broadcast":
        # 📢 sabhi (runnable) agents ko parallel — draft-safe fan_out, bounded.
        agents = sorted(RUNNABLE_MEMBERS)
        try:
            from app.agents import coordinator

            result = await asyncio.wait_for(
                coordinator.fan_out(q, agents=agents, max_agents=len(agents)),
                timeout=_TASK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return {
                "ok": True,
                "kind": "broadcast",
                "member": "",
                "scope": "team",
                "text": f"⏳ Broadcast time-limit ({int(_TASK_TIMEOUT)}s) me poora nahi hua — "
                "jitne agents ne kaam kiya woh events/ticker me hai.",
            }
        except Exception as e:
            return {
                "ok": False,
                "kind": "broadcast",
                "member": "",
                "scope": "team",
                "text": f"❌ Broadcast fail: {str(e)[:200]}",
                "error": str(e)[:300],
            }
        result = result or {}
        lines = [f"📢 {len(result.get('agents') or agents)} agents ko bheja:"]
        for r in (result.get("results") or [])[:8]:
            nm = STAFF.get(r.get("agent", ""), {}).get("name") or r.get("agent", "?")
            out = str(r.get("output") or r.get("summary") or r.get("result") or "").strip()
            lines.append(f"• {nm}: {out[:140]}" if out else f"• {nm}: (events me dekho)")
        if result.get("summary"):
            lines.append("\n🧑‍💼 Boss ka merge: " + str(result["summary"])[:400])
        return {
            "ok": True,
            "kind": "broadcast",
            "member": "",
            "scope": "team",
            "run_id": str(result.get("at") or ""),
            "text": "\n".join(lines)[:1400],
        }

    if route["kind"] == "task":
        res = await run_agent_task(route["member"], q, route["scope"])
        name = STAFF.get(route["member"], {}).get("name") or route["member"]
        if not res.get("ok"):
            return {
                "ok": False,
                "kind": "task",
                "member": route["member"],
                "scope": route["scope"],
                "text": f"❌ {name} ko dispatch fail hua: {res.get('error', '?')}",
                "error": res.get("error", ""),
            }
        if res.get("status") == "timeout":
            text = f"⏳ {name} ko kaam de diya — time-limit me poora nahi hua, jitna hua woh events/ticker me hai."
        else:
            text = f"📨 {name} ({route['scope']}) ne kaam kiya:\n{res.get('summary', '')}".strip()
        return {
            "ok": True,
            "kind": "task",
            "member": route["member"],
            "scope": route["scope"],
            "run_id": res.get("run_id", ""),
            "text": text[:1400],
        }

    # question -> grounded Boss answer
    try:
        snap = await build_snapshot()
    except Exception:  # pragma: no cover — build_snapshot khud never-raise hai
        snap = {}
    ctx = _ask_context_from_snapshot(snap or {})
    system = (
        "Tum 'Boss' ho — LeadsGenAI (leadsgenai.in) ke AI-staff office ke manager. "
        "Admin ke sawaal ka Hinglish (Roman) me seedha, chhota jawab do (max 6 sentences). "
        "SIRF neeche diye REAL facts use karo — number kabhi mat banao; jo data me nahi "
        "hai uske liye bolo 'yeh data abhi mere paas nahi, <kaunsa page/agent> dekho'. "
        "Kaam karwana ho to bata do ki 'X karo' likhne se main sahi agent ko de dunga.\n\n"
        "AAJ KE FACTS:\n" + (ctx or "(snapshot unavailable)")
    )
    try:
        from app.voice_agent import free_ai

        text, _p = await asyncio.wait_for(
            free_ai.chat(
                system,
                [{"role": "user", "content": q}],
                max_tokens=350,
                temperature=0.4,
                scope="office_ask",
            ),
            timeout=_ASK_ANSWER_TIMEOUT,
        )
        answer = (text or "").strip()
    except Exception as e:
        logger.warning(f"[office_hq] hq_ask answer LLM failed: {e}")
        answer = ""
    if not answer:
        answer = ("LLM abhi jawab nahi de paya. Snapshot facts:\n" + (ctx or "(kuch nahi mila)"))[
            :900
        ]
    return {"ok": True, "kind": "question", "text": answer[:1400]}


# --------------------------------------------------------------------------- #
# F6 "Team Improvement Council" (2026-07-05, user: "admin sabi agents se
# discuss project relate for improvements") — a real multi-agent discussion,
# grounded in TODAY'S snapshot facts (same context builder as HQ Ask), using
# the EXISTING coordinator.coordinate_agentverse (dynamic expert recruit ->
# each contributes -> solver synthesizes -> critic scores) — no new
# coordination engine invented. ALWAYS execute=False here: this is a
# discussion surface, not an action-runner (that stays run_agent_task/Kaam-Do).
# Each contribution carries its recruited `staff` key so the admin can
# 1-click dispatch it through the SAME draft-safe run_agent_task() path this
# file already exposes — no new dispatch surface. Bounded + never-raise.
# --------------------------------------------------------------------------- #
_COUNCIL_TIMEOUT = 110.0
_COUNCIL_TOPIC_MAX = 400
_DEFAULT_COUNCIL_TOPIC = (
    "LeadsGenAI platform (marketing automation + AI voice agent product) me is "
    "hafte sabse zyada ROI wala improvement kya hoga — revenue, lead-conversion, "
    "reliability, ya customer-retention?"
)


async def improvement_council(
    topic: str = "", team_size: int = 4, max_rounds: int = 1
) -> dict[str, Any]:
    """Snapshot-grounded AgentVerse discussion on what to improve next.

    Always draft-only (execute=False — a discussion, not an action run).
    Never raises; degrades to {ok:False, error} / {ok:True, status:"timeout"}."""
    topic = (topic or "").strip()[:_COUNCIL_TOPIC_MAX] or _DEFAULT_COUNCIL_TOPIC
    try:
        team_size = max(2, min(4, int(team_size or 4)))
    except Exception:
        team_size = 4
    try:
        max_rounds = max(1, min(2, int(max_rounds or 1)))
    except Exception:
        max_rounds = 1

    try:
        snap = await build_snapshot()
    except Exception:  # pragma: no cover — build_snapshot khud never-raise hai
        snap = {}
    ctx = _ask_context_from_snapshot(snap or {})
    goal = topic + (
        "\n\nAAJ KE REAL FACTS (isi pe grounded raho, number mat banao):\n" + ctx if ctx else ""
    )

    try:
        from app.platform import team

        team.log_event(
            member="manager", action="improvement_council_start", detail=topic[:180], status="ok"
        )
    except Exception as e:
        logger.debug(f"[office_hq] improvement_council log_event(start) skipped: {e}")

    try:
        from app.agents import coordinator

        result = await asyncio.wait_for(
            coordinator.coordinate_agentverse(
                goal, execute=False, max_rounds=max_rounds, team_size=team_size
            ),
            timeout=_COUNCIL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[office_hq] improvement_council hit {_COUNCIL_TIMEOUT}s budget")
        return {
            "ok": True,
            "status": "timeout",
            "topic": topic,
            "note": (
                f"Time-limit ({int(_COUNCIL_TIMEOUT)}s) me discussion poori nahi hui — "
                "chhota topic ya kam experts (team_size 2) try karo."
            ),
        }
    except Exception as e:
        logger.warning(f"[office_hq] improvement_council failed: {e}")
        return {"ok": False, "error": str(e)[:300], "topic": topic}

    result = result or {}
    if not result.get("ok", True):
        return {
            "ok": False,
            "error": str(result.get("error") or "council run failed"),
            "topic": topic,
        }

    contributions: list[dict[str, Any]] = []
    for c in result.get("contributions") or []:
        staff_key = str(c.get("staff") or "").strip().lower()
        out_val = c.get("output")
        contributions.append(
            {
                "role": str(c.get("role") or "")[:80],
                "staff": staff_key,
                "staff_name": (STAFF.get(staff_key, {}) or {}).get("name") or "",
                "output": (out_val if isinstance(out_val, str) else str(out_val or ""))[:800],
                "dispatchable": staff_key in STAFF,
            }
        )

    try:
        from app.platform import team

        team.log_event(
            member="manager",
            action="improvement_council_done",
            detail=f"score={result.get('final_score')} experts={len(contributions)}",
            status="ok",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "topic": topic,
        "experts": [
            {
                "role": e.get("role", ""),
                "expertise": e.get("expertise", ""),
                "staff": e.get("staff", ""),
            }
            for e in (result.get("experts") or [])
        ],
        "contributions": contributions,
        "solution": str(result.get("solution") or "")[:1600],
        "summary": str(result.get("summary") or "")[:600],
        "score": result.get("final_score", 0),
        "run_id": result.get("run_id", ""),
        "at": result.get("at", ""),
    }
