"""Segments API — dynamic condition-based lead/prospect segments (admin).

Mautic parity: ek segment = conditions ka live-evaluated set (NOT a snapshot).
Backed by app/platform/segments.py. Sab admin-gated, additive, kabhi raise nahi
(not-found pe proper 404, baaki errors safe dicts).

Prefix: /api/segments
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/segments", tags=["Segments"])


class ConditionIn(BaseModel):
    field: str = ""
    op: str = "eq"
    value: Any = None


class SegmentIn(BaseModel):
    name: str = Field("segment", max_length=80)
    match: str = "all"  # "all" | "any"
    conditions: list[ConditionIn] = Field(default_factory=list)


@router.get("/_meta")
async def segments_meta(_user=Depends(require_admin)) -> dict[str, Any]:
    """Field + op catalog for the UI builder. Kabhi raise nahi."""
    try:
        from app.platform import segments

        return {
            "ok": True,
            "fields": segments.SUPPORTED_FIELDS,
            "ops": segments.SUPPORTED_OPS,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "fields": {}, "ops": []}


@router.post("")
async def create_segment(body: SegmentIn, _user=Depends(require_admin)) -> dict[str, Any]:
    """Naya dynamic segment banao. Kabhi raise nahi."""
    try:
        from app.platform import segments

        rec = segments.create_segment(
            name=body.name,
            match=body.match,
            conditions=[c.model_dump() for c in body.conditions],
        )
        return {"ok": True, "segment": rec}
    except Exception as e:
        logger.warning(f"[segments-api] create failed: {e}")
        return {"ok": False, "error": str(e)}


@router.get("")
async def list_segments(_user=Depends(require_admin)) -> dict[str, Any]:
    """Saare segments (newest-first). Kabhi raise nahi."""
    try:
        from app.platform import segments

        return {"ok": True, "segments": segments.list_segments()}
    except Exception as e:
        return {"ok": False, "error": str(e), "segments": []}


@router.get("/{segment_id}")
async def get_segment(segment_id: str, _user=Depends(require_admin)) -> dict[str, Any]:
    """Ek segment. Not-found = 404."""
    try:
        from app.platform import segments

        rec = segments.get_segment(segment_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not rec:
        raise HTTPException(status_code=404, detail="segment nahi mila")
    return {"ok": True, "segment": rec}


@router.get("/{segment_id}/preview")
async def preview_segment(
    segment_id: str, limit: int = 500, _user=Depends(require_admin)
) -> dict[str, Any]:
    """Live-evaluate -> count + sample (first 50) + matched_ids. Not-found = 404."""
    try:
        from app.platform import segments

        rec = segments.get_segment(segment_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not rec:
        raise HTTPException(status_code=404, detail="segment nahi mila")
    try:
        from app.platform import segments

        result = segments.evaluate(rec, limit=limit)
        return {"ok": True, "segment_id": segment_id, "name": rec.get("name"), **result}
    except Exception as e:
        return {"ok": False, "error": str(e), "count": 0, "sample": [], "matched_ids": []}


@router.delete("/{segment_id}")
async def delete_segment(segment_id: str, _user=Depends(require_admin)) -> dict[str, Any]:
    """Segment delete. Not-found = 404."""
    try:
        from app.platform import segments

        ok = segments.delete_segment(segment_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not ok:
        raise HTTPException(status_code=404, detail="segment nahi mila")
    return {"ok": True, "deleted": segment_id}
