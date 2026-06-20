"""
Customer-facing Dashboard API
==============================
Powers frontend/customer_dashboard.html.

The END CUSTOMER here is a small business (the SaaS's client). They want to see
the leads + enquiries our platform generated for them and the calls the AI voice
agent made on their behalf.

Data is REAL (no fictional "SunVolt Energy" sample anymore). Sources, all
best-effort + never-500, mirror admin_dashboard.py's real-data approach:
  - DB (Lead, CallLog, Campaign) keyed by client_id  -> richest view
  - data/inquiries.jsonl filtered by this client      -> leads (mini-site/website)
    (matched on source_slug / client_id / business name / phone)
  - data/content_queue/<id>.jsonl                     -> content posts count
  - data/marketing_clients.jsonl                      -> the client's own record

When NOTHING real exists for a client, the dashboard returns honest ZEROS with
is_sample_data=True (so the UI can show a "no data yet" state) — it NEVER invents
businesses/leads. This module stays import-safe: heavy imports are local+guarded.

Mount in main.py with:
    from app.api.customer_dashboard import router as customer_router
    app.include_router(customer_router)
(Router already carries prefix="/api/customer".)
"""

import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer", tags=["Customer Dashboard"])

# Inquiries store (jsonl-first; same path public_site.py writes to).
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")


# --------------------------------------------------------------------------- #
# Onboarding checklist — drives customer portal getting-started wizard         #
# --------------------------------------------------------------------------- #
from app.api.customer_dashboard_builders import (  # noqa: F401  (helpers extracted 2026-06-20)
    _build_from_db,
    _build_from_files,
    _build_onboarding_checklist,
    _calls_from_events,
    _client_record,
    _content_posts_count,
    _enrich_dashboard,
    _fmt_duration,
    _inquiries_for_client,
    _lead_score_from_inquiry,
    _mask_full_phone,
    _mask_full_phone_local,
    _parse_dt,
    _read_inquiries,
    _score_tier,
)

# --------------------------------------------------------------------------- #
# Pydantic response models (this is the exact JSON contract the HTML consumes) #
# --------------------------------------------------------------------------- #
from app.api.customer_dashboard_models import (  # noqa: F401  (models extracted 2026-06-20)
    CallRow,
    Campaign,
    ChartsData,
    CrmSyncLeadResult,
    CrmSyncResponse,
    DashboardResponse,
    Kpis,
    LeadRow,
    OnboardingChecklist,
    OnboardingStep,
    SeriesPoint,
)


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/dashboard", response_model=DashboardResponse)
def get_customer_dashboard(
    request: Request,
    campaign: str | None = Query(None, description="Optional campaign id to filter by"),
    client_id: str = Depends(require_customer),
) -> DashboardResponse:
    """
    Return the full dashboard payload for a customer — REAL data only.

    1. Real DB (Lead, CallLog, Campaign) keyed by client_id + campaign — richest.
    2. Else FILE-based real builder: this client's inquiries (inquiries.jsonl,
       matched by source_slug / client_id / business / phone) + content-queue
       posts + agent-event call counts.
    No fictional "SunVolt Energy" sample. If a client genuinely has zero
    activity the response carries honest zeros with is_sample_data=True (UI
    shows a clean "no data yet" state) — never invented businesses or leads.
    """
    resp = _build_from_db(client_id=client_id, campaign=campaign)
    if resp is None:
        resp = _build_from_files(client_id=client_id, campaign=campaign)
    resp = _enrich_dashboard(resp, client_id)
    # White-label: on a reseller subdomain the middleware set request.state.tenant.
    try:
        resp.branding = getattr(request.state, "tenant", None)
    except Exception:
        pass
    return resp


@router.get("/speed-to-lead")
def customer_speed_to_lead(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    client_id: str = Depends(require_customer),
) -> dict:
    """Client-scoped speed-to-lead SLA metric for dashboard badge."""
    from app.platform import speed_to_lead

    client_rec = _client_record(client_id)
    return speed_to_lead.summary_for_client(client_id, client_rec, days)


@router.patch("/leads/{lead_id}")
async def patch_lead_status(
    lead_id: str,
    status: str = Body(..., embed=True),
    client_id: str = Depends(require_customer),
) -> dict:
    """B4: customer updates a lead's status inline. require_customer resolves
    client_id from the JWT, so a client can only ever record an override under
    its own id (IDOR-safe). Override applies only to this client's leads."""
    from app.platform.lead_overrides import ALLOWED_STATUSES, set_status

    if status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}"
        )
    ok = set_status(lead_id, client_id, status)
    return {"ok": ok, "lead_id": lead_id, "status": status}


@router.post("/dashboard/send-to-crm", response_model=CrmSyncResponse)
async def send_dashboard_leads_to_crm(
    campaign: str | None = Query(None, description="Optional campaign id to filter by"),
    client_id: str = Depends(require_customer),
) -> CrmSyncResponse:
    """Customer ke visible dashboard leads ko configured CRM me push karo.

    AuthZ: client_id JWT se aata hai (query-param tenancy nahi).
    """
    resp = _build_from_db(client_id=client_id, campaign=campaign)
    if resp is None:
        resp = _build_from_files(client_id=client_id, campaign=campaign)
    leads = list(resp.leads or [])[:100]
    if not leads:
        return CrmSyncResponse(
            ok=False,
            client_id=client_id,
            campaign=campaign,
            attempted=0,
            delivered=0,
            skipped=0,
            failed=0,
            provider=None,
            message="Sync karne ke liye leads nahi mili.",
            results=[],
        )
    try:
        from app.platform import crm_sync
    except Exception as e:
        return CrmSyncResponse(
            ok=False,
            client_id=client_id,
            campaign=campaign,
            attempted=len(leads),
            delivered=0,
            skipped=0,
            failed=len(leads),
            provider=None,
            message="CRM module unavailable.",
            results=[
                CrmSyncLeadResult(
                    business=(l.business or "-"),
                    ok=False,
                    error=str(e)[:140],
                )
                for l in leads
            ],
        )

    status = crm_sync.status(client_id=client_id)
    provider = str(status.get("provider") or "none")
    if provider == "none":
        return CrmSyncResponse(
            ok=False,
            client_id=client_id,
            campaign=campaign,
            attempted=len(leads),
            delivered=0,
            skipped=len(leads),
            failed=0,
            provider=provider,
            message="CRM configured nahi hai. Admin se Zoho/HubSpot connect karvao.",
            results=[
                CrmSyncLeadResult(
                    business=(l.business or "-"),
                    ok=False,
                    provider=provider,
                    skipped="no CRM configured",
                )
                for l in leads
            ],
        )

    results: list[CrmSyncLeadResult] = []
    delivered = skipped = failed = 0
    for l in leads:
        payload = {
            "business_name": l.business or "",
            "contact_name": l.contact or "",
            "phone": l.phone or "",
            "city": l.city or "",
            "niche": l.niche or "",
            "score": l.score or "",
            "qualification": l.qualification or "",
            "source": "customer_dashboard",
        }
        out = await crm_sync.push_lead(payload, client_id=client_id, note=l.qualification or "")
        ok = bool(out.get("ok"))
        if ok:
            delivered += 1
        elif out.get("skipped"):
            skipped += 1
        else:
            failed += 1
        results.append(
            CrmSyncLeadResult(
                business=l.business or "-",
                ok=ok,
                provider=str(out.get("provider") or provider),
                record_id=(str(out.get("record_id")) if out.get("record_id") else None),
                contact_id=(str(out.get("contact_id")) if out.get("contact_id") else None),
                skipped=(str(out.get("skipped")) if out.get("skipped") else None),
                error=(str(out.get("error")) if out.get("error") else None),
            )
        )
    message = (
        f"{delivered} lead CRM me sync hui."
        if delivered
        else ("CRM configured hai, par koi lead sync nahi hui." if failed else "CRM sync skipped.")
    )
    return CrmSyncResponse(
        ok=delivered > 0,
        client_id=client_id,
        campaign=campaign,
        attempted=len(leads),
        delivered=delivered,
        skipped=skipped,
        failed=failed,
        provider=provider,
        message=message,
        results=results,
    )


class RoutingMemberIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    phone: str = Field(..., min_length=10, max_length=15)


class RoutingConfigIn(BaseModel):
    members: list[RoutingMemberIn] = Field(default_factory=list, max_length=10)


class ApprovalDecideIn(BaseModel):
    action: str = Field(default="approve", pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=300)


@router.get("/branded-feed")
async def customer_branded_feed(client_id: str = Depends(require_customer)):
    """AdBanao-style aaj ke 3 branded posts (logo+naam frame) — customer scoped."""
    try:
        from app.marketing import brand_frames
        from app.marketing.clients_store import get_client

        c = get_client(client_id) or {}
        slug = str(c.get("slug") or client_id or "").strip()
        return await brand_frames.daily_feed(slug)
    except Exception as e:
        logger.debug("customer branded-feed failed: %s", e)
        return {"ok": False, "error": "feed load nahi hua", "posts": []}


@router.get("/approvals/pending")
def customer_pending_approvals(client_id: str = Depends(require_customer)):
    """Posts jo client approval ka wait kar rahe hain."""
    try:
        from app.marketing import content_approval

        rows = content_approval.pending(client_id)
        safe = [
            {
                "id": r.get("id"),
                "status": r.get("status"),
                "created_at": r.get("created_at"),
                "content": r.get("content") or {},
            }
            for r in rows
        ]
        return {"ok": True, "count": len(safe), "approvals": safe}
    except Exception as e:
        logger.debug("customer approvals pending failed: %s", e)
        return {"ok": False, "count": 0, "approvals": []}


@router.post("/approvals/{approval_id}/decide")
def customer_decide_approval(
    approval_id: str,
    body: ApprovalDecideIn,
    client_id: str = Depends(require_customer),
):
    """Portal se approve/reject — token link ki zaroorat nahi."""
    from app.marketing import content_approval

    return content_approval.decide_for_client(client_id, approval_id, body.action, body.note or "")


@router.get("/routing")
def customer_routing_get(client_id: str = Depends(require_customer)):
    """Client ki sales team round-robin config."""
    from app.platform import lead_distribution as ld

    cfg = ld.get_config(client_id)
    recent = ld.assignments(client_id, limit=15)
    return {"ok": True, "config": cfg, "recent_assignments": recent}


@router.post("/routing")
def customer_routing_set(
    body: RoutingConfigIn,
    client_id: str = Depends(require_customer),
):
    """Team members set karo — naye leads round-robin me bantenge."""
    from app.platform import lead_distribution as ld

    members = [{"name": m.name, "phone": m.phone} for m in body.members]
    return ld.set_config(client_id, members)


@router.get("/health")
def customer_dashboard_health() -> dict:
    """Lightweight liveness probe for the customer dashboard API."""
    return {"status": "ok", "service": "customer-dashboard"}
