"""Workforce Memory Hub admin API — inspect / recall / remember / purge / stats.

Layered per-STAFF-agent memory (TencentDB-inspired patterns, native JSONL+refs).
All admin-only. INERT when WORKFORCE_MEMORY unset.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/workforce-memory", tags=["Infrastructure"])


class RememberIn(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=40)
    tenant_id: str = Field("", max_length=120)
    content: str = Field(..., min_length=1, max_length=8000)
    layer: str = Field("l1_atom", max_length=32)
    asset: str = Field("chat", max_length=16)
    topic: str = Field("", max_length=120)
    offload: str | None = Field(None, max_length=80_000)
    visibility: str = Field("private", max_length=16)
    parent_id: str | None = Field(None, max_length=32)


class EquipIn(BaseModel):
    entry_id: str = Field(..., min_length=4, max_length=32)
    to_agent: str = Field(..., min_length=1, max_length=40)


@router.get("/stats")
async def stats(_user=Depends(require_admin)) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    return {
        "enabled": wm.is_enabled(),
        "hub": wm.hub_snapshot(),
        "counters": wm.stats(),
        "staff_count": len(wm.known_staff_ids()),
    }


@router.get("/bindings/{agent_id}")
async def bindings(agent_id: str, _user=Depends(require_admin)) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    aid = (agent_id or "").strip().lower()
    if not aid:
        raise HTTPException(status_code=422, detail="agent_id required")
    return {
        "agent_id": aid,
        "bindings": wm.agent_bindings(aid),
        "enabled": wm.is_enabled(),
    }


@router.get("/inspect")
async def inspect(
    agent_id: str = Query(..., min_length=1, max_length=40),
    tenant_id: str = Query("", max_length=120),
    limit: int = 50,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    rows = wm.list_entries(agent_id, limit=max(1, min(int(limit), 500)), tenant_id=tenant_id)
    return {
        "agent_id": agent_id.strip().lower(),
        "tenant_id": tenant_id,
        "namespace": wm.memory_namespace(agent_id, tenant_id),
        "count": len(rows),
        "entries": rows,
        "enabled": wm.is_enabled(),
        "bindings": wm.agent_bindings(agent_id),
    }


@router.get("/recall")
async def recall(
    agent_id: str = Query(..., min_length=1, max_length=40),
    tenant_id: str = Query("", max_length=120),
    q: str = Query("", max_length=400),
    limit: int = 8,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    rows = wm.recall(agent_id, q, limit=max(1, min(int(limit), 50)), tenant_id=tenant_id)
    return {
        "agent_id": agent_id.strip().lower(),
        "tenant_id": tenant_id,
        "namespace": wm.memory_namespace(agent_id, tenant_id),
        "query": q,
        "count": len(rows),
        "entries": rows,
        "brief": wm.recall_brief(agent_id, q, tenant_id=tenant_id),
        "canvas": wm.canvas_mermaid(agent_id, tenant_id=tenant_id),
        "enabled": wm.is_enabled(),
    }


@router.get("/drilldown")
async def drilldown(
    agent_id: str = Query(..., min_length=1, max_length=40),
    node_id: str = Query(..., min_length=4, max_length=32),
    tenant_id: str = Query("", max_length=120),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    text = wm.drilldown(agent_id, node_id, tenant_id=tenant_id)
    if text is None:
        raise HTTPException(status_code=404, detail="node_id not found")
    return {
        "agent_id": agent_id.strip().lower(),
        "tenant_id": tenant_id,
        "node_id": node_id,
        "content": text,
    }


@router.post("/remember")
async def remember(body: RememberIn, _user=Depends(require_admin)) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    return wm.remember(
        body.agent_id,
        body.content,
        layer=body.layer,
        asset=body.asset,
        topic=body.topic,
        offload=body.offload,
        visibility=body.visibility,
        parent_id=body.parent_id,
        tenant_id=body.tenant_id,
    )


@router.post("/equip")
async def equip(body: EquipIn, _user=Depends(require_admin)) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    return wm.equip(body.entry_id, body.to_agent)


@router.get("/equipments")
async def equipments(
    agent_id: str | None = Query(None, max_length=40),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    return wm.list_equipments(agent_id)


@router.post("/prune")
async def prune(
    dry_run: bool = Query(True),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """TTL prune L0/L1. Default dry_run=true (safe preview)."""
    from app.platform import workforce_memory as wm

    return wm.prune_expired(dry_run=bool(dry_run))


@router.post("/purge")
async def purge(
    agent_id: str = Query(..., min_length=1, max_length=40),
    tenant_id: str = Query("", max_length=120),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform import workforce_memory as wm

    return wm.purge_agent(agent_id, tenant_id=tenant_id)


__all__ = ["router"]
