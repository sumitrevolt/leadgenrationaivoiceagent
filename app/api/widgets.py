"""Widgets API — conversion widgets pack (popup/announcement-bar/spin-wheel) +
bio-link page (Linktree-killer) + first-party site beacon (Plausible-lite).

Mount (main session):
    from app.api.widgets import router as widgets_router
    app.include_router(widgets_router, prefix="/api")   # /api/widgets/*

PUBLIC (rate-limited, no auth):
  GET  /api/widgets/popup.js?slug=          popup-pack JS (client site pe embed)
  GET  /api/widgets/beacon.js?slug=         analytics beacon JS
  POST /api/widgets/beacon                  beacon collect (sendBeacon text/plain)
  GET  /api/widgets/bio/{slug}/c/{block_id} bio-link click track → 302

ADMIN:
  GET/POST /api/widgets/popup-config        per-slug popup pack config
  POST /api/widgets/popup-wheel-coupons     loyalty.py se wheel ke real coupon codes
  GET  /api/widgets/popup-snippet           copy-paste <script> one-liner
  GET/POST /api/widgets/bio-config          bio page blocks
  GET  /api/widgets/bio-stats?slug=         clicks per block
  GET  /api/widgets/site-stats?slug=&days=  beacon analytics + Hinglish summary

Sab additive + free-stack + never-raise (modules error dicts dete). Public
paths pure file-IO light hain (NO LLM/KB/ML — prod-down lesson). Slugs
regex-locked ([a-z0-9-]).
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/widgets", tags=["Widgets"])

_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_HOME = "https://leadsgenai.in"


def _valid_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    return s if _SLUG_OK.fullmatch(s) else ""


# ------------------------- popup pack (OptinMonster-lite) ------------------ #
class PopupConfigIn(BaseModel):
    slug: str
    popup: dict | None = None
    bar: dict | None = None
    wheel: dict | None = None


class WheelCouponsIn(BaseModel):
    client_id: str
    slug: str
    offers: list[dict]  # [{title, kind?, value?}] 2-6


@router.get("/popup.js", dependencies=[Depends(rate_limit("widgetjs", 60, 60))])
async def popup_js(slug: str = Query("", max_length=64)):
    """Popup-pack JS (PUBLIC) — client site pe ek <script> line se embed."""
    from fastapi.responses import Response

    s = _valid_slug(slug)
    js = "/* popup pack: invalid slug */"
    if s:
        try:
            from app.marketing import popup_widgets

            js = popup_widgets.render_js(s)
        except Exception as e:  # pragma: no cover - module defensive hai
            logger.warning(f"popup.js render failed: {e}")
            js = "/* popup pack unavailable */"
    return Response(
        js,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/popup-config")
async def popup_config_get(
    slug: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Effective popup-pack config (admin)."""
    from app.marketing import popup_widgets

    s = _valid_slug(slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return {"ok": True, "slug": s, "config": popup_widgets.get_config(s)}


@router.post("/popup-config")
async def popup_config_save(body: PopupConfigIn, _user=Depends(require_admin)):
    """Popup-pack config save (admin). Galat values defaults pe normalize hoti hain."""
    from app.marketing import popup_widgets

    s = _valid_slug(body.slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return popup_widgets.save_config(s, {"popup": body.popup, "bar": body.bar, "wheel": body.wheel})


@router.post("/popup-wheel-coupons")
async def popup_wheel_coupons(body: WheelCouponsIn, _user=Depends(require_admin)):
    """Spin-wheel ke liye loyalty.py se REAL coupon campaigns banao + wheel enable (admin)."""
    from app.marketing import popup_widgets

    s = _valid_slug(body.slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return popup_widgets.create_wheel_coupons(body.client_id, s, body.offers)


@router.get("/popup-snippet")
async def popup_snippet(
    slug: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Client ko dene ka copy-paste one-liner (admin)."""
    from app.marketing import popup_widgets

    s = _valid_slug(slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return {"ok": True, "slug": s, "snippet": popup_widgets.snippet(s)}


# ----------------------------- bio-link page ------------------------------- #
class BioConfigIn(BaseModel):
    slug: str
    blocks: list[dict]
    title: str | None = ""
    subtitle: str | None = ""


@router.get("/bio-config")
async def bio_config_get(
    slug: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Saved bio-link config + page URL (admin)."""
    from app.marketing import bio_link
    from app.marketing.embed_widget import site_base

    s = _valid_slug(slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    cfg = bio_link.get_bio(s)
    return {"ok": True, "slug": s, "config": cfg, "page_url": f"{site_base()}/b/{s}/bio"}


@router.post("/bio-config")
async def bio_config_save(body: BioConfigIn, _user=Depends(require_admin)):
    """Bio-link blocks save (admin). Types: link|whatsapp|call|upi|catalog|video|offer."""
    from app.marketing import bio_link

    s = _valid_slug(body.slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return bio_link.save_bio(s, body.blocks, title=body.title or "", subtitle=body.subtitle or "")


@router.get("/bio/{slug}/c/{block_id}", dependencies=[Depends(rate_limit("bioclick", 120, 60))])
async def bio_click(slug: str, block_id: str, request: Request):
    """Bio-link block click → log + 302 (PUBLIC). Unknown = graceful home redirect."""
    from fastapi.responses import RedirectResponse

    url: str | None = None
    s = _valid_slug(slug)
    if s:
        try:
            from app.marketing import bio_link

            url = bio_link.resolve_block(
                s,
                block_id[:24],
                ua=request.headers.get("user-agent", ""),
                ref=request.headers.get("referer", ""),
            )
        except Exception as e:  # pragma: no cover - resolve defensive hai
            logger.warning(f"bio click resolve failed: {e}")
    return RedirectResponse(url or _HOME, status_code=302)


@router.get("/bio-stats")
async def bio_stats(
    slug: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Bio-link clicks per block (admin)."""
    from app.marketing import bio_link

    s = _valid_slug(slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return {"ok": True, **bio_link.bio_stats(s)}


# --------------------------- site beacon (analytics) ----------------------- #
@router.get("/beacon.js", dependencies=[Depends(rate_limit("widgetjs", 60, 60))])
async def beacon_js(slug: str = Query("", max_length=64)):
    """Analytics beacon JS (~1KB, PUBLIC) — no cookies, privacy-coarse."""
    from fastapi.responses import Response

    from app.platform import site_beacon

    s = _valid_slug(slug)
    js = site_beacon.beacon_js(s) if s else "/* beacon: invalid slug */"
    return Response(
        js,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/beacon", dependencies=[Depends(rate_limit("beacon", 120, 60))])
async def beacon_collect(request: Request):
    """Beacon collect (PUBLIC) — sendBeacon text/plain body, isliye raw parse.
    Hamesha 200 {ok} — widget kabhi client site pe error na dikhaye."""
    data: dict[str, Any] = {}
    try:
        raw = await request.body()
        if 0 < len(raw) <= 4096:
            parsed = json.loads(raw.decode("utf-8", "ignore") or "{}")
            if isinstance(parsed, dict):
                data = parsed
    except Exception:
        return {"ok": False}
    ip = ""
    try:
        ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()) or (
            request.client.host if request.client else ""
        )
    except Exception:
        pass
    from app.platform import site_beacon

    return site_beacon.record_event(data, ip=ip, ua=request.headers.get("user-agent", ""))


@router.get("/site-stats")
async def site_stats(
    slug: str = Query(..., min_length=1, max_length=64),
    days: int = Query(7, ge=1, le=30),
    _user=Depends(require_admin),
):
    """Beacon analytics — visitors/top paths/sources/wa-tel clicks + Hinglish summary (admin)."""
    from app.platform import site_beacon

    s = _valid_slug(slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return {"ok": True, **site_beacon.stats(s, days=days)}


@router.get("/beacon-snippet")
async def beacon_snippet(
    slug: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Beacon ka copy-paste one-liner (admin)."""
    from app.platform import site_beacon

    s = _valid_slug(slug)
    if not s:
        return {"ok": False, "error": "invalid slug"}
    return {"ok": True, "slug": s, "snippet": site_beacon.snippet(s)}


__all__ = ["router"]
