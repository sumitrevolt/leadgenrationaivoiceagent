"""Goals API — admin-gated router over app.platform.goals.

Mounted at /api/goals. Goals are the tracked "why" hierarchy (company → team →
agent) above the task queue; tasks keep their own free-text goal fields and
link to goals advisory-style. Deliberately NO project/workspace endpoints —
LeadGen is single-repo (Paperclip projects do not map, see
docs/PAPERCLIP_INTEGRATION_ANALYSIS.md verdict #10).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.platform import goals as goals_mod

router = APIRouter(prefix="/goals", tags=["Goals"])


class CreateGoalRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    level: str = Field("team", max_length=20)
    status: str = Field("planned", max_length=20)
    description: str = Field("", max_length=4000)
    parent_goal_id: str | None = Field(None, max_length=36)
    owner_agent_id: str | None = Field(None, max_length=40)
    client_id: str | None = Field(None, max_length=36)
    campaign_id: str | None = Field(None, max_length=36)
    target_metric: str = Field("", max_length=200)


class UpdateGoalRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = Field(None, max_length=4000)
    status: str | None = Field(None, max_length=20)
    target_metric: str | None = Field(None, max_length=200)
    owner_agent_id: str | None = Field(None, max_length=40)
    progress_note: str | None = Field(None, max_length=2000)


class LinkTaskRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=36)


def _raise_if_not_ok(out: dict[str, Any], *, not_found_status: int = 404) -> dict[str, Any]:
    if not out.get("ok"):
        status = not_found_status if out.get("error") == "goal not found" else 400
        raise HTTPException(status_code=status, detail=out.get("error", "goals error"))
    return out


@router.get("")
async def list_goals(
    level: str | None = None,
    status: str | None = None,
    client_id: str | None = None,
    parent_goal_id: str | None = None,
    owner_agent_id: str | None = None,
    limit: int = 200,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    rows = await goals_mod.list_goals(
        level=level,
        status=status,
        client_id=client_id,
        parent_goal_id=parent_goal_id,
        owner_agent_id=owner_agent_id,
        limit=limit,
    )
    return {"ok": True, "goals": rows, "count": len(rows)}


@router.post("")
async def create_goal(req: CreateGoalRequest, _user=Depends(require_admin)) -> dict[str, Any]:
    out = await goals_mod.create_goal(
        req.title,
        level=req.level,
        status=req.status,
        description=req.description,
        parent_goal_id=req.parent_goal_id,
        owner_agent_id=req.owner_agent_id,
        client_id=req.client_id,
        campaign_id=req.campaign_id,
        target_metric=req.target_metric,
    )
    return _raise_if_not_ok(out, not_found_status=400)


@router.get("/{goal_id}")
async def get_goal(goal_id: str, _user=Depends(require_admin)) -> dict[str, Any]:
    row = await goals_mod.get_goal(goal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="goal not found")
    return {"ok": True, "goal": row}


@router.patch("/{goal_id}")
async def update_goal(
    goal_id: str, req: UpdateGoalRequest, _user=Depends(require_admin)
) -> dict[str, Any]:
    out = await goals_mod.update_goal(
        goal_id,
        title=req.title,
        description=req.description,
        status=req.status,
        target_metric=req.target_metric,
        owner_agent_id=req.owner_agent_id,
        progress_note=req.progress_note,
    )
    return _raise_if_not_ok(out)


@router.post("/{goal_id}/tasks")
async def link_task(
    goal_id: str, req: LinkTaskRequest, _user=Depends(require_admin)
) -> dict[str, Any]:
    out = await goals_mod.link_task(goal_id, req.task_id)
    return _raise_if_not_ok(out)
