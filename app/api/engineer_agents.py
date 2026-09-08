"""F.5 engineer-agent admin API — run + dashboard rollup.

Each call into the underlying module logs an audit event (agent_events table),
so the existing /app/team dashboard surfaces history without extra wiring.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import require_admin
from app.platform import engineer_agents as ea

router = APIRouter(prefix="/api/engineer-agents", tags=["Infrastructure"])

# Drift-proof: derive from the module's agent registry so new engineer agents
# (council 2026-06-25: dbre/deps/dataquality) are auto-recognized by the per-role
# endpoints — earlier this hardcoded only sre/finops/security and 422'd the rest.
_VALID = set(ea.roles())


@router.get("/all")
async def run_all(_user=Depends(require_admin)) -> dict:
    """Dashboard rollup — score + KPIs + actions for all engineer agents."""
    return ea.run_all()


_ROLE_TO_AGENT = dict(ea.AGENT_NAMES)


@router.get("/{role}/history")
async def history(role: str, limit: int = 50, _user=Depends(require_admin)) -> dict:
    """Recent agent_events for one engineer agent (trend chart fuel).

    Reads the same AgentEvent table the existing /app/team dashboard uses,
    filtered to the engineer-agent member. Falls back to empty list if DB
    unavailable — INERT (never raises).
    """
    role_l = (role or "").strip().lower()
    if role_l not in _VALID:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role '{role}'. Valid: {sorted(_VALID)}",
        )
    member = _ROLE_TO_AGENT[role_l]
    n = max(1, min(int(limit), 500))
    items: list[dict] = []
    try:
        from app.models.agent_event import AgentEvent
        from app.platform.team import _db

        db = _db()
        if db is None:
            return {"role": role_l, "agent": member, "count": 0, "events": []}
        try:
            rows = (
                db.query(AgentEvent)
                .filter(AgentEvent.member == member)
                .order_by(AgentEvent.created_at.desc())
                .limit(n)
                .all()
            )
            for r in rows:
                items.append(
                    {
                        "action": r.action,
                        "detail": r.detail,
                        "status": r.status,
                        "at": r.created_at.isoformat() if r.created_at else None,
                    }
                )
        finally:
            db.close()
    except Exception:
        pass
    return {"role": role_l, "agent": member, "count": len(items), "events": items}


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


@router.post("/{role}/run")
async def run_now(role: str, _user=Depends(require_admin)) -> dict:
    """L.5: force-run an engineer agent regardless of scheduler window. Useful
    after fixing a backup / arming a flag to verify the score recovers without
    waiting for the next scheduled tick. Same payload as GET /{role}."""
    role_l = (role or "").strip().lower()
    if role_l not in _VALID:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown role '{role}'. Valid: {sorted(_VALID)}",
        )
    return ea.run(role_l)


__all__ = ["router"]
