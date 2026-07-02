"""Operating HQ API — thin admin-gated router over app.platform.office_hq.

Mounted at /api/platform/office/*  (sibling of the existing /api/platform/team
router). Snapshot/pipeline-drilldown are read-only. Approvals decide + agent
manual-run reuse the EXISTING endpoints (/api/growth/approvals/drafts/*,
/api/platform/team/run/*) — deliberately not duplicated here. The mutation
endpoints below (pause/resume/assign/next-action/resolve-stuck/move) are REAL
actions with a narrow, honestly-documented scope — see app.platform.agent_controls
and app.platform.admin_pipeline_overrides docstrings for exactly what each one
does and does not affect.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/platform/office", tags=["Operating HQ"])


@router.get("/snapshot")
async def office_snapshot(current_user=Depends(require_admin)):
    """Full HQ snapshot — rooms, agents, metrics, 12-stage pipeline, approvals,
    system health, next-best-actions. Never raises (degrades to safe defaults
    per-section — see app.platform.office_hq)."""
    from app.platform import office_hq

    try:
        return await office_hq.build_snapshot()
    except Exception as e:  # pragma: no cover — belt-and-suspenders, builder never raises
        return {"ok": False, "error": str(e), "rooms": [], "agents": [], "metrics": {},
                "pipeline": [], "approvals": {"drafts": [], "counts": {}},
                "system_health": {}, "next_best_actions": []}


@router.post("/boss-review")
async def office_boss_review(current_user=Depends(require_admin)):
    """Boss Finalizer (manager agent) — FREE-LLM verdict + reason per pending
    approval item (cap 10, per-item timeout, never raises). RECOMMEND-ONLY:
    stores nothing, approves nothing — the human still clicks Approve/Reject
    on the existing decide endpoints. Code patches stay never-auto-applied."""
    from app.platform import office_hq

    try:
        return await office_hq.boss_review()
    except Exception as e:  # pragma: no cover — builder never raises
        return {"ok": False, "error": str(e), "verdicts": [], "reviewed": 0}


@router.get("/pipeline/{stage_id}")
async def office_pipeline_stage(stage_id: str, current_user=Depends(require_admin)):
    """Drill-down for one pipeline stage (full item list, not just top-3)."""
    from app.platform import office_hq

    try:
        return await office_hq.pipeline_stage_detail(stage_id)
    except Exception as e:  # pragma: no cover
        return {"id": stage_id, "count": 0, "items": [], "source": "mock", "error": str(e)}


# --------------------------------------------------------------------------- #
# Agent pause/resume — REAL, but narrowly scoped to the manual "Run now"
# button only (see app.platform.agent_controls docstring). Restricted to
# RUNNABLE_MEMBERS at the router edge so a pause flag can never be set on an
# agent it has zero effect on (that would be exactly the "lies to admin"
# failure mode the UI spec forbids).
# --------------------------------------------------------------------------- #
@router.post("/agents/{member}/pause")
async def office_pause_agent(member: str, current_user=Depends(require_admin)):
    from app.platform import agent_controls, office_hq

    if member not in office_hq.RUNNABLE_MEMBERS:
        return {"ok": False, "error": f"pause has no real effect on '{member}' (no manual-run wiring) — refused"}
    result = agent_controls.pause(member, by=getattr(current_user, "email", "admin") or "admin")
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/agents/{member}/resume")
async def office_resume_agent(member: str, current_user=Depends(require_admin)):
    from app.platform import agent_controls, office_hq

    result = agent_controls.resume(member, by=getattr(current_user, "email", "admin") or "admin")
    await office_hq.invalidate_snapshot_cache()
    return result


# --------------------------------------------------------------------------- #
# Pipeline item mutations
# --------------------------------------------------------------------------- #
class AssignOwnerIn(BaseModel):
    agent_key: str


class NextActionIn(BaseModel):
    note: str


class MoveItemIn(BaseModel):
    item_type: str  # "lead" | "deal"
    next_stage: str


@router.post("/pipeline/item/{item_id}/assign")
async def office_assign_owner(item_id: str, body: AssignOwnerIn, current_user=Depends(require_admin)):
    from app.platform import office_hq

    result = office_hq.assign_item_owner(item_id, body.agent_key, by=getattr(current_user, "email", "admin") or "admin")
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/pipeline/item/{item_id}/next-action")
async def office_set_next_action(item_id: str, body: NextActionIn, current_user=Depends(require_admin)):
    from app.platform import office_hq

    result = office_hq.set_item_next_action(item_id, body.note, by=getattr(current_user, "email", "admin") or "admin")
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/pipeline/item/{item_id}/resolve-stuck")
async def office_resolve_stuck(item_id: str, current_user=Depends(require_admin)):
    from app.platform import office_hq

    result = office_hq.resolve_item_stuck(item_id, by=getattr(current_user, "email", "admin") or "admin")
    await office_hq.invalidate_snapshot_cache()
    return result


@router.post("/pipeline/item/{item_id}/move")
async def office_move_item(item_id: str, body: MoveItemIn, current_user=Depends(require_admin)):
    from app.platform import office_hq

    result = office_hq.move_item(
        item_id, body.item_type, body.next_stage, by=getattr(current_user, "email", "admin") or "admin"
    )
    await office_hq.invalidate_snapshot_cache()
    return result
