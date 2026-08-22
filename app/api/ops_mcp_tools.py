"""Ops MCP tools — Hot Queue + Revenue summary as /mcp-exposed admin tools.

fastapi-mcp mount (app/main.py) `include_tags=["Platform", ...]` se tools
select karta hai, isliye saare routes tag="Platform" rakhe hain = Claude /
Hermes MCP clients inhe direct tools ki tarah call kar sakte hain.

Design rules (project discipline):
- Engines REUSE hote hain (`reply_agent`, `gst_invoice`) — yahan sirf thin
  admin surface hai, business logic duplicate NAHI.
- Auth double-layered: route-level `require_admin` + /mcp middleware ka
  Bearer/IP gate (fail-closed prod).
- Read-only + idempotent mark actions; koi external send, koi payment move.
- Rollback: main.py se is router ka include-block hatao (single line).

Added 2026-08-23 (Hermes Desktop ops sprint, owner-approved "sab karo").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(
    prefix="/ops",
    tags=["Platform"],
)


@router.get("/hotqueue", operation_id="ops_hot_queue")
async def ops_hot_queue(
    limit: int = 50,
    scope: str = "boss",
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Hot Queue snapshot for MCP agents — warm/intent rows + summary counts.

    scope=boss (default) | admin (parked) | all. Read-only."""
    from app.platform import reply_agent

    scope_n = str(scope or "boss").strip().lower()
    if scope_n not in ("boss", "admin", "all"):
        scope_n = "boss"
    try:
        rows = reply_agent.hot_queue(limit=max(1, min(200, limit)), scope=scope_n)
        summary = reply_agent.hot_queue_summary(rows, scope=scope_n)
    except Exception as exc:  # never raise — defensive surface
        logger.warning("ops_hot_queue err: %s", exc)
        return {"ok": False, "error": "hot_queue_unavailable", "items": [], "summary": {}}
    return {
        "ok": True,
        "count": len(rows),
        "scope": scope_n,
        "summary": summary,
        "items": rows,
    }


class OpsHotQueueActionIn(BaseModel):
    action: str  # "done" | "park"
    hq_id: str
    note: str = ""


@router.post(
    "/hotqueue/action",
    operation_id="ops_hot_queue_action",
    dependencies=[Depends(rate_limit("ops_hq_action", 60, 60))],
)
async def ops_hot_queue_action(
    body: OpsHotQueueActionIn,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Mark one Hot Queue row done ya park (idempotent mark, koi send nahi)."""
    from app.platform import reply_agent

    action_n = str(body.action or "").strip().lower()
    if action_n not in ("done", "park"):
        raise HTTPException(422, "action must be 'done' or 'park'")
    if not body.hq_id.strip():
        raise HTTPException(422, "hq_id required")
    try:
        if action_n == "done":
            ok = reply_agent.mark_handled(body.hq_id)
        else:
            ok = reply_agent.park_for_admin(body.hq_id, note=body.note or "")
    except Exception as exc:
        logger.warning("ops_hot_queue_action err: %s", exc)
        raise HTTPException(500, "action failed") from exc
    if not ok:
        raise HTTPException(404, "hq_id not found (ya already handled)")
    return {"ok": True, "hq_id": body.hq_id, "action": action_n}


@router.get("/revenue-summary", operation_id="ops_revenue_summary")
async def ops_revenue_summary(
    recent_limit: int = 10,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Verified collected-revenue digest for MCP agents — GST invoice ledger
    (data/invoices.jsonl) se. HONEST numbers only; voided alag count hote hain."""
    from app.billing import gst_invoice

    try:
        s = gst_invoice.stats()
        recent = gst_invoice.list_invoices(limit=max(1, min(50, recent_limit)))
    except Exception as exc:
        logger.warning("ops_revenue_summary err: %s", exc)
        return {"ok": False, "error": "ledger_unavailable"}
    slim = [
        {
            "number": r.get("number"),
            "client_id": r.get("client_id"),
            "plan": r.get("plan"),
            "gross_inr": r.get("gross_inr"),
            "voided": bool(r.get("voided")),
            "date": r.get("date") or r.get("created_at"),
        }
        for r in recent
    ]
    return {"ok": True, "stats": s, "recent": slim}


__all__ = ["router"]
