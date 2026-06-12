"""
Niche Prospect Database — FastAPI Router
========================================

AI Voice Agent ke liye per-niche prospect database ka REST API.
Har niche ke call-ready prospects — import, queue, post-call update, stats.

Endpoints:
  POST   /api/niche/prospects              — add single prospect
  POST   /api/niche/prospects/bulk         — bulk import (JSON rows ya CSV text)
  GET    /api/niche/prospects              — list prospects (niche/client/status/city filters)
  GET    /api/niche/prospects/next-to-call — call queue next batch
  PATCH  /api/niche/prospects/{id}         — post-call update (outcome + niche_data)
  GET    /api/niche/schema/{niche_key}     — niche-specific call schema (pre-call + collect fields)
  GET    /api/niche/stats                  — prospects count by niche + status

Auth: admin-required (require_admin) sirf write ops pe.
Rate limiting: list/schema = 60/60s; write = 20/60s.
Kabhi raise nahi karta — errors as JSON.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.ratelimit import rate_limit
from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/niche", tags=["Niche Database"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ProspectIn(BaseModel):
    phone: str = Field(..., description="Phone number (E.164 ya 10-digit)")
    company_name: str = Field("", description="Business / company name")
    contact_name: str = Field("", description="Owner / contact person name")
    email: str = Field("", description="Email address (optional)")
    city: str = Field("", description="City")
    state: str = Field("", description="State (optional)")
    niche: str = Field(..., description="Niche key from niches.py (e.g. home_loans)")
    client_id: str = Field(..., description="Client ID (your account)")
    source: str = Field("manual", description="Source tag: manual/import/csv/scrape")
    niche_data: dict = Field(default_factory=dict, description="Pre-call niche-specific data")


class BulkImportIn(BaseModel):
    rows: list[dict] = Field(default_factory=list, description="JSON array of prospect rows")
    csv_text: str = Field("", description="CSV text (header row required) — alternate to rows")
    niche: str = Field(..., description="Niche key")
    client_id: str = Field(..., description="Client ID")
    source: str = Field("import")


class PostCallUpdateIn(BaseModel):
    outcome: str = Field(..., description="qualified | callback | not_interested | wrong_number | dnd | voicemail")
    notes: str = Field("", description="Agent notes from call")
    niche_data: dict = Field(default_factory=dict, description="Collected qualification data")
    callback_hours: int = Field(24, description="Hours until callback (outcome=callback pe)")


# ---------------------------------------------------------------------------
# GET /niche/schema/{niche_key} — niche call schema (public, rate-limited)
# ---------------------------------------------------------------------------

@router.get("/schema/{niche_key}", summary="Get niche call schema")
async def get_niche_schema(
    niche_key: str,
    request: Request,
    _rl=Depends(rate_limit("niche_schema", 60, 60)),
):
    """AI agent ko call se pehle kya context chahiye — per-niche field definitions."""
    try:
        from app.platform.niche_database import get_niche_schema
        return {"ok": True, "schema": get_niche_schema(niche_key)}
    except Exception as e:
        logger.warning(f"get_niche_schema error: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/schemas", summary="All niche schemas")
async def all_niche_schemas(
    request: Request,
    _rl=Depends(rate_limit("niche_schemas", 20, 60)),
    _user=Depends(require_admin),
):
    """Saare voice niches ke schemas ek saath."""
    try:
        from app.platform.niche_database import NICHE_CALL_SCHEMA, get_niche_schema
        return {
            "ok": True,
            "schemas": {k: get_niche_schema(k) for k in NICHE_CALL_SCHEMA},
            "total": len(NICHE_CALL_SCHEMA),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# POST /niche/prospects — add single prospect
# ---------------------------------------------------------------------------

@router.post("/prospects", summary="Add single prospect")
async def add_prospect(
    body: ProspectIn,
    request: Request,
    _rl=Depends(rate_limit("niche_add", 20, 60)),
    _user=Depends(require_admin),
):
    """Single prospect add karo prospect database me."""
    try:
        from app.platform.niche_database import bulk_import
        row = {
            "phone": body.phone,
            "company": body.company_name,
            "contact_name": body.contact_name,
            "email": body.email,
            "city": body.city,
            "state": body.state,
            **body.niche_data,
        }
        result = await bulk_import([row], body.niche, body.client_id, body.source)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning(f"add_prospect error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# POST /niche/prospects/bulk — bulk import
# ---------------------------------------------------------------------------

@router.post("/prospects/bulk", summary="Bulk import prospects")
async def bulk_import_prospects(
    body: BulkImportIn,
    request: Request,
    _rl=Depends(rate_limit("niche_bulk", 5, 60)),
    _user=Depends(require_admin),
):
    """CSV ya JSON array se bulk prospects import karo.

    csv_text diya ho to rows field ignore hota hai.
    CSV me pehli row = header row honi chahiye.
    """
    try:
        from app.platform.niche_database import bulk_import

        rows: list[dict] = body.rows

        if body.csv_text.strip():
            reader = csv.DictReader(io.StringIO(body.csv_text.strip()))
            rows = [dict(r) for r in reader]

        if not rows:
            return {"ok": False, "error": "No rows provided"}

        result = await bulk_import(rows, body.niche, body.client_id, body.source)
        return {"ok": True, **result, "total_input": len(rows)}
    except Exception as e:
        logger.warning(f"bulk_import_prospects error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# GET /niche/prospects — list with filters
# ---------------------------------------------------------------------------

@router.get("/prospects", summary="List prospects")
async def list_prospects(
    request: Request,
    client_id: str = Query(..., description="Client ID"),
    niche: str = Query(None, description="Filter by niche key"),
    status: str = Query(None, description="Filter by status"),
    city: str = Query(None, description="Filter by city"),
    min_score: int = Query(0, description="Minimum lead score"),
    is_hot: bool = Query(None, description="Hot leads only"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _rl=Depends(rate_limit("niche_list", 60, 60)),
    _user=Depends(require_admin),
):
    """Prospects list karo — niche/status/city/score filters ke saath."""
    try:
        from app.models.base import get_async_session
        from app.models.lead import Lead, LeadStatus
        from sqlalchemy import and_, select

        filters = [Lead.assigned_to == client_id]
        if niche:
            filters.append(Lead.niche == niche.strip().lower())
        if status:
            try:
                filters.append(Lead.status == LeadStatus[status.upper()])
            except KeyError:
                pass
        if city:
            filters.append(Lead.city.ilike(f"%{city}%"))
        if min_score:
            filters.append(Lead.lead_score >= min_score)
        if is_hot is not None:
            filters.append(Lead.is_hot_lead == is_hot)

        async with get_async_session() as session:
            from sqlalchemy import func

            count_q = select(func.count(Lead.id)).where(and_(*filters))
            total = (await session.execute(count_q)).scalar() or 0

            q = (
                select(Lead)
                .where(and_(*filters))
                .order_by(Lead.is_hot_lead.desc(), Lead.lead_score.desc(), Lead.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(q)).scalars().all()

            items = []
            for lead in rows:
                try:
                    qd = json.loads(lead.qualification_data or "{}") if lead.qualification_data else {}
                except Exception:
                    qd = {}
                items.append({
                    "id": lead.id,
                    "company_name": lead.company_name,
                    "contact_name": lead.contact_name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "city": lead.city,
                    "niche": lead.niche,
                    "status": lead.status.value if lead.status else None,
                    "lead_score": lead.lead_score,
                    "is_hot_lead": lead.is_hot_lead,
                    "call_attempts": lead.call_attempts,
                    "last_called_at": lead.last_called_at.isoformat() if lead.last_called_at else None,
                    "next_call_at": lead.next_call_at.isoformat() if lead.next_call_at else None,
                    "qualification_data": qd,
                    "created_at": lead.created_at.isoformat() if hasattr(lead, "created_at") and lead.created_at else None,
                })

        return {
            "ok": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }
    except Exception as e:
        logger.warning(f"list_prospects error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# GET /niche/prospects/next-to-call — call queue
# ---------------------------------------------------------------------------

@router.get("/prospects/next-to-call", summary="Next prospects to call")
async def next_to_call(
    request: Request,
    client_id: str = Query(...),
    niche: str = Query(..., description="Niche key"),
    limit: int = Query(10, le=50),
    _rl=Depends(rate_limit("niche_queue", 60, 60)),
    _user=Depends(require_admin),
):
    """AI dialer ke liye next-to-call queue — priority ordered (callbacks first, hot leads, new, retry)."""
    try:
        from app.platform.niche_database import call_queue_next
        items = await call_queue_next(client_id, niche, limit)
        return {"ok": True, "total": len(items), "items": items, "niche": niche}
    except Exception as e:
        logger.warning(f"next_to_call error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# PATCH /niche/prospects/{id} — post-call update
# ---------------------------------------------------------------------------

@router.patch("/prospects/{lead_id}", summary="Post-call update")
async def post_call_update(
    lead_id: str,
    body: PostCallUpdateIn,
    request: Request,
    _rl=Depends(rate_limit("niche_update", 30, 60)),
    _user=Depends(require_admin),
):
    """Call ke baad prospect status + niche data update karo.

    outcome values:
      qualified     → HOT lead, score +20
      callback      → callback scheduled
      not_interested → dropped
      wrong_number   → wrong number
      dnd            → DND registered
      voicemail      → retry next day
    """
    try:
        from app.platform.niche_database import update_after_call
        result = await update_after_call(
            lead_id=lead_id,
            outcome=body.outcome,
            notes=body.notes,
            niche_data=body.niche_data or None,
            callback_hours=body.callback_hours,
        )
        return result
    except Exception as e:
        logger.warning(f"post_call_update error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# GET /niche/stats — prospects count by niche + status
# ---------------------------------------------------------------------------

@router.get("/stats", summary="Niche prospects stats")
async def niche_stats(
    request: Request,
    client_id: str = Query(...),
    niche: str = Query(None, description="Filter to single niche"),
    _rl=Depends(rate_limit("niche_stats", 30, 60)),
    _user=Depends(require_admin),
):
    """Per-niche prospect counts, status breakdown, avg score, callable count."""
    try:
        from app.platform.niche_database import niche_stats as _stats
        return await _stats(client_id, niche)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# GET /niche/voice-niches — list all voice niches with schema summary
# ---------------------------------------------------------------------------

@router.get("/voice-niches", summary="All voice niches list")
async def voice_niches_list(
    request: Request,
    _rl=Depends(rate_limit("niche_voice_list", 60, 60)),
):
    """All 25 voice niches — key, display, band, pitch_hook, schema summary."""
    try:
        from app.niches import NICHES
        from app.platform.niche_database import NICHE_CALL_SCHEMA

        voice_keys = {k for k, v in NICHES.items() if v.get("category") in ("voice", "both")}
        result = []
        for k in sorted(voice_keys):
            n = NICHES[k]
            schema = NICHE_CALL_SCHEMA.get(k, {})
            result.append({
                "key": k,
                "display": schema.get("display") or n.get("name", k),
                "tier": n.get("tier", "B"),
                "band": n.get("lead_band", "A"),
                "category": n.get("category", "voice"),
                "pitch_hook": n.get("pitch_hook", ""),
                "avg_deal_value": n.get("avg_deal_value", 0),
                "qualification_questions": n.get("qualification_questions", []),
                "collect_during_fields": len(schema.get("collect_during", [])),
                "pre_call_fields": len(schema.get("pre_call_fields", [])),
                "has_schema": k in NICHE_CALL_SCHEMA,
            })

        result.sort(key=lambda x: (x["tier"], x["key"]))
        return {"ok": True, "niches": result, "total": len(result)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
