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
# Batch 2 — MVP-12 coverage (festival, poster, review-request, follow-ups,     #
# reel, win-back, quote, next-best-action). All wrap existing generators.      #
# --------------------------------------------------------------------------- #
class FestivalReq(BaseModel):
    days: int = Field(45, ge=7, le=120)


class PosterReq(BaseModel):
    template: str = Field("clean-pro", max_length=40)
    tagline: str = Field("", max_length=120)
    offer: str = Field("", max_length=160)
    phone: str = Field("", max_length=40)
    festival: str = Field("", max_length=60)


class FollowupReq(BaseModel):
    lead_type: str = Field("new_inquiry", max_length=40)


class ReelReq(BaseModel):
    topic: str = Field("", max_length=120)
    n: int = Field(3, ge=1, le=6)


class WinbackReq(BaseModel):
    offer: str = Field("", max_length=200)
    customers: list[dict] | None = Field(None, description="[{name,phone,last_visit?}]")


class QuoteReq(BaseModel):
    city: str = Field("", max_length=80)
    plan: str = Field("growth", max_length=30)
    avg_deal_value: float = Field(20000, ge=0, le=100000000)
    missed_per_day: float = Field(5, ge=0, le=1000)


@router.post("/festival-post", dependencies=[Depends(_GEN_LIMIT)])
async def studio_festival_post(req: FestivalReq = Body(default=FestivalReq()), client_id: str = Depends(require_customer)) -> dict:
    """Upcoming Indian festivals + ready captions for each (Diwali/Holi/Eid/Rakhi…)."""
    c = _ctx(client_id)
    try:
        from app.marketing import festivals

        out = await festivals.festival_posts(business_name=c["business_name"], niche=c["niche"], days=req.days)
    except Exception as e:
        _fail("Festival Posts", e)
    return {"ok": True, "tool": "festival-post", "result": out, "context": c}


@router.post("/poster", dependencies=[Depends(_GEN_LIMIT)])
async def studio_poster(req: PosterReq = Body(default=PosterReq()), client_id: str = Depends(require_customer)) -> dict:
    """1080x1080 SVG offer/festival poster with shop name + offer + phone (downloadable)."""
    c = _ctx(client_id)
    try:
        from app.marketing import posters

        out = posters.generate_poster(
            template_id=req.template, business_name=c["business_name"],
            tagline=req.tagline, offer=req.offer, phone=req.phone, festival=req.festival,
        )
        templates = [t["id"] for t in posters.list_templates()]
    except Exception as e:
        _fail("Poster", e)
    return {"ok": True, "tool": "poster", "result": out, "templates": templates, "context": c}


@router.post("/review-request", dependencies=[Depends(_GEN_LIMIT)])
def studio_review_request(client_id: str = Depends(require_customer)) -> dict:
    """Happy-customer review-ask pack: WhatsApp/SMS message + Google review link (no LLM)."""
    c = _ctx(client_id)
    try:
        from app.marketing import review_kit

        pack = review_kit.review_ask_pack(c["business_name"])
        place_q = c["business_name"] + (f" {c['city']}" if c["city"] else "")
        link = review_kit.review_link(place_q)
    except Exception as e:
        _fail("Review Request", e)
    return {"ok": True, "tool": "review-request", "result": {"pack": pack, "link": link}, "context": c}


@router.post("/followup-sequence", dependencies=[Depends(_GEN_LIMIT)])
async def studio_followup_sequence(req: FollowupReq = Body(default=FollowupReq()), client_id: str = Depends(require_customer)) -> dict:
    """4-step WhatsApp follow-up drip (Day 1/3/7…) for a lead type."""
    c = _ctx(client_id)
    try:
        from app.marketing import drip

        out = await drip.drip_sequence(business_name=c["business_name"], niche=c["niche"], lead_type=req.lead_type)
    except Exception as e:
        _fail("Follow-up Sequence", e)
    return {"ok": True, "tool": "followup-sequence", "result": out, "context": c}


@router.post("/speed-followup", dependencies=[Depends(_GEN_LIMIT)])
async def studio_speed_followup(client_id: str = Depends(require_customer)) -> dict:
    """Instant first-touch follow-up message to send a brand-new lead in <2 min."""
    c = _ctx(client_id)
    try:
        from app.marketing import drip

        seq = await drip.drip_sequence(business_name=c["business_name"], niche=c["niche"], lead_type="new_inquiry")
        steps = (seq or {}).get("steps") or []
        instant = steps[0] if steps else {"message": "Namaste! Aapki enquiry mili — main abhi aapse baat karta hoon. 🙏"}
    except Exception as e:
        _fail("Speed-to-Lead", e)
    return {"ok": True, "tool": "speed-followup", "result": {"instant": instant}, "context": c}


@router.post("/reel-script", dependencies=[Depends(_GEN_LIMIT)])
async def studio_reel_script(req: ReelReq = Body(default=ReelReq()), client_id: str = Depends(require_customer)) -> dict:
    """Instagram/Reels Hinglish scripts (hook/body/cta/caption/duration)."""
    c = _ctx(client_id)
    try:
        from app.marketing import reels

        out = await reels.reels_scripts(business_name=c["business_name"], niche=c["niche"], topic=req.topic, n=req.n)
    except Exception as e:
        _fail("Reel Script", e)
    return {"ok": True, "tool": "reel-script", "result": out, "context": c}


@router.post("/win-back", dependencies=[Depends(_GEN_LIMIT)])
async def studio_win_back(req: WinbackReq = Body(default=WinbackReq()), client_id: str = Depends(require_customer)) -> dict:
    """Win-back / reactivation messages for old customers (+ wa.me links)."""
    c = _ctx(client_id)
    try:
        from app.marketing import reactivation

        out = await reactivation.reactivation_campaign(
            business_name=c["business_name"], niche=c["niche"], customers=req.customers, offer=req.offer,
        )
    except Exception as e:
        _fail("Win-back", e)
    return {"ok": True, "tool": "win-back", "result": out, "context": c}


@router.post("/quote-draft", dependencies=[Depends(_GEN_LIMIT)])
async def studio_quote_draft(req: QuoteReq = Body(default=QuoteReq()), client_id: str = Depends(require_customer)) -> dict:
    """Personalized proposal / estimate draft with ROI (customer can send to a lead)."""
    c = _ctx(client_id)
    try:
        from app.marketing import proposal

        out = await proposal.generate_proposal(
            business_name=c["business_name"], niche=c["niche"], city=(req.city or c["city"]),
            plan=req.plan, missed_per_day=req.missed_per_day, avg_deal_value=req.avg_deal_value,
        )
    except Exception as e:
        _fail("Quote Draft", e)
    return {"ok": True, "tool": "quote-draft", "result": out, "context": c}


@router.get("/next-best-action")
def studio_next_best_action(client_id: str = Depends(require_customer)) -> dict:
    """"Aaj kya karna hai" — prioritized task list from the client's live signals.

    PURE LOGIC (no LLM): reads leads / pending approvals / GBP score / content
    queue and returns an ordered action list. Never-empty, never-raise.
    """
    c = _ctx(client_id)
    actions: list[dict] = []

    # 1) New uncalled leads -> highest priority (paisa yahin)
    try:
        from app.api.customer_dashboard_builders import _inquiries_for_client

        leads = _inquiries_for_client(client_id) or []
        n_leads = len(leads)
        if n_leads:
            actions.append({"priority": 1, "icon": "🔥", "action": f"{n_leads} naye lead ko abhi call/WhatsApp karo",
                            "why": "2 minute me follow-up karne se 5x zyada deal lagti hai.", "target": "leadsCard"})
    except Exception as e:
        logger.debug("nba leads failed: %s", e)

    # 2) Pending content approvals
    try:
        from app.marketing import content_approval

        pend = content_approval.pending(client_id) if hasattr(content_approval, "pending") else []
        if pend:
            actions.append({"priority": 2, "icon": "✅", "action": f"{len(pend)} post approve karo",
                            "why": "Approve karte hi system publish/schedule kar dega.", "target": "approvalCard"})
    except Exception as e:
        logger.debug("nba approvals failed: %s", e)

    # 3) GBP score — low or missing -> audit/fix
    try:
        import json as _json
        import os as _os

        from app.api.customer_dashboard_builders import _safe_cid

        fp = _os.path.join("data", "gbp_audits", _safe_cid(client_id) + ".json")
        score = None
        if _os.path.exists(fp):
            with open(fp, encoding="utf-8") as fh:
                score = (_json.load(fh) or {}).get("score")
        if score is None:
            actions.append({"priority": 3, "icon": "🏪", "action": "Google Business audit karo (2 min)",
                            "why": "Score pata chalega + top-5 fix milenge — Google par upar aane ke liye.", "target": "studioCard"})
        elif isinstance(score, (int, float)) and score < 70:
            actions.append({"priority": 2, "icon": "🏪", "action": f"GBP score {int(score)}/100 — fixes lagao",
                            "why": "70+ profile zyada calls + direction requests laata hai.", "target": "studioCard"})
    except Exception as e:
        logger.debug("nba gbp failed: %s", e)

    # 4) Content freshness
    try:
        from app.api.customer_dashboard_builders import _content_posts_count

        rec = _client_record(client_id) or {}
        rid = str(rec.get("id") or client_id)
        if _content_posts_count(rid) == 0:
            actions.append({"priority": 3, "icon": "📝", "action": "Aaj ka post banao + share karo",
                            "why": "Regular posting se reach + trust dono badhte hain.", "target": "studioCard"})
    except Exception as e:
        logger.debug("nba content failed: %s", e)

    # 5) Always-on growth nudge
    actions.append({"priority": 4, "icon": "⭐", "action": "Khush customers ko review request bhejo",
                    "why": "Naye reviews = ranking + naye customers ka trust.", "target": "studioCard"})

    actions.sort(key=lambda a: a.get("priority", 9))
    return {"ok": True, "tool": "next-best-action", "actions": actions, "count": len(actions), "context": c}


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
    {"key": "festival-post", "icon": "🪔", "title": "Festival Posts", "desc": "Diwali/Holi/Eid auto captions", "method": "POST", "path": "/api/customer/studio/festival-post", "fields": ["days"]},
    {"key": "poster", "icon": "🖼️", "title": "Offer Poster", "desc": "Shop naam + offer + phone poster", "method": "POST", "path": "/api/customer/studio/poster", "fields": ["offer", "phone", "tagline"]},
    {"key": "review-request", "icon": "🙏", "title": "Review Request", "desc": "Review maangne ka message + link", "method": "POST", "path": "/api/customer/studio/review-request", "fields": []},
    {"key": "followup-sequence", "icon": "🔁", "title": "Follow-up Sequence", "desc": "Day 1/3/7 WhatsApp drip", "method": "POST", "path": "/api/customer/studio/followup-sequence", "fields": ["lead_type"]},
    {"key": "speed-followup", "icon": "⚡", "title": "Speed-to-Lead Reply", "desc": "Naye lead ka instant message", "method": "POST", "path": "/api/customer/studio/speed-followup", "fields": []},
    {"key": "reel-script", "icon": "🎬", "title": "Reel Script", "desc": "Instagram reel ka 15-30s script", "method": "POST", "path": "/api/customer/studio/reel-script", "fields": ["topic", "n"]},
    {"key": "win-back", "icon": "💌", "title": "Win-back Campaign", "desc": "Purane customers ko offer", "method": "POST", "path": "/api/customer/studio/win-back", "fields": ["offer"]},
    {"key": "quote-draft", "icon": "🧾", "title": "Quote / Estimate", "desc": "Inquiry se price quote draft", "method": "POST", "path": "/api/customer/studio/quote-draft", "fields": ["avg_deal_value"]},
    {"key": "next-best-action", "icon": "🎯", "title": "Next Best Action", "desc": "Aaj kya karna hai — task list", "method": "GET", "path": "/api/customer/studio/next-best-action", "fields": []},
]


@router.get("/tools")
def studio_tools(client_id: str = Depends(require_customer)) -> dict:
    """List of available studio tools + this client's resolved context."""
    return {"ok": True, "count": len(_TOOLS), "tools": _TOOLS, "context": _ctx(client_id)}
