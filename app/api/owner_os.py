"""Owner OS admin API — /api/admin/owner-os/*

Auth: require_admin. No secrets in responses. Mutations audited.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.models.user import User
from app.platform import owner_os
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/admin/owner-os", tags=["Owner OS"])


def _actor(user: User) -> str:
    return str(getattr(user, "email", None) or getattr(user, "id", None) or "admin")


class PreviewIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=2000)


class CommandIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=2000)
    idempotency_key: str | None = Field(None, max_length=80)
    confirm: bool = False
    run_now: bool = False


class KillIn(BaseModel):
    key: str = Field(..., min_length=3, max_length=64)
    engaged: bool
    reason: str = Field("", max_length=200)


class AgentControlIn(BaseModel):
    note: str = Field("", max_length=200)


class ReassignIn(BaseModel):
    agent_id: str = Field(..., min_length=2, max_length=40)


class ApprovalDecideIn(BaseModel):
    decision: str = Field(..., min_length=6, max_length=32)
    reason: str = Field("", max_length=200)


@router.get("/home")
async def owner_home(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.owner_home()


@router.get("/agents")
async def owner_agents(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.agent_registry()


@router.get("/inventory")
async def owner_inventory(user: User = Depends(require_admin)) -> dict[str, Any]:
    reg = owner_os.agent_registry()
    return {
        "ok": True,
        "inventory": reg.get("inventory"),
        "manager_explanation": reg.get("manager_explanation"),
        "system_supervisors": reg.get("system_supervisors"),
        "service_identities": reg.get("service_identities"),
        "runnable_members": reg.get("runnable_members"),
        "pause_semantics": reg.get("pause_semantics"),
    }


@router.get("/agents/{agent_id}")
async def owner_agent_detail(agent_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    reg = owner_os.agent_registry()
    hit = next((a for a in reg.get("agents") or [] if a.get("id") == agent_id), None)
    if not hit:
        raise HTTPException(status_code=404, detail="agent not found")
    return {
        "ok": True,
        "agent": hit,
        "pause_scope": "manual_runs_only",
        "pause_label": "Pause Manual Runs",
        "pause_note": owner_os.PAUSE_SCOPE_NOTE,
    }


@router.post(
    "/agents/{agent_id}/pause",
    dependencies=[Depends(rate_limit("owner_os", 30, 60))],
)
async def owner_pause_agent(
    agent_id: str, body: AgentControlIn | None = None, user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.platform import agent_controls
    from app.platform.office_hq import RUNNABLE_MEMBERS

    if agent_id not in RUNNABLE_MEMBERS:
        raise HTTPException(
            status_code=400,
            detail="Pause Manual Runs sirf RUNNABLE agents pe. Scheduled jobs alag — Automation → Schedule.",
        )
    note = (body.note if body else "") or "owner_os Pause Manual Runs"
    out = agent_controls.pause(agent_id, by=_actor(user), note=note)
    owner_os.audit(_actor(user), "agent_pause_manual_runs", {"agent_id": agent_id, "note": note})
    return {
        **out,
        "pause_label": "Pause Manual Runs",
        "pause_scope": "manual_runs_only",
        "note": owner_os.PAUSE_SCOPE_NOTE,
    }


@router.post(
    "/agents/{agent_id}/resume",
    dependencies=[Depends(rate_limit("owner_os", 30, 60))],
)
async def owner_resume_agent(agent_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    from app.platform import agent_controls

    out = agent_controls.resume(agent_id, by=_actor(user))
    owner_os.audit(_actor(user), "agent_resume_manual_runs", {"agent_id": agent_id})
    return {
        **out,
        "pause_label": "Resume Manual Runs",
        "pause_scope": "manual_runs_only",
        "note": owner_os.PAUSE_SCOPE_NOTE,
    }


@router.get("/tasks")
async def owner_tasks(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.task_board()


@router.get("/approvals")
async def owner_approvals(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.approvals_inbox()


@router.post(
    "/approvals/verification",
    dependencies=[Depends(rate_limit("owner_os", 10, 60))],
)
async def owner_create_verification_approval(user: User = Depends(require_admin)) -> dict[str, Any]:
    """Create one disposable internal approval (no external side effects)."""
    out = owner_os.create_verification_approval(actor=_actor(user))
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "create failed")
    return out


@router.post(
    "/approvals/{source}/{item_id}/decide",
    dependencies=[Depends(rate_limit("owner_os", 20, 60))],
)
async def owner_decide_approval(
    source: str,
    item_id: str,
    body: ApprovalDecideIn,
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    out = owner_os.decide_approval(
        source, item_id, body.decision, actor=_actor(user), reason=body.reason
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "decide failed")
    # Keep Mission Control / Office HQ cache in sync (same as growth decide path).
    try:
        from app.platform import office_hq

        await office_hq.invalidate_snapshot_cache()
    except Exception:
        pass
    return out


@router.get("/kill-switches")
async def owner_kills(user: User = Depends(require_admin)) -> dict[str, Any]:
    return {"ok": True, "switches": owner_os.kill_switch_board()}


@router.post(
    "/kill-switches",
    dependencies=[Depends(rate_limit("owner_os_kill", 20, 60))],
)
async def owner_set_kill(body: KillIn, user: User = Depends(require_admin)) -> dict[str, Any]:
    out = owner_os.set_kill_switch(body.key, body.engaged, by=_actor(user), reason=body.reason)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "kill switch refused")
    return out


@router.get("/training")
async def owner_training(page: str = "home", user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.training(page)


@router.get("/audit")
async def owner_audit(limit: int = 40, user: User = Depends(require_admin)) -> dict[str, Any]:
    return {"ok": True, "events": owner_os.recent_audit(min(max(limit, 1), 100))}


@router.post("/commands/preview", dependencies=[Depends(rate_limit("owner_os", 40, 60))])
async def owner_preview(body: PreviewIn, user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.parse_intent(body.text)


@router.get("/commands")
async def owner_list_commands(
    limit: int = 40, user: User = Depends(require_admin)
) -> dict[str, Any]:
    return {"ok": True, "commands": owner_os.list_commands(min(max(limit, 1), 100))}


@router.get("/commands/{command_id}")
async def owner_get_command(command_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    cmd = owner_os.get_command(command_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="command not found")
    return {"ok": True, "command": cmd}


@router.post("/commands", dependencies=[Depends(rate_limit("owner_os", 20, 60))])
async def owner_create_command(
    body: CommandIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    actor = _actor(user)
    if body.run_now:
        out = owner_os.run_now(body.text, actor=actor, idempotency_key=body.idempotency_key)
    else:
        out = owner_os.create_command(
            body.text, actor=actor, idempotency_key=body.idempotency_key, confirm=body.confirm
        )
        if body.confirm and (out.get("command") or {}).get("status") in ("READY", "QUEUED"):
            cid = out["command"]["command_id"]
            owner_os._update_command(cid, status="QUEUED", progress=5)
            out["executed"] = owner_os.execute_command(cid, actor=actor)
    return out


@router.post(
    "/commands/{command_id}/approve", dependencies=[Depends(rate_limit("owner_os", 20, 60))]
)
async def owner_approve(command_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    out = owner_os.approve_command(command_id, actor=_actor(user))
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "approve failed")
    return out


@router.post(
    "/commands/{command_id}/execute", dependencies=[Depends(rate_limit("owner_os", 20, 60))]
)
async def owner_execute(command_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    out = owner_os.execute_command(command_id, actor=_actor(user))
    if not out.get("ok") and out.get("error"):
        # still return body for evidence; HTTP 200 with ok=false is fine for UI
        return out
    return out


@router.post(
    "/commands/{command_id}/cancel", dependencies=[Depends(rate_limit("owner_os", 20, 60))]
)
async def owner_cancel(command_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    out = owner_os.cancel_command(command_id, actor=_actor(user))
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "cancel failed")
    return out


@router.post("/commands/{command_id}/retry", dependencies=[Depends(rate_limit("owner_os", 20, 60))])
async def owner_retry(command_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    out = owner_os.retry_command(command_id, actor=_actor(user))
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "retry failed")
    # auto-execute safe retries
    if (out.get("command") or {}).get("status") == "QUEUED":
        out["executed"] = owner_os.execute_command(command_id, actor=_actor(user))
    return out


@router.post(
    "/commands/{command_id}/reassign", dependencies=[Depends(rate_limit("owner_os", 20, 60))]
)
async def owner_reassign(
    command_id: str, body: ReassignIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    out = owner_os.reassign_command(command_id, body.agent_id, actor=_actor(user))
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "reassign failed")
    return out
