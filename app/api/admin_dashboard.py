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

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import require_admin
from app.models.base import get_async_db
from app.platform import admin_idempotency
from app.platform.admin_audit import record_admin_action

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
        logger.warning(
            "admin_dashboard: _collect_live_stats timed out/failed (%ss budget): %s", timeout, e
        )
        return {}


# ----------------------------------------------------------------------------
# REAL data aggregation. Every source is best-effort (file may be absent →
# 0). NEVER raises — returns a plain dict of true numbers.
# ----------------------------------------------------------------------------
from app.api.admin_dashboard_builders import (  # noqa: F401  (helpers extracted 2026-06-20)
    _automation_snapshot,
    _build_command_center,
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
        # ADR-121b: instead of all-zero fallback, compute critical KPIs
        # (client count + MRR) directly from fast JSONL source so the
        # dashboard never shows "0 clients / ₹0 MRR" when the full
        # _collect_live_stats times out (45s+ under real data).
        _fb_total = 0
        _fb_active = 0
        _fb_mrr = 0
        try:
            from app.api.admin_dashboard_builders import _client_mrr, _has_paid_evidence
            from app.marketing import clients_store as _cs

            _all = _cs.list_clients()
            _fb_total = len(_all)
            for _c in _all:
                if str(_c.get("status") or "").lower() == "active":
                    _fb_active += 1
                    if _has_paid_evidence(_c):
                        _fb_mrr += _client_mrr(_c)
        except Exception:
            pass
        return DashboardResponse(
            is_sample_data=False,
            generated_at=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            kpis=KPIs(
                total_clients=_fb_total,
                active_campaigns=_fb_active,
                calls_today=0,
                qualified_leads_month=0,
                revenue_month=_fb_mrr,
                telephony_cost_month=0,
                net_margin_pct=100.0 if _fb_mrr else 0.0,
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


@router.get("/trial-nudge/status")
async def admin_trial_nudge_status(_user=Depends(require_admin)) -> dict:
    """Trial-nudge admin surface: flag snapshot + dry-run eligible preview.

    Preview = run_trial_nudge(dry_run=True) — NO emails sent, NO stamps
    written; ENABLED gate bypassed for preview (arming decision helper) but
    HARD_OFF still blocks. BLK-02 UI-tab rule: admin feature = UI tab SAATH.
    """
    out: dict = {}
    try:
        from app.billing.trial_nudge import run_trial_nudge, status_flags

        out.update(status_flags())
        preview = await run_trial_nudge(dry_run=True, limit=20)
        out["preview"] = {
            "seen": preview.get("seen", 0),
            "eligible": preview.get("eligible", 0),
            "would_send": preview.get("would_send", 0),
            "skipped_active": preview.get("skipped_active", 0),
            "skipped_not_due": preview.get("skipped_not_due", 0),
            "skipped_no_email": preview.get("skipped_no_email", 0),
            "skipped_suppressed": preview.get("skipped_suppressed", 0),
            "skipped_cooldown": preview.get("skipped_cooldown", 0),
            "skip_reason": preview.get("skip_reason"),
            "items": preview.get("items", []),
        }
    except Exception as e:
        logger.warning("admin_dashboard: trial-nudge status failed (%s)", e)
        out["error"] = str(e)[:160]
    return out


@router.post("/trial-nudge/run")
async def admin_trial_nudge_run(request: Request, admin=Depends(require_admin)) -> dict:
    """Manual trial-nudge run (admin). ALL internal gates still apply —
    HARD_OFF blocks; TRIAL_NUDGE_ENABLED off => skip result returned so the
    admin sees exactly why nothing was sent. Real emails go out only when
    the job's own gates pass."""
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        limit = body.get("limit") if isinstance(body, dict) else None
        from app.billing.trial_nudge import run_trial_nudge

        result = await run_trial_nudge(limit=limit)
        logger.info(
            "admin trial-nudge run by %s: sent=%s skipped=%s",
            (admin or {}).get("username", "?"),
            result.get("sent"),
            result.get("skip_reason"),
        )
        return result
    except Exception as e:
        logger.warning("admin_dashboard: trial-nudge run failed (%s)", e)
        return {"error": str(e)[:160]}


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


def _build_client_timeline(
    client_id, agent_events, inquiries, audit, delivery_events=None, limit=50
):
    """Pure merge+sort of per-client events from 4 sources. Newest first."""
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
    for d in delivery_events or []:
        items.append(
            {
                "ts": str(d.get("at") or ""),
                "kind": "delivery",
                "source": "delivery_ledger",
                "summary": f"{d.get('icon', '')} {d.get('label', '')}".strip(),
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
    """B2: unified per-client event trail (agent_events + inquiries + audit + delivery ledger)."""
    if os.getenv("CLIENT_TIMELINE", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False, "client_id": client_id, "events": []}
    agent_events: list = []
    inquiries: list = []
    audit: list = []
    delivery_events: list = []
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
    try:
        from app.marketing import delivery_ledger

        # Existing customers ka pre-ledger history lazily backfill (idempotent).
        delivery_ledger.ensure_backfilled(client_id)
        delivery_events = delivery_ledger.timeline(client_id, limit=100, customer_only=False)
    except Exception:
        delivery_events = []
    events = _build_client_timeline(
        client_id, agent_events, inquiries, audit, delivery_events, limit
    )
    return {"enabled": True, "client_id": client_id, "events": events}


@router.get("/command-center")
async def admin_command_center(_user=Depends(require_admin)) -> dict:
    """Customer Delivery OS Phase 2 — business-outcome admin front door: total/
    paying/stuck-in-setup/receiving-value/failed-automation customers, pending
    approvals, revenue. Read-only rollup; never mutates state."""
    try:
        return await asyncio.to_thread(_build_command_center)
    except Exception as e:
        logger.warning("admin_command_center failed: %s", e)
        return {
            "ok": False,
            "summary": {},
            "revenue": {"mrr_total": 0, "by_plan": {}},
            "by_product": {},
            "per_customer": [],
        }


@router.get("/delivery-cockpit")
async def admin_delivery_cockpit(_user=Depends(require_admin)) -> dict:
    """Delivery-first cockpit for Product One operations.

    Shows pipeline, per-customer next action, deliverable completion, failures,
    approvals, and renewal readiness. Reuses existing delivery stores; never
    creates a new disconnected dashboard data source."""
    try:
        from app.marketing import product_one_delivery

        return await asyncio.to_thread(product_one_delivery.delivery_cockpit)
    except Exception as e:
        logger.warning("admin_delivery_cockpit failed: %s", e)
        return {"ok": False, "summary": {}, "pipeline": [], "customers": [], "error": str(e)[:160]}


@router.get("/delivery-assurance")
async def admin_delivery_assurance(
    include_healthy: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    _user=Depends(require_admin),
) -> dict:
    """Read-only missed / at-risk paid-customer delivery scan.

    Composes existing delivery primitives (canonical id + ledger evidence +
    customer_delivery_status). Never sends WhatsApp/email and never mutates
    delivery_state. Owner attribution: nikhil (revenue ops).
    """
    try:
        from app.marketing import delivery_assurance

        scan = await asyncio.to_thread(
            delivery_assurance.scan_missed_deliverables,
            limit,
            include_healthy,
        )
        return {"ok": scan.get("status") == "success", **scan}
    except Exception as e:
        logger.warning("admin_delivery_assurance failed: %s", e)
        return {
            "ok": False,
            "status": "error",
            "agent_id": "delivery_assurance",
            "checked": 0,
            "missed_count": 0,
            "at_risk_count": 0,
            "items": [],
            "error": str(e)[:160],
        }


@router.get("/entitlement-assurance")
async def admin_entitlement_assurance(
    limit: int = Query(200, ge=1, le=500),
    _user=Depends(require_admin),
) -> dict:
    """Read-only billing/entitlement-drift scan for Revenue Ops.

    Cross-checks plan <-> invoice <-> subscription state to surface revenue
    leaks: an active paid tenant with ZERO live invoice evidence
    (``paid_no_invoice``), an invoice on a non-active subscription
    (``invoice_without_active_subscription``), an ``unknown_plan``, or
    ``entitlement_drift``. Composes existing billing primitives
    (Rule-46 ledger + packages + subscription + canonical tenant ids) — NEVER
    creates/voids an invoice, changes a subscription, or mutates a client.
    Owner attribution: nikhil (revenue ops). Mirrors ``/delivery-assurance``.
    """
    try:
        from app.billing import entitlement_assurance

        scan = await asyncio.to_thread(entitlement_assurance.scan_entitlements, limit)
        return {"ok": scan.get("status") == "success", **scan}
    except Exception as e:
        logger.warning("admin_entitlement_assurance failed: %s", e)
        return {
            "ok": False,
            "status": "error",
            "agent_id": "entitlement_assurance",
            "domain": "billing",
            "checked": 0,
            "issues": [],
            "counts": {},
            "error": str(e)[:160],
        }


@router.get("/delivery-logs")
async def admin_delivery_logs(
    filter: str = Query("", max_length=80),
    client_id: str = Query("", max_length=80),
    _user=Depends(require_admin),
) -> dict:
    """Admin-friendly automation logs tied to customer delivery."""
    try:
        from app.marketing import product_one_delivery

        rows = await asyncio.to_thread(product_one_delivery.automation_events, filter, client_id)
        return {"ok": True, "filter": filter, "count": len(rows), "events": rows}
    except Exception as e:
        logger.warning("admin_delivery_logs failed: %s", e)
        return {"ok": False, "events": [], "error": str(e)[:160]}


class DeliveryActionIn(BaseModel):
    action: str = Field(..., max_length=60)
    deliverable_id: str = Field("", max_length=80)
    note: str = Field("", max_length=500)
    owner: str = Field("", max_length=80)
    status: str = Field("success", max_length=40)


@router.post("/clients/{client_id}/delivery-action")
async def admin_delivery_action(
    client_id: str,
    body: DeliveryActionIn,
    request: Request,
    admin=Depends(require_admin),
) -> dict:
    """Action buttons for Delivery Cockpit.

    Buttons call real existing operations where available (content generation,
    approval, monthly report) or create an explicit manual task/proof record.
    """
    cid = (client_id or "").strip()
    try:
        from app.marketing import product_one_delivery

        res = await product_one_delivery.record_manual_action(
            client_id,
            body.action,
            deliverable_id=body.deliverable_id,
            note=body.note,
            owner=body.owner,
            status=body.status,
        )
        await record_admin_action(
            request=request,
            actor=admin,
            action="client.delivery_action",
            target_type="client",
            target_id=cid,
            tenant=cid,
            after={
                "action": body.action,
                "deliverable_id": body.deliverable_id,
                "status": body.status,
            },
            result=("success" if (isinstance(res, dict) and res.get("ok", True)) else "failed"),
        )
        return res
    except Exception as e:
        logger.warning("admin_delivery_action failed: %s", e)
        await record_admin_action(
            request=request,
            actor=admin,
            action="client.delivery_action",
            target_type="client",
            target_id=cid,
            tenant=cid,
            after={"action": getattr(body, "action", None)},
            result="failed",
            error=str(e)[:200],
            severity="critical",
        )
        return {"ok": False, "error": str(e)[:160]}


@router.get("/automation-logs")
async def admin_automation_logs(
    client_id: str = Query("", max_length=80),
    job_type: str = Query("", max_length=100),
    status: str = Query("", max_length=20),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(200, ge=1, le=500),
    _user=Depends(require_admin),
) -> dict:
    """DB-backed centralized automation logs (ADR-064)."""
    try:
        from app.platform.automation_log_service import get_logs

        rows = get_logs(
            client_id=client_id,
            job_type=job_type,
            status=status,
            days=days,
            limit=limit,
        )
        return {"ok": True, "count": len(rows), "logs": rows}
    except Exception as e:
        logger.warning("admin_automation_logs failed: %s", e)
        return {"ok": False, "logs": [], "error": str(e)[:160]}


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
    client_id: str, body: ClientDeleteIn, request: Request, admin=Depends(require_admin)
) -> dict:
    """Permanently remove a client record (admin cleanup of test/junk). Irreversible
    → confirm required. Admin-gated like the other destructive admin actions."""
    cid = (client_id or "").strip()
    if not body.confirm:
        await record_admin_action(
            request=request,
            actor=admin,
            action="client.delete",
            target_type="client",
            target_id=cid,
            tenant=cid,
            result="rejected",
            error="confirm required",
        )
        return {"ok": False, "error": "confirm required"}
    _idem = admin_idempotency.begin(
        request=request,
        actor_id=getattr(admin, "id", None),
        scope="client.delete",
        payload={"client_id": cid, "confirm": True},
    )
    if isinstance(_idem, admin_idempotency.Replay):
        return _idem.response
    from app.marketing import clients_store

    ok = clients_store.delete_client(cid)
    result = {"ok": ok, "client_id": client_id, "deleted": ok}
    admin_idempotency.store(_idem, result)
    await record_admin_action(
        request=request,
        actor=admin,
        action="client.delete",
        target_type="client",
        target_id=cid,
        tenant=cid,
        after={"deleted": bool(ok)},
        result=("success" if ok else "failed"),
        error=(None if ok else "delete_client returned False"),
        idempotency_key=admin_idempotency.key_of(request),
    )
    return result


class ClientRemoveIn(BaseModel):
    confirm: bool = False
    reason: str = ""
    # Default SOFT: cancel + disable. Destructive file/record purge is opt-in.
    mode: str = "soft"  # soft | purge
    confirm_purge: bool = False  # required when mode=purge


@router.post("/clients/{client_id}/remove-customer")
async def admin_remove_customer(
    client_id: str,
    body: ClientRemoveIn,
    request: Request,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Admin customer removal — soft-disable by default; purge is owner-gated.

    **soft (default):** revoke portal login, CANCEL billing subscriptions
    (MRR truth), cancel scheduled content, mark converted autopilot prospects
    ``removed`` (never re-contacted), set clients_store status=``cancelled``.
    Brand kit + derived ledgers are KEPT for audit/DPDP retention.

    **purge:** same as soft, THEN delete brand kit + derived stores + the
    clients_store record. Requires ``confirm_purge=true`` AND
    ``ADMIN_CUSTOMER_PURGE_ENABLED=1`` (fail-closed when unset). Irreversible.

    Admin-gated + idempotent. Returns a per-store cleanup summary.
    """
    cid = (client_id or "").strip()
    mode = (body.mode or "soft").strip().lower() or "soft"
    if mode not in ("soft", "purge"):
        return {"ok": False, "error": "mode must be soft|purge"}

    if not body.confirm:
        await record_admin_action(
            request=request,
            actor=admin,
            action="client.disable" if mode == "soft" else "client.remove.purge",
            target_type="client",
            target_id=cid,
            tenant=cid,
            result="rejected",
            error="confirm required",
        )
        return {"ok": False, "error": "confirm required"}

    if mode == "purge":
        if not body.confirm_purge:
            await record_admin_action(
                request=request,
                actor=admin,
                action="client.remove.purge",
                target_type="client",
                target_id=cid,
                tenant=cid,
                result="rejected",
                error="confirm_purge required",
            )
            return {
                "ok": False,
                "error": "confirm_purge required for destructive purge",
            }
        _purge_armed = os.getenv("ADMIN_CUSTOMER_PURGE_ENABLED", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not _purge_armed:
            await record_admin_action(
                request=request,
                actor=admin,
                action="client.remove.purge",
                target_type="client",
                target_id=cid,
                tenant=cid,
                result="rejected",
                error="purge disabled",
            )
            return {
                "ok": False,
                "error": "purge disabled — set ADMIN_CUSTOMER_PURGE_ENABLED=1 (owner-gated)",
            }

    audit_action = "client.disable" if mode == "soft" else "client.remove.purge"
    _idem = admin_idempotency.begin(
        request=request,
        actor_id=getattr(admin, "id", None),
        scope=f"client.remove.{mode}",
        payload={
            "client_id": cid,
            "confirm": True,
            "mode": mode,
            "confirm_purge": bool(body.confirm_purge),
            "reason": body.reason,
        },
    )
    if isinstance(_idem, admin_idempotency.Replay):
        return _idem.response

    # Billing/invoice ids (e.g. `d79d690f61b3`) differ from the canonical marketing
    # id (`jiya-makeover`). Every derived store below is keyed on the MARKETING id,
    # so resolving the alias FIRST is what stops a half-removal: without this, an
    # alias id deletes nothing and still reports per-store `false` while the operator
    # believes the customer is gone. Never raises — unknown ids fall through as-is.
    requested_cid = cid
    try:
        from app.marketing import clients_store as _cs_resolve

        _canon = _cs_resolve.resolve_client(cid)
        if _canon and str(_canon.get("id") or "").strip():
            cid = str(_canon["id"]).strip()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[admin remove-customer] alias resolve failed: %s", e)

    summary: dict = {
        "client_id": cid,
        "requested_client_id": requested_cid,
        "reason": body.reason,
        "mode": mode,
        "auth_logins_revoked": 0,
        "auth_emails": [],
        "subscriptions_cancelled": 0,
        "subscription_ids": [],
        "content_cancelled": 0,
        "prospects_removed": 0,
        "prospect_ids": [],
        "client_status_set": False,
        "brand_kit_deleted": False,
        "delivery_deleted": False,
        "blogs_deleted": False,
        "crm_deleted": False,
        "content_queue_deleted": False,
        "clients_record_deleted": False,
    }

    def _rm(p: str) -> bool:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
                return True
        except Exception as e:
            logger.warning("[admin remove-customer] rm %s failed: %s", p, e)
        return False

    # 1. Portal login(s) — customer can no longer log in.
    try:
        from app.api import customer_auth

        auth = customer_auth.revoke_login_by_client(cid)
        summary["auth_logins_revoked"] = auth.get("removed", 0)
        summary["auth_emails"] = auth.get("emails", [])
    except Exception as e:
        logger.warning("[admin remove-customer] auth revoke failed: %s", e)

    # 2. Billing subscriptions → CANCELLED (MRR truth — audit 2026-08-08:
    #    before this, remove-customer deleted the client record but left ACTIVE
    #    Subscription rows, so admin MRR/subscriptions-active still counted a
    #    removed customer as revenue). Alias-aware like billing.cancel_subscription.
    try:
        from sqlalchemy import and_, select

        from app.models.payment import Subscription, SubscriptionStatus

        _sub_ids = [cid]
        try:
            from app.api.billing import _billing_client_ids

            _sub_ids = _billing_client_ids(cid) or _sub_ids
        except Exception:
            pass
        result = await db.execute(
            select(Subscription).where(
                and_(
                    Subscription.client_id.in_(_sub_ids),
                    Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE]),
                )
            )
        )
        for _sub in result.scalars().all():
            _sub.status = SubscriptionStatus.CANCELLED
            _sub.cancelled_at = datetime.utcnow()
            _sub.cancel_reason = body.reason or "customer_removed"
            summary["subscriptions_cancelled"] += 1
            summary["subscription_ids"].append(_sub.id)
        await db.commit()
    except Exception as e:
        logger.warning("[admin remove-customer] billing cancel failed: %s", e)

    # 3. Scheduled content → cancelled (never published later).
    try:
        from app.marketing import content_schedule

        summary["content_cancelled"] = content_schedule.cancel_for_client(cid)
    except Exception as e:
        logger.warning("[admin remove-customer] content cancel failed: %s", e)

    # 4. Autopilot prospects that converted to this client → terminal removed.
    try:
        from app.platform.sales_autopilot import store as _ap

        for prospect in _ap.find_by_converted_client(cid):
            rec = _ap.mark_removed(
                prospect.get("id") or prospect.get("prospect_id") or "",
                by=getattr(admin, "id", "admin") or "admin",
                reason=body.reason or "customer_removed",
            )
            if rec:
                summary["prospects_removed"] += 1
                summary["prospect_ids"].append(
                    str(prospect.get("id") or prospect.get("prospect_id"))
                )
    except Exception as e:
        logger.warning("[admin remove-customer] autopilot sweep failed: %s", e)

    if mode == "soft":
        # Soft: keep brand kit + ledgers; mark marketing record cancelled.
        try:
            from app.marketing import clients_store

            summary["client_status_set"] = bool(clients_store.set_status(cid, "cancelled"))
            if body.reason:
                try:
                    clients_store.update_client(cid, blocked_reason=str(body.reason)[:200])
                except Exception:
                    pass
        except Exception as e:
            logger.warning("[admin remove-customer] soft status set failed: %s", e)
    else:
        # Purge: brand kit + per-client derived stores + clients_store record.
        try:
            from app.marketing import brand_kit

            summary["brand_kit_deleted"] = brand_kit.delete_brand(cid)
        except Exception as e:
            logger.warning("[admin remove-customer] brand kit delete failed: %s", e)
        try:
            from app.marketing import product_one_delivery as _pod

            summary["delivery_deleted"] = _rm(_pod._events_path(cid))
        except Exception as e:
            logger.warning("[admin remove-customer] delivery delete failed: %s", e)
        try:
            from app.marketing import client_blog as _cb

            summary["blogs_deleted"] = _rm(str(_cb._path(cid)))
        except Exception as e:
            logger.warning("[admin remove-customer] blogs delete failed: %s", e)
        try:
            from app.marketing import crm_lite as _crm

            summary["crm_deleted"] = _rm(_crm._path(cid))
        except Exception as e:
            logger.warning("[admin remove-customer] crm delete failed: %s", e)
        try:
            from app.marketing import delivery_ledger as _dl

            summary["content_queue_deleted"] = _rm(
                os.path.join(_dl._CONTENT_QUEUE_DIR(), f"{_dl._safe_stem(cid)}.jsonl")
            )
        except Exception as e:
            logger.warning("[admin remove-customer] content-queue delete failed: %s", e)

        try:
            from app.marketing import clients_store

            summary["clients_record_deleted"] = bool(clients_store.delete_client(cid))
        except Exception as e:
            logger.warning("[admin remove-customer] clients_store delete failed: %s", e)

    ok = any(
        [
            summary["auth_logins_revoked"] > 0,
            summary["subscriptions_cancelled"] > 0,
            summary["content_cancelled"] > 0,
            summary["prospects_removed"] > 0,
            summary["client_status_set"],
            summary["brand_kit_deleted"],
            summary["delivery_deleted"],
            summary["blogs_deleted"],
            summary["crm_deleted"],
            summary["content_queue_deleted"],
            summary["clients_record_deleted"],
        ]
    )
    summary["ok"] = ok
    admin_idempotency.store(_idem, summary)
    await record_admin_action(
        request=request,
        actor=admin,
        action=audit_action,
        target_type="client",
        target_id=cid,
        tenant=cid,
        after=summary,
        result=("success" if ok else "failed"),
        error=(None if ok else "no stores had data to remove"),
        idempotency_key=admin_idempotency.key_of(request),
    )
    return summary


@router.post("/clients/dedupe")
async def admin_dedupe_clients(request: Request, admin=Depends(require_admin)) -> dict:
    """Remove exact-duplicate client records (same phone → keep newest)."""
    _idem = admin_idempotency.begin(
        request=request,
        actor_id=getattr(admin, "id", None),
        scope="client.dedupe",
        payload={},
    )
    if isinstance(_idem, admin_idempotency.Replay):
        return _idem.response
    from app.marketing import clients_store

    res = clients_store.dedupe_clients()
    result = {"ok": True, **res}
    admin_idempotency.store(_idem, result)
    await record_admin_action(
        request=request,
        actor=admin,
        action="client.dedupe",
        target_type="client",
        target_id="*",
        after=res,
        result="success",
        idempotency_key=admin_idempotency.key_of(request),
    )
    return result


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
async def bulk_email_clients(
    body: BulkEmailIn, request: Request, admin=Depends(require_admin)
) -> dict:
    """Selected clients ko transactional check-in email — SMTP off ho to graceful skip."""
    from app.api.billing import _client_email, _client_name
    from app.integrations.email_sender import EmailSender

    _n_targets = len(body.client_ids or [])
    try:
        from app.platform.owner_os import kill_engaged

        if kill_engaged("owner_bulk_email"):
            await record_admin_action(
                request=request,
                actor=admin,
                action="client.bulk_email",
                target_type="client",
                target_id="*",
                after={"targets": _n_targets},
                result="rejected",
                error="owner_bulk_email kill switch ENGAGED",
                severity="warning",
            )
            return {
                "ok": False,
                "sent": 0,
                "skipped": 0,
                "failed": 0,
                "error": "owner_bulk_email kill switch ENGAGED",
                "details": [],
            }
    except Exception:
        pass

    _idem = admin_idempotency.begin(
        request=request,
        actor_id=getattr(admin, "id", None),
        scope="client.bulk_email",
        payload={
            "client_ids": sorted(str(c) for c in (body.client_ids or [])),
            "subject": body.subject or "",
            "message": body.message or "",
        },
    )
    if isinstance(_idem, admin_idempotency.Replay):
        return _idem.response

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

    result = {
        "ok": sent > 0 or (skipped > 0 and failed == 0),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "smtp_configured": bool(sender.user and sender.password),
        "details": details[:20],
    }
    admin_idempotency.store(_idem, result)
    await record_admin_action(
        request=request,
        actor=admin,
        action="client.bulk_email",
        target_type="client",
        target_id="*",
        after={"sent": sent, "skipped": skipped, "failed": failed, "targets": _n_targets},
        result=("success" if failed == 0 else "partial"),
        error=(None if failed == 0 else f"{failed} sends failed"),
        severity=("info" if failed == 0 else "warning"),
        idempotency_key=admin_idempotency.key_of(request),
    )
    return result


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


@router.get("/boss-autopilot")
async def get_boss_autopilot(_user=Depends(require_admin)) -> dict:
    """Boss autonomy observability — flag, status, decisions, rollout (read-only).

    Real values only: enabled/ready reflect the live env flags; boss_rollout is
    the current rollout lane (held until the mutating canary); never fabricated.
    """
    out: dict = {"ok": True, "source": "app.platform.boss_autonomy"}
    try:
        from app.platform import boss_autonomy

        out["status"] = boss_autonomy.status()
    except Exception as e:  # noqa: BLE001 - best-effort observability
        out["status_error"] = str(e)[:160]
    try:
        from app.platform import boss_autonomy

        out["metrics"] = boss_autonomy.metrics()
    except Exception as e:  # noqa: BLE001
        out["metrics_error"] = str(e)[:160]
    try:
        from app.platform import boss_decision_governance as bdg

        out["governance"] = bdg.owner_os_visibility(limit=20)
    except Exception as e:  # noqa: BLE001
        out["governance_error"] = str(e)[:160]
    return out


@router.post("/ops/celery-trim")
async def trim_celery_queue(
    body: CeleryTrimIn, request: Request, admin=Depends(require_admin)
) -> dict:
    """Clear stale Celery backlog (beat re-schedules). confirm=true + depth>=min_depth required."""
    if not body.confirm:
        await record_admin_action(
            request=request,
            actor=admin,
            action="ops.celery_trim",
            target_type="queue",
            target_id="celery",
            result="rejected",
            error="confirm:true required",
            severity="warning",
        )
        return {"ok": False, "error": "confirm:true required — yeh pending tasks delete karta hai"}
    _idem = admin_idempotency.begin(
        request=request,
        actor_id=getattr(admin, "id", None),
        scope="ops.celery_trim",
        payload={"confirm": True, "min_depth": body.min_depth},
    )
    if isinstance(_idem, admin_idempotency.Replay):
        return _idem.response
    try:
        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        depth = int(r.llen("celery") or 0)
        if depth < body.min_depth:
            await record_admin_action(
                request=request,
                actor=admin,
                action="ops.celery_trim",
                target_type="queue",
                target_id="celery",
                before={"depth": depth, "min_depth": body.min_depth},
                result="rejected",
                error=f"depth {depth} < min_depth {body.min_depth}",
                severity="warning",
            )
            result = {
                "ok": False,
                "error": f"queue depth {depth} < min_depth {body.min_depth} — trim skip",
                "depth": depth,
            }
            admin_idempotency.store(_idem, result)
            return result
        r.delete("celery")
        result = {
            "ok": True,
            "cleared": depth,
            "message": "celery queue cleared — beat will re-queue jobs",
        }
        admin_idempotency.store(_idem, result)
        await record_admin_action(
            request=request,
            actor=admin,
            action="ops.celery_trim",
            target_type="queue",
            target_id="celery",
            before={"depth": depth},
            after={"cleared": depth},
            result="success",
            severity="warning",
            idempotency_key=admin_idempotency.key_of(request),
        )
        return result
    except Exception as e:
        # Transient failure: do NOT store → the in_progress lock expires (LOCK_TTL) so a
        # later retry re-executes rather than replaying a transient error.
        logger.warning("admin_dashboard: celery-trim failed (%s)", e)
        await record_admin_action(
            request=request,
            actor=admin,
            action="ops.celery_trim",
            target_type="queue",
            target_id="celery",
            result="failed",
            error=str(e)[:200],
            severity="critical",
        )
        return {"ok": False, "error": str(e)[:160]}
