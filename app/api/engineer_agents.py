"""F.5 engineer-agent admin API — run + dashboard rollup.

Each call into the underlying module logs an audit event (agent_events table),
so the existing /app/team dashboard surfaces history without extra wiring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import require_admin
from app.platform import engineer_agents as ea

router = APIRouter(prefix="/api/engineer-agents", tags=["Infrastructure"])

_VALID = {"sre", "finops", "security"}


@router.get("/all")
async def run_all(_user=Depends(require_admin)) -> dict:
    """Dashboard rollup — score + KPIs + actions for all three engineer agents."""
    return ea.run_all()


@router.get("/{role}")
async def run_one(role: str, _user=Depends(require_admin)) -> dict:
    """Run a single engineer agent. role = sre | finops | security."""
    role_l = (role or "").strip().lower()
    if role_l not in _VALID:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role '{role}'. Valid: {sorted(_VALID)}",
        )
    return ea.run(role_l)


__all__ = ["router"]
