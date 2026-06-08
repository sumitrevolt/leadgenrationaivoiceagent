"""
Team API — AI staff roster, live activity feed, manual job runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/platform/team", tags=["Team"])


@router.get("")
async def get_team_status(current_user: User = Depends(require_admin)):
    try:
        from app.platform import team
        return team.team_status()
    except Exception as e:
        logger.warning(f"[team-api] status failed: {e}")
        return {"error": str(e), "members": [], "totals": {}}


@router.get("/events")
async def get_team_events(limit: int = 60, member: str | None = None, current_user: User = Depends(require_admin)):
    try:
        from app.platform import team
        return {"events": team.recent_events(limit=limit, member=member)}
    except Exception as e:
        logger.warning(f"[team-api] events failed: {e}")
        return {"events": [], "error": str(e)}


@router.post("/run/{member}")
async def run_team_member(member: str, current_user: User = Depends(require_admin)):
    try:
        from app.agents import staff
        from app.platform import team
        team.log_event("manager", "task_assigned", f"manual run: {member}")
        return await staff.run_member(member)
    except Exception as e:
        logger.warning(f"[team-api] run {member} failed: {e}")
        return {"error": str(e)}


class ProspectStatusIn(BaseModel):
    status: str = Field(..., max_length=20, description="ready|sent|replied|client|dead")


@router.get("/prospects")
async def get_prospects(status: str | None = None, limit: int = 100, current_user: User = Depends(require_admin)):
    try:
        from app.platform import prospector
        return {"prospects": prospector.list_prospects(status=status, limit=limit)}
    except Exception as e:
        logger.warning(f"[team-api] prospects list failed: {e}")
        return {"prospects": [], "error": str(e)}


@router.post("/prospects/run")
async def run_prospecting_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import prospector, team
        team.log_event("manager", "task_assigned", "manual run: prospecting (rohan)")
        return await prospector.run_prospecting()
    except Exception as e:
        logger.warning(f"[team-api] prospects run failed: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/prospects/{pid}/status")
async def set_prospect_status(pid: str, body: ProspectStatusIn, current_user: User = Depends(require_admin)):
    try:
        from app.platform import prospector
        ok = prospector.mark_prospect(pid, body.status)
        return {"ok": ok, "id": pid, "status": body.status if ok else None}
    except Exception as e:
        logger.warning(f"[team-api] prospect status failed: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/email-outreach/run")
async def run_email_outreach_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import auto_outreach, team
        team.log_event("manager", "task_assigned", "manual run: email outreach (rohan)")
        return await auto_outreach.run_email_outreach()
    except Exception as e:
        logger.warning(f"[team-api] email-outreach run failed: {e}")
        return {"error": str(e)}


@router.get("/email-outreach/stats")
async def get_email_outreach_stats(current_user: User = Depends(require_admin)):
    try:
        from app.platform import auto_outreach
        return auto_outreach.outreach_stats()
    except Exception as e:
        logger.warning(f"[team-api] email-outreach stats failed: {e}")
        return {"error": str(e)}


@router.post("/email-followups/run")
async def run_email_followups_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import auto_outreach, team
        team.log_event("manager", "task_assigned", "manual run: email follow-ups (rohan)")
        return await auto_outreach.run_email_followups()
    except Exception as e:
        logger.warning(f"[team-api] email-followups run failed: {e}")
        return {"error": str(e)}


@router.get("/growth")
async def get_growth(current_user: User = Depends(require_admin)):
    try:
        from app.platform import growth_engine
        return {"pulse": growth_engine.latest_pulse(), "history": growth_engine.history(30)}
    except Exception as e:
        logger.warning(f"[team-api] growth get failed: {e}")
        return {"pulse": {}, "history": [], "error": str(e)}


@router.post("/growth/run")
async def run_growth_now(current_user: User = Depends(require_admin)):
    try:
        from app.platform import growth_engine, team
        team.log_event("manager", "task_assigned", "manual run: growth pulse")
        return await growth_engine.pulse()
    except Exception as e:
        logger.warning(f"[team-api] growth run failed: {e}")
        return {"error": str(e)}


__all__ = ["router"]
