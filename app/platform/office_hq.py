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
from datetime import datetime, timedelta, timezone
from typing import Any

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
    {"id": "coordinator", "name": "Coordinator Room", "emoji": "🧑‍💼",
     "purpose": "Kaam assign karta, stuck tasks dekhta, next-best-action deta"},
    {"id": "lead_lab", "name": "Data / Lead Lab", "emoji": "🧹",
     "purpose": "Lead import, dedupe, validation, enrichment, scoring"},
    {"id": "sales_crm", "name": "Sales / CRM Room", "emoji": "🤝",
     "purpose": "Qualified follow-up, deal stages, appointments, CRM sync"},
    {"id": "voice_team", "name": "Voice Team", "emoji": "📞",
     "purpose": "AI voice calls, queue, transcripts, appointment outcomes"},
    {"id": "marketing_team", "name": "Marketing Team", "emoji": "📣",
     "purpose": "WhatsApp/social/GBP content, offers, campaign creatives"},
    {"id": "qa_audit", "name": "QA / Audit Room", "emoji": "🧪",
     "purpose": "Automation quality checks, broken workflows, bad data"},
    {"id": "platform_engineering", "name": "Platform / Engineering", "emoji": "🛠️",
     "purpose": "System health, API/provider status, cron, queues, DB"},
    {"id": "admin_finance", "name": "Admin / Finance Room", "emoji": "💰",
     "purpose": "Billing, invoices, payments, subscriptions, churn-risk"},
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

# STAFF keys with a REAL, individually re-triggerable manual-run wired today
# (app/agents/staff.py run_member() dispatch table). Everyone else's "retry"
# button must stay disabled/omitted rather than lie about doing something.
RUNNABLE_MEMBERS = {"arjun", "meera", "kavya", "manager", "isha", "rohan"}

# automation_health job-key -> owning room, for blocked/error badges per room.
JOB_ROOM: dict[str, str] = {
    "prospect": "lead_lab", "midday_prospect": "lead_lab", "evening_prospect": "lead_lab",
    "pipeline": "lead_lab", "engineer_dataquality": "lead_lab",
    "reply_triage": "sales_crm",
    "qa": "qa_audit", "trainer": "qa_audit",
    "email_outreach": "marketing_team", "email_followup": "marketing_team",
    "content": "marketing_team", "blog": "marketing_team", "afternoon_content": "marketing_team",
    "weekly_marketing": "marketing_team", "kb_refresh": "marketing_team",
    "digest": "admin_finance", "revenue_snapshot": "admin_finance", "meter_watch": "admin_finance",
    "growth": "coordinator", "standup": "coordinator", "process_autostart": "coordinator",
    "ops": "platform_engineering", "watchdog": "platform_engineering", "onboard": "platform_engineering",
    "engineer_sre": "platform_engineering", "mcp_engineer": "platform_engineering",
    "engineer_finops": "admin_finance", "engineer_security": "platform_engineering",
    "engineer_dbre": "platform_engineering", "engineer_deps": "platform_engineering",
    "readiness_digest": "platform_engineering", "saturday_hygiene": "platform_engineering",
    "obsidian_push": "platform_engineering", "flow_cron": "platform_engineering",
    "evening_wrap": "platform_engineering",
}

# approvals_bridge source -> owning room (sales/coordinator/fde are the only
# 3 sources that engine supports today).
APPROVAL_ROOM = {"sales": "sales_crm", "coordinator": "coordinator", "fde": "sales_crm"}

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
        r["id"]: {**r, "agent_keys": [], "activeTaskCount": 0, "blockedTaskCount": 0,
                  "errorCount": 0, "approvalCount": 0, "status": "idle"}
        for r in ROOM_DEFS
    }
    agents: list[dict[str, Any]] = []
    try:
        from app.platform import agent_controls
        from app.platform.team import STAFF, team_status

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
        "new_leads_today": 0, "qualified_leads_today": 0, "calls_completed_today": 0,
        "appointments_booked": 0, "campaigns_ready": 0, "payments_pending": 0,
        "active_customers": 0, "failed_automations": 0, "approvals_needed": 0,
        "system_issues": 0, "mrr": 0,
    }
    try:
        live = live_stats if live_stats is not None else await _safe_collect_live_stats()
        out["calls_completed_today"] = int(live.get("real_calls_today") or 0)
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
async def build_pipeline(items_limit: int = 3, live_stats: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    stages: dict[str, dict[str, Any]] = {
        m["id"]: {**m, "count": 0, "stuckCount": 0, "errorCount": 0, "items": [],
                  "source": "mock", "note": "Backend data not wired yet."}
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
                res = await session.execute(select(Lead).order_by(Lead.created_at.desc()).limit(500))
                return list(res.scalars().all())

        rows = await _safe_db_call(_q(), timeout=8.0, label="pipeline.lead_select") or []
        s = stages["lead_source"]
        s["count"] = len(rows)
        s["source"] = "real"
        s["note"] = "Leads table — last 500 rows scanned."
        s["items"] = [_lead_item(r, "lead_source", overrides, approval_titles) for r in rows[:items_limit]]

        # 2) Cleaning & Enrichment — PARTIAL: real verification flags, but no
        # dedicated dedupe/enrichment table exists (Diya's dedupe pass is
        # report-only). Approximated via verified/phone_verified flags.
        unverified = [r for r in rows if not getattr(r, "phone_verified", False)]
        s2 = stages["cleaning_enrichment"]
        s2["count"] = len(unverified)
        s2["source"] = "partial"
        s2["note"] = "Approximated via phone_verified flag — no dedicated dedupe/enrichment table yet."

        # 3) Scoring & Qualification — real (lead_score bands + rejection statuses).
        hot = [r for r in rows if int(getattr(r, "lead_score", 0) or 0) >= 70]
        warm = [r for r in rows if 40 <= int(getattr(r, "lead_score", 0) or 0) < 70]
        rejected_st = {"not_interested", "wrong_number", "dnd", "lost"}
        rejected = [r for r in rows if _enum_value(r, "status") in rejected_st]
        s3 = stages["scoring_qualification"]
        s3["count"] = len(hot) + len(warm)
        s3["stuckCount"] = 0
        s3["source"] = "real"
        s3["note"] = f"{len(hot)} hot (score>=70) · {len(warm)} warm (40-69) · {len(rejected)} rejected."
        s3["items"] = [_lead_item(r, "scoring_qualification", overrides, approval_titles) for r in hot[:items_limit]]

        # 5) Outreach Queue — PARTIAL: only the voice-call channel is directly
        # queryable via Lead.next_call_at (email/WhatsApp cadence state lives
        # in data/cadence_leads.jsonl, not summarized here for this pass).
        now_dt = datetime.utcnow()
        due = [r for r in rows if getattr(r, "next_call_at", None) and r.next_call_at <= now_dt]
        s5 = stages["outreach_queue"]
        s5["count"] = len(due)
        s5["stuckCount"] = len(
            [r for r in due if r.next_call_at < now_dt - timedelta(hours=24)
             and not _is_resolved(overrides, getattr(r, "id", ""))]
        )
        s5["source"] = "partial"
        s5["note"] = "Voice call queue only (Lead.next_call_at). Email/WhatsApp cadence state not merged in yet."
        s5["items"] = [_lead_item(r, "outreach_queue", overrides, approval_titles) for r in due[:items_limit]]

        # 6) Conversation / Follow-up — real (CALLBACK status).
        callback = [r for r in rows if _enum_value(r, "status") == "callback"]
        s6 = stages["conversation_followup"]
        s6["count"] = len(callback)
        s6["stuckCount"] = len(
            [r for r in callback if getattr(r, "next_call_at", None) and r.next_call_at < now_dt
             and not _is_resolved(overrides, getattr(r, "id", ""))]
        )
        s6["source"] = "real"
        s6["items"] = [_lead_item(r, "conversation_followup", overrides, approval_titles) for r in callback[:items_limit]]

        # 7) Appointment / Demo Booking — real.
        appt = [r for r in rows if _enum_value(r, "status") == "appointment"]
        s7 = stages["appointment_booking"]
        s7["count"] = len(appt)
        s7["stuckCount"] = len(
            [r for r in appt if getattr(r, "appointment_date", None) and r.appointment_date < now_dt
             and not _is_resolved(overrides, getattr(r, "id", ""))]
        )
        s7["source"] = "real"
        s7["items"] = [_lead_item(r, "appointment_booking", overrides, approval_titles) for r in appt[:items_limit]]
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
        s4["note"] = "Total content-queue depth across clients (auto_content). Per-item preview not wired."
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
            if st.get("engine_on") else
            "SALES_ENGINE flag is off — deals store exists but is not being fed automatically."
        )
        s8["items"] = [
            _deal_item(d, overrides, approval_titles, stuck_cut) for d in list(reversed(deals))[:items_limit]
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
        s9["note"] = "Approximated via Subscription.status=trial — no bulk onboarding-checklist table exists yet."
    except Exception as e:
        logger.debug(f"[office_hq] customer_onboarding skipped: {e}")

    # 10) Service Delivery / Automation Running — PARTIAL: job-health proxy.
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        content_jobs = {"content", "blog", "afternoon_content", "weekly_marketing"}
        running = [j for j in (h.get("jobs") or []) if j.get("job") in content_jobs and j.get("status") == "ok"]
        failed = [j for j in (h.get("jobs") or []) if j.get("job") in content_jobs and j.get("status") == "last_failed"]
        s10 = stages["service_delivery"]
        s10["count"] = len(running)
        s10["errorCount"] = len(failed)
        s10["source"] = "partial"
        s10["note"] = "Content-job heartbeat proxy (automation_health) — not a per-customer delivery ledger."
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
        s11["note"] = f"{active} active subs · {past_due} past_due · {dstats.get('open', 0)} dunning cases open."
        s11["items"] = [_dunning_item(c, overrides) for c in (dstats.get("open_cases") or [])[:items_limit]]
    except Exception as e:
        logger.debug(f"[office_hq] billing_subscription skipped: {e}")

    # 12) Retention / Growth — real (client_health).
    try:
        from app.platform import client_health

        rep = await _safe_db_call(client_health.health_report(), timeout=8.0, label="pipeline.client_health") or []
        red = [r for r in rep if r.get("band") == "red"]
        s12 = stages["retention_growth"]
        s12["count"] = len(rep)
        s12["errorCount"] = len(red)
        s12["source"] = "real"
        s12["items"] = [_health_item(r, overrides) for r in red[:items_limit]]
    except Exception as e:
        logger.debug(f"[office_hq] retention_growth skipped: {e}")

    return [stages[m["id"]] for m in PIPELINE_STAGE_META]


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
    r: Any, stage_id: str,
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
        "nextAction": "Call karo" if stage_id in ("outreach_queue", "conversation_followup") else "Review karo",
        "slaRisk": bool(
            getattr(r, "next_call_at", None) and r.next_call_at < datetime.utcnow() - timedelta(hours=24)
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


def _dunning_item(c: dict[str, Any], overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
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


def _health_item(r: dict[str, Any], overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
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
    try:
        from app.platform import approvals_bridge

        d = approvals_bridge.list_drafts(include_decided=False) or {}
        drafts = d.get("drafts") or []
        for item in drafts:
            item["room"] = APPROVAL_ROOM.get(item.get("source"), "coordinator")
        return {"drafts": drafts, "counts": d.get("counts") or {}}
    except Exception as e:
        logger.debug(f"[office_hq] build_approvals failed: {e}")
        return {"drafts": [], "counts": {"by_source": {}, "pending": 0}}


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
            actions.append({
                "label": f"🗂️ {pending} draft(s) approval ke liye pending — review karo",
                "severity": "warning", "cta_target": "approvals",
            })
        overdue = len(health.get("overdue") or [])
        if overdue:
            actions.append({
                "label": f"⚠️ {overdue} automation job(s) time par nahi chale — check karo",
                "severity": "warning", "cta_target": "system_health",
            })
        if int(metrics.get("payments_pending") or 0):
            actions.append({
                "label": f"💳 {metrics['payments_pending']} payment pending — reminder bhejo",
                "severity": "warning", "cta_target": "billing_subscription",
            })
        retention = pipeline.get("retention_growth") or {}
        if int(retention.get("errorCount") or 0):
            actions.append({
                "label": f"❤️ {retention['errorCount']} client churn-risk (red) — proactively contact karo",
                "severity": "error", "cta_target": "retention_growth",
            })
        deal = pipeline.get("deal_conversion") or {}
        if int(deal.get("stuckCount") or 0):
            actions.append({
                "label": f"🤝 {deal['stuckCount']} deal(s) 14+ din se stuck — follow-up karo",
                "severity": "warning", "cta_target": "deal_conversion",
            })
        hot = int((pipeline.get("scoring_qualification") or {}).get("count") or 0)
        followup = int((pipeline.get("conversation_followup") or {}).get("stuckCount") or 0)
        if followup:
            actions.append({
                "label": f"🔥 {followup} follow-up overdue hai — hot leads ko call karo",
                "severity": "warning", "cta_target": "conversation_followup",
            })
        elif hot:
            actions.append({
                "label": f"🔥 {hot} hot lead(s) available — outreach shuru karo",
                "severity": "info", "cta_target": "scoring_qualification",
            })
    except Exception as e:
        logger.debug(f"[office_hq] next_best_actions failed: {e}")
    order = {"error": 0, "warning": 1, "info": 2}
    actions.sort(key=lambda a: order.get(a.get("severity", "info"), 3))
    return actions[:6]


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
    default instead of hanging the whole page again."""
    rooms, agents = build_rooms_and_agents()
    live_stats = await _safe_collect_live_stats()
    metrics, pipeline, approvals = await asyncio.gather(
        build_metrics(live_stats=live_stats),
        build_pipeline(items_limit=3, live_stats=live_stats),
        build_approvals(),
    )
    system_health = build_system_health()
    snapshot = {
        "ok": True,
        "rooms": rooms,
        "agents": agents,
        "metrics": metrics,
        "pipeline": pipeline,
        "approvals": approvals,
        "system_health": system_health,
        "generated_at": _now().isoformat(),
    }
    snapshot["next_best_actions"] = next_best_actions(snapshot)
    return snapshot


async def pipeline_stage_detail(stage_id: str) -> dict[str, Any]:
    """Full item list for one stage (drill-down, up to 50) — enough for the
    frontend's filter/search controls to operate on real data."""
    stages = await build_pipeline(items_limit=50)
    for s in stages:
        if s["id"] == stage_id:
            return s
    return {"id": stage_id, "name": stage_id, "count": 0, "items": [], "source": "mock",
            "note": "Unknown stage id."}


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
        return {"ok": ok, "item_id": item_id, "stage": next_stage, "via": "sales_pipeline.set_stage"}
    if item_type == "lead":
        return admin_pipeline_overrides.set_status_override(item_id, next_stage, by)
    return {"ok": False, "error": f"unsupported item_type: {item_type}"}
