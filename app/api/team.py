"""
Team API — AI staff roster, live activity feed, manual job runs.
================================================================

Final paths (main.py prefix="/api" ke saath, platform.py jaise):
  GET  /api/platform/team               -> roster + per-member live state
  GET  /api/platform/team/events        -> recent activity feed (?limit=&member=)
  POST /api/platform/team/run/{member}  -> staff job manually chalao (arjun/meera/kavya)
  GET  /api/platform/team/prospects             -> outreach queue (?status=&limit=)
  POST /api/platform/team/prospects/run         -> abhi prospecting chalao (Rohan)
  POST /api/platform/team/prospects/{pid}/status -> {status} ready→sent/replied/client/dead

Auth: wahi admin dependency pattern jo platform.py use karta hai
(require_admin). Handlers ke andar lazy imports — import-safe.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/platform/team", tags=["Team"])


@router.get("")
async def get_team_status(current_user: User = Depends(require_admin)):
    """Team dashboard payload — roster, states, aaj ke counts (requires admin)."""
    try:
        from app.platform import team
        return team.team_status()
    except Exception as e:
        logger.warning(f"[team-api] status failed: {e}")
        return {"error": str(e), "members": [], "totals": {}}


@router.get("/events")
async def get_team_events(
    limit: int = 60,
    member: Optional[str] = None,
    current_user: User = Depends(require_admin),
):
    """Live activity feed (newest first); member= se filter (requires admin)."""
    try:
        from app.platform import team
        return {"events": team.recent_events(limit=limit, member=member)}
    except Exception as e:
        logger.warning(f"[team-api] events failed: {e}")
        return {"events": [], "error": str(e)}


@router.post("/run/{member}")
async def run_team_member(member: str, current_user: User = Depends(require_admin)):
    """Staff member ka job on-demand chalao — arjun (QA) / meera (trainer) /
    kavya (ops). Result turant return hota hai (requires admin)."""
    try:
        from app.platform import team
        from app.agents import staff

        team.log_event("manager", "task_assigned", f"manual run: {member}")
        return await staff.run_member(member)
    except Exception as e:
        logger.warning(f"[team-api] run {member} failed: {e}")
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Prospects — Rohan ka Tier-1 client-hunting queue (data/prospects.jsonl)
# --------------------------------------------------------------------------- #
class ProspectStatusIn(BaseModel):
    status: str = Field(..., max_length=20, description="ready|sent|replied|client|dead")


@router.get("/prospects")
async def get_prospects(
    status: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(require_admin),
):
    """Outreach queue — prospects newest-first (?status= filter) (requires admin)."""
    try:
        from app.platform import prospector

        return {"prospects": prospector.list_prospects(status=status, limit=limit)}
    except Exception as e:
        logger.warning(f"[team-api] prospects list failed: {e}")
        return {"prospects": [], "error": str(e)}


@router.post("/prospects/run")
async def run_prospecting_now(current_user: User = Depends(require_admin)):
    """Abhi prospects dhundo — Google Maps scraper se Tier-1 client hunting
    (requires admin). Summary return karta hai; kabhi raise nahi karta."""
    try:
        from app.platform import prospector, team

        team.log_event("manager", "task_assigned", "manual run: prospecting (rohan)")
        return await prospector.run_prospecting()
    except Exception as e:
        logger.warning(f"[team-api] prospects run failed: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/prospects/{pid}/status")
async def set_prospect_status(
    pid: str,
    body: ProspectStatusIn,
    current_user: User = Depends(require_admin),
):
    """Prospect ka pipeline status update karo (requires admin)."""
    try:
        from app.platform import prospector

        ok = prospector.mark_prospect(pid, body.status)
        return {"ok": ok, "id": pid, "status": body.status if ok else None}
    except Exception as e:
        logger.warning(f"[team-api] prospect status failed: {e}")
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# Email outreach — system KHUD prospects ko cold email bhejta hai (Rohan)
# --------------------------------------------------------------------------- #
@router.post("/email-outreach/run")
async def run_email_outreach_now(current_user: User = Depends(require_admin)):
    """Abhi email outreach chalao — ready prospects (jinka email hai) ko
    personalized cold email bhejo (requires admin). Flag/SMTP off ho to
    skipped dict aata hai; kabhi raise nahi karta."""
    try:
        from app.platform import auto_outreach, team

        team.log_event("manager", "task_assigned", "manual run: email outreach (rohan)")
        return await auto_outreach.run_email_outreach()
    except Exception as e:
        logger.warning(f"[team-api] email-outreach run failed: {e}")
        return {"error": str(e)}


@router.get("/email-outreach/stats")
async def get_email_outreach_stats(current_user: User = Depends(require_admin)):
    """Email-outreach counts: total / with_email / emailed / pending (requires admin)."""
    try:
        from app.platform import auto_outreach

        return auto_outreach.outreach_stats()
    except Exception as e:
        logger.warning(f"[team-api] email-outreach stats failed: {e}")
        return {"error": str(e)}


@router.post("/email-followups/run")
async def run_email_followups_now(current_user: User = Depends(require_admin)):
    """Abhi follow-up emails chalao — pehle email ho chuke (par reply nahi aaye)
    prospects ko multi-touch follow-up bhejo (requires admin). Flag/SMTP off ho
    to skipped dict aata hai; kabhi raise nahi karta."""
    try:
        from app.platform import auto_outreach, team

        team.log_event("manager", "task_assigned", "manual run: email follow-ups (rohan)")
        return await auto_outreach.run_email_followups()
    except Exception as e:
        logger.warning(f"[team-api] email-followups run failed: {e}")
        return {"error": str(e)}


__all__ = ["router"]
