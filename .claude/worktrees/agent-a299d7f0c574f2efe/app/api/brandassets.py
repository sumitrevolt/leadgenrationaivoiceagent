"""Brand Assets API — branded frames, digital card, magic resize, review-post, stickers.

AdBanao-parity creative pack on top of EXISTING modules (posters/festivals/
brand_kit/clients_store/review_kit — rebuild nahi):

- GET  /api/brand/frames/daily?slug=        (admin) — aaj ke 3 ready branded posts
- POST /api/brand/frames/compose            (admin) — template SVG × brand frame
- GET  /api/brand/card/{slug}.vcf           (public, rate-limited) — vCard download
- GET  /api/brand/card/{slug}               (public, rate-limited) — digital visiting card
- POST /api/brand/resize                    (admin, multipart) — 1 creative → 4 social sizes
- GET  /api/brand/resize-file/{name}        (public, regex-locked serve)
- POST /api/brand/review-post               (admin) — 4-5★ review → thank-you poster
- POST /api/brand/stickers                  (admin) — 6 WhatsApp sticker PNGs
- GET  /api/brand/sticker-file/{slug}/{name} (public, regex-locked serve)

Mount (creative.py pattern): `app.include_router(brandassets_router, prefix="/api")`.
Sab module-fns never-raise ({"ok": False, "error"} dete hain).
"""

from __future__ import annotations

import os
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/brand", tags=["Brand Assets"])

_RESIZED_DIR = os.path.join("data", "resized")
_FRAMES_DIR = os.path.join("data", "frames")
_FILE_RE = re.compile(r"^[a-z0-9_-]+\.png$")


# --------------------------- F1: branded frames ---------------------------- #
@router.get("/frames/daily")
async def frames_daily(slug: str, date: str | None = None, _user=Depends(require_admin)):
    """Aaj ka ready-post feed — 3 branded-frame posters + captions (1-click post)."""
    from app.marketing import brand_frames

    return await brand_frames.daily_feed(slug, date)


class ComposeIn(BaseModel):
    slug: str = Field("", max_length=80)
    template_svg: str = Field("", max_length=400_000)  # apna SVG template
    template_id: str = Field("", max_length=40)  # ya posters.py ka template id
    festival: str = Field("", max_length=80)
    offer: str = Field("", max_length=160)


@router.post("/frames/compose")
async def frames_compose(body: ComposeIn, _user=Depends(require_admin)):
    """Diye gaye template (SVG ya posters template-id) pe client ka brand frame lagao."""
    from app.marketing import brand_frames

    brand = brand_frames.resolve_brand(body.slug)
    tpl = (body.template_svg or "").strip()
    if not tpl:
        from app.marketing import posters

        poster = posters.generate_poster(
            body.template_id or "clean-pro",
            business_name=brand.get("business_name", ""),
            tagline=brand.get("tagline", ""),
            offer=body.offer,
            phone=brand.get("phone", ""),
            festival=body.festival,
            brand_primary=brand.get("primary", ""),
            brand_accent=brand.get("accent", ""),
        )
        tpl = poster.get("svg", "")
    return brand_frames.compose_frame(tpl, brand)


# --------------------------- F2: digital card ------------------------------ #
# NOTE: .vcf route PEHLE declare hota hai (warna /card/{slug} greedy match kar leta).
@router.get("/card/{slug}.vcf", dependencies=[Depends(rate_limit("card", 30, 60))])
async def card_vcf(slug: str):
    """Save-contact vCard (.vcf) — public, rate-limited."""
    from app.marketing import business_card

    res = business_card.render_vcf(slug)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "card not found"))
    return Response(
        content=res["vcf"],
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{res["filename"]}"'},
    )


@router.get("/card/{slug}", dependencies=[Depends(rate_limit("card", 30, 60))])
async def card_html(slug: str):
    """Digital visiting card (mobile-first standalone page) — public, rate-limited."""
    from app.marketing import business_card

    res = business_card.render_card_html(slug)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "card not found"))
    return HTMLResponse(res["html"], headers={"Cache-Control": "public, max-age=300"})


# --------------------------- F3: magic resize ------------------------------ #
@router.post("/resize", dependencies=[Depends(rate_limit("resize", 10, 60))])
async def magic_resize_endpoint(
    file: UploadFile | None = File(None),
    svg: str = Form(""),
    sizes: str = Form(""),
    slug: str = Form(""),
    _user=Depends(require_admin),
):
    """Ek creative (photo upload YA SVG string) → square/story/banner/wa_status pack."""
    from app.marketing import magic_resize

    image_path = None
    if file is not None:
        try:
            data = await file.read()
        except Exception:
            data = b""
        if data:
            ext = (file.filename or "img.png").rsplit(".", 1)[-1].lower()
            if ext not in ("png", "jpg", "jpeg", "webp"):
                return JSONResponse(
                    {"ok": False, "error": "sirf png/jpg/webp upload karo."}, status_code=400
                )
            if len(data) > 8_000_000:
                return JSONResponse(
                    {"ok": False, "error": "file 8MB se badi hai."}, status_code=400
                )
            os.makedirs(_RESIZED_DIR, exist_ok=True)
            image_path = os.path.join(_RESIZED_DIR, f"upload_{uuid.uuid4().hex[:10]}.{ext}")
            with open(image_path, "wb") as f:
                f.write(data)

    out = magic_resize.resize_pack(image_path=image_path, svg=svg or None, sizes=sizes, slug=slug)
    # serve URLs (download buttons frontend me)
    if out.get("ok") and isinstance(out.get("files"), dict):
        out["urls"] = {
            k: f"/api/brand/resize-file/{os.path.basename(v)}" for k, v in out["files"].items()
        }
    return out


@router.get("/resize-file/{name}", dependencies=[Depends(rate_limit("rszf", 60, 60))])
async def resize_file(name: str):
    """Resized PNG serve (public, filename regex-locked)."""
    from fastapi.responses import FileResponse as _FR

    if not _FILE_RE.match(name or ""):
        raise HTTPException(status_code=404, detail="not found")
    for d in (_RESIZED_DIR, _FRAMES_DIR):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return _FR(
                p, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"}
            )
    raise HTTPException(status_code=404, detail="not found")


# --------------------------- F4: review → post ----------------------------- #
class ReviewPostIn(BaseModel):
    review_text: str = Field(..., min_length=3, max_length=600)
    author: str = Field("", max_length=60)
    rating: int = Field(5, ge=1, le=5)
    slug: str = Field("", max_length=80)


@router.post("/review-post")
async def review_post(body: ReviewPostIn, _user=Depends(require_admin)):
    """4-5★ review → branded thank-you poster SVG + Hinglish caption."""
    from app.marketing import review_to_post

    return await review_to_post.from_review(body.review_text, body.author, body.rating, body.slug)


# --------------------------- F5: sticker pack ------------------------------ #
class StickersIn(BaseModel):
    slug: str = Field("", max_length=80)
    business_name: str = Field("", max_length=80)
    niche: str = Field("", max_length=80)


@router.post("/stickers", dependencies=[Depends(rate_limit("stickers", 10, 60))])
async def stickers(body: StickersIn, _user=Depends(require_admin)):
    """6 WhatsApp stickers (512x512 transparent PNG) brand colors me."""
    from app.marketing import sticker_pack

    out = sticker_pack.generate_stickers(body.slug, body.business_name, body.niche)
    if out.get("ok") and isinstance(out.get("files"), list):
        tag = os.path.basename(out.get("dir", ""))
        out["urls"] = [f"/api/brand/sticker-file/{tag}/{os.path.basename(p)}" for p in out["files"]]
    return out


@router.get("/sticker-file/{slug}/{name}", dependencies=[Depends(rate_limit("stkf", 60, 60))])
async def sticker_file(slug: str, name: str):
    """Sticker PNG serve (public, slug+filename regex-locked)."""
    from fastapi.responses import FileResponse as _FR

    from app.marketing import sticker_pack

    p = sticker_pack.safe_sticker_path(slug, name)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return _FR(p, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
