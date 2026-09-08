"""Engage API — engagement batch (UPI QR, short-links, reviews widget, lead alerts).

  POST /api/engage/upi-qr            (admin)  client UPI payment QR pack
  POST /api/engage/links             (admin)  short link create (own-domain)
  GET  /api/engage/links/stats       (admin)  click stats (?code= optional)
  GET  /api/engage/reviews-widget/{slug}     (public, rate-limited) iframe HTML
  GET  /api/engage/reviews-widget.js/{slug}  (public, rate-limited) JS injector
  GET  /api/engage/reviews-snippet   (admin)  copy-paste snippet for client
  POST /api/engage/alerts/test       (admin)  test lead alert (setup verify)

  GET  /r/{code}                     (public, rate-limited) 302 redirect — yeh
       `redirect_router` pe hai (NO /api prefix): main.py me alag mount karo.

Mount (main session):
    from app.api.engage import router as engage_router, redirect_router
    app.include_router(engage_router, prefix="/api")   # /api/engage/*
    app.include_router(redirect_router)                # /r/{code}

Sab additive + free-stack + never-raise (modules error dicts dete). Koi
ML/KB/heavy-sync nahi — public paths pure file-IO light hain (prod-down lesson).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/engage", tags=["Engage"])
redirect_router = APIRouter(tags=["Engage"])  # NO prefix — /r/{code}


# ------------------------- F1: UPI payment QR (admin) ---------------------- #
class UpiQrIn(BaseModel):
    client_id: str
    amount: float | str | None = None
    note: str | None = None


@router.post("/upi-qr")
async def upi_qr_pack(body: UpiQrIn, _user=Depends(require_admin)):
    """Client record (upi_vpa field) se scan-and-pay QR + slip poster + WA share."""
    from app.marketing import upi_qr

    return upi_qr.payment_qr_pack(body.client_id, amount=body.amount, note=body.note or "")


# ----------------------- F2: short links + tracking ------------------------ #
class LinkIn(BaseModel):
    url: str
    label: str | None = ""
    channel: str | None = ""
    client_id: str | None = ""


@router.post("/links")
async def create_link(body: LinkIn, _user=Depends(require_admin)):
    """Own-domain short link banao (leadsgenai.in/r/xxxxxx) — attribution-ready."""
    from app.platform import short_links

    return short_links.create(
        body.url, label=body.label or "", channel=body.channel or "", client_id=body.client_id or ""
    )


@router.get("/links/stats")
async def link_stats(code: str = Query("", max_length=12), _user=Depends(require_admin)):
    """Click stats — by code/channel/day (?code= se single link)."""
    from app.platform import short_links

    return short_links.stats(code)


@redirect_router.get("/r/{code}", dependencies=[Depends(rate_limit("shortlink", 120, 60))])
async def short_redirect(code: str, request: Request):
    """Short link 302 redirect (PUBLIC). Unknown code → homepage (kabhi 404 nahi
    — printed QR/posters pe purane codes bhi graceful)."""
    from fastapi.responses import RedirectResponse

    from app.platform import short_links

    try:
        url = short_links.resolve(
            code,
            ua=request.headers.get("user-agent", ""),
            ref=request.headers.get("referer", ""),
        )
    except Exception:  # pragma: no cover - resolve defensive hai
        url = None
    return RedirectResponse(url or "https://leadsgenai.in", status_code=302)


# --------------------- F3: reviews/testimonial widget ---------------------- #
@router.get("/reviews-widget/{slug}", dependencies=[Depends(rate_limit("rvwidget", 60, 60))])
async def reviews_widget_page(slug: str):
    """Approved-reviews social-proof strip (iframe content, PUBLIC)."""
    from fastapi.responses import HTMLResponse

    from app.marketing import reviews_widget

    # NOTE: SecurityHeadersMiddleware har response pe X-Frame-Options=DENY likhta
    # hai (existing /b/{slug}/embed widget bhi isi ke saath LIVE chal raha) —
    # iframe-exempt karna ho to middleware me path-exemption chahiye (main session).
    return HTMLResponse(
        reviews_widget.reviews_widget_html(slug),
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/reviews-widget.js/{slug}", dependencies=[Depends(rate_limit("rvwidget", 60, 60))])
async def reviews_widget_js(slug: str):
    """JS injector — client site pe inline iframe insert (PUBLIC)."""
    from fastapi.responses import Response

    from app.marketing import reviews_widget

    return Response(
        reviews_widget.widget_js(slug),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/reviews-snippet")
async def reviews_snippet(
    slug: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Client ko dene ka copy-paste one-liner (admin)."""
    from app.marketing import reviews_widget

    return {"slug": slug, "snippet": reviews_widget.snippet(slug)}


# ------------------------ F4: instant lead alerts -------------------------- #
class AlertTestIn(BaseModel):
    client_id: str | None = ""


@router.post("/alerts/test")
async def alerts_test(body: AlertTestIn, _user=Depends(require_admin)):
    """Test alert bhejo — email setup verify karne ke liye (admin).

    Dedupe bypass ke liye unique test phone use hota hai."""
    import time as _t

    from app.platform import lead_alerts

    rec: dict[str, Any] = {
        "name": "Test Lead (setup check)",
        "phone": f"9{int(_t.time()) % 1000000000:09d}",  # unique → dedupe skip
        "source": "alerts-test",
        "message": "Yeh test alert hai — email setup verify.",
    }
    if body.client_id:
        rec["client_id"] = body.client_id
    res = await lead_alerts.notify_new_lead(rec)
    hints = []
    if not res.get("email_sent"):
        hints.append("Email nahi gaya: NOTIFY_EMAIL (+ SMTP creds) set karo.")
    return {**res, "hints": hints}


__all__ = ["router", "redirect_router"]
