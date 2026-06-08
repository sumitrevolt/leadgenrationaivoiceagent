"""
Marketing API — Dhanda.app-style AI marketing tools (FREE stack).
=================================================================

  GET  /api/marketing/packages         — pricing packages (PUBLIC — landing page)
  POST /api/marketing/post             — AI social post (caption+hashtags+image idea)
  GET  /api/marketing/gbp-tips         — Google Business Profile checklist (static)
  POST /api/marketing/calendar         — N-din content calendar
  GET  /api/marketing/audit/questions  — GBP self-audit ke 16 sawal
  POST /api/marketing/audit/score      — audit answers → 0-100 score + fixes
  POST /api/marketing/review-reply     — review ke 3 Hinglish replies
  GET  /api/marketing/festivals        — upcoming Indian festivals (static calendar)
  POST /api/marketing/festival-posts   — nearest festivals ke ready captions
  GET  /api/marketing/poster/templates — SVG poster templates list
  POST /api/marketing/poster           — 1080x1080 SVG poster generate
  POST /api/marketing/whatsapp-pack    — broadcast + status + reply pack
  POST /api/marketing/competitor       — competitor notes → copy/exploit/action tips
  POST /api/marketing/review-kit       — review-collection kit (QR + card + messages)
  GET  /api/marketing/report           — monthly HTML marketing report
  POST /api/marketing/reactivation     — purane customers ke win-back WA messages
  POST /api/marketing/drip             — 4-step WhatsApp nurture sequence
  POST /api/marketing/brand/{id}       — per-client brand profile save
  GET  /api/marketing/brand/{id}       — saved brand profile
  POST /api/marketing/crm/{id}/customers — customers add (phone dedupe)
  GET  /api/marketing/crm/{id}/customers — customers list (?tag=)
  GET  /api/marketing/crm/{id}/wishes  — aaj ke birthday/anniversary wishes
  POST /api/marketing/upi-kit          — UPI QR + payment slip + WA message
  POST /api/marketing/upi-qr           — UPI payment QR poster SVG
  POST /api/marketing/missed-call-reply — missed-call auto-reply message
  POST /api/marketing/catalog          — price-list SVG + WA catalog text
  POST /api/marketing/ads-pack         — Google RSA + Meta ad copy pack
  POST /api/marketing/reels            — n Reels scripts (hook/body/cta/tags)
  GET  /api/marketing/lead-scores      — inquiries ka hot/warm/cold scoring
  POST /api/marketing/gbp-texts        — GBP description + services + posts
  POST /api/marketing/content-pack     — 1-click monthly client deliverable pack
  GET  /api/marketing/blog             — published SEO articles list
  POST /api/marketing/blog/run         — publish n new niche×city articles
  GET  /api/marketing/blog/{slug}      — one article (full content)
  POST /api/marketing/referral         — Refer & Earn kit (code + WA + link + card)
  GET  /api/marketing/referral/stats   — referral usage counts (?code=)
  POST /api/marketing/evergreen/{id}   — recycle old top posts into queue

Sab admin-auth (sirf /packages public hai — static pricing data, koi secret
nahi). Generator functions kabhi raise nahi karte (template
fallback built-in) — phir bhi unexpected par 500 + detail dete hain.
Har generation team-log me jaata hai (isha) — import-safe, best-effort.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.marketing import (
    ads_copy,
    brand_kit,
    catalog,
    competitor,
    content_pack,
    crm_lite,
    drip,
    evergreen,
    festivals,
    gbp_audit,
    gbp_text,
    lead_scoring,
    missed_call,
    monthly_report,
    packages,
    post_generator,
    posters,
    reactivation,
    reels,
    referral_kit,
    review_kit,
    review_replies,
    seo_blog,
    upi_kit,
    upi_qr,
    whatsapp_pack,
)
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/marketing", tags=["Marketing"])


def _log_isha(action: str, detail: str) -> None:
    """Team activity log (best-effort — kabhi request fail nahi karata)."""
    try:
        from app.platform.team import log_event

        log_event("isha", action, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class PostRequest(BaseModel):
    """Social post generation request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    occasion: str = Field("", max_length=80)
    offer: str = Field("", max_length=200)
    language: str = Field("hinglish", max_length=30)


class CalendarRequest(BaseModel):
    """Content calendar request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    days: int = Field(7, ge=1, le=30)


class AuditScoreRequest(BaseModel):
    """GBP audit answers: {question_id: option_index}."""

    answers: dict[str, int] = Field(default_factory=dict)


class ReviewReplyRequest(BaseModel):
    """Review reply generation request."""

    review_text: str = Field(..., min_length=1, max_length=2000)
    rating: float | None = Field(None, ge=0, le=5)
    business_name: str = Field("", max_length=120)
    tone: str = Field("professional", max_length=40)


class FestivalPostsRequest(BaseModel):
    """Festival posts request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    days: int = Field(45, ge=1, le=730)


class PosterRequest(BaseModel):
    """SVG poster generation request (brand colors optional — brand_kit se)."""

    template_id: str = Field(..., min_length=1, max_length=60)
    business_name: str = Field(..., min_length=1, max_length=120)
    tagline: str = Field("", max_length=160)
    offer: str = Field("", max_length=160)
    phone: str = Field("", max_length=40)
    festival: str = Field("", max_length=80)
    client_id: str = Field("", max_length=64)  # set => saved brand auto-apply
    brand_primary: str = Field("", max_length=10)  # #RRGGBB
    brand_accent: str = Field("", max_length=10)  # #RRGGBB


class WhatsAppPackRequest(BaseModel):
    """WhatsApp broadcast pack request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    occasion: str = Field("", max_length=80)
    offer: str = Field("", max_length=200)


class CompetitorRequest(BaseModel):
    """Competitor comparison request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    competitor_notes: str = Field(..., min_length=1, max_length=4000)


class ReviewKitRequest(BaseModel):
    """Review-collection kit request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    place_query: str = Field("", max_length=200)


class ReactivationCustomer(BaseModel):
    """Ek purana customer (win-back ke liye)."""

    name: str = Field("", max_length=80)
    phone: str = Field("", max_length=20)
    last_visit: str = Field("", max_length=40)
    note: str = Field("", max_length=200)


class ReactivationRequest(BaseModel):
    """Database-reactivation campaign request (cap 50 customers)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    offer: str = Field("", max_length=200)
    customers: list[ReactivationCustomer] = Field(default_factory=list, max_length=50)


class DripRequest(BaseModel):
    """WhatsApp nurture sequence request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    lead_type: str = Field("new_inquiry", max_length=30)


class UPIQRRequest(BaseModel):
    """UPI QR Code poster request."""

    vpa: str = Field(..., min_length=3, max_length=120)
    business_name: str = Field(..., min_length=1, max_length=120)
    amount: float = Field(0.0, ge=0.0, le=100000.0)
    brand_primary: str = Field("", max_length=10)
    brand_accent: str = Field("", max_length=10)


class MissedCallRequest(BaseModel):
    """Missed call auto-reply request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    callback_url: str = Field("", max_length=200)


class BrandColors(BaseModel):
    """Brand colors (#RRGGBB; invalid => ignore)."""

    primary: str = Field("", max_length=10)
    accent: str = Field("", max_length=10)


class BrandRequest(BaseModel):
    """Per-client brand profile."""

    business_name: str = Field("", max_length=120)
    tagline: str = Field("", max_length=160)
    phone: str = Field("", max_length=40)
    colors: BrandColors = Field(default_factory=BrandColors)
    tone: str = Field("", max_length=40)
    logo_text: str = Field("", max_length=40)


class CrmCustomer(BaseModel):
    """CRM-lite customer row."""

    name: str = Field("", max_length=80)
    phone: str = Field(..., min_length=5, max_length=20)
    birthday: str = Field("", max_length=20)  # YYYY-MM-DD ya MM-DD
    anniversary: str = Field("", max_length=20)  # YYYY-MM-DD ya MM-DD
    tags: list[str] = Field(default_factory=list, max_length=10)


class CrmCustomersRequest(BaseModel):
    """CRM customers add request."""

    customers: list[CrmCustomer] = Field(default_factory=list, max_length=500)


class UpiKitRequest(BaseModel):
    """UPI payment kit request (vpa = naam@bank)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    vpa: str = Field(..., min_length=3, max_length=100)
    amount: float | None = Field(None, ge=0, le=10_000_000)
    note: str = Field("", max_length=100)


class CatalogItem(BaseModel):
    """Catalog ka ek item (price string flexible: '249' / '₹249')."""

    name: str = Field(..., min_length=1, max_length=80)
    price: str = Field("", max_length=20)
    desc: str = Field("", max_length=160)


class CatalogRequest(BaseModel):
    """Price-list catalog request (12 se zyada items trim ho jaate hain)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    items: list[CatalogItem] = Field(default_factory=list, max_length=24)
    style: str = Field("price_list", max_length=30)


class AdsPackRequest(BaseModel):
    """Google RSA + Meta ads copy request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    offer: str = Field("", max_length=200)
    city: str = Field("", max_length=80)


class ReelsRequest(BaseModel):
    """Reels scripts request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    topic: str = Field("", max_length=120)
    n: int = Field(3, ge=1, le=6)


class GbpTextsRequest(BaseModel):
    """GBP description + services + posts request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    city: str = Field("", max_length=80)
    services: list[str] = Field(default_factory=list, max_length=12)


class ContentPackRequest(BaseModel):
    """Monthly client content pack request (client_id => saved brand auto-apply)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    client_id: str = Field("", max_length=64)
    offer: str = Field("", max_length=200)
    phone: str = Field("", max_length=40)


class BlogRunRequest(BaseModel):
    """Programmatic SEO blog — kitne naye articles publish karne hain."""

    n: int = Field(3, ge=1, le=25)


class ReferralRequest(BaseModel):
    """Refer & Earn kit request (brand colors optional — card gradient)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    reward: str = Field("10% off", max_length=80)
    referrer_name: str = Field("", max_length=80)
    brand_primary: str = Field("", max_length=10)  # #RRGGBB
    brand_accent: str = Field("", max_length=10)  # #RRGGBB


class EvergreenRequest(BaseModel):
    """Evergreen recycle request (client_id path se aata hai)."""

    business_name: str = Field("", max_length=120)
    niche: str = Field("", max_length=80)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/packages")
async def get_marketing_packages():
    """Pricing packages (PUBLIC — NO auth; landing page isse fetch karta hai)."""
    try:
        return {"packages": packages.get_packages()}
    except Exception as e:
        logger.error(f"Packages lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Packages lookup failed: {e}")


@router.post("/post")
async def generate_marketing_post(
    req: PostRequest,
    current_user: User = Depends(require_admin),
):
    """Ready-to-copy social post banao (free LLM chain, template fallback)."""
    try:
        result = await post_generator.generate_post(
            business_name=req.business_name,
            niche=req.niche,
            occasion=req.occasion,
            offer=req.offer,
            language=req.language,
        )
        _log_isha("post_generated", f"{req.business_name} ({req.niche or 'general'})")
        return result
    except Exception as e:
        logger.error(f"Marketing post generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Post generation failed: {e}")


class AiImageRequest(BaseModel):
    """AI image (Pollinations free) — phrase se asli marketing image."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    occasion: str = Field("", max_length=120)
    offer: str = Field("", max_length=200)
    style: str = Field("vibrant professional", max_length=80)
    width: int = Field(1024, ge=256, le=1536)
    height: int = Field(1024, ge=256, le=1536)


@router.post("/ai-image")
async def generate_ai_image(
    req: AiImageRequest,
    current_user: User = Depends(require_admin),
):
    """AI image generation (Pollinations Flux, FREE) — real marketing-image URL from a prompt."""
    try:
        from app.marketing import ai_image

        result = await ai_image.marketing_image(
            req.business_name, req.niche, req.occasion, req.offer, req.style, req.width, req.height
        )
        _log_isha("ai_image", f"{req.business_name} ({req.occasion or req.niche})")
        return result
    except Exception as e:
        logger.error(f"AI image generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI image failed: {e}")


class CompletePostRequest(BaseModel):
    """Predis-style: ek phrase se complete post (caption + hashtags + AI image)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    occasion: str = Field("", max_length=120)
    offer: str = Field("", max_length=200)
    language: str = Field("hinglish", max_length=40)
    width: int = Field(1024, ge=256, le=1536)
    height: int = Field(1024, ge=256, le=1536)


@router.post("/complete-post")
async def generate_complete_post(
    req: CompletePostRequest,
    current_user: User = Depends(require_admin),
):
    """COMPLETE post ek phrase se — caption + hashtags + asli AI image (free), one shot."""
    try:
        import asyncio

        from app.marketing import ai_image

        post, img = await asyncio.gather(
            post_generator.generate_post(
                business_name=req.business_name, niche=req.niche,
                occasion=req.occasion, offer=req.offer, language=req.language,
            ),
            ai_image.marketing_image(
                req.business_name, req.niche, req.occasion, req.offer,
                width=req.width, height=req.height,
            ),
        )
        _log_isha("complete_post", f"{req.business_name} ({req.occasion or req.niche})")
        return {**post, "image_url": img.get("url", ""), "image_prompt": img.get("prompt", "")}
    except Exception as e:
        logger.error(f"Complete post failed: {e}")
        raise HTTPException(status_code=500, detail=f"Complete post failed: {e}")


class VariationsRequest(BaseModel):
    """A/B testing ke liye N caption variations."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    occasion: str = Field("", max_length=120)
    offer: str = Field("", max_length=200)
    language: str = Field("hinglish", max_length=40)
    count: int = Field(3, ge=2, le=4)


@router.post("/post-variations")
async def generate_post_variations(
    req: VariationsRequest,
    current_user: User = Depends(require_admin),
):
    """N alag-alag post variations (A/B test) — ek saath generate."""
    try:
        import asyncio

        posts = await asyncio.gather(
            *[
                post_generator.generate_post(
                    business_name=req.business_name, niche=req.niche,
                    occasion=req.occasion, offer=req.offer, language=req.language,
                )
                for _ in range(req.count)
            ]
        )
        _log_isha("post_variations", f"{req.business_name} x{req.count}")
        return {"count": len(posts), "variations": posts}
    except Exception as e:
        logger.error(f"Post variations failed: {e}")
        raise HTTPException(status_code=500, detail=f"Variations failed: {e}")


class ChatbotRequest(BaseModel):
    """Customer-facing FAQ + lead-capture chatbot (client-KB grounded)."""

    question: str = Field(..., min_length=1, max_length=500)
    client_id: str = Field("", max_length=64)
    niche: str = Field("general", max_length=80)


@router.post("/chatbot")
async def marketing_chatbot(req: ChatbotRequest, current_user: User = Depends(require_admin)):
    """Client ka website/WhatsApp FAQ + lead-capture bot (KB-grounded)."""
    try:
        from app.marketing import chatbot

        result = await chatbot.reply(req.question, req.client_id, req.niche)
        _log_isha("chatbot", f"{req.client_id or req.niche}: {req.question[:40]}")
        return result
    except Exception as e:
        logger.error(f"Chatbot failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chatbot failed: {e}")


class SentimentRequest(BaseModel):
    """Reviews/feedback list → sentiment + themes."""

    texts: list[str] = Field(..., min_length=1, max_length=50)


@router.post("/sentiment")
async def marketing_sentiment(req: SentimentRequest, current_user: User = Depends(require_admin)):
    """Reviews/feedback ka sentiment + themes + action."""
    try:
        from app.marketing import sentiment

        result = await sentiment.analyze(req.texts)
        _log_isha("sentiment", f"{len(req.texts)} texts")
        return result
    except Exception as e:
        logger.error(f"Sentiment failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sentiment failed: {e}")


class HashtagsRequest(BaseModel):
    """Trending hashtags + best-time-to-post."""

    niche: str = Field("general", max_length=80)
    city: str = Field("", max_length=80)
    count: int = Field(15, ge=5, le=30)


@router.post("/hashtags")
async def marketing_hashtags(req: HashtagsRequest, current_user: User = Depends(require_admin)):
    """Niche+city trending hashtags + best posting times."""
    try:
        from app.marketing import hashtags

        result = await hashtags.research(req.niche, req.city, req.count)
        _log_isha("hashtags", f"{req.niche} {req.city}")
        return result
    except Exception as e:
        logger.error(f"Hashtags failed: {e}")
        raise HTTPException(status_code=500, detail=f"Hashtags failed: {e}")


class LogoRequest(BaseModel):
    """AI logo generation (Pollinations free)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    style: str = Field("modern minimalist", max_length=80)


@router.post("/brand-logo")
async def marketing_brand_logo(req: LogoRequest, current_user: User = Depends(require_admin)):
    """AI logo image URL (Pollinations free)."""
    try:
        from app.marketing import ai_image

        url = ai_image.logo_url(req.business_name, req.niche, req.style)
        _log_isha("brand_logo", req.business_name)
        return {"url": url, "business_name": req.business_name, "provider": "pollinations-flux"}
    except Exception as e:
        logger.error(f"Logo failed: {e}")
        raise HTTPException(status_code=500, detail=f"Logo failed: {e}")


class ScheduleRequest(BaseModel):
    """Content ko ek date ke liye schedule karna (Buffer-style)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    date: str = Field("", max_length=10)  # YYYY-MM-DD
    occasion: str = Field("", max_length=120)
    offer: str = Field("", max_length=200)
    channel: str = Field("instagram", max_length=40)
    client_id: str = Field("", max_length=64)


@router.post("/schedule")
async def schedule_content(req: ScheduleRequest, current_user: User = Depends(require_admin)):
    """Content ko ek future date ke liye schedule karo."""
    try:
        from app.marketing import content_schedule

        item = content_schedule.schedule(
            req.business_name, req.niche, req.date, req.occasion, req.offer, req.channel, req.client_id
        )
        _log_isha("schedule_add", f"{req.business_name} @ {item.get('date')}")
        return item
    except Exception as e:
        logger.error(f"Schedule failed: {e}")
        raise HTTPException(status_code=500, detail=f"Schedule failed: {e}")


@router.get("/schedule")
async def get_scheduled(status: str = "", current_user: User = Depends(require_admin)):
    """Scheduled/ready content ki list."""
    try:
        from app.marketing import content_schedule

        return {"items": content_schedule.list_scheduled(status or None)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule list failed: {e}")


@router.post("/schedule/run")
async def run_schedule(current_user: User = Depends(require_admin)):
    """Due scheduled content abhi prepare karo (manual trigger)."""
    try:
        from app.marketing import content_schedule

        res = await content_schedule.run_due()
        _log_isha("schedule_run", str(res))
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schedule run failed: {e}")


class FestivalScheduleRequest(BaseModel):
    """Upcoming Indian festivals ko content scheduler me auto-queue karna."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    months_ahead: int = Field(3, ge=1, le=12)
    client_id: str = Field("", max_length=64)


@router.get("/festivals")
async def list_festivals(months_ahead: int = 6, current_user: User = Depends(require_admin)):
    """Upcoming Indian festivals (auto-marketing calendar — Diwali/Holi/Rakhi…)."""
    try:
        from app.marketing import festival_calendar

        return {"festivals": festival_calendar.upcoming(months_ahead=months_ahead)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Festivals failed: {e}")


@router.post("/festival-autoschedule")
async def festival_autoschedule(req: FestivalScheduleRequest, current_user: User = Depends(require_admin)):
    """Upcoming festivals ko content scheduler me ek-click auto-queue (dup-safe)."""
    try:
        from app.marketing import festival_calendar

        res = festival_calendar.autoschedule(req.business_name, req.niche, req.months_ahead, req.client_id)
        _log_isha("festival_autoschedule", f"{req.business_name}: {res.get('scheduled')} queued")
        return res
    except Exception as e:
        logger.error(f"Festival autoschedule failed: {e}")
        raise HTTPException(status_code=500, detail=f"Festival autoschedule failed: {e}")


@router.get("/gbp-tips")
async def get_gbp_tips(
    niche: str = "general",
    current_user: User = Depends(require_admin),
):
    """Google Business Profile improvement checklist (static, researched)."""
    try:
        return {"niche": niche or "general", "tips": post_generator.gbp_tips(niche)}
    except Exception as e:
        logger.error(f"GBP tips failed: {e}")
        raise HTTPException(status_code=500, detail=f"GBP tips failed: {e}")


@router.post("/calendar")
async def generate_content_calendar(
    req: CalendarRequest,
    current_user: User = Depends(require_admin),
):
    """N-din ka content calendar (1 LLM call, deterministic fallback)."""
    try:
        calendar = await post_generator.content_calendar(
            business_name=req.business_name,
            niche=req.niche,
            days=req.days,
        )
        _log_isha(
            "calendar_generated",
            f"{req.business_name} ({req.niche or 'general'}, {req.days} days)",
        )
        return {
            "business_name": req.business_name,
            "niche": req.niche or "general",
            "days": req.days,
            "calendar": calendar,
        }
    except Exception as e:
        logger.error(f"Content calendar generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Calendar generation failed: {e}")


# --------------------------------------------------------------------------- #
# GBP self-audit (no Google API — owner ke jawab se score)
# --------------------------------------------------------------------------- #


@router.get("/audit/questions")
async def get_audit_questions(current_user: User = Depends(require_admin)):
    """GBP self-audit ke 16 sawal (Hinglish, multiple-choice)."""
    try:
        return {"questions": gbp_audit.AUDIT_QUESTIONS, "total": len(gbp_audit.AUDIT_QUESTIONS)}
    except Exception as e:
        logger.error(f"Audit questions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Audit questions failed: {e}")


@router.post("/audit/score")
async def score_gbp_audit(
    req: AuditScoreRequest,
    current_user: User = Depends(require_admin),
):
    """Audit answers → weighted 0-100 score + grade + top-5 Hinglish fixes."""
    try:
        result = gbp_audit.score_audit(req.answers)
        _log_isha(
            "gbp_audit_scored",
            f"score={result.get('score')} grade={result.get('grade')} "
            f"({result.get('answered')}/{result.get('total_questions')} answered)",
        )
        return result
    except Exception as e:
        logger.error(f"Audit scoring failed: {e}")
        raise HTTPException(status_code=500, detail=f"Audit scoring failed: {e}")


# --------------------------------------------------------------------------- #
# Review replies
# --------------------------------------------------------------------------- #


@router.post("/review-reply")
async def generate_review_replies(
    req: ReviewReplyRequest,
    current_user: User = Depends(require_admin),
):
    """Ek review ke liye 3 ready Hinglish replies (short/medium/detailed)."""
    try:
        result = await review_replies.generate_replies(
            review_text=req.review_text,
            rating=req.rating,
            business_name=req.business_name,
            tone=req.tone,
        )
        _log_isha(
            "review_reply_generated",
            f"{req.business_name or 'business'} (rating={req.rating}, "
            f"sentiment={result.get('sentiment')})",
        )
        return result
    except Exception as e:
        logger.error(f"Review reply generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Review reply failed: {e}")


# --------------------------------------------------------------------------- #
# Festivals
# --------------------------------------------------------------------------- #


@router.get("/festivals")
async def get_festivals(
    days: int = 45,
    current_user: User = Depends(require_admin),
):
    """Aaj se agle N din ke Indian festivals (static curated calendar)."""
    try:
        return {"days": days, "festivals": festivals.upcoming(days)}
    except Exception as e:
        logger.error(f"Festivals lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Festivals lookup failed: {e}")


@router.post("/festival-posts")
async def generate_festival_posts(
    req: FestivalPostsRequest,
    current_user: User = Depends(require_admin),
):
    """Nearest festivals ke ready Hinglish captions (1 LLM call, template fallback)."""
    try:
        result = await festivals.festival_posts(
            business_name=req.business_name,
            niche=req.niche,
            days=req.days,
        )
        _log_isha(
            "festival_posts_generated",
            f"{req.business_name} ({req.niche or 'general'}, "
            f"{len(result.get('posts', []))} posts)",
        )
        return result
    except Exception as e:
        logger.error(f"Festival posts generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Festival posts failed: {e}")


# --------------------------------------------------------------------------- #
# SVG posters (AdBanao-lite)
# --------------------------------------------------------------------------- #


@router.get("/poster/templates")
async def get_poster_templates(current_user: User = Depends(require_admin)):
    """Available 1080x1080 SVG poster templates."""
    try:
        return {"templates": posters.list_templates()}
    except Exception as e:
        logger.error(f"Poster templates failed: {e}")
        raise HTTPException(status_code=500, detail=f"Poster templates failed: {e}")


@router.post("/poster")
async def generate_svg_poster(
    req: PosterRequest,
    current_user: User = Depends(require_admin),
):
    """Inline SVG poster banao (browser render / PNG convert ready).

    client_id set ho to saved brand (naam/tagline/phone/colors) auto-merge
    hota hai; explicit request values hamesha jeet-ti hain.
    """
    try:
        args = {
            "template_id": req.template_id,
            "business_name": req.business_name,
            "tagline": req.tagline,
            "offer": req.offer,
            "phone": req.phone,
            "festival": req.festival,
            "brand_primary": req.brand_primary,
            "brand_accent": req.brand_accent,
        }
        if req.client_id.strip():
            args = brand_kit.apply_brand_to_poster_args(req.client_id, args)
        result = posters.generate_poster(**args)
        _log_isha("poster_generated", f"{req.business_name} (template={result.get('template')})")
        return result
    except Exception as e:
        logger.error(f"Poster generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Poster generation failed: {e}")


# --------------------------------------------------------------------------- #
# WhatsApp pack
# --------------------------------------------------------------------------- #


@router.post("/whatsapp-pack")
async def generate_whatsapp_pack(
    req: WhatsAppPackRequest,
    current_user: User = Depends(require_admin),
):
    """WhatsApp broadcast(2) + status(3) + reply-templates(2) ek saath."""
    try:
        result = await whatsapp_pack.broadcast_pack(
            business_name=req.business_name,
            niche=req.niche,
            occasion=req.occasion,
            offer=req.offer,
        )
        _log_isha("whatsapp_pack_generated", f"{req.business_name} ({req.niche or 'general'})")
        return result
    except Exception as e:
        logger.error(f"WhatsApp pack generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"WhatsApp pack failed: {e}")


# --------------------------------------------------------------------------- #
# Competitor comparison
# --------------------------------------------------------------------------- #


@router.post("/competitor")
async def generate_competitor_tips(
    req: CompetitorRequest,
    current_user: User = Depends(require_admin),
):
    """Competitor notes → strengths-to-copy + gaps-to-exploit + 3-step action plan."""
    try:
        result = await competitor.compare_tips(
            business_name=req.business_name,
            niche=req.niche,
            competitor_notes=req.competitor_notes,
        )
        _log_isha("competitor_tips_generated", f"{req.business_name} ({req.niche or 'general'})")
        return result
    except Exception as e:
        logger.error(f"Competitor tips generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Competitor tips failed: {e}")


# --------------------------------------------------------------------------- #
# Review-collection kit (Birdeye-lite: QR + counter card + ask messages)
# --------------------------------------------------------------------------- #


@router.post("/review-kit")
async def generate_review_kit(
    req: ReviewKitRequest,
    current_user: User = Depends(require_admin),
):
    """Review maangne ka poora kit: links + QR SVG + counter card + WA/SMS lines."""
    try:
        result = await review_kit.full_kit(
            business_name=req.business_name,
            place_query=req.place_query,
        )
        _log_isha("review_kit_generated", f"{req.business_name}")
        return result
    except Exception as e:
        logger.error(f"Review kit generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Review kit failed: {e}")


# --------------------------------------------------------------------------- #
# Monthly report
# --------------------------------------------------------------------------- #


@router.get("/report")
async def get_monthly_report(
    client_name: str = "",
    month: str = "",
    current_user: User = Depends(require_admin),
):
    """Monthly marketing report (self-contained HTML + stats) — team events se."""
    try:
        result = await monthly_report.build_report(
            client_name=client_name,
            month=month or None,
        )
        _log_isha(
            "monthly_report_generated",
            f"{client_name or 'business'} ({result.get('month')}, "
            f"{result.get('stats', {}).get('total_actions', 0)} actions)",
        )
        return result
    except Exception as e:
        logger.error(f"Monthly report failed: {e}")
        raise HTTPException(status_code=500, detail=f"Monthly report failed: {e}")


# --------------------------------------------------------------------------- #
# Database reactivation (win-back campaign — manual one-click send)
# --------------------------------------------------------------------------- #


@router.post("/reactivation")
async def generate_reactivation_campaign(
    req: ReactivationRequest,
    current_user: User = Depends(require_admin),
):
    """Purane customers ke personalized win-back WA messages + wa.me links (cap 50)."""
    try:
        result = await reactivation.reactivation_campaign(
            business_name=req.business_name,
            niche=req.niche,
            customers=[c.model_dump() for c in req.customers],
            offer=req.offer,
        )
        _log_isha(
            "reactivation_generated", f"{req.business_name} ({result.get('count', 0)} customers)"
        )
        return result
    except Exception as e:
        logger.error(f"Reactivation campaign failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reactivation failed: {e}")


# --------------------------------------------------------------------------- #
# Drip / nurture sequences
# --------------------------------------------------------------------------- #


@router.post("/drip")
async def generate_drip_sequence(
    req: DripRequest,
    current_user: User = Depends(require_admin),
):
    """4-step WhatsApp nurture sequence (Day 0/2/5/9) lead_type ke hisab se."""
    try:
        result = await drip.drip_sequence(
            business_name=req.business_name,
            niche=req.niche,
            lead_type=req.lead_type,
        )
        _log_isha("drip_generated", f"{req.business_name} ({result.get('lead_type')})")
        return result
    except Exception as e:
        logger.error(f"Drip sequence failed: {e}")
        raise HTTPException(status_code=500, detail=f"Drip sequence failed: {e}")


# --------------------------------------------------------------------------- #
# Brand kit (per-client brand profile)
# --------------------------------------------------------------------------- #


@router.post("/brand/{client_id}")
async def save_client_brand(
    client_id: str,
    req: BrandRequest,
    current_user: User = Depends(require_admin),
):
    """Client ka brand profile save karo (posters/posts me auto-apply hota hai)."""
    try:
        brand = brand_kit.save_brand(client_id, req.model_dump())
        _log_isha(
            "brand_saved",
            f"{brand.get('business_name') or client_id} "
            f"(primary={brand.get('colors', {}).get('primary') or '-'})",
        )
        return {"saved": True, "brand": brand}
    except Exception as e:
        logger.error(f"Brand save failed: {e}")
        raise HTTPException(status_code=500, detail=f"Brand save failed: {e}")


@router.get("/brand/{client_id}")
async def get_client_brand(
    client_id: str,
    current_user: User = Depends(require_admin),
):
    """Saved brand profile (404 agar abhi save nahi hua)."""
    try:
        brand = brand_kit.get_brand(client_id)
    except Exception as e:
        logger.error(f"Brand lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Brand lookup failed: {e}")
    if brand is None:
        raise HTTPException(status_code=404, detail="Brand kit not found")
    return {"brand": brand}


# --------------------------------------------------------------------------- #
# CRM-lite (customers store + birthday/anniversary wishes)
# --------------------------------------------------------------------------- #


@router.post("/crm/{client_id}/customers")
async def add_crm_customers(
    client_id: str,
    req: CrmCustomersRequest,
    current_user: User = Depends(require_admin),
):
    """Customers add karo (10-digit phone dedupe — existing + same batch)."""
    try:
        result = crm_lite.add_customers(
            client_id,
            [c.model_dump() for c in req.customers],
        )
        _log_isha(
            "crm_customers_added",
            f"client={client_id} (+{result.get('added', 0)}, " f"total {result.get('total', 0)})",
        )
        return result
    except Exception as e:
        logger.error(f"CRM add failed: {e}")
        raise HTTPException(status_code=500, detail=f"CRM add failed: {e}")


@router.get("/crm/{client_id}/customers")
async def list_crm_customers(
    client_id: str,
    tag: str | None = None,
    current_user: User = Depends(require_admin),
):
    """Saved customers list (optional ?tag= filter)."""
    try:
        rows = crm_lite.list_customers(client_id, tag=tag)
        return {"customers": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"CRM list failed: {e}")
        raise HTTPException(status_code=500, detail=f"CRM list failed: {e}")


@router.get("/crm/{client_id}/wishes")
async def get_todays_wishes(
    client_id: str,
    business_name: str = "",
    current_user: User = Depends(require_admin),
):
    """Aaj ke birthday/anniversary customers ke ready wish messages + wa.me links."""
    try:
        result = await crm_lite.todays_wishes(client_id, business_name)
        if result.get("count"):
            _log_isha("wishes_generated", f"client={client_id} ({result['count']} wishes aaj)")
        return result
    except Exception as e:
        logger.error(f"Wishes lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Wishes lookup failed: {e}")


# --------------------------------------------------------------------------- #
# UPI payment kit (QR + slip + WA message — pure logic)
# --------------------------------------------------------------------------- #


@router.post("/upi-kit")
async def generate_upi_kit(
    req: UpiKitRequest,
    current_user: User = Depends(require_admin),
):
    """UPI scan-and-pay kit: upi:// link + QR SVG + payment slip + WA message."""
    try:
        result = upi_kit.payment_kit(
            business_name=req.business_name,
            vpa=req.vpa,
            amount=req.amount,
            note=req.note,
        )
        _log_isha(
            "upi_kit_generated",
            f"{req.business_name} (vpa_valid={result.get('vpa_valid')}, "
            f"amount={result.get('amount') or '-'})",
        )
        return result
    except Exception as e:
        logger.error(f"UPI kit generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"UPI kit failed: {e}")


# --------------------------------------------------------------------------- #
# UPI QR Poster (printable counter-stand poster)
# --------------------------------------------------------------------------- #


@router.post("/upi-qr")
async def generate_upi_qr(
    req: UPIQRRequest,
    current_user: User = Depends(require_admin),
):
    """UPI payment QR poster SVG generator (counter-stand design)."""
    try:
        result = upi_qr.generate_upi_poster(
            vpa=req.vpa,
            business_name=req.business_name,
            amount=req.amount,
            brand_primary=req.brand_primary,
            brand_accent=req.brand_accent,
        )
        _log_isha("upi_qr_poster_generated", f"{req.business_name}")
        return result
    except Exception as e:
        logger.error(f"UPI QR poster generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"UPI QR poster generation failed: {e}")


# --------------------------------------------------------------------------- #
# Missed Call WhatsApp auto-reply
# --------------------------------------------------------------------------- #


@router.post("/missed-call-reply")
async def generate_missed_call_reply(
    req: MissedCallRequest,
    current_user: User = Depends(require_admin),
):
    """Missed call WhatsApp auto-reply message generator (Hinglish/Roman script)."""
    try:
        result = await missed_call.generate_missed_call_reply(
            business_name=req.business_name,
            niche=req.niche,
            callback_url=req.callback_url,
        )
        _log_isha("missed_call_reply_generated", f"{req.business_name} ({req.niche})")
        return result
    except Exception as e:
        logger.error(f"Missed call reply generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Missed call reply generation failed: {e}")


# --------------------------------------------------------------------------- #
# Catalog (price-list SVG + WhatsApp catalog text)
# --------------------------------------------------------------------------- #


@router.post("/catalog")
async def generate_catalog(
    req: CatalogRequest,
    current_user: User = Depends(require_admin),
):
    """1080x1350 price-list card + WA catalog text + AI item descriptions."""
    try:
        result = await catalog.build_catalog(
            business_name=req.business_name,
            items=[i.model_dump() for i in req.items],
            style=req.style,
        )
        _log_isha("catalog_generated", f"{req.business_name} ({result.get('count', 0)} items)")
        return result
    except Exception as e:
        logger.error(f"Catalog generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Catalog failed: {e}")


# --------------------------------------------------------------------------- #
# Ads copy pack (Google RSA + Meta)
# --------------------------------------------------------------------------- #


@router.post("/ads-pack")
async def generate_ads_pack(
    req: AdsPackRequest,
    current_user: User = Depends(require_admin),
):
    """15 Google headlines (≤30 chars) + 4 descriptions + 3 Meta texts + 2 CTAs."""
    try:
        result = await ads_copy.ads_pack(
            business_name=req.business_name,
            niche=req.niche,
            offer=req.offer,
            city=req.city,
        )
        _log_isha("ads_pack_generated", f"{req.business_name} ({req.niche or 'general'})")
        return result
    except Exception as e:
        logger.error(f"Ads pack generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ads pack failed: {e}")


# --------------------------------------------------------------------------- #
# Reels scripts
# --------------------------------------------------------------------------- #


@router.post("/reels")
async def generate_reels_scripts(
    req: ReelsRequest,
    current_user: User = Depends(require_admin),
):
    """n Reels scripts: hook/body/cta/caption/hashtags — 30s ready-to-shoot."""
    try:
        result = await reels.reels_scripts(
            business_name=req.business_name,
            niche=req.niche,
            topic=req.topic,
            n=req.n,
        )
        _log_isha("reels_generated", f"{req.business_name} ({result.get('count', 0)} scripts)")
        return result
    except Exception as e:
        logger.error(f"Reels generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reels failed: {e}")


# --------------------------------------------------------------------------- #
# Lead scoring (website inquiries -> hot/warm/cold)
# --------------------------------------------------------------------------- #


@router.get("/lead-scores")
async def get_lead_scores(current_user: User = Depends(require_admin)):
    """Website inquiries ka rule-based scoring — hot pehle, wa.me ready."""
    try:
        result = lead_scoring.score_leads()
        _log_isha(
            "lead_scores_viewed",
            f"{result.get('total', 0)} leads " f"(hot={result.get('counts', {}).get('hot', 0)})",
        )
        return result
    except Exception as e:
        logger.error(f"Lead scoring failed: {e}")
        raise HTTPException(status_code=500, detail=f"Lead scoring failed: {e}")


# --------------------------------------------------------------------------- #
# GBP texts (description + services + Google posts)
# --------------------------------------------------------------------------- #


@router.post("/gbp-texts")
async def generate_gbp_texts(
    req: GbpTextsRequest,
    current_user: User = Depends(require_admin),
):
    """GBP description (≤750) + services texts (≤300) + 3 Google post updates."""
    try:
        result = await gbp_text.gbp_texts(
            business_name=req.business_name,
            niche=req.niche,
            city=req.city,
            services=req.services,
        )
        _log_isha(
            "gbp_texts_generated",
            f"{req.business_name} ({len(result.get('services', []))} services, "
            f"desc {result.get('description_chars', 0)} chars)",
        )
        return result
    except Exception as e:
        logger.error(f"GBP texts generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"GBP texts failed: {e}")


# --------------------------------------------------------------------------- #
# Client content pack (1-click monthly deliverable bundle)
# --------------------------------------------------------------------------- #


@router.post("/content-pack")
async def generate_client_content_pack(
    req: ContentPackRequest,
    current_user: User = Depends(require_admin),
):
    """Monthly deliverable pack: calendar + 3 posts + 2 posters + GBP +
    WhatsApp + festival plan — ek self-contained HTML me (client ko bhejne layak)."""
    try:
        result = await content_pack.build_client_pack(
            business_name=req.business_name,
            niche=req.niche,
            client_id=req.client_id,
            offer=req.offer,
            phone=req.phone,
        )
        counts = result.get("counts") or {}
        _log_isha(
            "content_pack",
            f"{req.business_name} ({req.niche or 'general'}, "
            f"{counts.get('posts', 0)} posts + {counts.get('posters', 0)} posters)",
        )
        return result
    except Exception as e:
        logger.error(f"Content pack generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Content pack failed: {e}")


# --------------------------------------------------------------------------- #
# Programmatic SEO blog (auto-published niche articles — inbound lead magnet)
# --------------------------------------------------------------------------- #


@router.get("/blog")
async def list_blog_articles(
    limit: int = 200,
    current_user: User = Depends(require_admin),
):
    """Sab published SEO articles ki lightweight list (newest first)."""
    try:
        rows = seo_blog.list_articles(limit=limit)
        return {"articles": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"Blog list failed: {e}")
        raise HTTPException(status_code=500, detail=f"Blog list failed: {e}")


@router.post("/blog/run")
async def run_blog_publish(
    req: BlogRunRequest,
    current_user: User = Depends(require_admin),
):
    """n naye niche×city articles generate + publish karo (free LLM, template fallback)."""
    try:
        result = await seo_blog.run_daily_blog(n=req.n)
        _log_isha("seo_blog_run", f"{result.get('published', 0)} articles published")
        return result
    except Exception as e:
        logger.error(f"Blog run failed: {e}")
        raise HTTPException(status_code=500, detail=f"Blog run failed: {e}")


@router.get("/blog/{slug}")
async def get_blog_article(
    slug: str,
    current_user: User = Depends(require_admin),
):
    """Ek article ka full content (slug se). 404 agar nahi mila."""
    try:
        article = seo_blog.get_article(slug)
    except Exception as e:
        logger.error(f"Blog article lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Blog article lookup failed: {e}")
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


# --------------------------------------------------------------------------- #
# Referral kit (Refer & Earn — code + WA message + link + card SVG)
# --------------------------------------------------------------------------- #


@router.post("/referral")
async def generate_referral_kit(
    req: ReferralRequest,
    current_user: User = Depends(require_admin),
):
    """Refer & Earn kit: referral code + WhatsApp share message + link + 1080 card."""
    try:
        result = referral_kit.make_referral(
            business_name=req.business_name,
            reward=req.reward,
            referrer_name=req.referrer_name,
            brand_primary=req.brand_primary,
            brand_accent=req.brand_accent,
        )
        _log_isha("referral_kit_generated", f"{req.business_name} (code={result.get('code')})")
        return result
    except Exception as e:
        logger.error(f"Referral kit generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Referral kit failed: {e}")


@router.get("/referral/stats")
async def get_referral_stats(
    code: str = "",
    current_user: User = Depends(require_admin),
):
    """Referral usage counts (code diya to us code ka, warna sab ka breakdown)."""
    try:
        return referral_kit.referral_stats(code or None)
    except Exception as e:
        logger.error(f"Referral stats failed: {e}")
        raise HTTPException(status_code=500, detail=f"Referral stats failed: {e}")


# --------------------------------------------------------------------------- #
# Evergreen recycling (purane top posts ko freshen karke queue me wapas)
# --------------------------------------------------------------------------- #


@router.post("/evergreen/{client_id}")
async def recycle_evergreen_content(
    client_id: str,
    req: EvergreenRequest,
    current_user: User = Depends(require_admin),
):
    """Client ke purane (21+ din) top posts ko freshen karke naye drafts queue me."""
    try:
        client = {
            "id": client_id,
            "business_name": req.business_name,
            "niche": req.niche,
        }
        appended = await evergreen.recycle_for_client(client)
        _log_isha("evergreen_recycle", f"client={client_id} ({len(appended)} re-shared)")
        return {"recycled": len(appended), "items": appended}
    except Exception as e:
        logger.error(f"Evergreen recycle failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evergreen recycle failed: {e}")
