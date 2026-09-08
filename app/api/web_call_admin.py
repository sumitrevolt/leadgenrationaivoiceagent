"""
Web Test-Call Transcripts API — Admin
=====================================
GET /api/admin/web-calls              → list saved web test-call sessions (all browsers)
GET /api/admin/web-calls/{sid}        → one session + full transcript

Web test-calls (/app/test-call) produce a TEXT transcript only (no audio/WAV),
saved by web_call.py → data/web_call_sessions.jsonl. The "Call Recordings"
section (call_recordings.py) lists phone-call WAVs only, so without this view
web test-calls never surface in the admin dashboard.

Import-safe: never raises at import time.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Query

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/admin/web-calls", tags=["Web Test Calls (Admin)"])

_REC_EXTS = ("webm", "mp4", "ogg", "wav")


def _recording_url(session_id: str | None, started_at: str | None) -> str | None:
    """Disk-check for an uploaded web-call recording (webcall_{sid}.<ext>) under the
    session's date dir → admin /api/admin/call-recordings serve URL, or None."""
    sid = (session_id or "").strip()
    day = str(started_at or "")[:10]
    if not sid or len(day) != 10:
        return None
    for ext in _REC_EXTS:
        fn = f"webcall_{sid}.{ext}"
        if os.path.isfile(os.path.join(_CALL_RECORDINGS_DIR(), day, fn)):
            return f"/api/admin/call-recordings/{day}/{fn}"
    return None


def _CALL_RECORDINGS_DIR() -> str:
    """Call recordings root — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_recordings_dir

    return str(call_recordings_dir())


@router.get("", summary="List saved web test-call transcripts (all browsers)")
async def list_web_calls(
    _user=Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    include_turns: bool = Query(False, description="Full transcript per row (heavy)"),
) -> dict:
    """Newest-first web test-call sessions across every browser lead_key."""
    try:
        from app.voice_agent.web_call_store import count_sessions, list_all_sessions

        sessions = list_all_sessions(limit=limit, include_turns=include_turns)
        for s in sessions:
            s["recording_url"] = _recording_url(s.get("session_id"), s.get("started_at"))
        return {"total": count_sessions(), "shown": len(sessions), "sessions": sessions}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"web-calls admin list failed ({e})")
        return {"total": 0, "shown": 0, "sessions": []}


@router.get("/kpis", summary="Call-center KPIs (Lekha — Call Analytics)")
async def web_call_kpis(_user=Depends(require_admin), days: int = Query(7, ge=1, le=90)) -> dict:
    """Aggregate call KPIs (latency p50/p95, duration, booking/dead-air rates) over
    the window. Defined BEFORE /{session_id} so the literal path isn't shadowed."""
    try:
        from app.voice_agent.call_analytics import compute_call_kpis

        return {"ok": True, "kpis": compute_call_kpis(days)}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"web-calls KPIs failed ({e})")
        return {"ok": False, "kpis": {}}


@router.get("/proposals", summary="Self-improve proposals (per-call learn gate)")
async def list_voice_proposals(
    _user=Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    status: str = Query("", description="proposed | promoted | rejected"),
) -> dict:
    """Per-call improvement proposals (failing calls). Each carries a candidate reply
    + a deterministic promotion-gate verdict. NEVER auto-applied — admin reviews."""
    try:
        from app.voice_agent.voice_self_improve import list_proposals

        rows = list_proposals(limit=limit, status=(status or None))
        return {"ok": True, "total": len(rows), "proposals": rows}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"voice proposals list failed ({e})")
        return {"ok": False, "total": 0, "proposals": []}


@router.post("/proposals/{proposal_id}/promote", summary="Promote a proposal (GATED)")
async def promote_voice_proposal(proposal_id: str, _user=Depends(require_admin)) -> dict:
    """Promote ONLY if the promotion-gate passes (candidate out-scores the bad reply +
    obeys telecaller rules). Flips status to 'promoted'; never blind-writes prod prompts."""
    try:
        from app.voice_agent.voice_self_improve import (
            list_proposals,
            promotion_gate,
            set_proposal_status,
        )

        match = next((p for p in list_proposals(limit=200) if p.get("id") == proposal_id), None)
        if not match:
            return {"ok": False, "error": "not_found"}
        gate = promotion_gate(match)
        if not gate.get("pass"):
            return {"ok": False, "error": "gate_failed", "gate": gate}
        ok = set_proposal_status(proposal_id, "promoted")
        if ok:
            # Component 3 — close the learn-from-calls loop: feed the admin-approved
            # correction to the LIVE agent (telecaller_brain injects top-N learned
            # replies per niche). Gated + bounded inside voice_learned; never blocks.
            try:
                from app.voice_agent import voice_learned

                voice_learned.record(
                    match.get("niche"), match.get("user_question"), match.get("candidate")
                )
            except Exception:
                pass
        return {"ok": ok, "gate": gate, "status": "promoted" if ok else "unchanged"}
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"voice proposal promote failed ({e})")
        return {"ok": False, "error": "internal"}


@router.post("/proposals/{proposal_id}/reject", summary="Reject a proposal")
async def reject_voice_proposal(proposal_id: str, _user=Depends(require_admin)) -> dict:
    try:
        from app.voice_agent.voice_self_improve import set_proposal_status

        return {"ok": set_proposal_status(proposal_id, "rejected")}
    except Exception:
        return {"ok": False}


@router.get("/{session_id}", summary="One web test-call + full transcript")
async def web_call_detail(session_id: str, _user=Depends(require_admin)) -> dict:
    """Full transcript for one saved session (no lead_key required — admin view)."""
    try:
        from app.voice_agent.web_call_store import get_session_any

        row = get_session_any(session_id)
        if not row:
            return {"ok": False, "session": None}
        return {
            "ok": True,
            "session": {
                "session_id": row.get("session_id"),
                "lead_key": row.get("lead_key"),
                "started_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
                "duration_s": row.get("duration_s"),
                "niche": row.get("niche"),
                "flow": row.get("flow"),
                "client_name": row.get("client_name"),
                "turn_count": row.get("turn_count") or len(row.get("turns") or []),
                "turns": row.get("turns") or [],
                "recording_url": _recording_url(row.get("session_id"), row.get("started_at")),
            },
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"web-calls admin detail failed ({e})")
        return {"ok": False, "session": None}
