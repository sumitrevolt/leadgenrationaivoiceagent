"""
internal_media — HMAC-protected routes that the local GPU renderer hits, plus
public admin routes for owner 1-clicks (approval/recrate/skip).
"""
from __future__ import annotations

import os
import hmac
import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["content-os"])
public = APIRouter(prefix="/api/content-os", tags=["content-os-public"])


HMAC_KEY = os.getenv("CONTENT_OS_HMAC_KEY", "")
INTERNAL_REQUIRED = os.getenv("CONTENT_OS_REQUIRE_INTERNAL_AUTH", "1") == "1"


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def _sign(body: bytes) -> str:
    if not HMAC_KEY:
        return ""
    return hmac.new(HMAC_KEY.encode(), body, hashlib.sha256).hexdigest()


async def _hmac_check(request: Request, x_render_signature: Optional[str] = Header(None)):
    if not INTERNAL_REQUIRED:
        return
    if not HMAC_KEY:
        # In dev where no key set, accept and log warning.
        logger.warning("[content_os] no HMAC key set; internal endpoints UNPROTECTED")
        return
    body = await request.body()
    sig = x_render_signature or ""
    if not sig or not hmac.compare_digest(sig, _sign(body)):
        raise HTTPException(status_code=401, detail="bad signature")


# --------------------------------------------------------------------------- #
# Internal — renderer → VPS
# --------------------------------------------------------------------------- #
class RenderDoneIn(BaseModel):
    brief_id: str
    owner_slug: str
    aspects_done: list[str] = []
    media_dir: str


@router.post("/render/done", dependencies=[Depends(_hmac_check)])
def render_done(inp: RenderDoneIn):
    """Renderer posts here when an MP4 set is finished."""
    try:
        from app.platform.team import log_event
        log_event(
            "content",
            "render_done",
            f"{inp.owner_slug}/{inp.brief_id} aspects={inp.aspects_done}",
            "ok",
            meta={"module": "content_os", "media_dir": inp.media_dir},
        )
    except Exception:
        pass
    # Persist a tiny receipt so scan_inbox doesn't double-queue it.
    try:
        with open(os.path.join(inp.media_dir, ".render_done"), "w", encoding="utf-8") as f:
            f.write(",".join(inp.aspects_done))
    except Exception as e:
        logger.warning("[content_os] could not mark render_done: %s", e)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Public — owner/admin one-click approvals
# --------------------------------------------------------------------------- #
class ApprovalIn(BaseModel):
    asset_id: str
    action: str           # "approve" | "recreate" | "skip"
    feedback: Optional[str] = None


@public.post("/approve")
def approve(inp: ApprovalIn):
    from app.marketing.content_os.inbox_watcher import approve, recreate, skip
    if inp.action == "approve":
        return approve(inp.asset_id)
    if inp.action == "recreate":
        return recreate(inp.asset_id, inp.feedback or "")
    if inp.action == "skip":
        return skip(inp.asset_id)
    raise HTTPException(400, "bad action")


@public.get("/pending")
def pending(limit: int = 25):
    from app.marketing.content_os.inbox_watcher import list_pending
    return {"ok": True, "items": list_pending(limit=limit)}


@public.get("/status")
def status():
    from app.marketing.content_os.engine import _today_ist
    from app.marketing.content_os.inbox_watcher import list_pending
    from app.marketing.content_os.engine import DATA_DIR
    return {
        "ok": True,
        "date_ist": _today_ist(),
        "pending": len(list_pending(limit=999)),
        "data_dir": str(DATA_DIR),
    }


@public.post("/run-now")
def run_now(force: bool = False):
    from app.marketing.content_os.engine import daily_video_run
    return daily_video_run(force=force)


@public.post("/run-for-client/{slug}")
def run_for_client(slug: str):
    from app.marketing.content_os.engine import run_for_client
    return run_for_client(slug)


# --------------------------------------------------------------------------- #
# Lead capture wiring (called by audit/landing forms and the bio-link)
# --------------------------------------------------------------------------- #
class LeadIn(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    niche: Optional[str] = None
    source: Optional[str] = None      # "ig_bio", "tt_bio", "yt_comment", ...
    utm: dict = {}
    notes: Optional[str] = None


@public.post("/lead")
def capture_lead(inp: LeadIn):
    """Capture → Hot Queue → customer_crm → DM auto-reply (best-effort).

    Never raises — failures end up in the audit trail for manual follow-up."""
    try:
        from app.marketing.customer_crm import create_lead
        lead = create_lead(
            name=inp.name,
            phone=inp.phone,
            email=inp.email,
            city=inp.city,
            niche=inp.niche,
            source=f"content_os:{inp.source}",
            utm=inp.utm,
            notes=inp.notes or "",
        )
    except Exception as e:
        logger.warning("[content_os.lead] crm_failed: %s", e)
        lead = {"id": None, "error": str(e)[:120]}

    # Send DM auto (best-effort) for IG/FB sourced leads.
    if inp.source and inp.source.startswith(("ig_", "fb_")) and inp.phone:
        try:
            from app.integrations.meta_graph import send_private_reply
            send_private_reply(
                recipient_id=inp.phone,        # best-effort: treat phone as PSID when applicable
                template_key="audit_results_v1",
                params={"name": inp.name, "audit_url": "https://leadsgenai.in/audit"},
            )
        except Exception as e:
            logger.info("[content_os.lead] DM skipped: %s", e)

    return {"ok": True, "lead": lead}
