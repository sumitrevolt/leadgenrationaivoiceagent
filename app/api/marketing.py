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
  POST /api/marketing/catalog          — price-list SVG + WA catalog text
  POST /api/marketing/ads-pack         — Google RSA + Meta ad copy pack
  POST /api/marketing/reels            — n Reels scripts (hook/body/cta/tags)
  GET  /api/marketing/lead-scores      — inquiries ka hot/warm/cold scoring
  POST /api/marketing/gbp-texts        — GBP description + services + posts
  POST /api/marketing/content-pack     — 1-click monthly client deliverable pack

Sab admin-auth (sirf /packages public hai — static pricing data, koi secret
nahi). Generator functions kabhi raise nahi karte (template
fallback built-in) — phir bhi unexpected par 500 + detail dete hain.
Har generation team-log me jaata hai (isha) — import-safe, best-effort.
"""
from typing import Dict, List, Optional

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
    festivals,
    gbp_audit,
    gbp_text,
    lead_scoring,
    monthly_report,
    packages,
    post_generator,
    posters,
    reactivation,
    reels,
    review_kit,
    review_replies,
    upi_kit,
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
    answers: Dict[str, int] = Field(default_factory=dict)


class ReviewReplyRequest(BaseModel):
    """Review reply generation request."""
    review_text: str = Field(..., min_length=1, max_length=2000)
    rating: Optional[float] = Field(None, ge=0, le=5)
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
    client_id: str = Field("", max_length=64)        # set => saved brand auto-apply
    brand_primary: str = Field("", max_length=10)    # #RRGGBB
    brand_accent: str = Field("", max_length=10)     # #RRGGBB


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
    customers: List[ReactivationCustomer] = Field(default_factory=list, max_length=50)


class DripRequest(BaseModel):
    """WhatsApp nurture sequence request."""
    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    lead_type: str = Field("new_inquiry", max_length=30)


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
    birthday: str = Field("", max_length=20)     # YYYY-MM-DD ya MM-DD
    anniversary: str = Field("", max_length=20)  # YYYY-MM-DD ya MM-DD
    tags: List[str] = Field(default_factory=list, max_length=10)


class CrmCustomersRequest(BaseModel):
    """CRM customers add request."""
    customers: List[CrmCustomer] = Field(default_factory=list, max_length=500)


class UpiKitRequest(BaseModel):
    """UPI payment kit request (vpa = naam@bank)."""
    business_name: str = Field(..., min_length=1, max_length=120)
    vpa: str = Field(..., min_length=3, max_length=100)
    amount: Optional[float] = Field(None, ge=0, le=10_000_000)
    note: str = Field("", max_length=100)


class CatalogItem(BaseModel):
    """Catalog ka ek item (price string flexible: '249' / '₹249')."""
    name: str = Field(..., min_length=1, max_length=80)
    price: str = Field("", max_length=20)
    desc: str = Field("", max_length=160)


class CatalogRequest(BaseModel):
    """Price-list catalog request (12 se zyada items trim ho jaate hain)."""
    business_name: str = Field(..., min_length=1, max_length=120)
    items: List[CatalogItem] = Field(default_factory=list, max_length=24)
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
    services: List[str] = Field(default_factory=list, max_length=12)


class ContentPackRequest(BaseModel):
    """Monthly client content pack request (client_id => saved brand auto-apply)."""
    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    client_id: str = Field("", max_length=64)
    offer: str = Field("", max_length=200)
    phone: str = Field("", max_length=40)


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
        return {"questions": gbp_audit.AUDIT_QUESTIONS,
                "total": len(gbp_audit.AUDIT_QUESTIONS)}
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
        _log_isha("gbp_audit_scored",
                  f"score={result.get('score')} grade={result.get('grade')} "
                  f"({result.get('answered')}/{result.get('total_questions')} answered)")
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
        _log_isha("review_reply_generated",
                  f"{req.business_name or 'business'} (rating={req.rating}, "
                  f"sentiment={result.get('sentiment')})")
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
        _log_isha("festival_posts_generated",
                  f"{req.business_name} ({req.niche or 'general'}, "
                  f"{len(result.get('posts', []))} posts)")
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
        _log_isha("poster_generated",
                  f"{req.business_name} (template={result.get('template')})")
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
        _log_isha("whatsapp_pack_generated",
                  f"{req.business_name} ({req.niche or 'general'})")
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
        _log_isha("competitor_tips_generated",
                  f"{req.business_name} ({req.niche or 'general'})")
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
            client_name=client_name, month=month or None,
        )
        _log_isha("monthly_report_generated",
                  f"{client_name or 'business'} ({result.get('month')}, "
                  f"{result.get('stats', {}).get('total_actions', 0)} actions)")
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
        _log_isha("reactivation_generated",
                  f"{req.business_name} ({result.get('count', 0)} customers)")
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
        _log_isha("drip_generated",
                  f"{req.business_name} ({result.get('lead_type')})")
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
        _log_isha("brand_saved",
                  f"{brand.get('business_name') or client_id} "
                  f"(primary={brand.get('colors', {}).get('primary') or '-'})")
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
            client_id, [c.model_dump() for c in req.customers],
        )
        _log_isha("crm_customers_added",
                  f"client={client_id} (+{result.get('added', 0)}, "
                  f"total {result.get('total', 0)})")
        return result
    except Exception as e:
        logger.error(f"CRM add failed: {e}")
        raise HTTPException(status_code=500, detail=f"CRM add failed: {e}")


@router.get("/crm/{client_id}/customers")
async def list_crm_customers(
    client_id: str,
    tag: Optional[str] = None,
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
            _log_isha("wishes_generated",
                      f"client={client_id} ({result['count']} wishes aaj)")
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
        _log_isha("upi_kit_generated",
                  f"{req.business_name} (vpa_valid={result.get('vpa_valid')}, "
                  f"amount={result.get('amount') or '-'})")
        return result
    except Exception as e:
        logger.error(f"UPI kit generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"UPI kit failed: {e}")


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
        _log_isha("catalog_generated",
                  f"{req.business_name} ({result.get('count', 0)} items)")
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
        _log_isha("ads_pack_generated",
                  f"{req.business_name} ({req.niche or 'general'})")
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
        _log_isha("reels_generated",
                  f"{req.business_name} ({result.get('count', 0)} scripts)")
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
        _log_isha("lead_scores_viewed",
                  f"{result.get('total', 0)} leads "
                  f"(hot={result.get('counts', {}).get('hot', 0)})")
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
        _log_isha("gbp_texts_generated",
                  f"{req.business_name} ({len(result.get('services', []))} services, "
                  f"desc {result.get('description_chars', 0)} chars)")
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
        _log_isha("content_pack",
                  f"{req.business_name} ({req.niche or 'general'}, "
                  f"{counts.get('posts', 0)} posts + {counts.get('posters', 0)} posters)")
        return result
    except Exception as e:
        logger.error(f"Content pack generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Content pack failed: {e}")
