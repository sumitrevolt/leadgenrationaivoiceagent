"""Journeys API — omnichannel rule engine ka admin surface (CRUD + runs + test).

Engine: app/marketing/journeys.py (event→action drafts, JOURNEY_ENGINE gated).
Sab writes admin-only. Page: /app/journeys.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.marketing import journeys
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/journeys", tags=["Journeys"])


class ActionIn(BaseModel):
    type: str
    params: dict = {}


class JourneyIn(BaseModel):
    name: str
    trigger: str
    actions: list[ActionIn] = []
    condition: dict | None = None
    enabled: bool = False


class ToggleIn(BaseModel):
    enabled: bool


class EmitIn(BaseModel):
    event: str
    context: dict = {}


@router.get("")
async def get_journeys(_user=Depends(require_admin)):
    """Saare rules + valid triggers/actions + engine on/off."""
    return {
        "engine_enabled": journeys._enabled(),
        "triggers": sorted(journeys.TRIGGERS),
        "actions": sorted(journeys.ACTIONS),
        "journeys": journeys.list_journeys(),
    }


@router.post("")
async def create_journey(body: JourneyIn, _user=Depends(require_admin)):
    rec = journeys.add_journey(
        body.name,
        body.trigger,
        [a.model_dump() for a in body.actions],
        body.condition,
        body.enabled,
    )
    return {"ok": True, "journey": rec}


@router.post("/seed")
async def seed_defaults(_user=Depends(require_admin)):
    """3 useful rules seed karo (disabled) — quick start."""
    n = journeys.seed_defaults()
    return {"ok": True, "seeded": n}


@router.post("/{jid}/toggle")
async def toggle_journey(jid: str, body: ToggleIn, _user=Depends(require_admin)):
    if not journeys.set_enabled(jid, body.enabled):
        raise HTTPException(status_code=404, detail="Journey not found")
    return {"ok": True, "id": jid, "enabled": body.enabled}


@router.delete("/{jid}")
async def delete_journey(jid: str, _user=Depends(require_admin)):
    if not journeys.delete_journey(jid):
        raise HTTPException(status_code=404, detail="Journey not found")
    return {"ok": True, "id": jid}


@router.get("/runs")
async def list_runs(_user=Depends(require_admin)):
    """Recent journey executions (drafts ready for 1-click human send)."""
    return {"runs": journeys.list_runs(50)}


@router.post("/emit")
async def emit_event(body: EmitIn, _user=Depends(require_admin)):
    """Manual test fire (JOURNEY_ENGINE=1 chahiye, warna empty)."""
    res = await journeys.emit_event(body.event, body.context)
    return {"ok": True, "engine_enabled": journeys._enabled(), "ran": len(res), "runs": res}
