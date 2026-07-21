"""Owner Copilot API — /api/owner-copilot/*

Inbound trust model:
  OpenClaw Gateway (or super-admin browser) → this API → Owner OS → 31 agents

Auth:
  - Human: canonical super-admin JWT only (module-RBAC insufficient)
  - Machine: OPENCLAW_API_TOKEN + OPENCLAW_GATEWAY_ALLOWED_IPS peer check

Gate: OPENCLAW_ENABLED (default off). Owner OS = sole action authority.
LeadGen does not call OpenClaw for core runtime (inbound-only).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.ratelimit import rate_limit
from app.integrations.openclaw.auth import CopilotActor, require_copilot_actor
from app.integrations.openclaw.commands import (
    classify_nl,
    execute_typed_command,
    list_command_catalogue,
)
from app.integrations.openclaw.context_builder import build_owner_context
from app.integrations.openclaw.policies import openclaw_enabled, policy_snapshot
from app.integrations.openclaw.schemas import CopilotCommandIn, CopilotNlIn
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/owner-copilot", tags=["Owner Copilot"])


def _require_enabled() -> None:
    if not openclaw_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "openclaw_disabled",
                "message": "OPENCLAW_ENABLED=0 — Owner Copilot edge layer off. Core platform unaffected.",
            },
        )


@router.get("/status")
async def copilot_status(actor: CopilotActor = Depends(require_copilot_actor)) -> dict[str, Any]:
    """Feature + policy + compact context. Works even when disabled (shows flag)."""
    snap = policy_snapshot()
    ctx = None
    if snap["enabled"]:
        try:
            ctx = build_owner_context()
        except Exception:
            ctx = None
    return {
        "ok": True,
        "enabled": snap["enabled"],
        "policy": snap,
        "context": ctx,
        "calling_hard_off": True,
        "trust_model": "inbound_openclaw_to_leadgen",
        "hierarchy": [
            "Admin",
            "OpenClaw Owner Copilot",
            "Owner OS",
            "Boss/Manager",
            "31 agents",
            "Celery/workflows",
        ],
        "actor": actor.label(),
        "actor_kind": actor.kind,
    }


@router.get("/catalogue")
async def copilot_catalogue(actor: CopilotActor = Depends(require_copilot_actor)) -> dict[str, Any]:
    _require_enabled()
    return list_command_catalogue()


@router.get("/daily-brief")
async def copilot_daily_brief(
    actor: CopilotActor = Depends(require_copilot_actor),
) -> dict[str, Any]:
    _require_enabled()
    return execute_typed_command(
        "business.daily_summary",
        {},
        actor=actor.label(),
        idempotency_key=None,
    )


@router.get("/approvals")
async def copilot_approvals(actor: CopilotActor = Depends(require_copilot_actor)) -> dict[str, Any]:
    _require_enabled()
    return execute_typed_command("approvals.list", {}, actor=actor.label())


@router.post(
    "/command",
    dependencies=[Depends(rate_limit("owner_copilot", 30, 60))],
)
async def copilot_command(
    body: CopilotCommandIn,
    actor: CopilotActor = Depends(require_copilot_actor),
) -> dict[str, Any]:
    _require_enabled()
    cmd = (body.command or "").strip()
    if any(x in cmd for x in (";", "|", "`", "$(", "\n", "DROP ", "DELETE FROM")):
        raise HTTPException(status_code=400, detail="invalid command characters")
    return execute_typed_command(
        cmd,
        body.params,
        actor=actor.label(),
        idempotency_key=body.idempotency_key,
        confirm=body.confirm,
        correlation_id=body.correlation_id,
        text=body.text,
    )


@router.post(
    "/nl",
    dependencies=[Depends(rate_limit("owner_copilot_nl", 20, 60))],
)
async def copilot_nl(
    body: CopilotNlIn,
    actor: CopilotActor = Depends(require_copilot_actor),
) -> dict[str, Any]:
    """Classify NL → typed proposal; optionally execute GREEN (or park AMBER)."""
    _require_enabled()
    proposal = classify_nl(body.text)
    if not body.execute:
        return {"ok": True, "proposal": proposal, "executed": None}
    if proposal.get("safety_lane") == "AMBER" and not body.confirm:
        return {
            "ok": True,
            "proposal": proposal,
            "executed": None,
            "note": "AMBER — confirm=true bhejo to Owner OS approval park hoga (mutate nahi)",
        }
    executed = execute_typed_command(
        proposal["command"],
        proposal.get("params") or {},
        actor=actor.label(),
        idempotency_key=body.idempotency_key,
        confirm=body.confirm,
        text=body.text,
    )
    return {"ok": True, "proposal": proposal, "executed": executed}


@router.get("/commands/{command_id}")
async def copilot_get_command(
    command_id: str, actor: CopilotActor = Depends(require_copilot_actor)
) -> dict[str, Any]:
    _require_enabled()
    from app.platform import owner_os

    cmd = owner_os.get_command(command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="command not found")
    return {"ok": True, "command": cmd, "actor": actor.label()}
