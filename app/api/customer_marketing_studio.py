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
_GEN_LIMIT = rate_limit("cust_studio", 60, 60)  # 60 generations / minute / IP (free-stack, but bounded)


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
# Batch 3 — toward 40 (competitor, FAQ-reply, carousel, bio-page, lead-magnet, #
# negative-review-rescue + pure-logic reminders/budget/appointment).          #
# --------------------------------------------------------------------------- #
class CompetitorReq(BaseModel):
    competitor_notes: str = Field("", max_length=1500, description="Competitor ke baare me notes")


class FaqReplyReq(BaseModel):
    question: str = Field(..., min_length=1, max_length=600)


class CarouselReq(BaseModel):
    topic: str = Field("", max_length=120)
    slides: int = Field(4, ge=3, le=5)


class LeadMagnetReq(BaseModel):
    city: str = Field("", max_length=80)


class NegReviewReq(BaseModel):
    review_text: str = Field(..., min_length=1, max_length=2000)
    rating: float | None = Field(1, ge=0, le=5)


class BudgetReq(BaseModel):
    avg_deal_value: float = Field(20000, ge=0, le=100000000)
    target_leads: int = Field(10, ge=1, le=1000, description="Mahine me chahiye leads")


class ReminderReq(BaseModel):
    kind: str = Field("appointment", max_length=30, description="appointment|renewal|service|payment")


@router.post("/competitor", dependencies=[Depends(_GEN_LIMIT)])
async def studio_competitor(req: CompetitorReq = Body(default=CompetitorReq()), client_id: str = Depends(require_customer)) -> dict:
    """Competitor notes → strengths to copy + gaps to exploit + action plan."""
    c = _ctx(client_id)
    try:
        from app.marketing import competitor

        out = await competitor.compare_tips(business_name=c["business_name"], niche=c["niche"], competitor_notes=req.competitor_notes)
    except Exception as e:
        _fail("Competitor", e)
    return {"ok": True, "tool": "competitor", "result": out, "context": c}


@router.post("/faq-reply", dependencies=[Depends(_GEN_LIMIT)])
async def studio_faq_reply(req: FaqReplyReq, client_id: str = Depends(require_customer)) -> dict:
    """FAQ / WhatsApp reply assistant — customer ke sawaal ka KB-grounded answer."""
    c = _ctx(client_id)
    try:
        from app.marketing import chatbot

        rec = _client_record(client_id) or {}
        cid = str(rec.get("id") or client_id)
        out = await chatbot.reply(question=req.question, client_id=cid, niche=c["niche"])
    except Exception as e:
        _fail("FAQ Reply", e)
    return {"ok": True, "tool": "faq-reply", "result": out, "context": c}


@router.post("/carousel", dependencies=[Depends(_GEN_LIMIT)])
async def studio_carousel(req: CarouselReq = Body(default=CarouselReq()), client_id: str = Depends(require_customer)) -> dict:
    """Instagram/LinkedIn carousel — slide texts + per-slide SVG."""
    c = _ctx(client_id)
    try:
        from app.marketing import carousel

        out = await carousel.generate_carousel(business_name=c["business_name"], niche=c["niche"], topic=req.topic, slides=req.slides)
    except Exception as e:
        _fail("Carousel", e)
    return {"ok": True, "tool": "carousel", "result": out, "context": c}


@router.post("/bio-page", dependencies=[Depends(_GEN_LIMIT)])
async def studio_bio_page(client_id: str = Depends(require_customer)) -> dict:
    """Social bio / landing copy kit — Insta/FB/Google bios + page setup."""
    c = _ctx(client_id)
    try:
        from app.marketing import social_page_kit

        out = await social_page_kit.build_page_kit(business_name=c["business_name"], niche=c["niche"], city=c["city"])
    except Exception as e:
        _fail("Bio Page", e)
    return {"ok": True, "tool": "bio-page", "result": out, "context": c}


@router.post("/lead-magnet", dependencies=[Depends(_GEN_LIMIT)])
async def studio_lead_magnet(req: LeadMagnetReq = Body(default=LeadMagnetReq()), client_id: str = Depends(require_customer)) -> dict:
    """Free lead-magnet guide (checklist/tips PDF) to capture leads."""
    c = _ctx(client_id)
    try:
        from app.marketing import lead_magnet

        rec = _client_record(client_id) or {}
        out = await lead_magnet.generate(niche=c["niche"], city=(req.city or c["city"]), business_name=c["business_name"], slug=str(rec.get("slug") or ""))
    except Exception as e:
        _fail("Lead Magnet", e)
    return {"ok": True, "tool": "lead-magnet", "result": out, "context": c}


@router.post("/negative-review-rescue", dependencies=[Depends(_GEN_LIMIT)])
async def studio_negative_review_rescue(req: NegReviewReq, client_id: str = Depends(require_customer)) -> dict:
    """Bad review ke liye polite damage-control replies (empathetic tone)."""
    c = _ctx(client_id)
    try:
        from app.marketing import review_replies

        out = await review_replies.generate_replies(
            review_text=req.review_text, rating=req.rating, business_name=c["business_name"], tone="empathetic",
        )
    except Exception as e:
        _fail("Negative Review Rescue", e)
    return {"ok": True, "tool": "negative-review-rescue", "result": out, "context": c}


@router.get("/photo-reminder")
def studio_photo_reminder(client_id: str = Depends(require_customer)) -> dict:
    """Weekly GBP/social photo upload ideas + reminder (PURE LOGIC, no LLM)."""
    c = _ctx(client_id)
    niche = c["niche"]
    ideas = [
        "Aaj ka kaam / finished work ki 2-3 photo",
        "Team / aap khud kaam karte hue (trust banta hai)",
        "Shop / setup ka clean front photo",
        "Happy customer (permission se) ya unka result",
        "Before/After — sabse zyada engagement",
        f"{niche.title()} ka koi tip ya behind-the-scenes",
    ]
    return {"ok": True, "tool": "photo-reminder",
            "message": "Google par har hafte 1-2 nayi photo daalo — listing active dikhti hai + zyada calls aati hain.",
            "ideas": ideas, "context": c}


@router.post("/budget-suggest")
def studio_budget_suggest(req: BudgetReq = Body(default=BudgetReq()), client_id: str = Depends(require_customer)) -> dict:
    """Daily ad budget suggestion (PURE LOGIC) from deal value + lead goal."""
    c = _ctx(client_id)
    # Conservative small-business assumptions: ~₹40 CPL, 12% lead->deal close.
    cpl = 40.0
    leads_needed = max(1, req.target_leads)
    monthly = cpl * leads_needed
    daily = round(monthly / 30.0, 0)
    deals = max(1, int(round(leads_needed * 0.12)))
    revenue = deals * req.avg_deal_value
    return {"ok": True, "tool": "budget-suggest", "context": c,
            "result": {
                "suggested_daily_inr": daily,
                "suggested_monthly_inr": round(monthly, 0),
                "assumed_cost_per_lead_inr": cpl,
                "expected_leads": leads_needed,
                "expected_deals": deals,
                "expected_revenue_inr": revenue,
                "note": "Chhote business ke liye safe start. 1-2 hafte baad results dekh ke badhao/ghatao.",
            }}


@router.post("/customer-reminder")
def studio_customer_reminder(req: ReminderReq = Body(default=ReminderReq()), client_id: str = Depends(require_customer)) -> dict:
    """Appointment / renewal / service / payment reminder message templates (PURE LOGIC)."""
    c = _ctx(client_id)
    biz = c["business_name"]
    kind = (req.kind or "appointment").strip().lower()
    templates = {
        "appointment": [
            f"Namaste 🙏 {biz} se reminder — aapka appointment kal hai. Time confirm hai? Reply 'YES' ya naya time batayein.",
            f"Reminder: kal aapka slot {biz} me booked hai. Milte hain! Koi badlav ho to bata dein.",
        ],
        "renewal": [
            f"Namaste! {biz} — aapki service/plan jald renew hone wali hai. Aaj renew karein, bina rukawat seva jaari rahe 🙏",
            f"Reminder: renewal due hai. 1-click renew link bhej dun? Reply 'HAAN'.",
        ],
        "service": [
            f"{biz}: aapki next service/maintenance due hai. Slot book kar lein taaki sab sahi chale 👍",
            f"Reminder — last service ko time ho gaya. Aaj book karein, baad me rush se bachein.",
        ],
        "payment": [
            f"Namaste 🙏 {biz} — aapka payment pending hai. UPI/link se aaj clear kar dein to badi madad hogi. Dhanyawad!",
            f"Gentle reminder: invoice pending hai. Koi dikkat ho to bata dein, hum help karenge.",
        ],
    }
    msgs = templates.get(kind, templates["appointment"])
    return {"ok": True, "tool": "customer-reminder", "kind": kind, "messages": msgs, "context": c}


@router.post("/appointment-assistant")
def studio_appointment_assistant(client_id: str = Depends(require_customer)) -> dict:
    """Slot-suggestion + booking-confirmation message templates (PURE LOGIC)."""
    c = _ctx(client_id)
    biz = c["business_name"]
    return {"ok": True, "tool": "appointment-assistant", "context": c,
            "result": {
                "slot_offer": [
                    f"Namaste 🙏 {biz} — aapke liye 2 slot free hain: aaj 4 PM ya kal 11 AM. Kaunsa theek hai?",
                    f"Booking ke liye bas time bata dein — main {biz} me aapka slot pakka kar deta hoon 👍",
                ],
                "confirmation": [
                    f"Confirmed! ✅ Aapka appointment {biz} me book ho gaya. Time pe milte hain. Address/location bhej dun?",
                    f"Ho gaya booking! Reminder ek din pehle bhej dunga. Dhanyawad 🙏",
                ],
                "no_show_followup": [
                    f"Aaj aap aa nahi paaye — koi baat nahi! {biz} me naya slot rakh dun? Bas time bata dein.",
                ],
            }}


# --------------------------------------------------------------------------- #
# Batch 4 — Growth-OS (#41-100): planner/templates/blog/audit/testimonial/     #
# repurpose/referral + pure-logic ROI/objection/best-time/brief/coach.         #
# --------------------------------------------------------------------------- #
class MonthPlanReq(BaseModel):
    offer: str = Field("", max_length=160)
    channel: str = Field("instagram", max_length=30)


class TemplatesReq(BaseModel):
    occasion: str = Field("", max_length=60)


class BlogReq(BaseModel):
    topic: str = Field("", max_length=160)
    city: str = Field("", max_length=80)


class AuditReq(BaseModel):
    url: str = Field(..., min_length=4, max_length=500)


class TestimonialReq(BaseModel):
    review_text: str = Field(..., min_length=1, max_length=2000)
    author: str = Field("", max_length=80)
    rating: int = Field(5, ge=1, le=5)


class RepurposeReq(BaseModel):
    topic_or_url: str = Field(..., min_length=1, max_length=500)


class ReferralReq(BaseModel):
    reward: str = Field("10% off", max_length=80)


class RoiReq(BaseModel):
    monthly_spend: float = Field(5000, ge=0, le=100000000)
    avg_deal_value: float = Field(20000, ge=0, le=100000000)
    leads_per_month: int = Field(20, ge=0, le=100000)
    close_rate_pct: float = Field(12, ge=0, le=100)


class ObjectionReq(BaseModel):
    objection: str = Field("", max_length=300, description="Customer ka objection (khali = common list)")


@router.post("/month-planner", dependencies=[Depends(_GEN_LIMIT)])
def studio_month_planner(req: MonthPlanReq = Body(default=MonthPlanReq()), client_id: str = Depends(require_customer)) -> dict:
    """30-din ka content/campaign plan (themes + festival hooks per day)."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    try:
        from app.marketing import month_planner

        out = month_planner.plan_month(
            niche=c["niche"], client_id=str(rec.get("id") or client_id), slug=str(rec.get("slug") or ""),
            business_name=c["business_name"], offer=req.offer, channel=req.channel, dry_run=True, commit=False,
        )
    except Exception as e:
        _fail("Month Planner", e)
    return {"ok": True, "tool": "month-planner", "result": out, "context": c}


@router.post("/templates", dependencies=[Depends(_GEN_LIMIT)])
def studio_templates(req: TemplatesReq = Body(default=TemplatesReq()), client_id: str = Depends(require_customer)) -> dict:
    """Niche template library — ready post/poster ideas for the client's niche."""
    c = _ctx(client_id)
    try:
        from app.marketing import template_library

        out = template_library.list_templates(niche=c["niche"], occasion=req.occasion, limit=40)
    except Exception as e:
        _fail("Templates", e)
    return {"ok": True, "tool": "templates", "result": out, "context": c}


@router.post("/blog", dependencies=[Depends(_GEN_LIMIT)])
async def studio_blog(req: BlogReq = Body(default=BlogReq()), client_id: str = Depends(require_customer)) -> dict:
    """Local-SEO blog article (title + HTML body) for the client's niche/city."""
    c = _ctx(client_id)
    try:
        from app.marketing import seo_blog

        out = await seo_blog.generate_article(niche=c["niche"], city=(req.city or c["city"]), topic=(req.topic or None))
    except Exception as e:
        _fail("Blog", e)
    return {"ok": True, "tool": "blog", "result": out, "context": c}


@router.post("/landing-audit", dependencies=[Depends(_GEN_LIMIT)])
async def studio_landing_audit(req: AuditReq, client_id: str = Depends(require_customer)) -> dict:
    """Website/landing audit — CTA, mobile, speed, trust signals (SSRF-guarded)."""
    c = _ctx(client_id)
    try:
        from app.marketing import website_auditor

        out = await website_auditor.audit_url(req.url)
    except Exception as e:
        _fail("Landing Audit", e)
    return {"ok": True, "tool": "landing-audit", "result": out, "context": c}


@router.post("/testimonial", dependencies=[Depends(_GEN_LIMIT)])
async def studio_testimonial(req: TestimonialReq, client_id: str = Depends(require_customer)) -> dict:
    """Good review → branded thank-you poster (SVG) + social caption."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    try:
        from app.marketing import review_to_post

        out = await review_to_post.from_review(review_text=req.review_text, author=req.author, rating=req.rating, slug=str(rec.get("slug") or ""))
    except Exception as e:
        _fail("Testimonial", e)
    return {"ok": True, "tool": "testimonial", "result": out, "context": c}


@router.post("/repurpose", dependencies=[Depends(_GEN_LIMIT)])
async def studio_repurpose(req: RepurposeReq, client_id: str = Depends(require_customer)) -> dict:
    """1 topic/URL → 7 formats (post, WA, email, reel, etc.)."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    try:
        from app.marketing import repurpose

        out = await repurpose.repurpose(topic_or_url=req.topic_or_url, niche=c["niche"], slug=str(rec.get("slug") or ""), business_name=c["business_name"])
    except Exception as e:
        _fail("Repurpose", e)
    return {"ok": True, "tool": "repurpose", "result": out, "context": c}


@router.post("/referral", dependencies=[Depends(_GEN_LIMIT)])
def studio_referral(req: ReferralReq = Body(default=ReferralReq()), client_id: str = Depends(require_customer)) -> dict:
    """Referral kit — code + WhatsApp message + link + 1080 card SVG."""
    c = _ctx(client_id)
    try:
        from app.marketing import referral_kit

        out = referral_kit.make_referral(business_name=c["business_name"], reward=req.reward)
    except Exception as e:
        _fail("Referral", e)
    return {"ok": True, "tool": "referral", "result": out, "context": c}


@router.post("/roi-calculator")
def studio_roi_calculator(req: RoiReq = Body(default=RoiReq()), client_id: str = Depends(require_customer)) -> dict:
    """Marketing ROI estimate (PURE MATH) — spend vs expected revenue."""
    c = _ctx(client_id)
    deals = req.leads_per_month * (req.close_rate_pct / 100.0)
    revenue = deals * req.avg_deal_value
    roi_pct = ((revenue - req.monthly_spend) / req.monthly_spend * 100.0) if req.monthly_spend > 0 else None
    cpl = (req.monthly_spend / req.leads_per_month) if req.leads_per_month > 0 else None
    return {"ok": True, "tool": "roi-calculator", "context": c,
            "result": {
                "monthly_spend_inr": round(req.monthly_spend, 0),
                "expected_deals": round(deals, 1),
                "expected_revenue_inr": round(revenue, 0),
                "roi_pct": round(roi_pct, 0) if roi_pct is not None else None,
                "cost_per_lead_inr": round(cpl, 0) if cpl is not None else None,
                "verdict": ("Profit me ho 👍" if roi_pct and roi_pct > 0 else "Spend/close-rate improve karo"),
            }}


@router.post("/objection-handler")
def studio_objection_handler(req: ObjectionReq = Body(default=ObjectionReq()), client_id: str = Depends(require_customer)) -> dict:
    """Common sales objections ke best Hinglish replies (PURE LOGIC library)."""
    c = _ctx(client_id)
    biz = c["business_name"]
    lib = {
        "mehenga": f"Samajh sakta hoon. {biz} me daam thoda zyada isliye hai kyunki quality + warranty + service guaranteed milti hai — sasta lekar baar-baar kharcha zyada padta hai. Aaj ek baar try karke dekhiye.",
        "time": "Bilkul, jaldi nahi. Main aapko detail WhatsApp kar deta hoon, aaram se dekh lijiye — koi sawaal ho to main yahin hoon.",
        "sochenge": "Zaroor sochiye! Bas itna — abhi book karne pe {} milega. Main aapke liye 24 ghante hold kar deta hoon.".format("special rate"),
        "competitor": f"Achhi baat hai aap compare kar rahe ho. {biz} ka farak hai — service + bharosa + after-support. Ek demo le lijiye, khud farak dikhega.",
        "discount": "Aapke liye ek best price nikaalta hoon — par quality compromise nahi. Chhota loyalty discount de sakta hoon, deal pakki karein?",
    }
    obj = (req.objection or "").lower()
    matched = None
    for key, ans in lib.items():
        if key in obj:
            matched = {"objection": req.objection, "reply": ans}
            break
    return {"ok": True, "tool": "objection-handler", "context": c,
            "matched": matched, "library": [{"objection": k, "reply": v} for k, v in lib.items()]}


@router.get("/best-time")
def studio_best_time(client_id: str = Depends(require_customer)) -> dict:
    """Best time to post/message/call (PURE LOGIC, India SMB norms)."""
    c = _ctx(client_id)
    return {"ok": True, "tool": "best-time", "context": c,
            "result": {
                "whatsapp": "Subah 9-11 AM ya shaam 6-8 PM (lunch/dinner se pehle).",
                "instagram_post": "Shaam 7-9 PM (peak scroll time).",
                "instagram_reel": "1-3 PM lunch ya 8-10 PM raat.",
                "phone_call": "11 AM-1 PM ya 4-6 PM (subah-subah/late evening avoid).",
                "new_lead_followup": "Lead aate hi 2-5 min ke andar — sabse zyada conversion.",
                "tip": "Calling-window TRAI 9 AM-7 PM ke andar rakho.",
            }}


@router.get("/owner-brief")
def studio_owner_brief(client_id: str = Depends(require_customer)) -> dict:
    """Daily owner brief (PURE LOGIC) — aaj ke leads/approvals/posts ek nazar me."""
    c = _ctx(client_id)
    leads_n = approvals_n = 0
    try:
        from app.api.customer_dashboard_builders import _inquiries_for_client

        leads_n = len(_inquiries_for_client(client_id) or [])
    except Exception:
        pass
    try:
        from app.marketing import content_approval

        approvals_n = len(content_approval.pending(client_id) or []) if hasattr(content_approval, "pending") else 0
    except Exception:
        pass
    brief = [
        f"🔥 {leads_n} naye lead — inko aaj call/WhatsApp karo." if leads_n else "🔥 Abhi koi naya lead nahi — outreach/post badhao.",
        f"✅ {approvals_n} post approval pending." if approvals_n else "✅ Koi approval pending nahi.",
        "📝 Aaj ka post + 1 Google photo daalo.",
        "⭐ 1 khush customer se review maango.",
    ]
    return {"ok": True, "tool": "owner-brief", "context": c, "leads": leads_n, "approvals": approvals_n, "brief": brief}


@router.get("/growth-coach")
def studio_growth_coach(client_id: str = Depends(require_customer)) -> dict:
    """Weekly AI growth coach — agle 7 din ke 3 high-impact actions (PURE LOGIC)."""
    c = _ctx(client_id)
    niche = c["niche"]
    actions = [
        {"action": "Roz 1 post + 1 Google photo (7 din)", "why": "Consistency se reach + trust dono badhte hain."},
        {"action": "5 khush customers se Google review maango", "why": "Reviews = ranking + naye customers ka bharosa."},
        {"action": f"{niche.title()} ka 1 offer banao + WhatsApp status + GBP post", "why": "Ek offer multi-channel pe = zyada leads."},
    ]
    return {"ok": True, "tool": "growth-coach", "context": c, "week_focus": "Visibility + Reviews + 1 Offer", "actions": actions}


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
    {"key": "competitor", "icon": "🔍", "title": "Competitor Tracker", "desc": "Strengths copy + gaps exploit", "method": "POST", "path": "/api/customer/studio/competitor", "fields": ["competitor_notes"]},
    {"key": "faq-reply", "icon": "🤖", "title": "FAQ / Reply Assistant", "desc": "Customer sawaal ka smart answer", "method": "POST", "path": "/api/customer/studio/faq-reply", "fields": ["question"]},
    {"key": "carousel", "icon": "🎠", "title": "Carousel Maker", "desc": "Insta carousel slides + SVG", "method": "POST", "path": "/api/customer/studio/carousel", "fields": ["topic", "slides"]},
    {"key": "bio-page", "icon": "🔗", "title": "Bio / Landing Copy", "desc": "Insta/FB/Google bios + page", "method": "POST", "path": "/api/customer/studio/bio-page", "fields": []},
    {"key": "lead-magnet", "icon": "🧲", "title": "Lead Magnet", "desc": "Free guide/checklist for leads", "method": "POST", "path": "/api/customer/studio/lead-magnet", "fields": ["city"]},
    {"key": "negative-review-rescue", "icon": "🛟", "title": "Bad Review Rescue", "desc": "Polite damage-control reply", "method": "POST", "path": "/api/customer/studio/negative-review-rescue", "fields": ["review_text", "rating"]},
    {"key": "photo-reminder", "icon": "📸", "title": "Photo Reminder", "desc": "Weekly GBP photo ideas", "method": "GET", "path": "/api/customer/studio/photo-reminder", "fields": []},
    {"key": "budget-suggest", "icon": "💰", "title": "Ad Budget Suggest", "desc": "Daily ad budget plan", "method": "POST", "path": "/api/customer/studio/budget-suggest", "fields": ["avg_deal_value", "target_leads"]},
    {"key": "customer-reminder", "icon": "⏰", "title": "Customer Reminder", "desc": "Appointment/renewal/payment msg", "method": "POST", "path": "/api/customer/studio/customer-reminder", "fields": ["kind"]},
    {"key": "appointment-assistant", "icon": "📅", "title": "Appointment Assistant", "desc": "Slot + booking confirmation msg", "method": "POST", "path": "/api/customer/studio/appointment-assistant", "fields": []},
    {"key": "month-planner", "icon": "📆", "title": "Monthly Campaign Plan", "desc": "30-din ka theme + festival plan", "method": "POST", "path": "/api/customer/studio/month-planner", "fields": ["offer", "channel"]},
    {"key": "templates", "icon": "🗂️", "title": "Template Library", "desc": "Niche ke ready post/poster ideas", "method": "POST", "path": "/api/customer/studio/templates", "fields": ["occasion"]},
    {"key": "blog", "icon": "✍️", "title": "Blog Writer", "desc": "Local-SEO blog article", "method": "POST", "path": "/api/customer/studio/blog", "fields": ["topic", "city"]},
    {"key": "landing-audit", "icon": "🔎", "title": "Website Audit", "desc": "CTA/mobile/speed/trust score", "method": "POST", "path": "/api/customer/studio/landing-audit", "fields": ["url"]},
    {"key": "testimonial", "icon": "💬", "title": "Testimonial Poster", "desc": "Review → branded poster + caption", "method": "POST", "path": "/api/customer/studio/testimonial", "fields": ["review_text", "author", "rating"]},
    {"key": "repurpose", "icon": "♻️", "title": "Content Repurpose", "desc": "1 topic → 7 formats", "method": "POST", "path": "/api/customer/studio/repurpose", "fields": ["topic_or_url"]},
    {"key": "referral", "icon": "🎁", "title": "Referral Kit", "desc": "Code + message + card", "method": "POST", "path": "/api/customer/studio/referral", "fields": ["reward"]},
    {"key": "roi-calculator", "icon": "📊", "title": "ROI Calculator", "desc": "Spend vs revenue estimate", "method": "POST", "path": "/api/customer/studio/roi-calculator", "fields": ["monthly_spend", "avg_deal_value", "leads_per_month"]},
    {"key": "objection-handler", "icon": "🛡️", "title": "Objection Handler", "desc": "'Mehenga hai' ka best reply", "method": "POST", "path": "/api/customer/studio/objection-handler", "fields": ["objection"]},
    {"key": "best-time", "icon": "🕐", "title": "Best Time to Post", "desc": "Kab post/call/message karein", "method": "GET", "path": "/api/customer/studio/best-time", "fields": []},
    {"key": "owner-brief", "icon": "📋", "title": "Daily Owner Brief", "desc": "Aaj ka summary ek nazar", "method": "GET", "path": "/api/customer/studio/owner-brief", "fields": []},
    {"key": "growth-coach", "icon": "🚀", "title": "AI Growth Coach", "desc": "Hafte ke 3 high-impact actions", "method": "GET", "path": "/api/customer/studio/growth-coach", "fields": []},
]


@router.get("/tools")
def studio_tools(client_id: str = Depends(require_customer)) -> dict:
    """List of available studio tools + this client's resolved context."""
    return {"ok": True, "count": len(_TOOLS), "tools": _TOOLS, "context": _ctx(client_id)}
