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
    reason: str = Field("", max_length=200)
    ttl_hours: int | None = Field(None, ge=1, le=168)
    idempotency_key: str | None = Field(None, max_length=80)


class AgentExecutionControlIn(BaseModel):
    """V1.1 scoped execution controls (Isha slice first)."""

    manual_pause: bool | None = None
    scheduled_pause: bool | None = None
    stop_claims: bool | None = None
    drain: bool | None = None
    reason: str = Field("", max_length=200)
    ttl_hours: int | None = Field(None, ge=1, le=168)
    idempotency_key: str | None = Field(None, max_length=80)


class TaskControlIn(BaseModel):
    task_id: str = Field(..., min_length=4, max_length=80)
    reason: str = Field("", max_length=200)


class RouteHealthIn(BaseModel):
    """Sanitized non-customer route probe — approved task keys only."""

    task_type: str = Field("leadgen.agent_ops", min_length=8, max_length=64)
    prompt: str = Field("Reply with exactly: OWNER_OS_ROUTE_OK", min_length=8, max_length=120)


class ReassignIn(BaseModel):
    agent_id: str = Field(..., min_length=2, max_length=40)


class ApprovalDecideIn(BaseModel):
    decision: str = Field(..., min_length=6, max_length=32)
    reason: str = Field("", max_length=200)


class RuntimeRunIn(BaseModel):
    """Agent Runtime pilot dispatch (Phase-B). Runner enforces the full contract
    policy (pilot allowlist / RED block / kill / approval / budget) fail-CLOSED."""

    agent_id: str = Field(..., min_length=2, max_length=40)
    action: str = Field(..., min_length=3, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = Field("", max_length=80)
    approval_ref: str = Field("", max_length=80)
    idempotency_key: str = Field("", max_length=80)
    timeout_s: float | None = Field(None, gt=0, le=600)


@router.get("/home")
async def owner_home(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.owner_home()


@router.get("/agents")
async def owner_agents(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.agent_registry()


@router.get("/maturity")
async def owner_agent_maturity(user: User = Depends(require_admin)) -> dict[str, Any]:
    """31-agent memory/KB/skills/governance matrix; read-only projection."""
    from app.platform import agent_maturity

    return agent_maturity.portfolio()


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
    from app.platform import owner_agent_execution as oae

    snap = (
        oae.isha_execution_snapshot()
        if agent_id == "isha"
        else {
            "ok": True,
            "agent_id": agent_id,
            "control": oae.control_view(agent_id),
            "counts": oae.task_counts_for_agent(agent_id),
            "workflows": [],
            "omniroute": {},
            "calling_hard_off": True,
        }
    )
    from app.platform import agent_maturity

    return {
        "ok": True,
        "agent": hit,
        "maturity": agent_maturity.profile(agent_id),
        "pause_scope": "manual_runs_only",
        "pause_label": "Pause Manual Runs",
        "pause_note": owner_os.PAUSE_SCOPE_NOTE,
        "execution": snap,
    }


@router.post(
    "/agents/{agent_id}/pause",
    dependencies=[Depends(rate_limit("owner_os", 30, 60))],
)
async def owner_pause_agent(
    agent_id: str, body: AgentControlIn | None = None, user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.platform import owner_agent_execution as oae
    from app.platform.office_hq import RUNNABLE_MEMBERS

    if agent_id not in RUNNABLE_MEMBERS:
        raise HTTPException(
            status_code=400,
            detail="Pause Manual Runs sirf RUNNABLE agents pe. Scheduled jobs alag — Automation → Schedule.",
        )
    note = (
        (body.note if body else "") or (body.reason if body else "") or "owner_os Pause Manual Runs"
    )
    out = oae.set_control(
        agent_id,
        by=_actor(user),
        reason=note,
        ttl_hours=body.ttl_hours if body else None,
        idempotency_key=body.idempotency_key if body else None,
        manual_pause=True,
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "pause failed")
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
    from app.platform import owner_agent_execution as oae

    out = oae.resume(agent_id, by=_actor(user), reason="owner_os resume")
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "resume failed")
    return {
        **out,
        "pause_label": "Resume Manual Runs",
        "pause_scope": "manual_runs_only",
        "note": owner_os.PAUSE_SCOPE_NOTE,
    }


@router.post(
    "/agents/{agent_id}/controls",
    dependencies=[Depends(rate_limit("owner_os", 30, 60))],
)
async def owner_set_agent_controls(
    agent_id: str, body: AgentExecutionControlIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    """V1.1: set scoped execution controls (scheduled pause / stop claims / drain)."""
    from app.platform import owner_agent_execution as oae

    flags = {
        k: v
        for k, v in {
            "manual_pause": body.manual_pause,
            "scheduled_pause": body.scheduled_pause,
            "stop_claims": body.stop_claims,
            "drain": body.drain,
        }.items()
        if v is not None
    }
    if not flags:
        raise HTTPException(status_code=400, detail="at least one control flag required")
    out = oae.set_control(
        agent_id,
        by=_actor(user),
        reason=body.reason or "owner_os execution control",
        ttl_hours=body.ttl_hours,
        idempotency_key=body.idempotency_key,
        **flags,
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "control failed")
    return out


@router.post(
    "/agents/{agent_id}/restore-defaults",
    dependencies=[Depends(rate_limit("owner_os", 30, 60))],
)
async def owner_restore_agent_defaults(
    agent_id: str, user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.platform import owner_agent_execution as oae

    return oae.restore_defaults(agent_id, by=_actor(user))


@router.post(
    "/agents/{agent_id}/cancel-queued",
    dependencies=[Depends(rate_limit("owner_os", 20, 60))],
)
async def owner_cancel_queued(
    agent_id: str, body: TaskControlIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.platform import owner_agent_execution as oae

    out = oae.cancel_queued_task(agent_id, body.task_id, by=_actor(user), reason=body.reason)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "cancel failed")
    return out


@router.post(
    "/agents/{agent_id}/request-cancel-running",
    dependencies=[Depends(rate_limit("owner_os", 20, 60))],
)
async def owner_request_cancel_running(
    agent_id: str, body: TaskControlIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.platform import owner_agent_execution as oae

    out = oae.request_cancel_running(agent_id, body.task_id, by=_actor(user), reason=body.reason)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "request failed")
    return out


@router.get("/workflows")
async def owner_workflows(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.workflow_registry()


@router.get("/workflows/{workflow_id}")
async def owner_workflow_detail(
    workflow_id: str, user: User = Depends(require_admin)
) -> dict[str, Any]:
    out = owner_os.workflow_detail(workflow_id)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error") or "not found")
    return out


@router.get("/routes")
async def owner_route_matrix(user: User = Depends(require_admin)) -> dict[str, Any]:
    return owner_os.route_matrix()


@router.post(
    "/routes/health-test",
    dependencies=[Depends(rate_limit("owner_os_route", 10, 60))],
)
async def owner_route_health_test(
    body: RouteHealthIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    out = await owner_os.route_health_test(
        task_type=body.task_type, prompt=body.prompt, actor=_actor(user)
    )
    if not out.get("ok") and out.get("error"):
        raise HTTPException(status_code=400, detail=out.get("error"))
    return out


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


@router.get("/runtime")
async def owner_runtime_status(user: User = Depends(require_admin)) -> dict[str, Any]:
    """Agent Runtime (Phase-B) operator board — mode/lane, heartbeats, useful work,
    active tasks, budgets, kill-switch state, runtime DLQ. Never raises."""
    from app.platform import agent_runtime
    from app.platform.agent_runtime_workforce import (
        ensure_workforce_registered,
        workforce_rollout_state,
    )

    ensure_workforce_registered()
    out = agent_runtime.runtime_status()
    out["dlq_tail"] = agent_runtime.runtime_dlq(20)
    out["workforce_rollout"] = workforce_rollout_state()
    from app.platform.workforce_runtime import provider_for, rollout_wave
    from app.platform.workforce_runtime import runtime_status as workforce_runtime_status

    out["workforce_runtime"] = workforce_runtime_status()
    for row in out.get("agents") or []:
        agent_id = str(row.get("agent_id") or "")
        row["provider"] = provider_for(agent_id)
        row["rollout_wave"] = rollout_wave(agent_id)
    return out


class MissionChatIn(BaseModel):
    text: str = Field(..., min_length=2, max_length=500)
    base_sha: str = Field("", max_length=64)
    idempotency_key: str = Field("", max_length=80)
    confirm: bool = False


@router.get("/missions")
async def owner_missions(user: User = Depends(require_admin)) -> dict[str, Any]:
    """Chat-first mission control board (durable ledger; not a 32nd agent)."""
    from app.platform import mission_control as mc

    return mc.mission_status()


@router.get("/missions/{mission_id}")
async def owner_mission_one(mission_id: str, user: User = Depends(require_admin)) -> dict[str, Any]:
    from app.platform import mission_control as mc

    out = mc.mission_status(mission_id)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error") or "not_found")
    return out


@router.post("/missions/chat", dependencies=[Depends(rate_limit("owner_os", 30, 60))])
async def owner_mission_chat(
    body: MissionChatIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Short chat → durable mission packet. RED outbound cannot be armed here."""
    from app.platform import mission_control as mc

    return mc.handle_chat(
        body.text,
        actor=_actor(user),
        base_sha=body.base_sha or None,
        idempotency_key=body.idempotency_key or None,
        confirm=body.confirm,
    )


@router.post(
    "/runtime/run",
    dependencies=[Depends(rate_limit("owner_os_runtime", 15, 60))],
)
async def owner_runtime_run(
    body: RuntimeRunIn, user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Operator-triggered runtime dispatch under FULL contract policy. Non-pilot /
    RED / kill-engaged / unapproved AMBER = structured blocked result (fail-closed)."""
    from app.platform import agent_runtime
    from app.platform.agent_runtime_workforce import ensure_workforce_registered

    ensure_workforce_registered()
    result = await agent_runtime.submit(
        body.agent_id,
        body.action,
        body.payload,
        tenant_id=body.tenant_id,
        approval_ref=body.approval_ref,
        idempotency_key=body.idempotency_key,
        trigger="owner_os",
        timeout_s=body.timeout_s,
    )
    owner_os.audit(
        _actor(user),
        "agent_runtime_run",
        {
            "target": body.agent_id,
            "agent_id": body.agent_id,
            "action": body.action,
            "status": result.status,
            "reason": result.reason,
            "tenant_id": body.tenant_id,
            "task_id": result.task_id,
        },
    )
    out: dict[str, Any] = {
        "ok": result.status in ("succeeded", "queued"),
        "result": result.to_dict(),
        "agent_id": body.agent_id,
        "capability": body.action,
        "status": result.status,
        "reason_code": result.reason or "",
        "provider": result.provider,
        "queue": result.queue,
        "heartbeat": result.heartbeat,
        "runtime_version": result.runtime_version,
        "rollout_wave": result.rollout_wave,
    }
    # Durable duplicate / store-unavailable projection (no fabricated IDs)
    try:
        from app.platform import agent_runtime_idempotency as arid

        out["idempotency_backend"] = arid.backend_status().get("idempotency_backend")
        out["fallback_active"] = arid.backend_status().get("fallback_active")
    except Exception:
        out["idempotency_backend"] = "unknown"
        out["fallback_active"] = True
    if result.reason in ("duplicate_suppressed", "duplicate_in_progress") and isinstance(
        result.output, dict
    ):
        out["original_run_id"] = result.output.get("original_run_id")
        out["original_status"] = result.output.get("original_status")
        out["result_reference"] = result.output.get("result_digest")
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
