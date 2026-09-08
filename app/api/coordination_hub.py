"""Coordination Hub API — Owner OS namespaced thin projection.

Prefix: /api/admin/owner-os/coordination-hub
Admin JWT for reads. Tool heartbeat + Buzz webhook = HMAC only (no admin bearer).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.models.user import User
from app.platform import coordination_hub as hub
from app.platform import coordination_hub_events as events
from app.platform.coordination_hub_auth import hub_enabled, verify_tool_attestation
from app.platform.coordination_hub_git import probe_git
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(
    prefix="/api/admin/owner-os/coordination-hub",
    tags=["Owner OS Coordination Hub"],
)


def _require_hub_on() -> None:
    if not hub_enabled():
        raise HTTPException(status_code=404, detail="coordination_hub_disabled")


def _extract_hmac(request: Request) -> tuple[str | None, str | None, str | None, str | None]:
    h = request.headers
    return (
        h.get("X-CoordHub-Timestamp") or h.get("x-coordhub-timestamp"),
        h.get("X-CoordHub-Nonce") or h.get("x-coordhub-nonce"),
        h.get("X-CoordHub-Signature") or h.get("x-coordhub-signature"),
        h.get("X-CoordHub-Event-Type") or h.get("x-coordhub-event-type"),
    )


def _parse_json_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


async def _verify_inbound(
    request: Request,
    *,
    tool_id: str,
    default_event: str,
) -> tuple[dict[str, Any], bytes]:
    """HMAC-only gate. Admin bearer / API key alone is insufficient."""
    raw = await request.body()
    ts, nonce, sig, event_hdr = _extract_hmac(request)
    event_type = (event_hdr or default_event).strip().lower()
    if not (ts and nonce and sig):
        raise HTTPException(
            status_code=401,
            detail="hmac_required",
        )
    result = verify_tool_attestation(
        tool_id=tool_id,
        event_type=event_type,
        body=raw,
        issued_at=ts,
        nonce=nonce,
        signature=sig,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail=str(result.get("reason") or "hmac_invalid"))
    return result, raw


@router.get("/snapshot")
async def get_snapshot(
    include_git: bool = True,
    events_limit: int = 40,
    _user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin read of Hub projection (inert when flag OFF)."""
    return hub.snapshot(include_git=include_git, events_limit=min(max(events_limit, 1), 200))


@router.get("/events")
async def get_events(
    limit: int = 50,
    _user: User = Depends(require_admin),
) -> dict[str, Any]:
    if not hub_enabled():
        return {"ok": True, "enabled": False, "events": []}
    return {"ok": True, "enabled": True, "events": events.list_events(limit=limit)}


@router.get("/git")
async def get_git(_user: User = Depends(require_admin)) -> dict[str, Any]:
    _require_hub_on()
    return probe_git()


@router.post("/tools/{tool_id}/heartbeat")
async def tool_heartbeat(tool_id: str, request: Request) -> dict[str, Any]:
    """Per-tool HMAC heartbeat. Does not accept admin JWT as auth."""
    _require_hub_on()
    tid = str(tool_id or "").strip().lower()
    verified, raw = await _verify_inbound(request, tool_id=tid, default_event="heartbeat")
    body = _parse_json_body(raw)
    status = str(body.get("status") or "online")[:32]
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    presence = events.update_presence(tool_id=tid, status=status, meta=meta)
    ev = events.append_event(
        tool_id=tid,
        event_type="heartbeat",
        payload={"status": status, **{k: meta[k] for k in list(meta)[:10]}},
        nonce_fp=str(verified.get("nonce_fp") or ""),
        body_sha256=str(verified.get("body_sha256") or ""),
    )
    return {
        "ok": True,
        "tool_id": tid,
        "presence": presence,
        "event": ev,
        "auth": "hmac",
    }


@router.post("/webhooks/buzz")
async def buzz_webhook(request: Request) -> dict[str, Any]:
    """Dedicated Buzz HMAC webhook — append event only; never admin token."""
    _require_hub_on()
    verified, raw = await _verify_inbound(request, tool_id="buzz", default_event="buzz_event")
    body = _parse_json_body(raw)
    event_type = str(body.get("event_type") or "buzz_event")[:64]
    presence = events.update_presence(
        tool_id="buzz",
        status=str(body.get("status") or "online")[:32],
        meta={"channel": str(body.get("channel") or "")[:80]},
    )
    ev = events.append_event(
        tool_id="buzz",
        event_type=event_type,
        payload={
            "channel": str(body.get("channel") or "")[:80],
            "summary": str(body.get("summary") or "")[:400],
        },
        nonce_fp=str(verified.get("nonce_fp") or ""),
        body_sha256=str(verified.get("body_sha256") or ""),
    )
    return {"ok": True, "auth": "hmac", "presence": presence, "event": ev}


class MutationProbeIn(BaseModel):
    action: str = Field(..., min_length=2, max_length=40)


@router.post("/mutations/refuse")
async def refuse_mutation(
    body: MutationProbeIn,
    _user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Explicit refuse surface — documents that Hub is projection-only."""
    return hub.mutation_refused(body.action)


__all__ = ["router"]
