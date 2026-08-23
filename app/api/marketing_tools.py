"""Marketing per-niche tool generators — GBP audit, review replies, festivals, SVG
posters, WhatsApp/page kits, competitor, report, reactivation, drip, brand kit,
CRM-lite, UPI kit/QR, catalog, ads/reels, lead-scoring, content pack, blog, referral.

Extracted from app/api/marketing.py (2026-06-20 refactor) to shrink the god-router.
Mounted via marketing.router.include_router(); paths unchanged (/api/marketing/...).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.marketing_models import (
    AdsPackRequest,
    AuditScoreRequest,
    BlogRunRequest,
    BrandRequest,
    CatalogRequest,
    CompetitorRequest,
    ContentPackRequest,
    CrmCustomersRequest,
    DripRequest,
    EvergreenRequest,
    FestivalPostsRequest,
    GbpTextsRequest,
    MissedCallRequest,
    PosterRequest,
    ReactivationRequest,
    ReelsRequest,
    ReferralRequest,
    ReviewKitRequest,
    ReviewReplyRequest,
    UpiKitRequest,
    UPIQRRequest,
    WhatsAppPackRequest,
)
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
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

router = APIRouter(tags=["Marketing"])


def _log_isha(action: str, detail: str) -> None:
    """Team activity log (best-effort — kabhi request fail nahi karata)."""
    try:
        from app.platform.team import log_event

        log_event("isha", action, detail)
    except Exception:
        pass


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
            f"{req.business_name} ({req.niche or 'general'}, {len(result.get('posts', []))} posts)",
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
# Social PAGE KIT — naye FB/Insta/LinkedIn/X/GBP/WA pages ka paste-ready setup
# --------------------------------------------------------------------------- #


class PageKitRequest(BaseModel):
    business_name: str
    niche: str = "general"
    city: str = ""
    phone: str = ""
    posts_count: int = 5


@router.post("/page-kit")
async def generate_page_kit(
    req: PageKitRequest,
    current_user: User = Depends(require_admin),
):
    """Complete social-page setup kit: har platform ka name/handle/bio/about +
    logo + cover prompt + pehle 5 posts + hashtags. (Pages create karna
    account-action hai — yeh 1-click-copy content deta hai.)"""
    try:
        from app.marketing.social_page_kit import build_page_kit

        result = await build_page_kit(
            business_name=req.business_name,
            niche=req.niche,
            city=req.city,
            phone=req.phone,
            posts_count=req.posts_count,
        )
        _log_isha("page_kit_generated", f"{req.business_name} ({req.niche})")
        return result
    except Exception as e:
        logger.error(f"Page kit generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Page kit failed: {e}")


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
            f"client={client_id} (+{result.get('added', 0)}, total {result.get('total', 0)})",
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
            f"{result.get('total', 0)} leads (hot={result.get('counts', {}).get('hot', 0)})",
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
