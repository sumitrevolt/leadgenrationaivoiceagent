"""Lifecycle API — newsletter + winback + email-signature + lead-magnet.

  POST /api/lifecycle/newsletter/subscribers      (admin)  per-client subs import
  GET  /api/lifecycle/newsletter/preview          (admin)  compose preview (?client_id=)
  POST /api/lifecycle/newsletter/run              (admin)  manual monthly run (gated send)
  GET  /api/lifecycle/newsletter/unsub/{token}    (PUBLIC, 10/60s) 1-click opt-out page
  GET  /api/lifecycle/newsletter/rss-digest       (admin)  blog -> email digest draft
  GET  /api/lifecycle/winback/inactive            (admin)  inactive prospects/customers
  POST /api/lifecycle/winback/run                 (admin)  win-back drafts (gated)
  GET  /api/lifecycle/winback/drafts              (admin)  saved drafts
  GET  /api/lifecycle/email-signature             (admin)  branded signature kit (?slug=|client_id=&banner=)
  POST /api/lifecycle/lead-magnet                 (admin)  niche guide generate
  GET  /api/lifecycle/lead-magnet-file/{name}     (PUBLIC, 30/60s) regex-locked serve

Mount (main session):
    from app.api.lifecycle import router as lifecycle_router
    app.include_router(lifecycle_router, prefix="/api")   # /api/lifecycle/*

Patterns (localseo.py/engage.py jaisa): lazy imports, modules never-raise
(error dicts), LLM endpoints `asyncio.wait_for` 25s (prod-down lesson — event
loop kabhi block nahi), file-scan endpoints `asyncio.to_thread`. Flags
(default OFF, scheduler ke liye): NEWSLETTER_ENGINE, WINBACK_ENGINE.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/lifecycle", tags=["Lifecycle"])

_LLM_TIMEOUT = 25  # seconds — LLM/network endpoints kabhi loop block na karein


def _timeout_dict(what: str) -> dict:
    return {
        "ok": False,
        "error": "timeout",
        "message": f"{what} me time lag raha hai — thodi der baad try karo (scheduler bhi complete karega).",
    }


# --------------------------------------------------------------------------- #
# Newsletter (Mailchimp-lite, per-client)
# --------------------------------------------------------------------------- #
class SubscriberIn(BaseModel):
    name: str = Field("", max_length=80)
    email: str = Field(..., min_length=6, max_length=254)


class SubscribersImportIn(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=64)
    subscribers: list[SubscriberIn] = Field(..., min_length=1, max_length=1000)


@router.post("/newsletter/subscribers")
async def newsletter_subscribers_import(body: SubscribersImportIn, _user=Depends(require_admin)):
    """Client ke OPTED-IN customers ki email list import (dedupe by email)."""
    from app.marketing import newsletter

    rows = [s.model_dump() for s in body.subscribers]
    return await asyncio.to_thread(newsletter.add_subscribers, body.client_id, rows)


@router.get("/newsletter/subscribers")
async def newsletter_subscribers_list(
    client_id: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Active subscribers list (tokens included — admin only)."""
    from app.marketing import newsletter

    subs = await asyncio.to_thread(newsletter.subscribers, client_id)
    return {"ok": True, "client_id": client_id, "count": len(subs), "subscribers": subs}


@router.get("/newsletter/preview")
async def newsletter_preview(
    client_id: str = Query(..., min_length=1, max_length=64), _user=Depends(require_admin)
):
    """Compose preview (LLM polish, 25s hard timeout; fallback deterministic)."""
    from app.marketing import newsletter

    try:
        return await asyncio.wait_for(newsletter.compose(client_id), timeout=_LLM_TIMEOUT)
    except asyncio.TimeoutError:
        return _timeout_dict("Newsletter compose")
    except Exception as e:  # pragma: no cover — module never-raise hai
        logger.warning(f"[lifecycle] newsletter preview failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


class NewsletterRunIn(BaseModel):
    force: bool = False  # month-dedupe bypass (testing)


@router.post("/newsletter/run")
async def newsletter_run(body: NewsletterRunIn | None = None, _user=Depends(require_admin)):
    """Manual monthly run. NEWSLETTER_ENGINE=1 = send; OFF = record-only.
    25s hard timeout — partial run safe (per-client month-dedupe likh chuka hota)."""
    from app.marketing import newsletter

    try:
        return await asyncio.wait_for(
            newsletter.run_due_if_enabled(force=bool(body and body.force)), timeout=_LLM_TIMEOUT
        )
    except asyncio.TimeoutError:
        return _timeout_dict("Newsletter run")
    except Exception as e:  # pragma: no cover
        logger.warning(f"[lifecycle] newsletter run failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


@router.get(
    "/newsletter/unsub/{token}",
    response_class=HTMLResponse,
    dependencies=[Depends(rate_limit("nlunsub", 10, 60))],
)
async def newsletter_unsub(token: str):
    """PUBLIC 1-click unsubscribe (email footer link). Tiny Hinglish page."""
    from app.marketing import newsletter

    if not (8 <= len(token or "") <= 40):
        return HTMLResponse(newsletter.unsub_html({"ok": False}), status_code=400)
    res = await asyncio.to_thread(newsletter.unsubscribe, token)
    return HTMLResponse(newsletter.unsub_html(res), status_code=200 if res.get("ok") else 404)


async def _outreach_unsub(token: str) -> HTMLResponse:
    """Suppress a cold-outreach email by one-click token. Never-raise."""
    from app.platform import email_unsub

    email = email_unsub.verify_token(token or "")
    if not email:
        return HTMLResponse("<h3>Invalid or expired unsubscribe link.</h3>", status_code=400)
    await asyncio.to_thread(email_unsub.suppress, email, "one_click")
    return HTMLResponse(
        f"<h3>Unsubscribed ✓</h3><p>{email} ko ab marketing emails nahi aayenge. "
        "Galti se hua? admin@leadsgenai.in pe reply karo.</p>",
        status_code=200,
    )


@router.get(
    "/outreach-unsub/{token}",
    response_class=HTMLResponse,
    dependencies=[Depends(rate_limit("outreachunsub", 20, 60))],
)
async def outreach_unsub_get(token: str):
    """PUBLIC cold-outreach unsubscribe — human footer link (GET)."""
    return await _outreach_unsub(token)


@router.post(
    "/outreach-unsub/{token}",
    response_class=HTMLResponse,
    dependencies=[Depends(rate_limit("outreachunsubp", 30, 60))],
)
async def outreach_unsub_post(token: str):
    """RFC 8058 one-click unsubscribe — mail-client POST (List-Unsubscribe-Post)."""
    return await _outreach_unsub(token)


@router.get("/newsletter/rss-digest")
async def newsletter_rss_digest(limit: int = Query(5, ge=1, le=20), _user=Depends(require_admin)):
    """Apne blog ke naye posts -> email digest DRAFT (send nahi karta)."""
    from app.marketing import newsletter

    return await asyncio.to_thread(newsletter.rss_to_email, limit)


# --------------------------------------------------------------------------- #
# Winback (inactive re-engagement — drafts only)
# --------------------------------------------------------------------------- #
@router.get("/winback/inactive")
async def winback_inactive(
    days: int = Query(60, ge=7, le=3650),
    limit: int = Query(100, ge=1, le=500),
    _user=Depends(require_admin),
):
    """Inactive prospects + end-customers (file-scan thread me — loop block nahi)."""
    from app.platform import winback

    rows = await asyncio.to_thread(winback.find_inactive, days, limit)
    return {"ok": True, "days": days, "count": len(rows), "inactive": rows}


class WinbackRunIn(BaseModel):
    days: int = Field(60, ge=7, le=3650)


@router.post("/winback/run")
async def winback_run(body: WinbackRunIn | None = None, _user=Depends(require_admin)):
    """Win-back drafts banao (GATED WINBACK_ENGINE=1; drafts-only, NO auto-send)."""
    from app.platform import winback

    return await winback.run_due_if_enabled(days=(body.days if body else 60))


@router.get("/winback/drafts")
async def winback_drafts(limit: int = Query(100, ge=1, le=1000), _user=Depends(require_admin)):
    """Saved win-back drafts (wa_link/email 1-click ke liye)."""
    from app.platform import winback

    rows = await asyncio.to_thread(winback.list_drafts, limit)
    return {"ok": True, "count": len(rows), "drafts": rows}


# --------------------------------------------------------------------------- #
# Email signature kit (pure logic — no flag)
# --------------------------------------------------------------------------- #
@router.get("/email-signature")
async def email_signature(
    slug: str = Query("", max_length=80),
    client_id: str = Query("", max_length=64),
    banner: str = Query("", max_length=140),
    _user=Depends(require_admin),
):
    """Branded HTML signature + plain-text + Hinglish paste instructions."""
    from app.marketing import email_signature as sig

    if not slug and not client_id:
        raise HTTPException(status_code=422, detail="slug ya client_id me se ek do")
    return await asyncio.to_thread(sig.generate, client_id or None, slug or None, banner or None)


# --------------------------------------------------------------------------- #
# Lead magnet (niche guide generator)
# --------------------------------------------------------------------------- #
class LeadMagnetIn(BaseModel):
    niche: str = Field(..., min_length=2, max_length=60)
    city: str = Field("", max_length=60)
    business_name: str = Field(..., min_length=2, max_length=120)
    slug: str = Field("", max_length=80)


@router.post("/lead-magnet")
async def lead_magnet_generate(body: LeadMagnetIn, _user=Depends(require_admin)):
    """Branded niche guide (LLM points + static fallback) — HTML (+PDF agar dep ho)."""
    from app.marketing import lead_magnet

    try:
        return await asyncio.wait_for(
            lead_magnet.generate(body.niche, body.city, body.business_name, body.slug),
            timeout=_LLM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return _timeout_dict("Guide generation")
    except Exception as e:  # pragma: no cover
        logger.warning(f"[lifecycle] lead-magnet failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


@router.get("/lead-magnet-file/{name}", dependencies=[Depends(rate_limit("lmfile", 30, 60))])
async def lead_magnet_file(name: str):
    """PUBLIC guide serve (filename regex-locked, dir-locked — ai-img-file pattern)."""
    from app.marketing import lead_magnet

    p = lead_magnet.safe_file_path(name)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    media = "application/pdf" if p.endswith(".pdf") else "text/html"
    return FileResponse(p, media_type=media, headers={"Cache-Control": "public, max-age=3600"})
