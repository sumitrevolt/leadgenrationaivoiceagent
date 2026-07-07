"""Voice-AI API — live human transfer + 'Ask AI' call insights + dialer leaderboard.

Routes (admin, mount `app.include_router(voiceai_router, prefix="/api")` → /api/voiceai/*):
  POST /voiceai/transfer     — AI call → owner live-transfer w/ Hinglish context (CALL_TRANSFER gate)
  GET  /voiceai/transfers    — recent transfer log
  POST /voiceai/ask          — NL question over call/lead data (Vodex-style, 10/60s)
  GET  /voiceai/call-stats   — pure-python call/dialer/cadence counts
  GET  /voiceai/leaderboard  — telecaller gamification ranking (?days=1|7)
  POST /voiceai/consent/{record,opt-out,opt-in,retention-sweep} — TCCCPR/DPDP consent ledger
  GET  /voiceai/consent/{suppressed,history}                    — suppression list + per-phone audit

Pattern: ai.py jaisa — router-level per-IP rate limit (LLM abuse guard, FAIL-OPEN)
+ require_admin har endpoint pe. LLM calls async free_ai + asyncio.wait_for hard
timeout (event-loop kabhi block nahi — widget-chat prod-down lesson). Lazy imports,
endpoints kabhi 500 nahi (except validation 422).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Per-IP rate limit on ALL /api/voiceai/* (LLM cost/abuse guard). FAIL-OPEN.
router = APIRouter(
    prefix="/voiceai", tags=["Voice AI"], dependencies=[Depends(rate_limit("voiceai", 30, 60))]
)

_LLM_TIMEOUT = 25  # seconds — free_ai chain hard cap (loop-safe)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class TransferIn(BaseModel):
    """Live human transfer request."""

    owner_phone: str
    call_context: dict = {}


class AskIn(BaseModel):
    """NL question over call/lead data."""

    question: str


# --------------------------------------------------------------------------- #
# F1 — Live human transfer w/ context (gated CALL_TRANSFER=1)
# --------------------------------------------------------------------------- #
@router.post("/transfer")
async def transfer_call(body: TransferIn, _user: User = Depends(require_admin)):
    """AI call → owner live-transfer: Hinglish summary + Vobiz connect-leg
    (creds pe) + WA 1-click link + email draft. Flag OFF = inert."""
    if not (body.owner_phone or "").strip():
        raise HTTPException(status_code=422, detail="owner_phone chahiye (10-digit).")
    from app.telephony.call_transfer import request_transfer

    try:
        return await asyncio.wait_for(
            request_transfer(body.call_context or {}, body.owner_phone), timeout=_LLM_TIMEOUT + 10
        )
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout — dobara try karo"}
    except Exception as e:  # request_transfer never raises; belt-and-braces
        logger.warning(f"[voiceai] transfer failed: {e}")
        return {"ok": False, "reason": str(e)[:200]}


@router.get("/transfers")
async def recent_transfers(limit: int = 50, _user: User = Depends(require_admin)):
    """Recent live-transfer log (newest first)."""
    from app.telephony.call_transfer import enabled, list_transfers

    return {"enabled": enabled(), "transfers": list_transfers(limit)}


# --------------------------------------------------------------------------- #
# F2 — 'Ask AI' over call/lead data (Vodex-style)
# --------------------------------------------------------------------------- #
@router.post("/ask", dependencies=[Depends(rate_limit("voiceai_ask", 10, 60))])
async def ask_calls(body: AskIn, _user: User = Depends(require_admin)):
    """Hinglish NL question over call qualifications / dialer / cadence data.
    LLM fail = stats fallback answer (kabhi khaali nahi)."""
    q = (body.question or "").strip()
    if len(q) < 3:
        raise HTTPException(
            status_code=422,
            detail="Sawaal likho — e.g. 'aaj kitne interested the?' ya 'callbacks kitne pending?'",
        )
    from app.platform import call_insights

    try:
        return await asyncio.wait_for(call_insights.ask(q), timeout=_LLM_TIMEOUT)
    except asyncio.TimeoutError:
        stats = call_insights.quick_stats()
        return {
            "ok": True,
            "answer": call_insights._stats_answer(stats),
            "stats": stats,
            "provider": "",
            "note": "AI timeout — direct counts diye.",
        }
    except Exception as e:
        logger.warning(f"[voiceai] ask failed: {e}")
        return {"ok": False, "answer": "Abhi process nahi hua — dobara try karo.", "stats": {}}


@router.get("/call-stats")
async def call_stats(_user: User = Depends(require_admin)):
    """Pure-python counts: qualifications + dialer dispositions + cadence steps."""
    from app.platform import call_insights

    return call_insights.quick_stats()


# --------------------------------------------------------------------------- #
# F3 — Dialer leaderboard (telecaller gamification)
# --------------------------------------------------------------------------- #
@router.get("/leaderboard")
async def dialer_leaderboard(days: int = 1, _user: User = Depends(require_admin)):
    """Telecaller ranking last N din (1=daily, 7=weekly) + Hinglish shoutout."""
    from app.platform import dialer_leaderboard as lb

    return lb.leaderboard(days)


# --------------------------------------------------------------------------- #
# F4 — Consent + opt-out ledger (TCCCPR/DPDP) — app/telephony/consent_ledger.py
# --------------------------------------------------------------------------- #
class ConsentIn(BaseModel):
    phone: str
    scope: str = "voice_promo"
    source: str = ""
    proof: str = ""
    client_id: str = ""


class OptOutIn(BaseModel):
    phone: str
    reason: str = "user_request"
    channel: str = "manual"


class OptInIn(BaseModel):
    phone: str
    source: str = "admin"
    proof: str = ""


@router.post("/consent/record")
async def consent_record(body: ConsentIn, _user: User = Depends(require_admin)):
    """Timestamped consent record (source/proof DPDP audit ke liye)."""
    from app.telephony import consent_ledger

    return consent_ledger.record_consent(
        body.phone, scope=body.scope, source=body.source, proof=body.proof, client_id=body.client_id
    )


@router.post("/consent/opt-out")
async def consent_opt_out(body: OptOutIn, _user: User = Depends(require_admin)):
    """Manual opt-out → instant suppression (voice + WA cross-channel)."""
    from app.telephony import consent_ledger

    return consent_ledger.record_opt_out(body.phone, reason=body.reason, channel=body.channel)


@router.post("/consent/opt-in")
async def consent_opt_in(body: OptInIn, _user: User = Depends(require_admin)):
    """Re-consent: suppression se hatao + fresh consent record (explicit only)."""
    from app.telephony import consent_ledger

    return consent_ledger.opt_back_in(body.phone, source=body.source, proof=body.proof)


@router.get("/consent/suppressed")
async def consent_suppressed(limit: int = 500, _user: User = Depends(require_admin)):
    """Opt-out suppression list (newest first)."""
    from app.telephony import consent_ledger

    return {"items": consent_ledger.suppression_list(limit)}


@router.get("/consent/history")
async def consent_history(phone: str, _user: User = Depends(require_admin)):
    """Phone ka poora consent/opt-out history (DPDP access right)."""
    from app.telephony import consent_ledger

    return {
        "phone": phone,
        "suppressed": consent_ledger.is_suppressed(phone),
        "history": consent_ledger.ledger_for(phone),
    }


@router.post("/consent/retention-sweep")
async def consent_retention_sweep(_user: User = Depends(require_admin)):
    """Manual recording-retention sweep (delete sirf RECORDING_RETENTION=1 pe)."""
    from app.telephony import consent_ledger

    return consent_ledger.retention_sweep()
