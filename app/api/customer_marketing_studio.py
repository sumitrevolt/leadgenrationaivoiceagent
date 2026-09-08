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
_GEN_LIMIT = rate_limit(
    "cust_studio", 60, 60
)  # 60 generations / minute / IP (free-stack, but bounded)


# --------------------------------------------------------------------------- #
# Client context — niche/business/city ALWAYS from the authed client's record  #
# --------------------------------------------------------------------------- #
def _entitlement_gate(client_id: str, rec: dict) -> None:
    """STUDIO_ENTITLEMENT_GATE=1 (default OFF = zero behavior change): block
    (a) expired free trials and (b) paid-plan signups that never actually paid,
    after a 7-day grace (signup provisions the plan pre-payment — audit
    2026-07-04 P2: without this, a free signup keeps generating forever).
    Payment proof = an ACTIVE/TRIAL/PAUSED Subscription row (UPI/Stripe
    activation creates one). Every lookup failure = ALLOW (fail-open — a DB
    hiccup must never lock a paying customer out of their studio)."""
    import os as _os

    if (_os.environ.get("STUDIO_ENTITLEMENT_GATE", "0") or "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    if not rec:
        return
    from datetime import datetime, timedelta

    def _parse(ts: str):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "").split("+")[0])
        except Exception:
            return None

    pay_cta = "Plan active nahi hai — /pricing se payment karke unlock karo."
    # (a) Trial path: expired trial => 402.
    if rec.get("trial") or str(rec.get("plan") or "").strip().lower() == "trial":
        exp = _parse(rec.get("trial_expires") or "")
        if exp is not None and exp < datetime.utcnow():
            raise HTTPException(status_code=402, detail=f"FREE trial khatam. {pay_cta}")
        return
    # (b) Paid-plan record: allow if a real subscription exists; else 7-day grace.
    try:
        from app.billing.usage import _latest_subscription
        from app.models.base import get_db_session
        from app.models.payment import SubscriptionStatus

        with get_db_session() as db:
            sub = _latest_subscription(db, client_id)
            if sub is not None and sub.status in (
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.PAUSED,
            ):
                return
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("entitlement gate sub-lookup skipped (fail-open): %s", e)
        return
    created = _parse(rec.get("created_at") or "")
    if created is None:
        return  # unknown age — fail-open
    if datetime.utcnow() - created > timedelta(days=7):
        raise HTTPException(status_code=402, detail=pay_cta)


def _ctx(client_id: str) -> dict:
    rec = _client_record(client_id) or {}
    _entitlement_gate(client_id, rec)
    _brand = rec.get("brand") if isinstance(rec.get("brand"), dict) else {}
    return {
        "business_name": str(
            rec.get("business_name") or rec.get("name") or "Aapka Business"
        ).strip(),
        "niche": str(rec.get("niche") or "general").strip().lower() or "general",
        "city": str(rec.get("city") or rec.get("location") or "").strip(),
        "website": str(rec.get("website") or "").strip(),
        # Client-scoped branding/CTA (carousel/referral etc. — customer output me
        # LeadGen ka apna CTA/default-violet nahi, CLIENT ki mini-site/brand jaani chahiye).
        "slug": str(rec.get("slug") or "").strip(),
        "phone": str(rec.get("phone") or "").strip(),
        "brand_primary": str(_brand.get("primary") or "").strip(),
        "brand_accent": str(_brand.get("accent") or "").strip(),
        "has_record": bool(rec),
    }


def _client_inquiries(client_id: str) -> list[dict]:
    """This client's own inquiries (IDOR-safe; _inquiries_for_client needs the record)."""
    try:
        from app.api.customer_dashboard_builders import _inquiries_for_client

        return _inquiries_for_client(client_id, _client_record(client_id)) or []
    except Exception as e:
        logger.debug("_client_inquiries failed: %s", e)
        return []


def _inq_age_hours(rec: dict) -> float:
    """Inquiry age in hours (best-effort; large number if unknown)."""
    try:
        from datetime import datetime

        from app.api.customer_dashboard_builders import _parse_dt

        dt = _parse_dt(str(rec.get("at") or rec.get("created_at") or ""))
        if not dt:
            return 9e9
        return max(0.0, (datetime.now() - dt.replace(tzinfo=None)).total_seconds() / 3600.0)
    except Exception:
        return 9e9


_INTENT_RULES = [
    (
        "complaint",
        [
            "complaint",
            "problem",
            "kharab",
            "galat",
            "refund",
            "worst",
            "bekaar",
            "late",
            "ganda",
            "naraz",
        ],
    ),
    ("price", ["price", "rate", "kitna", "kitne", "cost", "charge", "daam", "quotation", "quote"]),
    (
        "booking",
        ["book", "appointment", "slot", "timing", "kab", "available", "chahiye", "order", "visit"],
    ),
    (
        "spam",
        [
            "loan",
            "crypto",
            "seo expert",
            "earn money",
            "investment",
            "http://",
            "https://",
            "bitcoin",
        ],
    ),
]


def _classify_intent(msg: str) -> str:
    m = (msg or "").lower()
    for label, words in _INTENT_RULES:
        if any(w in m for w in words):
            return label
    return "general"


_INTENT_ACTION = {
    "price": "Rate clear bhejo + ek chhota offer add karo.",
    "booking": "Slot offer karo aur jaldi confirm karo.",
    "complaint": "Turant sorry + solution do — escalate karo.",
    "spam": "Skip — ye genuine lead nahi lagta.",
    "general": "Friendly reply do + unki zaroorat poocho.",
}


def _wa_link(phone: str) -> str:
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
    return f"https://wa.me/91{d}" if len(d) == 10 else ""


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


class VariationsReq(BaseModel):
    count: int = Field(3, ge=2, le=4)
    occasion: str = Field("", max_length=120)
    offer: str = Field("", max_length=120)


class ReviewKitReq(BaseModel):
    google_link: str = Field("", max_length=300)


class CatalogReq(BaseModel):
    items: str = Field("", max_length=2000)  # "Name:Price" comma-separated
    vpa: str = Field("", max_length=80)  # customer's OWN UPI id for per-item pay-links


class MiniSiteReq(BaseModel):
    palette: str = Field("", max_length=40)
    primary: str = Field("", max_length=9)
    accent: str = Field("", max_length=9)
    logo_url: str = Field("", max_length=500)
    tagline: str = Field("", max_length=160)


# --------------------------------------------------------------------------- #
# Generators (each wraps an existing app.marketing.* function)                 #
# --------------------------------------------------------------------------- #
def _fail(name: str, exc: Exception):
    logger.error("studio.%s failed: %s", name, exc)
    raise HTTPException(
        status_code=503, detail=f"{name} abhi available nahi — thodi der baad try karo."
    )


@router.post("/variations", dependencies=[Depends(_GEN_LIMIT)])
async def studio_variations(
    req: VariationsReq = Body(default=VariationsReq()), client_id: str = Depends(require_customer)
) -> dict:
    """A/B post variations (2-4 alag versions) — jo chale wo chuno. (Pehle admin-only tha.)"""
    import asyncio

    c = _ctx(client_id)
    posts: list = []
    try:
        from app.marketing import post_generator

        n = max(2, min(int(req.count or 3), 4))
        posts = list(
            await asyncio.gather(
                *[
                    post_generator.generate_post(
                        business_name=c["business_name"],
                        niche=c["niche"],
                        occasion=req.occasion,
                        offer=req.offer,
                    )
                    for _ in range(n)
                ]
            )
        )
    except Exception as e:
        _fail("Post Variations", e)
    return {
        "ok": True,
        "tool": "variations",
        "count": len(posts),
        "variations": posts,
        "context": c,
    }


@router.post("/review-kit", dependencies=[Depends(_GEN_LIMIT)])
async def studio_review_kit(
    req: ReviewKitReq = Body(default=ReviewKitReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Review kit — khush customer ko Google-review request, naraz ko private feedback
    (1-star public se bachao). Copy-paste WhatsApp messages, branded. Template-based, never fails.
    """
    c = _ctx(client_id)
    biz = c.get("business_name") or "Hum"
    glink = (req.google_link or "").strip()
    review_cta = (
        f"👉 1 min me Google review: {glink}"
        if glink
        else "👉 Google pe humein search karke ⭐ review dein"
    )
    happy = (
        f"Namaste! 🙏 {biz} ko choose karne ke liye shukriya. Aapko humari service pasand "
        f"aayi ho to ek chhota favour — {review_cta}\nAapka 30-second review humare liye "
        "bohot maayne rakhta hai. 💛"
    )
    unhappy = (
        f"Namaste 🙏 {biz} se aapka experience perfect nahi raha — humein khed hai. Kya hua, "
        "seedha humein batayein (yeh PRIVATE hai, public nahi) — hum turant theek karenge. "
        "Aapki baat humare liye sabse zaroori hai."
    )
    return {
        "ok": True,
        "tool": "review-kit",
        "result": {
            "happy_message": happy,
            "unhappy_message": unhappy,
            "tip": "Khush customer → 'happy' bhejo (Google review milega). Naraz → 'unhappy' "
            "(private feedback; 1-star public review se bachao).",
        },
        "context": c,
    }


@router.post("/catalog", dependencies=[Depends(_GEN_LIMIT)])
async def studio_catalog(
    req: CatalogReq = Body(default=CatalogReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Service/product catalog (rate-list) + per-item UPI pay-link. Customer ka customer
    seedha UPI pe pay kare — koi gateway nahi (UPI deep-link universal). Template-based."""
    import urllib.parse as _u

    c = _ctx(client_id)
    biz = c.get("business_name") or "Business"
    vpa = (req.vpa or "").strip()
    items: list[dict] = []
    for raw in (req.items or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        name, price = raw, ""
        if ":" in raw:
            name, price = raw.split(":", 1)
        name = name.strip()
        price = "".join(ch for ch in price if ch.isdigit())
        pay = ""
        if vpa and price:
            pay = "upi://pay?" + _u.urlencode({"pa": vpa, "pn": biz, "am": price, "cu": "INR"})
        items.append({"name": name, "price": price, "pay_link": pay})
    lines = [f"*{biz} — Rate List* 📋", ""]
    for it in items:
        p = f" — ₹{it['price']}" if it["price"] else ""
        lines.append(
            f"• {it['name']}{p}" + (f"\n  💳 Pay: {it['pay_link']}" if it["pay_link"] else "")
        )
    if not vpa:
        lines.append("\n(Apna UPI ID daalo to har item pe direct pay-link bhi aayega)")
    return {
        "ok": True,
        "tool": "catalog",
        "result": {"items": items, "share_text": "\n".join(lines), "vpa": vpa},
        "context": c,
    }


@router.post("/minisite", dependencies=[Depends(_GEN_LIMIT)])
async def studio_minisite(
    req: MiniSiteReq = Body(default=MiniSiteReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Apni mini-site KHUD customize karo — palette/colors/logo/tagline. Slug token se
    resolve (IDOR-safe; doosre ki site edit nahi). Update → /b/{slug} pe turant live.
    (Pehle ye sirf admin kar sakta tha.)"""
    from app.api import minisite_builder as mb
    from app.marketing import clients_store

    # Mini-site/brand marketing id pe keyed — billing/login alias canonicalize.
    mcid = clients_store.canonical_client_id(client_id)
    c = clients_store.resolve_client(client_id) or {}
    slug = str(c.get("slug") or "").strip()
    if not slug:
        _fail("Mini-site", Exception("aapki mini-site slug nahi mili"))
    cfg = mb.set_config(
        slug,
        palette=(req.palette or None),
        logo_url=(req.logo_url or None),
        primary=(req.primary or None),
        accent=(req.accent or None),
    )
    if (req.tagline or "").strip():
        try:
            brand = dict(c.get("brand") or {})
            brand["tagline"] = req.tagline.strip()[:160]
            clients_store.update_client(mcid, brand=brand)
        except Exception as e:
            logger.debug("minisite tagline update skip: %s", e)
    return {
        "ok": True,
        "tool": "minisite",
        "result": {"config": cfg, "url": f"/b/{slug}", "palettes": list(mb.PALETTES.keys())},
        "context": _ctx(client_id),
    }


@router.post("/post", dependencies=[Depends(_GEN_LIMIT)])
async def studio_post(
    req: PostReq = Body(default=PostReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Ready-to-post social caption + hashtags + image idea for the client's niche."""
    c = _ctx(client_id)
    try:
        from app.marketing import post_generator

        out = await post_generator.generate_post(
            business_name=c["business_name"],
            niche=c["niche"],
            occasion=req.occasion,
            offer=req.offer,
            language=req.language,
        )
    except Exception as e:  # generators never raise, but stay defensive
        _fail("AI Post", e)
    return {"ok": True, "tool": "post", "result": out, "context": c}


@router.post("/calendar", dependencies=[Depends(_GEN_LIMIT)])
async def studio_calendar(
    req: CalendarReq = Body(default=CalendarReq()), client_id: str = Depends(require_customer)
) -> dict:
    """N-day content calendar (themes + hook lines) for the client's niche."""
    c = _ctx(client_id)
    try:
        from app.marketing import post_generator

        items = await post_generator.content_calendar(
            business_name=c["business_name"],
            niche=c["niche"],
            days=req.days,
        )
    except Exception as e:
        _fail("Content Calendar", e)
    return {"ok": True, "tool": "calendar", "days": req.days, "items": items, "context": c}


@router.post("/whatsapp", dependencies=[Depends(_GEN_LIMIT)])
async def studio_whatsapp(
    req: WhatsAppReq = Body(default=WhatsAppReq()), client_id: str = Depends(require_customer)
) -> dict:
    """WhatsApp broadcast + status + reply pack (copy-paste; NOT auto-sent)."""
    c = _ctx(client_id)
    try:
        from app.marketing import whatsapp_pack

        out = await whatsapp_pack.broadcast_pack(
            business_name=c["business_name"],
            niche=c["niche"],
            occasion=req.occasion,
            offer=req.offer,
        )
    except Exception as e:
        _fail("WhatsApp Pack", e)
    return {
        "ok": True,
        "tool": "whatsapp",
        "result": out,
        "note": "Copy karke khud bhejo (auto-send ban-safe OFF).",
        "context": c,
    }


@router.post("/review-reply", dependencies=[Depends(_GEN_LIMIT)])
async def studio_review_reply(
    req: ReviewReplyReq, client_id: str = Depends(require_customer)
) -> dict:
    """3 Hinglish replies (short/medium/detailed) for a Google review."""
    c = _ctx(client_id)
    try:
        from app.marketing import review_replies

        out = await review_replies.generate_replies(
            review_text=req.review_text,
            rating=req.rating,
            business_name=c["business_name"],
            tone=req.tone,
        )
    except Exception as e:
        _fail("Review Reply", e)
    return {"ok": True, "tool": "review-reply", "result": out, "context": c}


@router.post("/gbp-text", dependencies=[Depends(_GEN_LIMIT)])
async def studio_gbp_text(
    req: GbpTextReq = Body(default=GbpTextReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Google Business Profile description + service texts + 3 posts."""
    c = _ctx(client_id)
    try:
        from app.marketing import gbp_text

        out = await gbp_text.gbp_texts(
            business_name=c["business_name"],
            niche=c["niche"],
            city=(req.city or c["city"]),
            services=req.services,
        )
    except Exception as e:
        _fail("GBP Text", e)
    return {"ok": True, "tool": "gbp-text", "result": out, "context": c}


@router.post("/ads", dependencies=[Depends(_GEN_LIMIT)])
async def studio_ads(
    req: AdsReq = Body(default=AdsReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Google RSA + Meta ad copy pack (char-limit safe headlines/descriptions)."""
    c = _ctx(client_id)
    try:
        from app.marketing import ads_copy

        out = await ads_copy.ads_pack(
            business_name=c["business_name"],
            niche=c["niche"],
            offer=req.offer,
            city=(req.city or c["city"]),
        )
    except Exception as e:
        _fail("Ad Copy", e)
    return {"ok": True, "tool": "ads", "result": out, "context": c}


@router.post("/hashtags", dependencies=[Depends(_GEN_LIMIT)])
async def studio_hashtags(
    req: HashtagReq = Body(default=HashtagReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Researched hashtag set for the client's niche/city."""
    c = _ctx(client_id)
    try:
        from app.marketing import hashtags

        out = await hashtags.research(
            niche=c["niche"], city=(req.city or c["city"]), count=req.count
        )
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
    inquiry: str = Field(
        "", max_length=1200, description="Customer ne kya poocha / kaunsa kaam chahiye"
    )
    service: str = Field("", max_length=200, description="Service/kaam ka naam (optional)")
    budget_hint: str = Field(
        "", max_length=120, description="Approx budget / price-range hint (optional)"
    )
    customer_name: str = Field(
        "", max_length=80, description="Jis customer ke liye quote hai (optional)"
    )


class UpiQrReq(BaseModel):
    vpa: str = Field(
        "", max_length=100, description="Apna UPI ID (naam@bank) — ek baar set, save ho jata"
    )
    amount: float | None = Field(
        None, ge=0, le=100000000, description="Fixed amount (optional; khali = any-amount QR)"
    )
    note: str = Field("", max_length=100, description="Payment note (optional)")


class StudioImageReq(BaseModel):
    occasion: str = Field("", max_length=120, description="Festival / theme / topic")
    offer: str = Field("", max_length=200, description="Discount / offer line")
    style: str = Field("vibrant professional", max_length=80)
    width: int = Field(1024, ge=256, le=1536)
    height: int = Field(1024, ge=256, le=1536)


class CompletePostStudioReq(BaseModel):
    occasion: str = Field("", max_length=120)
    offer: str = Field("", max_length=200)
    language: str = Field("hinglish", max_length=40)
    width: int = Field(1024, ge=256, le=1536)
    height: int = Field(1024, ge=256, le=1536)


@router.post("/festival-post", dependencies=[Depends(_GEN_LIMIT)])
async def studio_festival_post(
    req: FestivalReq = Body(default=FestivalReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Upcoming Indian festivals + ready captions for each (Diwali/Holi/Eid/Rakhi…)."""
    c = _ctx(client_id)
    try:
        from app.marketing import festivals

        out = await festivals.festival_posts(
            business_name=c["business_name"], niche=c["niche"], days=req.days
        )
    except Exception as e:
        _fail("Festival Posts", e)
    return {"ok": True, "tool": "festival-post", "result": out, "context": c}


@router.post("/poster", dependencies=[Depends(_GEN_LIMIT)])
async def studio_poster(
    req: PosterReq = Body(default=PosterReq()), client_id: str = Depends(require_customer)
) -> dict:
    """1080x1080 SVG offer/festival poster with shop name + offer + phone (downloadable)."""
    c = _ctx(client_id)
    try:
        from app.marketing import posters

        out = posters.generate_poster(
            template_id=req.template,
            business_name=c["business_name"],
            tagline=req.tagline,
            offer=req.offer,
            phone=req.phone,
            festival=req.festival,
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
    return {
        "ok": True,
        "tool": "review-request",
        "result": {"pack": pack, "link": link},
        "context": c,
    }


@router.post("/followup-sequence", dependencies=[Depends(_GEN_LIMIT)])
async def studio_followup_sequence(
    req: FollowupReq = Body(default=FollowupReq()), client_id: str = Depends(require_customer)
) -> dict:
    """4-step WhatsApp follow-up drip (Day 1/3/7…) for a lead type."""
    c = _ctx(client_id)
    try:
        from app.marketing import drip

        out = await drip.drip_sequence(
            business_name=c["business_name"], niche=c["niche"], lead_type=req.lead_type
        )
    except Exception as e:
        _fail("Follow-up Sequence", e)
    return {"ok": True, "tool": "followup-sequence", "result": out, "context": c}


@router.post("/speed-followup", dependencies=[Depends(_GEN_LIMIT)])
async def studio_speed_followup(client_id: str = Depends(require_customer)) -> dict:
    """Instant first-touch follow-up message to send a brand-new lead in <2 min."""
    c = _ctx(client_id)
    try:
        from app.marketing import drip

        seq = await drip.drip_sequence(
            business_name=c["business_name"], niche=c["niche"], lead_type="new_inquiry"
        )
        steps = (seq or {}).get("steps") or []
        instant = (
            steps[0]
            if steps
            else {"message": "Namaste! Aapki enquiry mili — main abhi aapse baat karta hoon. 🙏"}
        )
    except Exception as e:
        _fail("Speed-to-Lead", e)
    return {"ok": True, "tool": "speed-followup", "result": {"instant": instant}, "context": c}


@router.post("/reel-script", dependencies=[Depends(_GEN_LIMIT)])
async def studio_reel_script(
    req: ReelReq = Body(default=ReelReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Instagram/Reels Hinglish scripts (hook/body/cta/caption/duration)."""
    c = _ctx(client_id)
    try:
        from app.marketing import reels

        out = await reels.reels_scripts(
            business_name=c["business_name"], niche=c["niche"], topic=req.topic, n=req.n
        )
    except Exception as e:
        _fail("Reel Script", e)
    return {"ok": True, "tool": "reel-script", "result": out, "context": c}


@router.post("/win-back", dependencies=[Depends(_GEN_LIMIT)])
async def studio_win_back(
    req: WinbackReq = Body(default=WinbackReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Win-back / reactivation messages for old customers (+ wa.me links)."""
    c = _ctx(client_id)
    try:
        from app.marketing import reactivation

        out = await reactivation.reactivation_campaign(
            business_name=c["business_name"],
            niche=c["niche"],
            customers=req.customers,
            offer=req.offer,
        )
    except Exception as e:
        _fail("Win-back", e)
    return {"ok": True, "tool": "win-back", "result": out, "context": c}


@router.post("/quote-draft", dependencies=[Depends(_GEN_LIMIT)])
async def studio_quote_draft(
    req: QuoteReq = Body(default=QuoteReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Customer-scoped price-quote draft — CLIENT ke apne END-customer ke liye ek
    professional Hinglish quotation (business_name/niche/brand + inquiry text se).

    Pehle ye ``proposal.generate_proposal`` call karta tha jo LEADGEN ka apna sales
    pitch banata (Growth ₹2,999 tak mention karta) — ye customer ke portal me galat
    output tha (audit 2026-07-05). Ab ye us salon/shop ka quote banata JO WO apne
    customer ko bhej sake. free_ai.chat pattern (proposal.py jaisa) + never-empty
    template fallback — UI kabhi blank nahi."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    biz = c["business_name"]
    niche_h = (c["niche"] or "general").replace("_", " ")
    brand = rec.get("brand") if isinstance(rec.get("brand"), dict) else {}
    tagline = str((brand or {}).get("tagline") or "").strip()
    who = (req.customer_name or "").strip()
    greet_name = f" {who}" if who else ""
    service = (req.service or "").strip()
    inquiry = (req.inquiry or "").strip()
    budget = (req.budget_hint or "").strip()
    phone = str(rec.get("phone") or "").strip()

    # Never-empty template quote (LLM output isko replace kar sakta, warna yahi jaata).
    _svc_line = f"Aapki requirement: {service or inquiry or 'aapke kaam'}"
    quote_text = (
        f"*{biz} — Quotation*\n\n"
        f"Namaste{greet_name} 🙏 Aapki inquiry ke liye dhanyawad.\n"
        f"{_svc_line}.\n\n"
        f"Hum {niche_h} me quality kaam + time pe delivery dete hain. "
        f"{('Budget ' + budget + ' ke hisaab se ') if budget else ''}best rate + options aapko "
        f"bhej rahe hain — final price kaam ke scope pe depend karega.\n\n"
        f"Aage badhne ke liye reply karein ya call karein"
        f"{(' — ' + phone) if phone else ''}. Hum aaj hi confirm kar denge. 👍\n\n"
        f"— {biz}" + (f"\n{tagline}" if tagline else "")
    )

    try:
        from app.voice_agent import free_ai

        sys = (
            "Tum ek local Indian business (salon/shop/service) ke liye price-QUOTATION "
            "writer ho. Ek SHORT (6-9 line) professional Hinglish quote likho JO YE BUSINESS "
            "apne CUSTOMER ko bheje: greeting → customer ki requirement → hum kya denge (quality/"
            "delivery) → indicative pricing/options (koi fixed number invent mat karo agar diya "
            "nahi) → next step (reply/call/book). SIRF is business ka naam use karo. Kisi platform/"
            "software/vendor ('LeadGen', 'AI agent', SaaS plan/₹pricing) ka ZIKR bilkul mat karo. "
            "Sirf quotation text return karo."
        )
        prompt = (
            f"Business: {biz}. Niche: {niche_h}. City: {c['city'] or '-'}. "
            + (f"Brand tagline: {tagline}. " if tagline else "")
            + (f"Customer ka naam: {who}. " if who else "")
            + (f"Service/kaam: {service}. " if service else "")
            + (f"Customer ki inquiry: {inquiry}. " if inquiry else "")
            + (f"Budget hint: {budget}. " if budget else "")
            + (f"Contact number: {phone}. " if phone else "")
        )
        txt, _ = await free_ai.chat(
            sys, [{"role": "user", "content": prompt}], max_tokens=320, temperature=0.6
        )
        if txt and txt.strip():
            quote_text = txt.strip()
    except Exception as e:
        logger.debug("studio quote-draft llm skip: %s", e)

    return {
        "ok": True,
        "tool": "quote-draft",
        "result": {
            "business_name": biz,
            "customer_name": who,
            "quote": quote_text,
            "note": "Ye quote aap apne customer ko WhatsApp/email pe bhej sakte ho. Final price kaam ke scope pe adjust karo.",
        },
        "context": c,
    }


@router.post("/upi-qr", dependencies=[Depends(_GEN_LIMIT)])
def studio_upi_qr(
    req: UpiQrReq = Body(default=UpiQrReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Apna UPI payment QR pack — customer ka customer seedha UPI se pay kare (koi
    gateway nahi). VPA ek baar daalo, client record me save ho jata (agli baar auto).
    upi_qr.payment_qr_pack ka customer-facing wrapper (engage/upi-qr admin-only tha).

    IDOR-safe: client_id HAMESHA auth dependency se — request body me client_id nahi."""
    c = _ctx(client_id)
    from app.marketing import clients_store, upi_qr

    # New VPA diya to persist (whitelisted field) — warna record ka purana use hota.
    vpa = (req.vpa or "").strip()
    if vpa:
        try:
            clients_store.update_client(client_id, upi_vpa=vpa)
        except Exception as e:
            logger.debug("studio upi-qr vpa persist skip: %s", e)
    pack = upi_qr.payment_qr_pack(client_id, amount=req.amount, note=(req.note or ""))
    if not pack.get("ok"):
        # VPA missing/invalid → actionable message, not a 5xx (pack never raises).
        return {
            "ok": False,
            "tool": "upi-qr",
            "error": pack.get("error") or "UPI ID (naam@bank) daalo.",
            "context": c,
        }
    return {"ok": True, "tool": "upi-qr", "result": pack, "context": c}


@router.post("/ai-image", dependencies=[Depends(_GEN_LIMIT)])
async def studio_ai_image(
    req: StudioImageReq = Body(default=StudioImageReq()), client_id: str = Depends(require_customer)
) -> dict:
    """AI marketing-image (Pollinations Flux, FREE) — customer ke apne business/niche
    ke liye real image URL. Admin-only /api/marketing/ai-image ka customer wrapper
    (business_name/niche client record se — IDOR-safe)."""
    c = _ctx(client_id)
    try:
        from app.marketing import ai_image

        out = await ai_image.marketing_image(
            c["business_name"],
            c["niche"],
            req.occasion,
            req.offer,
            req.style,
            req.width,
            req.height,
        )
    except Exception as e:
        _fail("AI Image", e)
    return {"ok": True, "tool": "ai-image", "result": out, "context": c}


@router.post("/complete-post", dependencies=[Depends(_GEN_LIMIT)])
async def studio_complete_post(
    req: CompletePostStudioReq = Body(default=CompletePostStudioReq()),
    client_id: str = Depends(require_customer),
) -> dict:
    """COMPLETE post ek shot me — caption + hashtags + asli AI image (free). Admin-only
    /api/marketing/complete-post ka customer wrapper (business/niche client record se)."""
    import asyncio

    c = _ctx(client_id)
    try:
        from app.marketing import ai_image, post_generator

        post, img = await asyncio.gather(
            post_generator.generate_post(
                business_name=c["business_name"],
                niche=c["niche"],
                occasion=req.occasion,
                offer=req.offer,
                language=req.language,
            ),
            ai_image.marketing_image(
                c["business_name"],
                c["niche"],
                req.occasion,
                req.offer,
                width=req.width,
                height=req.height,
            ),
        )
    except Exception as e:
        _fail("Complete Post", e)
    result = {**post, "image_url": img.get("url", ""), "image_prompt": img.get("prompt", "")}
    return {"ok": True, "tool": "complete-post", "result": result, "context": c}


@router.get("/next-best-action")
def studio_next_best_action(client_id: str = Depends(require_customer)) -> dict:
    """ "Aaj kya karna hai" — prioritized task list from the client's live signals.

    PURE LOGIC (no LLM): reads leads / pending approvals / GBP score / content
    queue and returns an ordered action list. Never-empty, never-raise.
    """
    c = _ctx(client_id)
    actions: list[dict] = []

    # 1) New uncalled leads -> highest priority (paisa yahin)
    try:
        leads = _client_inquiries(client_id)
        n_leads = len(leads)
        if n_leads:
            actions.append(
                {
                    "priority": 1,
                    "icon": "🔥",
                    "action": f"{n_leads} naye lead ko abhi call/WhatsApp karo",
                    "why": "2 minute me follow-up karne se 5x zyada deal lagti hai.",
                    "target": "leadsCard",
                }
            )
    except Exception as e:
        logger.debug("nba leads failed: %s", e)

    # 2) Pending content approvals
    try:
        from app.marketing import clients_store, content_approval

        # Approvals marketing id pe keyed — billing/login alias canonicalize.
        _mcid = clients_store.canonical_client_id(client_id)
        pend = content_approval.pending(_mcid) if hasattr(content_approval, "pending") else []
        if pend:
            actions.append(
                {
                    "priority": 2,
                    "icon": "✅",
                    "action": f"{len(pend)} post approve karo",
                    "why": "Approve karte hi system publish/schedule kar dega.",
                    "target": "approvalCard",
                }
            )
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
            actions.append(
                {
                    "priority": 3,
                    "icon": "🏪",
                    "action": "Google Business audit karo (2 min)",
                    "why": "Score pata chalega + top-5 fix milenge — Google par upar aane ke liye.",
                    "target": "studioCard",
                }
            )
        elif isinstance(score, int | float) and score < 70:
            actions.append(
                {
                    "priority": 2,
                    "icon": "🏪",
                    "action": f"GBP score {int(score)}/100 — fixes lagao",
                    "why": "70+ profile zyada calls + direction requests laata hai.",
                    "target": "studioCard",
                }
            )
    except Exception as e:
        logger.debug("nba gbp failed: %s", e)

    # 4) Content freshness
    try:
        from app.api.customer_dashboard_builders import _content_posts_count

        rec = _client_record(client_id) or {}
        if _content_posts_count(client_id, rec) == 0:
            actions.append(
                {
                    "priority": 3,
                    "icon": "📝",
                    "action": "Aaj ka post banao + share karo",
                    "why": "Regular posting se reach + trust dono badhte hain.",
                    "target": "studioCard",
                }
            )
    except Exception as e:
        logger.debug("nba content failed: %s", e)

    # 5) Always-on growth nudge
    actions.append(
        {
            "priority": 4,
            "icon": "⭐",
            "action": "Khush customers ko review request bhejo",
            "why": "Naye reviews = ranking + naye customers ka trust.",
            "target": "studioCard",
        }
    )

    actions.sort(key=lambda a: a.get("priority", 9))
    return {
        "ok": True,
        "tool": "next-best-action",
        "actions": actions,
        "count": len(actions),
        "context": c,
    }


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
    kind: str = Field(
        "appointment", max_length=30, description="appointment|renewal|service|payment"
    )


@router.post("/competitor", dependencies=[Depends(_GEN_LIMIT)])
async def studio_competitor(
    req: CompetitorReq = Body(default=CompetitorReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Competitor notes → strengths to copy + gaps to exploit + action plan."""
    c = _ctx(client_id)
    try:
        from app.marketing import competitor

        out = await competitor.compare_tips(
            business_name=c["business_name"],
            niche=c["niche"],
            competitor_notes=req.competitor_notes,
        )
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
async def studio_carousel(
    req: CarouselReq = Body(default=CarouselReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Instagram/LinkedIn carousel — slide texts + per-slide SVG."""
    c = _ctx(client_id)
    try:
        from app.marketing import carousel

        out = await carousel.generate_carousel(
            business_name=c["business_name"],
            niche=c["niche"],
            topic=req.topic,
            slides=req.slides,
            slug=c.get("slug", ""),
            phone=c.get("phone", ""),
            brand_primary=c.get("brand_primary", ""),
        )
    except Exception as e:
        _fail("Carousel", e)
    return {"ok": True, "tool": "carousel", "result": out, "context": c}


@router.post("/bio-page", dependencies=[Depends(_GEN_LIMIT)])
async def studio_bio_page(client_id: str = Depends(require_customer)) -> dict:
    """Social bio / landing copy kit — Insta/FB/Google bios + page setup."""
    c = _ctx(client_id)
    try:
        from app.marketing import social_page_kit

        out = await social_page_kit.build_page_kit(
            business_name=c["business_name"], niche=c["niche"], city=c["city"]
        )
    except Exception as e:
        _fail("Bio Page", e)
    return {"ok": True, "tool": "bio-page", "result": out, "context": c}


@router.post("/lead-magnet", dependencies=[Depends(_GEN_LIMIT)])
async def studio_lead_magnet(
    req: LeadMagnetReq = Body(default=LeadMagnetReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Free lead-magnet guide (checklist/tips PDF) to capture leads."""
    c = _ctx(client_id)
    try:
        from app.marketing import lead_magnet

        rec = _client_record(client_id) or {}
        out = await lead_magnet.generate(
            niche=c["niche"],
            city=(req.city or c["city"]),
            business_name=c["business_name"],
            slug=str(rec.get("slug") or ""),
        )
    except Exception as e:
        _fail("Lead Magnet", e)
    return {"ok": True, "tool": "lead-magnet", "result": out, "context": c}


@router.post("/negative-review-rescue", dependencies=[Depends(_GEN_LIMIT)])
async def studio_negative_review_rescue(
    req: NegReviewReq, client_id: str = Depends(require_customer)
) -> dict:
    """Bad review ke liye polite damage-control replies (empathetic tone)."""
    c = _ctx(client_id)
    try:
        from app.marketing import review_replies

        out = await review_replies.generate_replies(
            review_text=req.review_text,
            rating=req.rating,
            business_name=c["business_name"],
            tone="empathetic",
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
    return {
        "ok": True,
        "tool": "photo-reminder",
        "message": "Google par har hafte 1-2 nayi photo daalo — listing active dikhti hai + zyada calls aati hain.",
        "ideas": ideas,
        "context": c,
    }


@router.post("/budget-suggest")
def studio_budget_suggest(
    req: BudgetReq = Body(default=BudgetReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Daily ad budget suggestion (PURE LOGIC) from deal value + lead goal."""
    c = _ctx(client_id)
    # Conservative small-business assumptions: ~₹40 CPL, 12% lead->deal close.
    cpl = 40.0
    leads_needed = max(1, req.target_leads)
    monthly = cpl * leads_needed
    daily = round(monthly / 30.0, 0)
    deals = max(1, int(round(leads_needed * 0.12)))
    revenue = deals * req.avg_deal_value
    return {
        "ok": True,
        "tool": "budget-suggest",
        "context": c,
        "result": {
            "suggested_daily_inr": daily,
            "suggested_monthly_inr": round(monthly, 0),
            "assumed_cost_per_lead_inr": cpl,
            "expected_leads": leads_needed,
            "expected_deals": deals,
            "expected_revenue_inr": revenue,
            "note": "Chhote business ke liye safe start. 1-2 hafte baad results dekh ke badhao/ghatao.",
        },
    }


@router.post("/customer-reminder")
def studio_customer_reminder(
    req: ReminderReq = Body(default=ReminderReq()), client_id: str = Depends(require_customer)
) -> dict:
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
            "Reminder: renewal due hai. 1-click renew link bhej dun? Reply 'HAAN'.",
        ],
        "service": [
            f"{biz}: aapki next service/maintenance due hai. Slot book kar lein taaki sab sahi chale 👍",
            "Reminder — last service ko time ho gaya. Aaj book karein, baad me rush se bachein.",
        ],
        "payment": [
            f"Namaste 🙏 {biz} — aapka payment pending hai. UPI/link se aaj clear kar dein to badi madad hogi. Dhanyawad!",
            "Gentle reminder: invoice pending hai. Koi dikkat ho to bata dein, hum help karenge.",
        ],
    }
    msgs = templates.get(kind, templates["appointment"])
    return {"ok": True, "tool": "customer-reminder", "kind": kind, "messages": msgs, "context": c}


@router.post("/appointment-assistant")
def studio_appointment_assistant(client_id: str = Depends(require_customer)) -> dict:
    """Slot-suggestion + booking-confirmation message templates (PURE LOGIC)."""
    c = _ctx(client_id)
    biz = c["business_name"]
    return {
        "ok": True,
        "tool": "appointment-assistant",
        "context": c,
        "result": {
            "slot_offer": [
                f"Namaste 🙏 {biz} — aapke liye 2 slot free hain: aaj 4 PM ya kal 11 AM. Kaunsa theek hai?",
                f"Booking ke liye bas time bata dein — main {biz} me aapka slot pakka kar deta hoon 👍",
            ],
            "confirmation": [
                f"Confirmed! ✅ Aapka appointment {biz} me book ho gaya. Time pe milte hain. Address/location bhej dun?",
                "Ho gaya booking! Reminder ek din pehle bhej dunga. Dhanyawad 🙏",
            ],
            "no_show_followup": [
                f"Aaj aap aa nahi paaye — koi baat nahi! {biz} me naya slot rakh dun? Bas time bata dein.",
            ],
        },
    }


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
    objection: str = Field(
        "", max_length=300, description="Customer ka objection (khali = common list)"
    )


@router.post("/month-planner", dependencies=[Depends(_GEN_LIMIT)])
def studio_month_planner(
    req: MonthPlanReq = Body(default=MonthPlanReq()), client_id: str = Depends(require_customer)
) -> dict:
    """30-din ka content/campaign plan (themes + festival hooks per day)."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    try:
        from app.marketing import month_planner

        out = month_planner.plan_month(
            niche=c["niche"],
            client_id=str(rec.get("id") or client_id),
            slug=str(rec.get("slug") or ""),
            business_name=c["business_name"],
            offer=req.offer,
            channel=req.channel,
            dry_run=True,
            commit=False,
        )
    except Exception as e:
        _fail("Month Planner", e)
    return {"ok": True, "tool": "month-planner", "result": out, "context": c}


@router.post("/templates", dependencies=[Depends(_GEN_LIMIT)])
def studio_templates(
    req: TemplatesReq = Body(default=TemplatesReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Niche template library — ready post/poster ideas for the client's niche."""
    c = _ctx(client_id)
    try:
        from app.marketing import template_library

        out = template_library.list_templates(niche=c["niche"], occasion=req.occasion, limit=40)
    except Exception as e:
        _fail("Templates", e)
    return {"ok": True, "tool": "templates", "result": out, "context": c}


@router.post("/blog", dependencies=[Depends(_GEN_LIMIT)])
async def studio_blog(
    req: BlogReq = Body(default=BlogReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Local-SEO blog post — generate + STORE + live at /b/{slug}/blog (Google-indexable).
    (#29 fix: pehle sirf template milta tha, koi live per-client blog page nahi.)"""
    c = _ctx(client_id)
    try:
        from app.marketing import client_blog

        post = await client_blog.generate_and_store(
            client_id,
            business_name=c["business_name"],
            niche=c["niche"],
            topic=(req.topic or ""),
            keyword=(req.city or ""),
        )
    except Exception as e:
        _fail("Blog", e)
    slug = str(client_blog.client_slug(client_id) or "").strip()
    return {
        "ok": True,
        "tool": "blog",
        "result": {
            "post": post,
            "url": (f"/b/{slug}/blog/{post.get('slug', '')}" if slug else ""),
            "blog_url": (f"/b/{slug}/blog" if slug else ""),
        },
        "context": c,
    }


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
async def studio_testimonial(
    req: TestimonialReq, client_id: str = Depends(require_customer)
) -> dict:
    """Good review → branded thank-you poster (SVG) + social caption."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    try:
        from app.marketing import review_to_post

        out = await review_to_post.from_review(
            review_text=req.review_text,
            author=req.author,
            rating=req.rating,
            slug=str(rec.get("slug") or ""),
        )
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

        out = await repurpose.repurpose(
            topic_or_url=req.topic_or_url,
            niche=c["niche"],
            slug=str(rec.get("slug") or ""),
            business_name=c["business_name"],
        )
    except Exception as e:
        _fail("Repurpose", e)
    return {"ok": True, "tool": "repurpose", "result": out, "context": c}


@router.post("/referral", dependencies=[Depends(_GEN_LIMIT)])
def studio_referral(
    req: ReferralReq = Body(default=ReferralReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Referral kit — code + WhatsApp message + link + 1080 card SVG."""
    c = _ctx(client_id)
    try:
        from app.marketing import referral_kit

        out = referral_kit.make_referral(
            business_name=c["business_name"],
            reward=req.reward,
            brand_primary=c.get("brand_primary", ""),
            brand_accent=c.get("brand_accent", ""),
            slug=c.get("slug", ""),
        )
    except Exception as e:
        _fail("Referral", e)
    return {"ok": True, "tool": "referral", "result": out, "context": c}


@router.post("/roi-calculator")
def studio_roi_calculator(
    req: RoiReq = Body(default=RoiReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Marketing ROI estimate (PURE MATH) — spend vs expected revenue."""
    c = _ctx(client_id)
    deals = req.leads_per_month * (req.close_rate_pct / 100.0)
    revenue = deals * req.avg_deal_value
    roi_pct = (
        ((revenue - req.monthly_spend) / req.monthly_spend * 100.0)
        if req.monthly_spend > 0
        else None
    )
    cpl = (req.monthly_spend / req.leads_per_month) if req.leads_per_month > 0 else None
    return {
        "ok": True,
        "tool": "roi-calculator",
        "context": c,
        "result": {
            "monthly_spend_inr": round(req.monthly_spend, 0),
            "expected_deals": round(deals, 1),
            "expected_revenue_inr": round(revenue, 0),
            "roi_pct": round(roi_pct, 0) if roi_pct is not None else None,
            "cost_per_lead_inr": round(cpl, 0) if cpl is not None else None,
            "verdict": (
                "Profit me ho 👍" if roi_pct and roi_pct > 0 else "Spend/close-rate improve karo"
            ),
        },
    }


@router.post("/objection-handler")
def studio_objection_handler(
    req: ObjectionReq = Body(default=ObjectionReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Common sales objections ke best Hinglish replies (PURE LOGIC library)."""
    c = _ctx(client_id)
    biz = c["business_name"]
    lib = {
        "mehenga": f"Samajh sakta hoon. {biz} me daam thoda zyada isliye hai kyunki quality + warranty + service guaranteed milti hai — sasta lekar baar-baar kharcha zyada padta hai. Aaj ek baar try karke dekhiye.",
        "time": "Bilkul, jaldi nahi. Main aapko detail WhatsApp kar deta hoon, aaram se dekh lijiye — koi sawaal ho to main yahin hoon.",
        "sochenge": "Zaroor sochiye! Bas itna — abhi book karne pe {} milega. Main aapke liye 24 ghante hold kar deta hoon.".format(
            "special rate"
        ),
        "competitor": f"Achhi baat hai aap compare kar rahe ho. {biz} ka farak hai — service + bharosa + after-support. Ek demo le lijiye, khud farak dikhega.",
        "discount": "Aapke liye ek best price nikaalta hoon — par quality compromise nahi. Chhota loyalty discount de sakta hoon, deal pakki karein?",
    }
    obj = (req.objection or "").lower()
    matched = None
    for key, ans in lib.items():
        if key in obj:
            matched = {"objection": req.objection, "reply": ans}
            break
    return {
        "ok": True,
        "tool": "objection-handler",
        "context": c,
        "matched": matched,
        "library": [{"objection": k, "reply": v} for k, v in lib.items()],
    }


@router.get("/best-time")
def studio_best_time(client_id: str = Depends(require_customer)) -> dict:
    """Best time to post/message/call (PURE LOGIC, India SMB norms)."""
    c = _ctx(client_id)
    return {
        "ok": True,
        "tool": "best-time",
        "context": c,
        "result": {
            "whatsapp": "Subah 9-11 AM ya shaam 6-8 PM (lunch/dinner se pehle).",
            "instagram_post": "Shaam 7-9 PM (peak scroll time).",
            "instagram_reel": "1-3 PM lunch ya 8-10 PM raat.",
            "phone_call": "11 AM-1 PM ya 4-6 PM (subah-subah/late evening avoid).",
            "new_lead_followup": "Lead aate hi 2-5 min ke andar — sabse zyada conversion.",
            "tip": "Calling-window TRAI 9 AM-7 PM ke andar rakho.",
        },
    }


@router.get("/owner-brief")
def studio_owner_brief(client_id: str = Depends(require_customer)) -> dict:
    """Daily owner brief (PURE LOGIC) — aaj ke leads/approvals/posts ek nazar me."""
    c = _ctx(client_id)
    leads_n = approvals_n = 0
    leads_n = len(_client_inquiries(client_id))
    try:
        from app.marketing import clients_store, content_approval

        _mcid = clients_store.canonical_client_id(client_id)
        approvals_n = (
            len(content_approval.pending(_mcid) or [])
            if hasattr(content_approval, "pending")
            else 0
        )
    except Exception:
        pass
    brief = [
        (
            f"🔥 {leads_n} naye lead — inko aaj call/WhatsApp karo."
            if leads_n
            else "🔥 Abhi koi naya lead nahi — outreach/post badhao."
        ),
        (
            f"✅ {approvals_n} post approval pending."
            if approvals_n
            else "✅ Koi approval pending nahi."
        ),
        "📝 Aaj ka post + 1 Google photo daalo.",
        "⭐ 1 khush customer se review maango.",
    ]
    return {
        "ok": True,
        "tool": "owner-brief",
        "context": c,
        "leads": leads_n,
        "approvals": approvals_n,
        "brief": brief,
    }


@router.get("/growth-coach")
def studio_growth_coach(client_id: str = Depends(require_customer)) -> dict:
    """Weekly AI growth coach — agle 7 din ke 3 high-impact actions (PURE LOGIC)."""
    c = _ctx(client_id)
    niche = c["niche"]
    actions = [
        {
            "action": "Roz 1 post + 1 Google photo (7 din)",
            "why": "Consistency se reach + trust dono badhte hain.",
        },
        {
            "action": "5 khush customers se Google review maango",
            "why": "Reviews = ranking + naye customers ka bharosa.",
        },
        {
            "action": f"{niche.title()} ka 1 offer banao + WhatsApp status + GBP post",
            "why": "Ek offer multi-channel pe = zyada leads.",
        },
    ]
    return {
        "ok": True,
        "tool": "growth-coach",
        "context": c,
        "week_focus": "Visibility + Reviews + 1 Offer",
        "actions": actions,
    }


# --------------------------------------------------------------------------- #
# Batch 5 — complete the buildable set (#41-100). Pure-logic packs (uniform    #
# "sections" shape, zero LLM/network) + 3 generator wires.                     #
# --------------------------------------------------------------------------- #
class TopicReq(BaseModel):
    topic: str = Field("", max_length=160)


class CouponReq(BaseModel):
    title: str = Field("Special Offer", max_length=80)
    kind: str = Field("percent", max_length=20, description="percent|flat|freebie")
    value: int = Field(10, ge=0, le=100000)
    expiry_days: int = Field(30, ge=1, le=365)


class ServiceAreaReq(BaseModel):
    city: str = Field("", max_length=80)


class ServiceMenuReq(BaseModel):
    items_text: str = Field("", max_length=2000, description="Ek line per item: 'Naam : price'")
    style: str = Field("price_list", max_length=20)


def _pack(tool: str, client_id: str, fn_name: str, *args) -> dict:
    """Run a studio_packs pure-logic generator and wrap with context."""
    c = _ctx(client_id)
    try:
        from app.marketing import studio_packs

        out = getattr(studio_packs, fn_name)(*args)
    except Exception as e:
        logger.debug("studio pack %s failed: %s", fn_name, e)
        out = {"sections": [{"title": "Note", "items": ["Abhi available nahi — thodi der baad."]}]}
    return {"ok": True, "tool": tool, **out, "context": c}


@router.get("/business-description")
def studio_business_description(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack(
        "business-description",
        client_id,
        "business_description",
        c["business_name"],
        c["niche"],
        c["city"],
    )


@router.get("/brand-palette")
def studio_brand_palette(client_id: str = Depends(require_customer)) -> dict:
    return _pack("brand-palette", client_id, "brand_palette", _ctx(client_id)["niche"])


@router.get("/customer-avatar")
def studio_customer_avatar(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("customer-avatar", client_id, "customer_avatar", c["niche"], c["city"])


@router.get("/seasonal-offers")
def studio_seasonal_offers(client_id: str = Depends(require_customer)) -> dict:
    return _pack("seasonal-offers", client_id, "seasonal_offers", _ctx(client_id)["niche"])


@router.get("/local-event-campaign")
def studio_local_event(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("local-event-campaign", client_id, "local_event_campaign", c["niche"], c["city"])


@router.get("/case-study")
def studio_case_study(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("case-study", client_id, "case_study", c["business_name"], c["niche"])


@router.get("/grid-planner")
def studio_grid_planner(client_id: str = Depends(require_customer)) -> dict:
    return _pack("grid-planner", client_id, "grid_planner", _ctx(client_id)["niche"])


@router.get("/highlights")
def studio_highlights(client_id: str = Depends(require_customer)) -> dict:
    return _pack("highlights", client_id, "highlights", _ctx(client_id)["niche"])


@router.post("/voiceover")
def studio_voiceover(
    req: TopicReq = Body(default=TopicReq()), client_id: str = Depends(require_customer)
) -> dict:
    c = _ctx(client_id)
    return _pack(
        "voiceover", client_id, "voiceover_script", c["business_name"], c["niche"], req.topic
    )


@router.post("/youtube-metadata")
def studio_youtube_metadata(
    req: TopicReq = Body(default=TopicReq()), client_id: str = Depends(require_customer)
) -> dict:
    c = _ctx(client_id)
    return _pack(
        "youtube-metadata", client_id, "youtube_metadata", c["business_name"], c["niche"], req.topic
    )


@router.get("/faq-page")
def studio_faq_page(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("faq-page", client_id, "faq_page", c["business_name"], c["niche"])


@router.get("/schema-markup")
def studio_schema_markup(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    return _pack(
        "schema-markup",
        client_id,
        "schema_markup",
        c["business_name"],
        c["niche"],
        c["city"],
        str(rec.get("phone") or ""),
    )


@router.get("/conversion-tracking")
def studio_conversion_tracking(client_id: str = Depends(require_customer)) -> dict:
    return _pack("conversion-tracking", client_id, "conversion_tracking", _ctx(client_id)["niche"])


@router.get("/lost-lead-reason")
def studio_lost_lead_reason(client_id: str = Depends(require_customer)) -> dict:
    return _pack("lost-lead-reason", client_id, "lost_lead_reason", _ctx(client_id)["niche"])


@router.get("/complaint-recovery")
def studio_complaint_recovery(client_id: str = Depends(require_customer)) -> dict:
    return _pack(
        "complaint-recovery", client_id, "complaint_recovery", _ctx(client_id)["business_name"]
    )


@router.get("/ugc-request")
def studio_ugc_request(client_id: str = Depends(require_customer)) -> dict:
    return _pack("ugc-request", client_id, "ugc_request", _ctx(client_id)["business_name"])


# --------------------------------------------------------------------------- #
# Batch 6 — engine LINKS (per-client views, IDOR-safe). Surface existing       #
# backend capability scoped to THIS customer's own inquiries.                  #
# --------------------------------------------------------------------------- #
@router.get("/ai-inbox")
def studio_ai_inbox(client_id: str = Depends(require_customer)) -> dict:
    """AI Inbox — is customer ki apni inquiries ko intent + urgency se classify
    karke suggested action deta hai (per-client, IDOR-safe). reply_agent ka
    customer-facing view (uska global IMAP inbox NAHI)."""
    c = _ctx(client_id)
    items: list[dict] = []
    counts = {"urgent": 0, "price": 0, "booking": 0, "complaint": 0, "spam": 0, "general": 0}
    for r in _client_inquiries(client_id)[:50]:
        msg = str(r.get("message") or "")
        intent = _classify_intent(msg)
        age_h = _inq_age_hours(r)
        urgent = intent in ("price", "booking", "complaint") and age_h <= 6
        counts[intent] = counts.get(intent, 0) + 1
        if urgent:
            counts["urgent"] += 1
        items.append(
            {
                "name": str(r.get("name") or "Customer")[:60],
                "phone": str(r.get("phone") or ""),
                "wa_link": _wa_link(r.get("phone")),
                "message": msg[:240],
                "intent": intent,
                "urgent": urgent,
                "age_hours": round(age_h, 1) if age_h < 9e8 else None,
                "suggestion": _INTENT_ACTION.get(intent, ""),
            }
        )
    # urgent + freshest first
    items.sort(
        key=lambda x: (
            not x["urgent"],
            x.get("age_hours") if x.get("age_hours") is not None else 9e9,
        )
    )
    return {
        "ok": True,
        "tool": "ai-inbox",
        "context": c,
        "count": len(items),
        "counts": counts,
        "items": items,
        "empty_note": "Abhi koi inquiry nahi — mini-site/widget share karo to leads yahan aayenge.",
    }


@router.get("/re-engagement")
def studio_re_engagement(client_id: str = Depends(require_customer)) -> dict:
    """Re-engagement — cold/inactive leads (48h+ purane) surface karke 1-click
    win-back message deta hai. cadence/lifecycle engine ka per-client view."""
    c = _ctx(client_id)
    biz = c["business_name"]
    cold: list[dict] = []
    for r in _client_inquiries(client_id):
        age_h = _inq_age_hours(r)
        if age_h < 48 or age_h > 9e8:  # too new or unknown -> skip
            continue
        days = int(age_h // 24)
        name = str(r.get("name") or "ji")[:60]
        cold.append(
            {
                "name": name,
                "phone": str(r.get("phone") or ""),
                "wa_link": _wa_link(r.get("phone")),
                "days_cold": days,
                "message": (
                    f"Namaste {name}! 🙏 {biz} se — aapne kuch din pehle enquiry ki thi. "
                    "Abhi bhi interested ho to ek special offer de sakta hoon. Bataiye? 😊"
                ),
            }
        )
    cold.sort(key=lambda x: x["days_cold"], reverse=True)
    return {
        "ok": True,
        "tool": "re-engagement",
        "context": c,
        "count": len(cold),
        "items": cold[:50],
        "empty_note": "Abhi koi cold lead nahi — sab fresh hain ya follow-up ho chuka.",
    }


# --------------------------------------------------------------------------- #
# Batch 7 — web-research-grounded (Birdeye/Podium/GHL/BrightLocal/WA-commerce  #
# parity). 9 pure-logic packs + 2 wires (listings/NAP, website widget).        #
# --------------------------------------------------------------------------- #
@router.get("/nps-survey")
def studio_nps_survey(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("nps-survey", client_id, "nps_survey", c["business_name"], c["niche"])


@router.get("/whatsapp-catalog")
def studio_whatsapp_catalog(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("whatsapp-catalog", client_id, "whatsapp_catalog", c["business_name"], c["niche"])


@router.get("/click-to-whatsapp-ad")
def studio_click_to_whatsapp_ad(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack(
        "click-to-whatsapp-ad", client_id, "click_to_whatsapp_ad", c["business_name"], c["niche"]
    )


@router.get("/sms-pack")
def studio_sms_pack(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("sms-pack", client_id, "sms_pack", c["business_name"], c["niche"])


@router.get("/aeo-checklist")
def studio_aeo_checklist(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("aeo-checklist", client_id, "aeo_checklist", c["business_name"], c["niche"])


@router.get("/loyalty-program")
def studio_loyalty_program(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("loyalty-program", client_id, "loyalty_program", c["business_name"], c["niche"])


@router.get("/rank-check-guide")
def studio_rank_check_guide(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack(
        "rank-check-guide", client_id, "rank_check_guide", c["business_name"], c["niche"], c["city"]
    )


@router.get("/booking-link")
def studio_booking_link(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack("booking-link", client_id, "booking_link", c["business_name"], c["niche"])


@router.get("/newsletter-outline")
def studio_newsletter_outline(client_id: str = Depends(require_customer)) -> dict:
    c = _ctx(client_id)
    return _pack(
        "newsletter-outline", client_id, "newsletter_outline", c["business_name"], c["niche"]
    )


@router.get("/listings")
def studio_listings(client_id: str = Depends(require_customer)) -> dict:
    """NAP / citations directory checklist (India: Google/JustDial/Sulekha/IndiaMART…)
    with manual deep-links + presence score. BrightLocal/Moz-Local parity, zero-scrape."""
    c = _ctx(client_id)
    try:
        from app.marketing import listings_presence

        out = listings_presence.checklist(
            business_name=c["business_name"], city=c["city"], niche=c["niche"]
        )
    except Exception as e:
        _fail("Listings", e)
    return {"ok": True, "tool": "listings", "result": out, "context": c}


@router.get("/website-widget")
def studio_website_widget(client_id: str = Depends(require_customer)) -> dict:
    """Copy-paste website lead-capture widget snippet (embeddable on any site)."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    slug = str(rec.get("slug") or rec.get("id") or client_id)
    code = ""
    try:
        from app.marketing import embed_widget

        code = embed_widget.snippet(slug, mode="form")
    except Exception as e:
        logger.debug("website-widget failed: %s", e)
    if not code:
        code = f'<script src="https://leadsgenai.in/b/{slug}/widget.js" async></script>'
    return {
        "ok": True,
        "tool": "website-widget",
        "context": c,
        "result": {
            "snippet": code,
            "note": "Ye code apni website ke page me paste karo — enquiry form/widget aa jayega.",
        },
    }


# --------------------------------------------------------------------------- #
# Batch 8 — more FREE-stack wires (meme, card, signature, regional post,       #
# trends, partnerships, reviews widget). All zero-paid-API.                    #
# --------------------------------------------------------------------------- #
class MultilangReq(BaseModel):
    caption: str = Field(..., min_length=1, max_length=1000)
    langs: list[str] | None = Field(None, description="hi, mr, ta, te, bn… (blank = default set)")


def _snippet_of(out) -> str:
    if isinstance(out, str):
        return out
    if isinstance(out, dict):
        for k in ("snippet", "html", "signature_html", "card_html", "code"):
            if out.get(k):
                return str(out[k])
    return ""


@router.post("/meme", dependencies=[Depends(_GEN_LIMIT)])
async def studio_meme(
    req: TopicReq = Body(default=TopicReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Relatable Hinglish meme — top/bottom text + SVG + caption (downloadable)."""
    c = _ctx(client_id)
    try:
        from app.marketing import meme_gen

        out = await meme_gen.generate_meme(
            business_name=c["business_name"], niche=c["niche"], topic=req.topic
        )
    except Exception as e:
        _fail("Meme", e)
    return {"ok": True, "tool": "meme", "result": out, "context": c}


@router.post("/multilang-post", dependencies=[Depends(_GEN_LIMIT)])
async def studio_multilang_post(
    req: MultilangReq, client_id: str = Depends(require_customer)
) -> dict:
    """Ek caption ko regional languages me translate (Hindi/Marathi/Tamil/Telugu/Bengali…)."""
    c = _ctx(client_id)
    try:
        from app.marketing import multilang_post

        out = await multilang_post.translate_post(caption=req.caption, langs=req.langs)
    except Exception as e:
        _fail("Multi-language Post", e)
    return {"ok": True, "tool": "multilang-post", "result": out, "context": c}


@router.get("/trends")
async def studio_trends(client_id: str = Depends(require_customer)) -> dict:
    """Trending topics → aapke niche ke liye post angles (free RSS, never-empty)."""
    c = _ctx(client_id)
    try:
        from app.marketing import trends

        out = await trends.trend_angles(niche=c["niche"], business_name=c["business_name"], n=4)
    except Exception as e:
        _fail("Trends", e)
    return {"ok": True, "tool": "trends", "result": out, "context": c}


@router.get("/partnerships")
async def studio_partnerships(client_id: str = Depends(require_customer)) -> dict:
    """Co-marketing / partnership pitch drafts for complementary local businesses."""
    c = _ctx(client_id)
    try:
        from app.marketing import partnerships

        out = await partnerships.draft_batch(city=c["city"])
    except Exception as e:
        _fail("Partnerships", e)
    return {"ok": True, "tool": "partnerships", "result": out, "context": c}


@router.get("/business-card")
def studio_business_card(client_id: str = Depends(require_customer)) -> dict:
    """Digital business card (HTML) — share link/QR, save-to-contacts."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    slug = str(rec.get("slug") or rec.get("id") or client_id)
    code = ""
    try:
        from app.marketing import business_card

        code = _snippet_of(business_card.render_card_html(slug))
    except Exception as e:
        logger.debug("business-card failed: %s", e)
    return {
        "ok": True,
        "tool": "business-card",
        "context": c,
        "result": {
            "snippet": code or "Card abhi available nahi.",
            "note": "Ye HTML card share karo ya website pe lagao.",
        },
    }


@router.get("/email-signature")
def studio_email_signature(client_id: str = Depends(require_customer)) -> dict:
    """Branded email signature (HTML) — har email me brand + CTA."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    code = ""
    try:
        from app.marketing import email_signature

        code = _snippet_of(
            email_signature.generate(
                client_id=str(rec.get("id") or client_id), slug=str(rec.get("slug") or "")
            )
        )
    except Exception as e:
        logger.debug("email-signature failed: %s", e)
    return {
        "ok": True,
        "tool": "email-signature",
        "context": c,
        "result": {
            "snippet": code or "Signature abhi available nahi.",
            "note": "Gmail/Outlook signature settings me paste karo.",
        },
    }


@router.get("/reviews-widget")
def studio_reviews_widget(client_id: str = Depends(require_customer)) -> dict:
    """Embeddable reviews widget — apni website pe Google reviews dikhaao."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    slug = str(rec.get("slug") or rec.get("id") or client_id)
    code = ""
    try:
        from app.marketing import reviews_widget

        code = _snippet_of(reviews_widget.snippet(slug))
    except Exception as e:
        logger.debug("reviews-widget failed: %s", e)
    if not code:
        code = f'<script src="https://leadsgenai.in/b/{slug}/reviews.js" async></script>'
    return {
        "ok": True,
        "tool": "reviews-widget",
        "context": c,
        "result": {
            "snippet": code,
            "note": "Ye code website pe paste karo — reviews auto dikhenge.",
        },
    }


# --------------------------------------------------------------------------- #
# Batch 9 — final free-stack wires (niche-pack, missed-call #24, sentiment,    #
# community-content) + evergreen ideas.                                        #
# --------------------------------------------------------------------------- #
class SentimentReq(BaseModel):
    reviews: list[str] = Field(..., min_length=1, description="Reviews/feedback lines to analyze")


@router.get("/niche-pack")
async def studio_niche_pack(client_id: str = Depends(require_customer)) -> dict:
    """Complete niche content pack — multiple ready posts for the client's niche."""
    c = _ctx(client_id)
    try:
        from app.marketing import niche_pack

        out = await niche_pack.build_pack(
            niche_key=c["niche"], business_name=c["business_name"], city=c["city"], count=2
        )
    except Exception as e:
        _fail("Niche Pack", e)
    return {"ok": True, "tool": "niche-pack", "result": out, "context": c}


@router.get("/missed-call-reply")
async def studio_missed_call_reply(client_id: str = Depends(require_customer)) -> dict:
    """Missed-call ke baad bhejne ka auto WhatsApp/SMS message (#24)."""
    c = _ctx(client_id)
    try:
        from app.marketing import missed_call

        out = await missed_call.generate_missed_call_reply(
            business_name=c["business_name"], niche=c["niche"]
        )
    except Exception as e:
        _fail("Missed Call Reply", e)
    return {"ok": True, "tool": "missed-call-reply", "result": out, "context": c}


@router.post("/sentiment", dependencies=[Depends(_GEN_LIMIT)])
async def studio_sentiment(req: SentimentReq, client_id: str = Depends(require_customer)) -> dict:
    """Reviews/feedback ka sentiment analysis — positive/negative + theme."""
    c = _ctx(client_id)
    try:
        from app.marketing import sentiment

        out = await sentiment.analyze([str(x) for x in (req.reviews or []) if str(x).strip()][:50])
    except Exception as e:
        _fail("Sentiment", e)
    return {"ok": True, "tool": "sentiment", "result": out, "context": c}


@router.get("/community-content")
async def studio_community_content(client_id: str = Depends(require_customer)) -> dict:
    """Community posts — Quora/Reddit/WhatsApp-group/LinkedIn ke liye content."""
    c = _ctx(client_id)
    try:
        from app.marketing import community_content

        out = await community_content.draft_batch(niche=c["niche"])
    except Exception as e:
        _fail("Community Content", e)
    return {"ok": True, "tool": "community-content", "result": out, "context": c}


@router.get("/evergreen-ideas")
def studio_evergreen_ideas(client_id: str = Depends(require_customer)) -> dict:
    return _pack("evergreen-ideas", client_id, "evergreen_ideas", _ctx(client_id)["niche"])


# --- 3 generator wires ---
@router.post("/coupon", dependencies=[Depends(_GEN_LIMIT)])
def studio_coupon(
    req: CouponReq = Body(default=CouponReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Coupon campaign + shareable code + WhatsApp text (1-click human send)."""
    c = _ctx(client_id)
    rec = _client_record(client_id) or {}
    try:
        from app.marketing import loyalty

        out = loyalty.create_campaign(
            client_id=str(rec.get("id") or client_id),
            title=req.title,
            kind=req.kind,
            value=req.value,
            expiry_days=req.expiry_days,
        )
    except Exception as e:
        _fail("Coupon", e)
    return {"ok": True, "tool": "coupon", "result": out, "context": c}


@router.post("/service-area", dependencies=[Depends(_GEN_LIMIT)])
async def studio_service_area(
    req: ServiceAreaReq = Body(default=ServiceAreaReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Local SEO 'niche in city' landing page (title/body/FAQ/schema)."""
    c = _ctx(client_id)
    try:
        from app.marketing import seo_pages

        out = await seo_pages.generate_page(
            niche=c["niche"], city=(req.city or c["city"] or "India")
        )
    except Exception as e:
        _fail("Service Area Page", e)
    return {"ok": True, "tool": "service-area", "result": out, "context": c}


@router.post("/service-menu", dependencies=[Depends(_GEN_LIMIT)])
async def studio_service_menu(
    req: ServiceMenuReq = Body(default=ServiceMenuReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Services/products → clean menu/price-list card (SVG) + WhatsApp text."""
    c = _ctx(client_id)
    items: list[dict] = []
    for line in (req.items_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            name, _, price = line.partition(":")
        elif "-" in line:
            name, _, price = line.partition("-")
        else:
            name, price = line, ""
        items.append({"name": name.strip()[:80], "price": price.strip()[:40]})
    if not items:
        items = [{"name": "Service 1", "price": ""}, {"name": "Service 2", "price": ""}]
    try:
        from app.marketing import catalog

        out = await catalog.build_catalog(
            business_name=c["business_name"], items=items, style=req.style
        )
    except Exception as e:
        _fail("Service Menu", e)
    return {"ok": True, "tool": "service-menu", "result": out, "context": c}


# --------------------------------------------------------------------------- #
# Capability list — drives the UI cards (so frontend stays in sync)            #
# --------------------------------------------------------------------------- #
_TOOLS = [
    {
        "key": "post",
        "icon": "📝",
        "title": "AI Social Post",
        "desc": "Ready caption + hashtags + image idea",
        "method": "POST",
        "path": "/api/customer/studio/post",
        "fields": ["occasion", "offer"],
    },
    {
        "key": "complete-post",
        "icon": "🖼️",
        "title": "Complete Post (+ AI Image)",
        "desc": "Caption + hashtags + asli AI image",
        "method": "POST",
        "path": "/api/customer/studio/complete-post",
        "fields": ["occasion", "offer"],
    },
    {
        "key": "ai-image",
        "icon": "🎨",
        "title": "AI Image",
        "desc": "Business ke liye marketing image (free)",
        "method": "POST",
        "path": "/api/customer/studio/ai-image",
        "fields": ["occasion", "offer", "style"],
    },
    {
        "key": "upi-qr",
        "icon": "💳",
        "title": "UPI Payment QR",
        "desc": "Apna scan-&-pay QR + poster",
        "method": "POST",
        "path": "/api/customer/studio/upi-qr",
        "fields": ["vpa", "amount", "note"],
    },
    {
        "key": "calendar",
        "icon": "🗓️",
        "title": "Content Calendar",
        "desc": "7-din ka post plan",
        "method": "POST",
        "path": "/api/customer/studio/calendar",
        "fields": ["days"],
    },
    {
        "key": "whatsapp",
        "icon": "💬",
        "title": "WhatsApp Pack",
        "desc": "Broadcast + status + reply lines",
        "method": "POST",
        "path": "/api/customer/studio/whatsapp",
        "fields": ["occasion", "offer"],
    },
    {
        "key": "review-reply",
        "icon": "⭐",
        "title": "Review Reply",
        "desc": "Google review ka 3-style reply",
        "method": "POST",
        "path": "/api/customer/studio/review-reply",
        "fields": ["review_text", "rating"],
    },
    {
        "key": "gbp-text",
        "icon": "🏪",
        "title": "Google Business Text",
        "desc": "GBP description + posts",
        "method": "POST",
        "path": "/api/customer/studio/gbp-text",
        "fields": ["services", "city"],
    },
    {
        "key": "ads",
        "icon": "📣",
        "title": "Ad Copy Pack",
        "desc": "Google + Meta ad headlines",
        "method": "POST",
        "path": "/api/customer/studio/ads",
        "fields": ["offer", "city"],
    },
    {
        "key": "hashtags",
        "icon": "#️⃣",
        "title": "Hashtag Research",
        "desc": "Niche ke best hashtags",
        "method": "POST",
        "path": "/api/customer/studio/hashtags",
        "fields": ["count", "city"],
    },
    {
        "key": "gbp-tips",
        "icon": "📈",
        "title": "GBP Growth Tips",
        "desc": "Google ranking tips (free)",
        "method": "GET",
        "path": "/api/customer/studio/gbp-tips",
        "fields": [],
    },
    {
        "key": "gbp-audit",
        "icon": "📊",
        "title": "GBP Audit (0–100)",
        "desc": "16 sawal → score + top-5 Hinglish fixes (saved)",
        "method": "GET",
        "path": "/api/customer/gbp/questions",
        "fields": [],
    },
    {
        "key": "festival-post",
        "icon": "🪔",
        "title": "Festival Posts",
        "desc": "Diwali/Holi/Eid auto captions",
        "method": "POST",
        "path": "/api/customer/studio/festival-post",
        "fields": ["days"],
    },
    {
        "key": "poster",
        "icon": "🖼️",
        "title": "Offer Poster",
        "desc": "Shop naam + offer + phone poster",
        "method": "POST",
        "path": "/api/customer/studio/poster",
        "fields": ["offer", "phone", "tagline"],
    },
    {
        "key": "review-request",
        "icon": "🙏",
        "title": "Review Request",
        "desc": "Review maangne ka message + link",
        "method": "POST",
        "path": "/api/customer/studio/review-request",
        "fields": [],
    },
    {
        "key": "followup-sequence",
        "icon": "🔁",
        "title": "Follow-up Sequence",
        "desc": "Day 1/3/7 WhatsApp drip",
        "method": "POST",
        "path": "/api/customer/studio/followup-sequence",
        "fields": ["lead_type"],
    },
    {
        "key": "speed-followup",
        "icon": "⚡",
        "title": "Speed-to-Lead Reply",
        "desc": "Naye lead ka instant message",
        "method": "POST",
        "path": "/api/customer/studio/speed-followup",
        "fields": [],
    },
    {
        "key": "reel-script",
        "icon": "🎬",
        "title": "Reel Script",
        "desc": "Instagram reel ka 15-30s script",
        "method": "POST",
        "path": "/api/customer/studio/reel-script",
        "fields": ["topic", "n"],
    },
    {
        "key": "win-back",
        "icon": "💌",
        "title": "Win-back Campaign",
        "desc": "Purane customers ko offer",
        "method": "POST",
        "path": "/api/customer/studio/win-back",
        "fields": ["offer"],
    },
    {
        "key": "quote-draft",
        "icon": "🧾",
        "title": "Quote / Estimate",
        "desc": "Customer ke liye price-quote draft",
        "method": "POST",
        "path": "/api/customer/studio/quote-draft",
        "fields": ["inquiry", "service", "budget_hint", "customer_name"],
    },
    {
        "key": "next-best-action",
        "icon": "🎯",
        "title": "Next Best Action",
        "desc": "Aaj kya karna hai — task list",
        "method": "GET",
        "path": "/api/customer/studio/next-best-action",
        "fields": [],
    },
    {
        "key": "competitor",
        "icon": "🔍",
        "title": "Competitor Tracker",
        "desc": "Strengths copy + gaps exploit",
        "method": "POST",
        "path": "/api/customer/studio/competitor",
        "fields": ["competitor_notes"],
    },
    {
        "key": "faq-reply",
        "icon": "🤖",
        "title": "FAQ / Reply Assistant",
        "desc": "Customer sawaal ka smart answer",
        "method": "POST",
        "path": "/api/customer/studio/faq-reply",
        "fields": ["question"],
    },
    {
        "key": "carousel",
        "icon": "🎠",
        "title": "Carousel Maker",
        "desc": "Insta carousel slides + SVG",
        "method": "POST",
        "path": "/api/customer/studio/carousel",
        "fields": ["topic", "slides"],
    },
    {
        "key": "bio-page",
        "icon": "🔗",
        "title": "Bio / Landing Copy",
        "desc": "Insta/FB/Google bios + page",
        "method": "POST",
        "path": "/api/customer/studio/bio-page",
        "fields": [],
    },
    {
        "key": "lead-magnet",
        "icon": "🧲",
        "title": "Lead Magnet",
        "desc": "Free guide/checklist for leads",
        "method": "POST",
        "path": "/api/customer/studio/lead-magnet",
        "fields": ["city"],
    },
    {
        "key": "negative-review-rescue",
        "icon": "🛟",
        "title": "Bad Review Rescue",
        "desc": "Polite damage-control reply",
        "method": "POST",
        "path": "/api/customer/studio/negative-review-rescue",
        "fields": ["review_text", "rating"],
    },
    {
        "key": "photo-reminder",
        "icon": "📸",
        "title": "Photo Reminder",
        "desc": "Weekly GBP photo ideas",
        "method": "GET",
        "path": "/api/customer/studio/photo-reminder",
        "fields": [],
    },
    {
        "key": "budget-suggest",
        "icon": "💰",
        "title": "Ad Budget Suggest",
        "desc": "Daily ad budget plan",
        "method": "POST",
        "path": "/api/customer/studio/budget-suggest",
        "fields": ["avg_deal_value", "target_leads"],
    },
    {
        "key": "customer-reminder",
        "icon": "⏰",
        "title": "Customer Reminder",
        "desc": "Appointment/renewal/payment msg",
        "method": "POST",
        "path": "/api/customer/studio/customer-reminder",
        "fields": ["kind"],
    },
    {
        "key": "appointment-assistant",
        "icon": "📅",
        "title": "Appointment Assistant",
        "desc": "Slot + booking confirmation msg",
        "method": "POST",
        "path": "/api/customer/studio/appointment-assistant",
        "fields": [],
    },
    {
        "key": "month-planner",
        "icon": "📆",
        "title": "Monthly Campaign Plan",
        "desc": "30-din ka theme + festival plan",
        "method": "POST",
        "path": "/api/customer/studio/month-planner",
        "fields": ["offer", "channel"],
    },
    {
        "key": "templates",
        "icon": "🗂️",
        "title": "Template Library",
        "desc": "Niche ke ready post/poster ideas",
        "method": "POST",
        "path": "/api/customer/studio/templates",
        "fields": ["occasion"],
    },
    {
        "key": "blog",
        "icon": "✍️",
        "title": "Blog Writer",
        "desc": "Local-SEO blog article",
        "method": "POST",
        "path": "/api/customer/studio/blog",
        "fields": ["topic", "city"],
    },
    {
        "key": "landing-audit",
        "icon": "🔎",
        "title": "Website Audit",
        "desc": "CTA/mobile/speed/trust score",
        "method": "POST",
        "path": "/api/customer/studio/landing-audit",
        "fields": ["url"],
    },
    {
        "key": "testimonial",
        "icon": "💬",
        "title": "Testimonial Poster",
        "desc": "Review → branded poster + caption",
        "method": "POST",
        "path": "/api/customer/studio/testimonial",
        "fields": ["review_text", "author", "rating"],
    },
    {
        "key": "repurpose",
        "icon": "♻️",
        "title": "Content Repurpose",
        "desc": "1 topic → 7 formats",
        "method": "POST",
        "path": "/api/customer/studio/repurpose",
        "fields": ["topic_or_url"],
    },
    {
        "key": "referral",
        "icon": "🎁",
        "title": "Referral Kit",
        "desc": "Code + message + card",
        "method": "POST",
        "path": "/api/customer/studio/referral",
        "fields": ["reward"],
    },
    {
        "key": "roi-calculator",
        "icon": "📊",
        "title": "ROI Calculator",
        "desc": "Spend vs revenue estimate",
        "method": "POST",
        "path": "/api/customer/studio/roi-calculator",
        "fields": ["monthly_spend", "avg_deal_value", "leads_per_month"],
    },
    {
        "key": "objection-handler",
        "icon": "🛡️",
        "title": "Objection Handler",
        "desc": "'Mehenga hai' ka best reply",
        "method": "POST",
        "path": "/api/customer/studio/objection-handler",
        "fields": ["objection"],
    },
    {
        "key": "best-time",
        "icon": "🕐",
        "title": "Best Time to Post",
        "desc": "Kab post/call/message karein",
        "method": "GET",
        "path": "/api/customer/studio/best-time",
        "fields": [],
    },
    {
        "key": "owner-brief",
        "icon": "📋",
        "title": "Daily Owner Brief",
        "desc": "Aaj ka summary ek nazar",
        "method": "GET",
        "path": "/api/customer/studio/owner-brief",
        "fields": [],
    },
    {
        "key": "growth-coach",
        "icon": "🚀",
        "title": "AI Growth Coach",
        "desc": "Hafte ke 3 high-impact actions",
        "method": "GET",
        "path": "/api/customer/studio/growth-coach",
        "fields": [],
    },
    {
        "key": "business-description",
        "icon": "🏷️",
        "title": "Business Description",
        "desc": "Website/GBP/social bio",
        "method": "GET",
        "path": "/api/customer/studio/business-description",
        "fields": [],
    },
    {
        "key": "service-menu",
        "icon": "📋",
        "title": "Service Menu / Price List",
        "desc": "Services → clean menu card",
        "method": "POST",
        "path": "/api/customer/studio/service-menu",
        "fields": ["items_text"],
    },
    {
        "key": "coupon",
        "icon": "🎟️",
        "title": "Coupon Generator",
        "desc": "Coupon code + expiry + WA text",
        "method": "POST",
        "path": "/api/customer/studio/coupon",
        "fields": ["title", "value"],
    },
    {
        "key": "brand-palette",
        "icon": "🎨",
        "title": "Brand Palette",
        "desc": "Colors + font suggestion",
        "method": "GET",
        "path": "/api/customer/studio/brand-palette",
        "fields": [],
    },
    {
        "key": "customer-avatar",
        "icon": "🧑",
        "title": "Customer Avatar",
        "desc": "Ideal customer profile",
        "method": "GET",
        "path": "/api/customer/studio/customer-avatar",
        "fields": [],
    },
    {
        "key": "seasonal-offers",
        "icon": "🌦️",
        "title": "Seasonal Offers",
        "desc": "Season-wise offer ideas",
        "method": "GET",
        "path": "/api/customer/studio/seasonal-offers",
        "fields": [],
    },
    {
        "key": "local-event-campaign",
        "icon": "🎪",
        "title": "Local Event Campaign",
        "desc": "City event tie-in ideas",
        "method": "GET",
        "path": "/api/customer/studio/local-event-campaign",
        "fields": [],
    },
    {
        "key": "case-study",
        "icon": "📖",
        "title": "Case Study",
        "desc": "Customer success story",
        "method": "GET",
        "path": "/api/customer/studio/case-study",
        "fields": [],
    },
    {
        "key": "grid-planner",
        "icon": "🔲",
        "title": "Instagram Grid Plan",
        "desc": "9-grid feed layout",
        "method": "GET",
        "path": "/api/customer/studio/grid-planner",
        "fields": [],
    },
    {
        "key": "highlights",
        "icon": "⭕",
        "title": "Story Highlights",
        "desc": "Highlight categories",
        "method": "GET",
        "path": "/api/customer/studio/highlights",
        "fields": [],
    },
    {
        "key": "voiceover",
        "icon": "🎙️",
        "title": "Voiceover Script",
        "desc": "Hinglish reel/ad VO",
        "method": "POST",
        "path": "/api/customer/studio/voiceover",
        "fields": ["topic"],
    },
    {
        "key": "youtube-metadata",
        "icon": "▶️",
        "title": "YouTube Metadata",
        "desc": "Title + tags + description",
        "method": "POST",
        "path": "/api/customer/studio/youtube-metadata",
        "fields": ["topic"],
    },
    {
        "key": "faq-page",
        "icon": "❔",
        "title": "FAQ Page",
        "desc": "Website FAQ Q&A",
        "method": "GET",
        "path": "/api/customer/studio/faq-page",
        "fields": [],
    },
    {
        "key": "service-area",
        "icon": "📍",
        "title": "Service Area Page",
        "desc": "'Niche in city' SEO page",
        "method": "POST",
        "path": "/api/customer/studio/service-area",
        "fields": ["city"],
    },
    {
        "key": "schema-markup",
        "icon": "🧩",
        "title": "Schema Markup",
        "desc": "LocalBusiness JSON-LD",
        "method": "GET",
        "path": "/api/customer/studio/schema-markup",
        "fields": [],
    },
    {
        "key": "conversion-tracking",
        "icon": "🎯",
        "title": "Tracking Setup Guide",
        "desc": "GA/pixel/UTM checklist",
        "method": "GET",
        "path": "/api/customer/studio/conversion-tracking",
        "fields": [],
    },
    {
        "key": "lost-lead-reason",
        "icon": "🕵️",
        "title": "Lost Lead Reasons",
        "desc": "Kyu convert nahi hua + fix",
        "method": "GET",
        "path": "/api/customer/studio/lost-lead-reason",
        "fields": [],
    },
    {
        "key": "complaint-recovery",
        "icon": "🩹",
        "title": "Complaint Recovery",
        "desc": "Angry customer flow",
        "method": "GET",
        "path": "/api/customer/studio/complaint-recovery",
        "fields": [],
    },
    {
        "key": "ugc-request",
        "icon": "📷",
        "title": "UGC Request",
        "desc": "Customer photo/video maango",
        "method": "GET",
        "path": "/api/customer/studio/ugc-request",
        "fields": [],
    },
    {
        "key": "ai-inbox",
        "icon": "📥",
        "title": "AI Inbox",
        "desc": "Inquiries intent+urgency se sorted",
        "method": "GET",
        "path": "/api/customer/studio/ai-inbox",
        "fields": [],
    },
    {
        "key": "re-engagement",
        "icon": "🔄",
        "title": "Re-engagement",
        "desc": "Cold leads + 1-click win-back",
        "method": "GET",
        "path": "/api/customer/studio/re-engagement",
        "fields": [],
    },
    {
        "key": "listings",
        "icon": "🗺️",
        "title": "Listings / NAP Check",
        "desc": "Directory checklist + score",
        "method": "GET",
        "path": "/api/customer/studio/listings",
        "fields": [],
    },
    {
        "key": "website-widget",
        "icon": "🧷",
        "title": "Website Widget",
        "desc": "Embed lead-capture code",
        "method": "GET",
        "path": "/api/customer/studio/website-widget",
        "fields": [],
    },
    {
        "key": "aeo-checklist",
        "icon": "🤖",
        "title": "Get Found by AI",
        "desc": "ChatGPT/Gemini optimization",
        "method": "GET",
        "path": "/api/customer/studio/aeo-checklist",
        "fields": [],
    },
    {
        "key": "whatsapp-catalog",
        "icon": "🛒",
        "title": "WhatsApp Catalog",
        "desc": "Product-discovery flow",
        "method": "GET",
        "path": "/api/customer/studio/whatsapp-catalog",
        "fields": [],
    },
    {
        "key": "click-to-whatsapp-ad",
        "icon": "📲",
        "title": "Click-to-WhatsApp Ad",
        "desc": "Meta WA ad copy",
        "method": "GET",
        "path": "/api/customer/studio/click-to-whatsapp-ad",
        "fields": [],
    },
    {
        "key": "sms-pack",
        "icon": "✉️",
        "title": "SMS Pack",
        "desc": "DLT-aware SMS templates",
        "method": "GET",
        "path": "/api/customer/studio/sms-pack",
        "fields": [],
    },
    {
        "key": "nps-survey",
        "icon": "📈",
        "title": "NPS / CSAT Survey",
        "desc": "Feedback survey builder",
        "method": "GET",
        "path": "/api/customer/studio/nps-survey",
        "fields": [],
    },
    {
        "key": "loyalty-program",
        "icon": "🏅",
        "title": "Loyalty Program",
        "desc": "Points + gamified design",
        "method": "GET",
        "path": "/api/customer/studio/loyalty-program",
        "fields": [],
    },
    {
        "key": "rank-check-guide",
        "icon": "📡",
        "title": "Rank Check Guide",
        "desc": "DIY Google rank tracking",
        "method": "GET",
        "path": "/api/customer/studio/rank-check-guide",
        "fields": [],
    },
    {
        "key": "booking-link",
        "icon": "🗓️",
        "title": "Booking Setup",
        "desc": "Booking link + messages",
        "method": "GET",
        "path": "/api/customer/studio/booking-link",
        "fields": [],
    },
    {
        "key": "newsletter-outline",
        "icon": "📰",
        "title": "Newsletter Outline",
        "desc": "Monthly email plan",
        "method": "GET",
        "path": "/api/customer/studio/newsletter-outline",
        "fields": [],
    },
    {
        "key": "meme",
        "icon": "😂",
        "title": "Meme Maker",
        "desc": "Relatable Hinglish meme + SVG",
        "method": "POST",
        "path": "/api/customer/studio/meme",
        "fields": ["topic"],
    },
    {
        "key": "multilang-post",
        "icon": "🌐",
        "title": "Regional Language Post",
        "desc": "Caption → Hindi/Marathi/Tamil…",
        "method": "POST",
        "path": "/api/customer/studio/multilang-post",
        "fields": ["caption"],
    },
    {
        "key": "trends",
        "icon": "📊",
        "title": "Trending Topics",
        "desc": "Niche ke trend post-angles",
        "method": "GET",
        "path": "/api/customer/studio/trends",
        "fields": [],
    },
    {
        "key": "partnerships",
        "icon": "🤝",
        "title": "Partnership Pitch",
        "desc": "Co-marketing pitch drafts",
        "method": "GET",
        "path": "/api/customer/studio/partnerships",
        "fields": [],
    },
    {
        "key": "business-card",
        "icon": "💳",
        "title": "Digital Business Card",
        "desc": "Shareable HTML card",
        "method": "GET",
        "path": "/api/customer/studio/business-card",
        "fields": [],
    },
    {
        "key": "email-signature",
        "icon": "✍️",
        "title": "Email Signature",
        "desc": "Branded email signature",
        "method": "GET",
        "path": "/api/customer/studio/email-signature",
        "fields": [],
    },
    {
        "key": "reviews-widget",
        "icon": "⭐",
        "title": "Reviews Widget",
        "desc": "Website pe reviews dikhaao",
        "method": "GET",
        "path": "/api/customer/studio/reviews-widget",
        "fields": [],
    },
    {
        "key": "niche-pack",
        "icon": "📦",
        "title": "Niche Content Pack",
        "desc": "Multiple ready posts",
        "method": "GET",
        "path": "/api/customer/studio/niche-pack",
        "fields": [],
    },
    {
        "key": "missed-call-reply",
        "icon": "📵",
        "title": "Missed-Call Reply",
        "desc": "Auto message after missed call",
        "method": "GET",
        "path": "/api/customer/studio/missed-call-reply",
        "fields": [],
    },
    {
        "key": "sentiment",
        "icon": "🧠",
        "title": "Review Sentiment",
        "desc": "Reviews ka sentiment analysis",
        "method": "POST",
        "path": "/api/customer/studio/sentiment",
        "fields": ["reviews"],
    },
    {
        "key": "community-content",
        "icon": "🗣️",
        "title": "Community Content",
        "desc": "Quora/Reddit/group posts",
        "method": "GET",
        "path": "/api/customer/studio/community-content",
        "fields": [],
    },
    {
        "key": "evergreen-ideas",
        "icon": "🌲",
        "title": "Evergreen Ideas",
        "desc": "Kabhi bhi repost-able posts",
        "method": "GET",
        "path": "/api/customer/studio/evergreen-ideas",
        "fields": [],
    },
]


@router.get("/tools")
def studio_tools(client_id: str = Depends(require_customer)) -> dict:
    """List of available studio tools + this client's resolved context."""
    return {"ok": True, "count": len(_TOOLS), "tools": _TOOLS, "context": _ctx(client_id)}
