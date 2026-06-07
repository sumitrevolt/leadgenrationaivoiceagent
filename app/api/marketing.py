"""
Marketing API — Dhanda.app-style AI marketing tools (FREE stack).
=================================================================

  POST /api/marketing/post      — AI social post (caption+hashtags+image idea)
  GET  /api/marketing/gbp-tips  — Google Business Profile checklist (static)
  POST /api/marketing/calendar  — N-din content calendar

Sab admin-auth. Generator functions kabhi raise nahi karte (template
fallback built-in) — phir bhi unexpected par 500 + detail dete hain.
Har generation team-log me jaata hai (isha) — import-safe, best-effort.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.marketing import post_generator
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
