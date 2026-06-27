"""
Customer AI Marketing Studio API
================================
Powers the "AI Marketing Studio" section of frontend/customer_marketing.html.

These are the REAL customer-value AI-marketing features (vs. the SaaS-portal
infra in customer_dashboard.py). A small-business owner self-serves ready-to-use
marketing assets for THEIR niche/business:

  POST /api/customer/studio/post          -> ready social post (caption+hashtags)
  POST /api/customer/studio/calendar      -> 7-day content calendar
  POST /api/customer/studio/whatsapp      -> WhatsApp broadcast/status pack
  POST /api/customer/studio/review-reply  -> 3 replies for a Google review
  POST /api/customer/studio/gbp-text      -> Google Business description + posts
  POST /api/customer/studio/ads           -> Google RSA + Meta ad copy pack
  POST /api/customer/studio/hashtags      -> researched hashtag set
  GET  /api/customer/studio/gbp-tips      -> niche GBP growth tips (no LLM)
  GET  /api/customer/studio/tools         -> capability list (drives UI cards)

Design rules (mirrors marketing-feature skill + existing customer endpoints):
  * Free-stack only — every generator already does free_ai LLM + never-empty
    template fallback, so the UI is never blank and there is no paid dependency.
  * BAN-SAFE — these GENERATE copy only. Nothing is auto-sent (no WhatsApp/email
    blast). The customer copies the output and posts/sends manually.
  * client-scoped — business_name / niche / city come from the customer's own
    record (require_customer -> _client_record), never from request body, so one
    customer can't generate "as" another.
  * Cost guard — per-caller rate limit on the LLM endpoints.

Mount in main.py:
    from app.api.customer_marketing_studio import router as customer_studio_router
    app.include_router(customer_studio_router)
(Router already carries prefix="/api/customer/studio".)
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer
from app.api.customer_dashboard_builders import _client_record
from app.api.ratelimit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer/studio", tags=["Customer Marketing Studio"])

# Per-caller cost guard for the LLM generation endpoints (free providers, but
# circuit-breakered — keep self-serve usage bounded). GET tips/tools are exempt.
_GEN_LIMIT = rate_limit("cust_studio", 30, 60)  # 30 generations / minute


# --------------------------------------------------------------------------- #
# Client context — niche/business/city ALWAYS from the authed client's record  #
# --------------------------------------------------------------------------- #
def _ctx(client_id: str) -> dict:
    rec = _client_record(client_id) or {}
    return {
        "business_name": str(rec.get("business_name") or rec.get("name") or "Aapka Business").strip(),
        "niche": str(rec.get("niche") or "general").strip().lower() or "general",
        "city": str(rec.get("city") or rec.get("location") or "").strip(),
        "website": str(rec.get("website") or "").strip(),
        "has_record": bool(rec),
    }


# --------------------------------------------------------------------------- #
# Request bodies (all optional — generators have safe defaults)                #
# --------------------------------------------------------------------------- #
class PostReq(BaseModel):
    occasion: str = Field("", max_length=120, description="Festival / theme / topic")
    offer: str = Field("", max_length=200, description="Discount / offer line")
    language: str = Field("hinglish", max_length=20)


class CalendarReq(BaseModel):
    days: int = Field(7, ge=1, le=30)


class WhatsAppReq(BaseModel):
    occasion: str = Field("", max_length=120)
    offer: str = Field("", max_length=200)


class ReviewReplyReq(BaseModel):
    review_text: str = Field(..., min_length=1, max_length=2000)
    rating: float | None = Field(None, ge=0, le=5)
    tone: str = Field("professional", max_length=30)


class GbpTextReq(BaseModel):
    services: list[str] | None = Field(None, description="Up to ~6 service names")
    city: str = Field("", max_length=80, description="Override city (else client record)")


class AdsReq(BaseModel):
    offer: str = Field("", max_length=200)
    city: str = Field("", max_length=80)


class HashtagReq(BaseModel):
    count: int = Field(15, ge=5, le=30)
    city: str = Field("", max_length=80)


# --------------------------------------------------------------------------- #
# Generators (each wraps an existing app.marketing.* function)                 #
# --------------------------------------------------------------------------- #
def _fail(name: str, exc: Exception):
    logger.error("studio.%s failed: %s", name, exc)
    raise HTTPException(status_code=503, detail=f"{name} abhi available nahi — thodi der baad try karo.")


@router.post("/post", dependencies=[Depends(_GEN_LIMIT)])
async def studio_post(req: PostReq = Body(default=PostReq()), client_id: str = Depends(require_customer)) -> dict:
    """Ready-to-post social caption + hashtags + image idea for the client's niche."""
    c = _ctx(client_id)
    try:
        from app.marketing import post_generator

        out = await post_generator.generate_post(
            business_name=c["business_name"], niche=c["niche"],
            occasion=req.occasion, offer=req.offer, language=req.language,
        )
    except Exception as e:  # generators never raise, but stay defensive
        _fail("AI Post", e)
    return {"ok": True, "tool": "post", "result": out, "context": c}


@router.post("/calendar", dependencies=[Depends(_GEN_LIMIT)])
async def studio_calendar(req: CalendarReq = Body(default=CalendarReq()), client_id: str = Depends(require_customer)) -> dict:
    """N-day content calendar (themes + hook lines) for the client's niche."""
    c = _ctx(client_id)
    try:
        from app.marketing import post_generator

        items = await post_generator.content_calendar(
            business_name=c["business_name"], niche=c["niche"], days=req.days,
        )
    except Exception as e:
        _fail("Content Calendar", e)
    return {"ok": True, "tool": "calendar", "days": req.days, "items": items, "context": c}


@router.post("/whatsapp", dependencies=[Depends(_GEN_LIMIT)])
async def studio_whatsapp(req: WhatsAppReq = Body(default=WhatsAppReq()), client_id: str = Depends(require_customer)) -> dict:
    """WhatsApp broadcast + status + reply pack (copy-paste; NOT auto-sent)."""
    c = _ctx(client_id)
    try:
        from app.marketing import whatsapp_pack

        out = await whatsapp_pack.broadcast_pack(
            business_name=c["business_name"], niche=c["niche"],
            occasion=req.occasion, offer=req.offer,
        )
    except Exception as e:
        _fail("WhatsApp Pack", e)
    return {"ok": True, "tool": "whatsapp", "result": out, "note": "Copy karke khud bhejo (auto-send ban-safe OFF).", "context": c}


@router.post("/review-reply", dependencies=[Depends(_GEN_LIMIT)])
async def studio_review_reply(req: ReviewReplyReq, client_id: str = Depends(require_customer)) -> dict:
    """3 Hinglish replies (short/medium/detailed) for a Google review."""
    c = _ctx(client_id)
    try:
        from app.marketing import review_replies

        out = await review_replies.generate_replies(
            review_text=req.review_text, rating=req.rating,
            business_name=c["business_name"], tone=req.tone,
        )
    except Exception as e:
        _fail("Review Reply", e)
    return {"ok": True, "tool": "review-reply", "result": out, "context": c}


@router.post("/gbp-text", dependencies=[Depends(_GEN_LIMIT)])
async def studio_gbp_text(req: GbpTextReq = Body(default=GbpTextReq()), client_id: str = Depends(require_customer)) -> dict:
    """Google Business Profile description + service texts + 3 posts."""
    c = _ctx(client_id)
    try:
        from app.marketing import gbp_text

        out = await gbp_text.gbp_texts(
            business_name=c["business_name"], niche=c["niche"],
            city=(req.city or c["city"]), services=req.services,
        )
    except Exception as e:
        _fail("GBP Text", e)
    return {"ok": True, "tool": "gbp-text", "result": out, "context": c}


@router.post("/ads", dependencies=[Depends(_GEN_LIMIT)])
async def studio_ads(req: AdsReq = Body(default=AdsReq()), client_id: str = Depends(require_customer)) -> dict:
    """Google RSA + Meta ad copy pack (char-limit safe headlines/descriptions)."""
    c = _ctx(client_id)
    try:
        from app.marketing import ads_copy

        out = await ads_copy.ads_pack(
            business_name=c["business_name"], niche=c["niche"],
            offer=req.offer, city=(req.city or c["city"]),
        )
    except Exception as e:
        _fail("Ad Copy", e)
    return {"ok": True, "tool": "ads", "result": out, "context": c}


@router.post("/hashtags", dependencies=[Depends(_GEN_LIMIT)])
async def studio_hashtags(req: HashtagReq = Body(default=HashtagReq()), client_id: str = Depends(require_customer)) -> dict:
    """Researched hashtag set for the client's niche/city."""
    c = _ctx(client_id)
    try:
        from app.marketing import hashtags

        out = await hashtags.research(niche=c["niche"], city=(req.city or c["city"]), count=req.count)
    except Exception as e:
        _fail("Hashtags", e)
    return {"ok": True, "tool": "hashtags", "result": out, "context": c}


@router.get("/gbp-tips")
def studio_gbp_tips(client_id: str = Depends(require_customer)) -> dict:
    """Niche-specific Google Business growth tips (PURE LOGIC, no LLM cost)."""
    c = _ctx(client_id)
    try:
        from app.marketing import post_generator

        tips = post_generator.gbp_tips(c["niche"])
    except Exception as e:
        logger.debug("studio_gbp_tips failed: %s", e)
        tips = []
    return {"ok": True, "tool": "gbp-tips", "tips": tips, "context": c}


# --------------------------------------------------------------------------- #
# Capability list — drives the UI cards (so frontend stays in sync)            #
# --------------------------------------------------------------------------- #
_TOOLS = [
    {"key": "post", "icon": "📝", "title": "AI Social Post", "desc": "Ready caption + hashtags + image idea", "method": "POST", "path": "/api/customer/studio/post", "fields": ["occasion", "offer"]},
    {"key": "calendar", "icon": "🗓️", "title": "Content Calendar", "desc": "7-din ka post plan", "method": "POST", "path": "/api/customer/studio/calendar", "fields": ["days"]},
    {"key": "whatsapp", "icon": "💬", "title": "WhatsApp Pack", "desc": "Broadcast + status + reply lines", "method": "POST", "path": "/api/customer/studio/whatsapp", "fields": ["occasion", "offer"]},
    {"key": "review-reply", "icon": "⭐", "title": "Review Reply", "desc": "Google review ka 3-style reply", "method": "POST", "path": "/api/customer/studio/review-reply", "fields": ["review_text", "rating"]},
    {"key": "gbp-text", "icon": "🏪", "title": "Google Business Text", "desc": "GBP description + posts", "method": "POST", "path": "/api/customer/studio/gbp-text", "fields": ["services", "city"]},
    {"key": "ads", "icon": "📣", "title": "Ad Copy Pack", "desc": "Google + Meta ad headlines", "method": "POST", "path": "/api/customer/studio/ads", "fields": ["offer", "city"]},
    {"key": "hashtags", "icon": "#️⃣", "title": "Hashtag Research", "desc": "Niche ke best hashtags", "method": "POST", "path": "/api/customer/studio/hashtags", "fields": ["count", "city"]},
    {"key": "gbp-tips", "icon": "📈", "title": "GBP Growth Tips", "desc": "Google ranking tips (free)", "method": "GET", "path": "/api/customer/studio/gbp-tips", "fields": []},
]


@router.get("/tools")
def studio_tools(client_id: str = Depends(require_customer)) -> dict:
    """List of available studio tools + this client's resolved context."""
    return {"ok": True, "count": len(_TOOLS), "tools": _TOOLS, "context": _ctx(client_id)}
