"""
Marketing API — Dhanda.app-style AI marketing tools (FREE stack).
=================================================================

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

Sab admin-auth. Generator functions kabhi raise nahi karte (template
fallback built-in) — phir bhi unexpected par 500 + detail dete hain.
Har generation team-log me jaata hai (isha) — import-safe, best-effort.
"""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.marketing import (
    competitor,
    festivals,
    gbp_audit,
    post_generator,
    posters,
    review_replies,
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
    """SVG poster generation request."""
    template_id: str = Field(..., min_length=1, max_length=60)
    business_name: str = Field(..., min_length=1, max_length=120)
    tagline: str = Field("", max_length=160)
    offer: str = Field("", max_length=160)
    phone: str = Field("", max_length=40)
    festival: str = Field("", max_length=80)


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


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

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
    """Inline SVG poster banao (browser render / PNG convert ready)."""
    try:
        result = posters.generate_poster(
            template_id=req.template_id,
            business_name=req.business_name,
            tagline=req.tagline,
            offer=req.offer,
            phone=req.phone,
            festival=req.festival,
        )
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
