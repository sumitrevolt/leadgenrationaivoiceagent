"""
Admin Dashboard API
Owner/operator overview + control view for the AI voice-agent lead-gen SaaS.

Provides GET /api/admin/dashboard which returns a single JSON payload consumed
by frontend/admin_dashboard.html. Shape is kept COMPATIBLE with that HTML so the
page renders, but the numbers are now REAL — pulled from the actual data the
platform produces (prospects, inquiries, marketing clients, emails, blog,
content queue, AI-staff activity). NO hardcoded SunVolt/sample data.

Sources (all best-effort, never 500):
  - data/prospects.jsonl          (prospector.list_prospects)
  - data/inquiries.jsonl          (public inquiries)
  - data/marketing_clients.jsonl  (clients_store.list_clients)
  - data/blog/*.json              (seo_blog.list_articles)
  - data/content_queue/*.jsonl    (auto_content.list_queue)
  - agent_events table            (team.team_status / recent_events)
  - auto_outreach.outreach_stats  (emails sent / pending)
  - app/marketing/packages        (plan prices for revenue estimate)

is_sample_data is ALWAYS False — we show the truth, even if everything is zero.

Import-safe: heavy imports are local + guarded so this module always mounts.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])

# Inquiries store (jsonl-first; same path public_site.py writes to).
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")


async def _safe_collect_live_stats(timeout: float = 8.0) -> dict:
    """`_collect_live_stats()` is SYNC (prospector scan + per-client content-
    queue file reads) and confirmed 45s+ under real prod data (2026-07-01
    office_hq incident, same underlying call). Calling it directly inside an
    async route blocks this event-loop worker for that long — which races
    past the admin dashboard's 8s client-side AbortController and falls back
    to the zero-filled DEMO payload (clients showing 0 despite real rows,
    2026-07-04). Run off-loop with a hard deadline; degrade to {} on
    timeout/failure rather than blocking or 500ing."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(_collect_live_stats), timeout=timeout)
    except Exception as e:
        logger.warning("admin_dashboard: _collect_live_stats timed out/failed (%ss budget): %s", timeout, e)
        return {}


# ----------------------------------------------------------------------------
# REAL data aggregation. Every source is best-effort (file may be absent →
# 0). NEVER raises — returns a plain dict of true numbers.
# ----------------------------------------------------------------------------
from app.api.admin_dashboard_builders import (  # noqa: F401  (helpers extracted 2026-06-20)
    _automation_snapshot,
    _build_from_db,
    _build_real,
    _client_mrr,
    _client_product,
    _clients_by_product,
    _collect_live_stats,
    _emails_sent_today,
    _inquiry_count_for_client,
    _is_today_iso,
    _plan_price,
    _read_inquiries,
    _real_agents,
    _real_calls_today,
    _real_charts,
    _real_clients,
    _real_health,
    _real_kpis,
    _sync_db,
)

# ----------------------------------------------------------------------------
# Pydantic models (the contract the HTML expects)
# ----------------------------------------------------------------------------
from app.api.admin_dashboard_models import (  # noqa: F401  (models extracted 2026-06-20)
    Agent,
    CallsPerDay,
    Campaign,
    Charts,
    Client,
    DashboardResponse,
    Health,
    KPIs,
    LeadsByNiche,
    RevenueCostSeries,
)


# ----------------------------------------------------------------------------
# Route
# ----------------------------------------------------------------------------
@router.get("/dashboard", response_model=DashboardResponse)
async def get_admin_dashboard(
    product: str | None = Query(
        None,
        description="Optional filter: marketing | voice | combo (clients panel only)",
    ),
    _user=Depends(require_admin),
) -> DashboardResponse:
    """
    Owner/operator dashboard payload — REAL data only.

    KPIs/clients/agents/charts are computed from the actual platform output:
    prospects, inquiries, marketing clients, emails sent, blog articles,
    content queue and AI-staff activity. is_sample_data is always False — the
    numbers reflect reality, even if everything is currently zero.

    If a richer DB (clients/campaigns/billing tables) is populated, that detail
    is merged in on top of the real aggregates.
    """
    try:
        # _build_real() is SYNC (prospector scan + per-client content-queue file
        # reads inside _collect_live_stats) — confirmed 45s+ under real prod data
        # (2026-07-01 office_hq incident, same underlying call). Calling it
        # directly here blocked THIS event-loop worker for the same duration,
        # which raced past the frontend's 8s AbortController and fell back to
        # the zero-filled DEMO payload — clients showing 0 even though
        # clients_store had real rows (2026-07-04). Run off-loop with a hard
        # deadline, same guard as office_hq._safe_collect_live_stats.
        resp = await asyncio.wait_for(asyncio.to_thread(_build_real), timeout=8.0)
    except Exception as e:  # absolute guard — never 500
        logger.warning("admin_dashboard: build_real failed (%s)", e)
        return DashboardResponse(
            is_sample_data=False,
            generated_at=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            kpis=KPIs(
                total_clients=0,
                active_campaigns=0,
                calls_today=0,
                qualified_leads_month=0,
                revenue_month=0,
                telephony_cost_month=0,
                net_margin_pct=0.0,
            ),
            clients=[],
            agents=[],
            campaigns=[],
            health=Health(api="up", db="down", telephony="down", scrapers="up"),
            charts=_real_charts({}),
            live={},
        )

    # NOTE: relational clients/campaigns tables me PURANA seeded DEMO data hai
    # (SunVolt Solar Pvt Ltd, ₹2.3L revenue) — woh override "purana data dikha
    # raha" wali bug ki jad thi. Marketing business ka source-of-truth ab
    # file-based aggregates (prospects/inquiries/clients_store/blog/emails) hai,
    # isliye _build_real() ka result HI return hota hai — DB demo-seed se override
    # NAHI. (Future: jab relational tables me asli clients aayein, _build_from_db
    # ko sirf empty panels bharne ke liye merge karna, KPIs replace karne ke liye nahi.)
    pf = (product or "").strip().lower()
    if pf in ("marketing", "voice", "combo"):
        resp.clients = [c for c in resp.clients if c.product == pf]
    return resp


@router.get("/revenue-analytics")
async def get_revenue_analytics(_user=Depends(require_admin)) -> dict:
    """MRR, churn-risk, LTV estimate — powers admin revenue analytics panel."""
    out: dict = {
        "mrr": 0,
        "subscriptions": {},
        "churn_risk_pct": 0.0,
        "clients_red": 0,
        "clients_yellow": 0,
        "clients_green": 0,
        "ltv_estimate_inr": 0,
        "hot_leads": 0,
        "health_top_risk": [],
    }
    try:
        from app.platform import client_health, revenue_digest

        stats = await revenue_digest._collect()
        out["mrr"] = int(stats.get("mrr") or 0)
        out["subscriptions"] = stats.get("subscriptions") or {}
        out["hot_leads"] = int(stats.get("hot_leads") or 0)
        out["deals"] = stats.get("deals") or {}
        out["dunning"] = stats.get("dunning") or {}
        health = await client_health.health_report()
        reds = sum(1 for h in health if h.get("band") == "red")
        yellows = sum(1 for h in health if h.get("band") == "yellow")
        greens = sum(1 for h in health if h.get("band") == "green")
        total = len(health) or 1
        active = int((out["subscriptions"] or {}).get("active") or 0) or total
        out["clients_red"] = reds
        out["clients_yellow"] = yellows
        out["clients_green"] = greens
        out["churn_risk_pct"] = round((reds + yellows) / total * 100, 1)
        out["ltv_estimate_inr"] = int(out["mrr"] * 12 / max(1, active))
        out["health_top_risk"] = [
            {
                "client_id": h.get("client_id"),
                "business_name": h.get("business_name"),
                "score": h.get("score"),
                "band": h.get("band"),
                "action": h.get("action"),
            }
            for h in health[:8]
        ]
    except Exception as e:
        logger.warning("admin_dashboard: revenue-analytics failed (%s)", e)
        out["error"] = str(e)[:160]
    return out


@router.get("/revenue-trend")
async def get_revenue_trend(days: int = 90, _user=Depends(require_admin)) -> dict:
    """B1: MRR/churn/LTV time-series for the admin revenue chart. Flag-gated."""
    if os.getenv("REVENUE_TRENDS", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False, "points": [], "note": "REVENUE_TRENDS off"}
    try:
        from app.platform import revenue_snapshots

        pts = revenue_snapshots.read_trend(days=days, price_fn=_client_mrr)
        return {"enabled": True, "points": pts, "note": ""}
    except Exception as e:
        logger.warning("admin_dashboard: revenue-trend failed (%s)", e)
        return {"enabled": True, "points": [], "note": str(e)[:160]}


def _build_client_timeline(client_id, agent_events, inquiries, audit, limit=50):
    """Pure merge+sort of per-client events from 3 sources. Newest first."""
    items: list[dict] = []
    for ev in agent_events or []:
        meta = ev.get("meta") or {}
        if str(meta.get("client_id") or "") != str(client_id):
            continue
        items.append(
            {
                "ts": str(ev.get("at") or ""),
                "kind": str(ev.get("action") or "event"),
                "source": "agent",
                "summary": f"{ev.get('member', '')}: {(ev.get('detail') or '')[:120]}".strip(": "),
            }
        )
    for r in inquiries or []:
        if str(r.get("client_id") or "") != str(client_id):
            continue
        items.append(
            {
                # inquiries.jsonl writes the timestamp under "at" (public_site.py)
                "ts": str(r.get("at") or r.get("ts") or r.get("created_at") or ""),
                "kind": "lead",
                "source": "lead",
                "summary": f"Enquiry from {r.get('name') or '-'}",
            }
        )
    for a in audit or []:
        if str(a.get("resource_id") or "") != str(client_id):
            continue
        items.append(
            {
                "ts": str(a.get("created_at") or ""),
                "kind": "audit",
                "source": "audit",
                "summary": str(a.get("action") or "audit"),
            }
        )
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[: max(1, min(int(limit), 200))]


def _fetch_client_audit(client_id: str, limit: int = 100) -> list[dict]:
    """Best-effort sync read of AuditLog rows whose resource_id == client_id.
    Never raises; returns [] if DB unreachable."""
    try:
        from app.models.user import AuditLog
        from app.platform.team import _db

        db = _db()
        if db is None:
            return []
        try:
            rows = (
                db.query(AuditLog)
                .filter(AuditLog.resource_id == str(client_id))
                .order_by(AuditLog.created_at.desc())
                .limit(max(1, min(int(limit), 200)))
                .all()
            )
            return [
                {
                    "created_at": (
                        getattr(r, "created_at", None).isoformat()
                        if getattr(r, "created_at", None)
                        else ""
                    ),
                    "action": getattr(r, "action", ""),
                    "resource_id": getattr(r, "resource_id", ""),
                }
                for r in rows
            ]
        finally:
            db.close()
    except Exception as e:
        logger.debug("admin_dashboard: client audit fetch failed (%s)", e)
        return []


@router.get("/clients/{client_id}/timeline")
async def get_client_timeline(
    client_id: str, limit: int = 50, _user=Depends(require_admin)
) -> dict:
    """B2: unified per-client event trail (agent_events + inquiries + audit)."""
    if os.getenv("CLIENT_TIMELINE", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False, "client_id": client_id, "events": []}
    agent_events: list = []
    inquiries: list = []
    audit: list = []
    try:
        from app.platform.team import recent_events

        agent_events = recent_events(limit=200)
    except Exception:
        pass
    try:
        inquiries = _read_inquiries()
    except Exception:
        pass
    try:
        audit = _fetch_client_audit(client_id)
    except Exception:
        audit = []
    events = _build_client_timeline(client_id, agent_events, inquiries, audit, limit)
    return {"enabled": True, "client_id": client_id, "events": events}


@router.get("/activity-feed")
def get_activity_feed(
    limit: int = Query(40, ge=1, le=100),
    _user=Depends(require_admin),
) -> dict:
    """Agent events timeline for admin activity panel."""
    try:
        from app.platform.team import recent_events

        events = recent_events(limit=limit)
        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.warning("admin_dashboard: activity-feed failed (%s)", e)
        return {"events": [], "count": 0, "error": str(e)[:120]}


@router.get("/hourly-activity")
def get_hourly_activity(
    hours: int = Query(24, ge=1, le=72),
    _user=Depends(require_admin),
) -> dict:
    """Agent events ko IST ghante-wise bucket karke 'is ghante kya kya hua' timeline.

    Admin dashboard ka 'hourly activity log' card isse banta hai — job-status grid
    (renderHourlyOps) se alag: yeh actual chronological kaam ka log hai (sab AI staff
    ke events, har ghante kitne + kya). Best-effort — kabhi 500 nahi.
    """
    try:
        from app.platform.team import recent_events

        try:
            from zoneinfo import ZoneInfo

            ist = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist = timezone.utc

        evs = recent_events(limit=1500, hours=hours)
        buckets: dict[str, dict] = {}
        for ev in evs:
            at = ev.get("at")
            if not at:
                continue
            try:
                dt = datetime.fromisoformat(str(at))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(ist)
            except Exception:
                continue
            key = dt.strftime("%Y-%m-%d %H")
            b = buckets.get(key)
            if b is None:
                label = dt.strftime("%d %b, %I %p").replace(", 0", ", ")
                b = {
                    "hour_key": key,
                    "label": label,
                    "count": 0,
                    "errors": 0,
                    "members": {},
                    "samples": [],
                }
                buckets[key] = b
            b["count"] += 1
            if str(ev.get("status")) in ("error", "warn"):
                b["errors"] += 1
            nm = ev.get("name") or ev.get("member") or "?"
            b["members"][nm] = b["members"].get(nm, 0) + 1
            if len(b["samples"]) < 10:
                b["samples"].append(
                    {
                        "name": nm,
                        "emoji": ev.get("emoji", ""),
                        "action": ev.get("action", ""),
                        "detail": str(ev.get("detail") or "")[:100],
                        "status": ev.get("status", "ok"),
                        "at": dt.strftime("%H:%M"),
                    }
                )
        ordered = [buckets[k] for k in sorted(buckets, reverse=True)]
        for b in ordered:
            b["members"] = sorted(
                ({"name": n, "count": c} for n, c in b["members"].items()),
                key=lambda x: -x["count"],
            )[:8]
        return {
            "buckets": ordered,
            "total": len(evs),
            "hours": hours,
            "generated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning("admin_dashboard: hourly-activity failed (%s)", e)
        return {"buckets": [], "total": 0, "error": str(e)[:120]}


@router.get("/prospects-preview")
def get_prospects_preview(
    limit: int = Query(40, ge=1, le=200),
    _user=Depends(require_admin),
) -> dict:
    """Prospect pipeline preview for admin leads section."""
    try:
        from app.platform import prospector

        rows = prospector.list_prospects(limit=limit) or []
        by_status: dict[str, int] = {}
        for r in rows:
            st = str(r.get("status") or "ready").lower()
            by_status[st] = by_status.get(st, 0) + 1
        preview = [
            {
                "business": r.get("business_name") or r.get("name") or "-",
                "city": r.get("city") or "-",
                "niche": r.get("niche") or "-",
                "status": r.get("status") or "ready",
                "phone": r.get("phone") or "",
                "email": r.get("email") or "",
            }
            for r in rows[:limit]
        ]
        return {"prospects": preview, "by_status": by_status, "total": len(rows)}
    except Exception as e:
        logger.warning("admin_dashboard: prospects-preview failed (%s)", e)
        return {"prospects": [], "by_status": {}, "total": 0, "error": str(e)[:120]}


@router.get("/live-stats")
async def get_live_stats(_user=Depends(require_admin)) -> dict:
    """Lightweight REAL aggregates dict (prospects, inquiries, clients, emails,
    blog, content, staff actions, calls). Best-effort — never 500."""
    try:
        stats = await _safe_collect_live_stats()
        stats["generated_at"] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        stats["is_sample_data"] = False
        return stats
    except Exception as e:
        logger.warning("admin_dashboard: live-stats failed (%s)", e)
        return {"is_sample_data": False, "error": str(e)}


@router.get("/sync-health")
async def admin_sync_health(_user=Depends(require_admin)) -> dict:
    """Recently-shipped backend features surfaced for the admin dashboard
    (so the UI stays synced with the project): deliverability (SPF/DKIM/DMARC +
    bounce/complaint), judge-calibration, approval-queue pending, flags-on.
    Each leg best-effort — never 500."""
    out: dict = {}
    try:
        from app.platform import deliverability_monitor as _dm

        out["deliverability"] = _dm.check_records()
    except Exception as e:
        out["deliverability"] = {"error": str(e)[:120]}
    try:
        from app.platform import email_warmup as _ew

        out["email"] = _ew.status()
    except Exception as e:
        out["email"] = {"error": str(e)[:120]}
    try:
        from app.agents import judge_calibration as _jc

        out["judges"] = _jc.calibrate()
    except Exception as e:
        out["judges"] = {"error": str(e)[:120]}
    try:
        from app.platform import approvals_bridge as _ab

        out["approvals"] = _ab.list_drafts().get("counts", {})
    except Exception as e:
        out["approvals"] = {"error": str(e)[:120]}
    try:
        import os as _os

        from app.api.growth import AUTOMATION_FLAGS

        on = [
            f
            for f in AUTOMATION_FLAGS
            if (_os.environ.get(f) or "").strip().lower() in ("1", "true", "yes")
        ]
        out["flags"] = {"on": len(on), "total": len(AUTOMATION_FLAGS)}
    except Exception as e:
        out["flags"] = {"error": str(e)[:120]}
    out["generated_at"] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
    return out


class ClientDeleteIn(BaseModel):
    confirm: bool = False


@router.post("/clients/{client_id}/delete")
async def admin_delete_client(
    client_id: str, body: ClientDeleteIn, _user=Depends(require_admin)
) -> dict:
    """Permanently remove a client record (admin cleanup of test/junk). Irreversible
    → confirm required. Admin-gated like the other destructive admin actions."""
    if not body.confirm:
        return {"ok": False, "error": "confirm required"}
    from app.marketing import clients_store

    ok = clients_store.delete_client((client_id or "").strip())
    return {"ok": ok, "client_id": client_id, "deleted": ok}


@router.post("/clients/dedupe")
async def admin_dedupe_clients(_user=Depends(require_admin)) -> dict:
    """Remove exact-duplicate client records (same phone → keep newest)."""
    from app.marketing import clients_store

    return {"ok": True, **clients_store.dedupe_clients()}


@router.get("/agents")
async def admin_agents(_user=Depends(require_admin)) -> dict:
    """Real AI staff roster (team_status → 18 members) as a STANDALONE fast call —
    so the dashboard's agents panel always shows the FULL team even if the heavy
    /api/admin/dashboard payload is slow/unavailable. Never 500."""
    ags = _real_agents()
    return {"agents": ags, "count": len(ags)}


class BulkEmailIn(BaseModel):
    client_ids: list[str] = Field(..., min_length=1, max_length=50)
    subject: str | None = "LeadsGenAI — quick check-in"
    message: str | None = ""


@router.post("/clients/bulk-email")
async def bulk_email_clients(body: BulkEmailIn, _user=Depends(require_admin)) -> dict:
    """Selected clients ko transactional check-in email — SMTP off ho to graceful skip."""
    from app.api.billing import _client_email, _client_name
    from app.integrations.email_sender import EmailSender

    subject = (body.subject or "LeadsGenAI — quick check-in").strip()[:200]
    custom = (body.message or "").strip()
    sender = EmailSender()
    sent = 0
    skipped = 0
    failed = 0
    details: list[dict] = []

    for raw_cid in body.client_ids[:50]:
        cid = str(raw_cid or "").strip()
        if not cid:
            skipped += 1
            continue
        to = _client_email(cid)
        if not to or "@" not in to or to.endswith("@example.com"):
            skipped += 1
            details.append({"client_id": cid, "status": "skipped", "reason": "no_email"})
            continue
        name = _client_name(cid)
        text = custom or (
            f"Namaste {name},\n\n"
            "Yeh LeadsGenAI se ek quick check-in hai — aapka dashboard aur leads theek chal rahe hain?\n"
            "Koi sawal ho to reply karein ya portal pe login karein: https://leadsgenai.in/app/customer\n\n"
            "— LeadsGenAI Team"
        )
        try:
            ok = await sender.send_email([to], subject, text)
            if ok:
                sent += 1
                details.append({"client_id": cid, "status": "sent", "email": to})
            else:
                failed += 1
                details.append({"client_id": cid, "status": "failed", "email": to})
        except Exception as e:
            failed += 1
            details.append({"client_id": cid, "status": "failed", "error": str(e)[:80]})

    return {
        "ok": sent > 0 or (skipped > 0 and failed == 0),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "smtp_configured": bool(sender.user and sender.password),
        "details": details[:20],
    }


class CeleryTrimIn(BaseModel):
    confirm: bool = False
    min_depth: int = Field(50, ge=10, le=50000)


@router.get("/ops-snapshot")
async def get_ops_snapshot(_user=Depends(require_admin)) -> dict:
    """Single admin ops payload — live stats + today overview + recent agent events."""
    live = await _safe_collect_live_stats()
    live["generated_at"] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
    try:
        from app.platform.team import recent_events

        live["recent_events"] = recent_events(limit=25)
    except Exception as e:
        live["recent_events"] = []
        live["recent_events_error"] = str(e)[:120]
    return live


@router.post("/ops/celery-trim")
async def trim_celery_queue(body: CeleryTrimIn, _user=Depends(require_admin)) -> dict:
    """Clear stale Celery backlog (beat re-schedules). confirm=true + depth>=min_depth required."""
    if not body.confirm:
        return {"ok": False, "error": "confirm:true required — yeh pending tasks delete karta hai"}
    try:
        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        depth = int(r.llen("celery") or 0)
        if depth < body.min_depth:
            return {
                "ok": False,
                "error": f"queue depth {depth} < min_depth {body.min_depth} — trim skip",
                "depth": depth,
            }
        r.delete("celery")
        return {
            "ok": True,
            "cleared": depth,
            "message": "celery queue cleared — beat will re-queue jobs",
        }
    except Exception as e:
        logger.warning("admin_dashboard: celery-trim failed (%s)", e)
        return {"ok": False, "error": str(e)[:160]}
