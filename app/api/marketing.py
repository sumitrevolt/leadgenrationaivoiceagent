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

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
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


from app.api.marketing_models import (  # noqa: F401  (request models extracted 2026-06-20)
    AdsPackRequest,
    AuditScoreRequest,
    BlogRunRequest,
    BrandColors,
    BrandRequest,
    CalendarRequest,
    CatalogItem,
    CatalogRequest,
    CompetitorRequest,
    ContentPackRequest,
    CrmCustomer,
    CrmCustomersRequest,
    DripRequest,
    EvergreenRequest,
    FestivalPostsRequest,
    GbpTextsRequest,
    MissedCallRequest,
    PosterRequest,
    PostRequest,
    ReactivationCustomer,
    ReactivationRequest,
    ReelsRequest,
    ReferralRequest,
    ReviewKitRequest,
    ReviewReplyRequest,
    UpiKitRequest,
    UPIQRRequest,
    WhatsAppPackRequest,
)

# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


_pkg_cache = None


def _get_pkg_cache():
    global _pkg_cache
    if _pkg_cache is None:
        try:
            from app.cache import Cache

            _pkg_cache = Cache(prefix="api_packages", default_ttl=600)
        except Exception:
            pass
    return _pkg_cache


@router.get("/packages")
async def get_marketing_packages():
    """Pricing packages (PUBLIC — NO auth; landing page isse fetch karta hai). Redis-cached 10 min."""
    cache = _get_pkg_cache()
    if cache:
        try:
            cached = await cache.get("marketing")
            if cached:
                return cached
        except Exception:
            pass
    try:
        result = {"packages": packages.get_public_packages()}
        if cache:
            try:
                await cache.set("marketing", result)
            except Exception:
                pass
        return result
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


@router.post("/photo-poster")
async def photo_poster(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    style: str = Form("vibrant professional"),
    current_user: User = Depends(require_admin),
):
    """Photo → AI poster (Predis/Canva-killer): user ki dukaan/product photo + prompt →
    image-to-image (Pollinations kontext). POLLINATIONS_API_KEY required."""
    from app.marketing import ai_image

    if not ai_image.has_key():
        raise HTTPException(
            status_code=402, detail="POLLINATIONS_API_KEY set karo (enter.pollinations.ai free)"
        )
    photo = await file.read()
    if not photo or len(photo) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="photo missing ya >8MB")
    full_prompt = (
        prompt or ""
    ).strip() or "turn this photo into a professional social-media marketing poster"
    if style:
        full_prompt += f", {style} style, high quality, space for text"
    data, name = await ai_image.edit_image_bytes(full_prompt, photo)
    if not data:
        raise HTTPException(status_code=502, detail="image edit failed (upstream)")
    _log_isha("photo_poster", f"{file.filename} → poster")
    return {
        "url": f"/api/marketing/ai-img-file/{name}",
        "prompt": full_prompt,
        "provider": "pollinations-kontext",
    }


@router.get("/ai-img-file/{name}", dependencies=[Depends(rate_limit("aiimgf", 60, 60))])
async def ai_img_file(name: str):
    """Cached AI image serve (public, filename regex-locked)."""
    from fastapi.responses import FileResponse as _FR

    from app.marketing import ai_image

    p = ai_image.cache_file_path(name)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return _FR(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/ai-image-proxy", dependencies=[Depends(rate_limit("aiimg", 20, 60))])
async def ai_image_proxy(prompt: str, w: int = 1024, h: int = 1024, seed: int | None = None):
    """sk_ key-safe image serve: server-side Pollinations fetch (Authorization header) +
    disk cache (data/ai_images/) — key kabhi client tak nahi jaati, repeat load free.
    Public (img-tag se load hota) but rate-limited."""
    from fastapi.responses import Response

    from app.marketing import ai_image

    w, h = max(256, min(int(w), 1536)), max(256, min(int(h), 1536))
    data = await ai_image.fetch_image_bytes(prompt[:480], w, h, seed)
    if not data:
        raise HTTPException(status_code=502, detail="image generation unavailable (key/upstream)")
    return Response(
        content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"}
    )


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
                business_name=req.business_name,
                niche=req.niche,
                occasion=req.occasion,
                offer=req.offer,
                language=req.language,
            ),
            ai_image.marketing_image(
                req.business_name,
                req.niche,
                req.occasion,
                req.offer,
                width=req.width,
                height=req.height,
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
                    business_name=req.business_name,
                    niche=req.niche,
                    occasion=req.occasion,
                    offer=req.offer,
                    language=req.language,
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
            req.business_name,
            req.niche,
            req.date,
            req.occasion,
            req.offer,
            req.channel,
            req.client_id,
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
    """Upcoming festivals (existing calendar) ko content scheduler me auto-queue."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    days: int = Field(90, ge=7, le=400)
    client_id: str = Field("", max_length=64)


@router.post("/festival-autoschedule")
async def festival_autoschedule(
    req: FestivalScheduleRequest, current_user: User = Depends(require_admin)
):
    """Existing festival calendar ke upcoming festivals ko content scheduler me dup-safe queue."""
    try:
        from app.marketing import content_schedule

        bn = (req.business_name or "").strip() or "Aapka Business"
        fests = festivals.upcoming(req.days) or []
        existing = {
            (i.get("business_name"), i.get("date"), i.get("occasion"))
            for i in content_schedule.list_scheduled()
        }
        scheduled, skipped, items = 0, 0, []
        for f in fests:
            d = (f.get("date") or "").strip()
            occ = (f.get("name") or "").strip()
            if not d or (bn, d, occ) in existing:
                skipped += 1
                continue
            it = content_schedule.schedule(bn, req.niche, d, occ, "", "instagram", req.client_id)
            items.append({"date": d, "name": occ, "id": it.get("id")})
            scheduled += 1
        _log_isha("festival_autoschedule", f"{bn}: {scheduled} queued")
        return {"scheduled": scheduled, "skipped": skipped, "items": items}
    except Exception as e:
        logger.error(f"Festival autoschedule failed: {e}")
        raise HTTPException(status_code=500, detail=f"Festival autoschedule failed: {e}")


@router.get("/embed-snippet")
async def embed_snippet(slug: str, current_user: User = Depends(require_admin)):
    """Client website lead-capture widget ka copy-paste snippet + URLs (slug = mini-site slug)."""
    try:
        from app.marketing import embed_widget

        s = (slug or "").strip()
        if not s:
            raise HTTPException(status_code=422, detail="slug zaroori hai")
        base = embed_widget.site_base()
        biz = ""
        try:
            from app.marketing.clients_store import get_by_slug

            c = get_by_slug(s)
            if c:
                biz = str(c.get("business_name") or "")
        except Exception:
            pass
        return {
            "slug": s,
            "business_name": biz,
            "snippet": embed_widget.snippet(s),
            "widget_url": f"{base}/b/{s}/widget.js",
            "embed_url": f"{base}/b/{s}/embed",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embed snippet failed: {e}")


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


# Marketing tool generators extracted to app/api/marketing_tools.py (2026-06-20);
# included below so /api/marketing/* paths stay unchanged.
from app.api.marketing_tools import router as _tools_router  # noqa: E402

router.include_router(_tools_router)
