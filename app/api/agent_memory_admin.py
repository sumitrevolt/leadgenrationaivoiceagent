"""Agent-memory admin API — operator inspection + DPDP-compliant purge.

The voice agent stores cross-session lead facts in `app/voice_agent/agent_memory.py`
(Qdrant `agent_memory` collection, namespaced `lead:<id>` / `client:<id>`).
Until this module landed, those facts were write-only from an operator
perspective — no way to inspect "what does the agent know about lead X?" and
no way to honor a DPDP/TRAI right-to-be-forgotten request.

This adds three admin endpoints:

- GET  /api/agent-memory/inspect?subject_id=...&scope=lead -> facts list
- POST /api/agent-memory/purge?subject_id=...&scope=lead   -> purged count
- GET  /api/agent-memory/stats                              -> counters

All admin-only. INERT when AGENT_MEMORY flag is unset (backend itself returns
empty / disabled). Per project ethos: never raises on backend error — always
returns a structured "what happened" body so an ops dashboard can react.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/agent-memory", tags=["Infrastructure"])


def _validate(subject_id: str, scope: str) -> tuple[str, str]:
    sid = (subject_id or "").strip()
    sc = (scope or "lead").strip().lower()
    if not sid:
        raise HTTPException(status_code=422, detail="subject_id required")
    if sc not in {"lead", "client", "agent"}:
        raise HTTPException(status_code=422, detail="scope must be lead|client|agent")
    return sid, sc


@router.get("/inspect")
async def inspect(
    subject_id: str = Query(..., min_length=1, max_length=128),
    scope: str = "lead",
    limit: int = 100,
    _user=Depends(require_admin),
) -> dict:
    """List stored facts for a subject (operator debugging)."""
    from app.voice_agent import agent_memory

    sid, sc = _validate(subject_id, scope)
    facts = await agent_memory.list_facts(sid, scope=sc, limit=max(1, min(int(limit), 500)))
    return {
        "subject_id": sid,
        "scope": sc,
        "count": len(facts),
        "facts": facts,
        "enabled": agent_memory.is_enabled(),
    }


@router.post("/purge")
async def purge(
    subject_id: str = Query(..., min_length=1, max_length=128),
    scope: str = "lead",
    _user=Depends(require_admin),
) -> dict:
    """DPDP right-to-be-forgotten erase. Returns purged count (or -1 for Mem0
    backend which doesn't report a count)."""
    from app.voice_agent import agent_memory

    sid, sc = _validate(subject_id, scope)
    return await agent_memory.purge_subject(sid, scope=sc)


@router.get("/stats")
async def stats(_user=Depends(require_admin)) -> dict:
    """Module-level counters: stored / recall_hit / recall_miss / purged / error."""
    from app.voice_agent import agent_memory

    return {
        "enabled": agent_memory.is_enabled(),
        "counters": agent_memory.stats(),
    }


__all__ = ["router"]
