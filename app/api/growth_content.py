"""Competitor-parity content endpoints (carousel / meme / multilang).

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/...).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Growth"])


# ---------------- Competitor-parity content (carousel/meme/multilang) ---------------- #
class CarouselIn(BaseModel):
    business_name: str
    niche: str | None = "general"
    topic: str | None = ""
    slides: int | None = 4


@router.post("/content/carousel")
async def content_carousel(body: CarouselIn, _user=Depends(require_admin)):
    """Predis-style carousel pack: 3-5 branded SVG slides + caption."""
    from app.marketing import carousel

    return await carousel.generate_carousel(
        body.business_name, body.niche or "general", body.topic or "", body.slides or 4
    )


class MemeIn(BaseModel):
    business_name: str | None = ""
    niche: str | None = "general"
    topic: str | None = ""


@router.post("/content/meme")
async def content_meme(body: MemeIn, _user=Depends(require_admin)):
    """Desi business meme (SVG + caption + hashtags)."""
    from app.marketing import meme_gen

    return await meme_gen.generate_meme(
        body.business_name or "", body.niche or "general", body.topic or ""
    )


class MultilangIn(BaseModel):
    caption: str
    langs: list[str] | None = None


@router.post("/content/multilang")
async def content_multilang(body: MultilangIn, _user=Depends(require_admin)):
    """Caption → Hindi/Marathi/Hinglish versions (local reach 2-3x)."""
    from app.marketing import multilang_post

    return await multilang_post.translate_post(body.caption, body.langs)
