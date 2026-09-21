"""Hermes3D Virtual Office Custom Runtime API Routes (2026-09-21)
============================================================
Serves custom runtime endpoints for iamlukethedev/Hermes3D 3D office visualization.
Dual mounts:
- /api/hermes3d/*
- /api/runtime/custom/*
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.models.user import User
from app.platform.hermes3d_bridge import get_hermes3d_bridge

router = APIRouter(tags=["hermes3d"])


def _verify_allowlist(request: Request) -> None:
    bridge = get_hermes3d_bridge()
    client_ip = request.client.host if request.client else None
    # Check X-Forwarded-For if present
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if not bridge.is_client_allowed(client_ip):
        raise HTTPException(status_code=403, detail="Forbidden: client not on custom runtime allowlist")


class CommandPayload(BaseModel):
    action: str = Field(..., description="Action name (e.g. toggle_2d_mode, focus_agent, run_cycle)")
    target_agent: str | None = Field(default=None, description="Target staff agent or supervisory bot ID")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action parameters")


# --------------------------------------------------------------------------- #
# Endpoints (Dual Mount: /api/hermes3d and /api/runtime/custom)
# --------------------------------------------------------------------------- #

@router.get("/api/hermes3d/health", dependencies=[Depends(_verify_allowlist)])
@router.get("/api/runtime/custom/health", dependencies=[Depends(_verify_allowlist)])
async def hermes3d_health() -> dict[str, Any]:
    return get_hermes3d_bridge().get_health()


@router.get("/api/hermes3d/registry", dependencies=[Depends(_verify_allowlist)])
@router.get("/api/runtime/custom/registry", dependencies=[Depends(_verify_allowlist)])
async def hermes3d_registry() -> dict[str, Any]:
    return get_hermes3d_bridge().get_registry()


@router.get("/api/hermes3d/state", dependencies=[Depends(_verify_allowlist)])
@router.get("/api/runtime/custom/state", dependencies=[Depends(_verify_allowlist)])
async def hermes3d_state() -> dict[str, Any]:
    return get_hermes3d_bridge().get_state()


@router.get("/api/hermes3d/config", dependencies=[Depends(_verify_allowlist)])
@router.get("/api/runtime/custom/config", dependencies=[Depends(_verify_allowlist)])
async def hermes3d_config() -> dict[str, Any]:
    return get_hermes3d_bridge().get_config()


@router.post("/api/hermes3d/command", dependencies=[Depends(_verify_allowlist)])
@router.post("/api/runtime/custom/command", dependencies=[Depends(_verify_allowlist)])
async def hermes3d_command(
    payload: CommandPayload,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    bridge = get_hermes3d_bridge()
    return bridge.handle_command(
        action=payload.action,
        target_agent=payload.target_agent,
        parameters=payload.parameters,
    )
