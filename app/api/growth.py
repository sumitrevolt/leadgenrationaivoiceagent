"""Growth API — naye 2026 growth features ka surface (admin).

- Lead scoring / hot-leads (app/platform/lead_scoring.py)
- Review generation engine, sentiment-gated (app/marketing/review_engine.py)
- WhatsApp Flows send (app/marketing/whatsapp_flows.py — Meta-gated)
- Missed-call -> AI callback (app/telephony/missed_call.py — Vobiz-gated)

Sab additive + free + gated. Writes admin-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/growth", tags=["Growth"])


# ----------------------------- Lead scoring ----------------------------- #
@router.get("/leads/hot")
async def hot_leads(limit: int = 25, _user=Depends(require_admin)):
    """Top hot leads (0-100 scored, in-market prospects pe focus)."""
    from app.platform import lead_scoring

    return await lead_scoring.top_hot_leads(limit)


@router.post("/leads/rescore")
async def rescore_leads(limit: int = 500, _user=Depends(require_admin)):
    """Saare leads ko rescore karke lead_score + is_hot_lead DB me update karo."""
    from app.platform import lead_scoring

    return await lead_scoring.rescore_db(limit)


class ScoreOneIn(BaseModel):
    lead: dict


@router.post("/leads/score")
async def score_one(body: ScoreOneIn, _user=Depends(require_admin)):
    """Ek lead-dict ka live score + breakdown (debug/preview)."""
    from app.platform import lead_scoring

    s = lead_scoring.score_lead(body.lead)
    return {"score": s, "is_hot": lead_scoring.is_hot(s), "components": lead_scoring.score_components(body.lead)}


# ----------------------------- Review engine ---------------------------- #
class ReviewReqIn(BaseModel):
    business_name: str
    place_query: str | None = None
    customer_name: str | None = ""
    customer_phone: str | None = ""
    sentiment_score: int | None = None  # 1-5; <4 => private feedback
    auto_send: bool | None = None


@router.post("/review/request")
async def review_request(body: ReviewReqIn, _user=Depends(require_admin)):
    """Sentiment-gated review request banao (happy->Google, unhappy->private)."""
    from app.marketing import review_engine

    return await review_engine.request_review(
        business_name=body.business_name,
        place_query=body.place_query,
        customer_name=body.customer_name or "",
        customer_phone=body.customer_phone or "",
        sentiment_score=body.sentiment_score,
        auto_send=body.auto_send,
    )


@router.get("/review/requests")
async def review_requests(limit: int = 100, _user=Depends(require_admin)):
    from app.marketing import review_engine

    return {"requests": review_engine.list_requests(limit)}


# --------------------------- WhatsApp Flows ----------------------------- #
class FlowSendIn(BaseModel):
    to_number: str
    cta: str | None = "Enquiry karein"


@router.post("/whatsapp/flow/send")
async def whatsapp_flow_send(body: FlowSendIn, _user=Depends(require_admin)):
    """In-chat lead-capture Flow bhejo (Meta-gated; flow_id/creds na ho -> inert)."""
    from app.marketing import whatsapp_flows

    return await whatsapp_flows.send_flow(body.to_number, flow_cta=body.cta or "Enquiry karein")


# --------------------------- Missed-call callback ----------------------- #
class MissedCallIn(BaseModel):
    from_number: str
    niche: str | None = "general"
    business: str | None = ""


@router.post("/missed-call")
async def missed_call(body: MissedCallIn, _user=Depends(require_admin)):
    """Missed-call -> lead capture + (gated) instant AI callback. Telephony webhook
    isi ko call karega; abhi admin test endpoint."""
    if not (body.from_number or "").strip():
        raise HTTPException(status_code=422, detail="from_number chahiye.")
    from app.telephony.missed_call import handle_missed_call

    return await handle_missed_call(body.from_number, body.niche or "general", body.business or "")
