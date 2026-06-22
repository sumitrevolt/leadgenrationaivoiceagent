"""SEO/Ops API — rank tracker + unified conversations + human dialer.

Mount (main session): app.include_router(seoops.router, prefix="/api")
→ final paths /api/seoops/*

Pattern (growth.py jaisa): admin-only via require_admin, lazy imports in
handlers, modules khud never-raise (error dicts). Koi auto-send/auto-call
NAHI — drafts + tel:/wa.me links (ban-safe).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/seoops", tags=["SEO-Ops"])


# --------------------------------------------------------------------------- #
# F1 — Local rank tracker (BrightLocal-style, ongoing)
# --------------------------------------------------------------------------- #
class RankConfigIn(BaseModel):
    client_id: str
    keywords: list[str]
    city: str
    business_name: str = ""
    phone: str = ""


class RankCheckIn(BaseModel):
    business_name: str
    keyword: str
    city: str
    phone: str = ""


@router.post("/rank/config")
async def rank_config(body: RankConfigIn, _user=Depends(require_admin)):
    """Client ke tracking keywords set/update karo."""
    from app.platform import rank_tracker

    return rank_tracker.track(
        body.client_id, body.keywords, body.city, body.business_name, body.phone
    )


@router.get("/rank/config")
async def rank_configs(_user=Depends(require_admin)):
    """Saare configured clients + keywords."""
    from app.platform import rank_tracker

    return {"configs": rank_tracker.list_configs()}


@router.post("/rank/check")
async def rank_check(body: RankCheckIn, _user=Depends(require_admin)):
    """One-off rank check (history me save nahi hota) — quick demo/sales use."""
    from app.platform import rank_tracker

    return await rank_tracker.check_rank(body.business_name, body.phone, body.keyword, body.city)


@router.post("/rank/run")
async def rank_run(_user=Depends(require_admin)):
    """Saare configs ab check karo (lookup cap ke saath) + history me likho."""
    from app.platform import rank_tracker

    return await rank_tracker.run_tracking()


@router.get("/rank/history")
async def rank_history(client_id: str = "", limit: int = 100, _user=Depends(require_admin)):
    """Rank history newest-first (optional client filter)."""
    from app.platform import rank_tracker

    return {"history": rank_tracker.history(client_id, limit)}


# --------------------------------------------------------------------------- #
# F2 — Unified conversation inbox (drafts-only, ban-safe)
# --------------------------------------------------------------------------- #
class ReplyIn(BaseModel):
    text: str
    channel: str = "manual"


@router.get("/conversations")
async def conversations_list(limit: int = 50, _user=Depends(require_admin)):
    """Saari conversations (email replies + web chat + inquiries) thread-view."""
    from app.platform import conversations

    return {"threads": conversations.list_threads(limit)}


@router.get("/conversations/{key}")
async def conversation_thread(key: str, _user=Depends(require_admin)):
    """Ek thread ke messages + contact links (tel/wa.me/mailto)."""
    from app.platform import conversations

    return conversations.get_thread(key)


@router.post("/conversations/{key}/reply")
async def conversation_reply(key: str, body: ReplyIn, _user=Depends(require_admin)):
    """Reply DRAFT save karo — human khud bhejta hai (auto-send nahi, ban-safe)."""
    from app.platform import conversations

    return conversations.add_manual_reply_draft(key, body.text, body.channel)


# --------------------------------------------------------------------------- #
# F3 — Human dialer mode (telecaller productivity)
# --------------------------------------------------------------------------- #
class DispositionIn(BaseModel):
    phone: str
    disposition: str
    notes: str = ""


@router.post("/dialer/disposition")
async def dialer_disposition(body: DispositionIn, _user=Depends(require_admin)):
    """Call ka result log karo (interested/callback/no-answer/wrong-number/not-interested)."""
    from app.platform import dialer_log

    return dialer_log.log_disposition(body.phone, body.disposition, body.notes)


@router.get("/dialer/stats")
async def dialer_stats(_user=Depends(require_admin)):
    """Aaj ke calls by disposition — telecaller scoreboard."""
    from app.platform import dialer_log

    return dialer_log.stats_today()


__all__ = ["router"]
