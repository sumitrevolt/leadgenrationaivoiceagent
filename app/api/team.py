"""
Team API — AI staff roster, live activity feed, manual job runs.
================================================================

Final paths (main.py prefix="/api" ke saath, platform.py jaise):
  GET  /api/platform/team               -> roster + per-member live state
  GET  /api/platform/team/events        -> recent activity feed (?limit=&member=)
  POST /api/platform/team/run/{member}  -> staff job manually chalao (arjun/meera/kavya)

Auth: wahi admin dependency pattern jo platform.py use karta hai
(require_admin). Handlers ke andar lazy imports — import-safe.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

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


__all__ = ["router"]
