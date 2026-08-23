"""One canonical workforce dispatch seam: direct rollback or isolated DSH queue."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from app.platform.workforce_runtime import run_store
from app.platform.workforce_runtime.types import WorkforceRequest, WorkforceResult

logger = logging.getLogger(__name__)

DSH_RUNTIME_FLAG = "DSH_RUNTIME_ENABLED"
DSH_SHADOW_FLAG = "DSH_SHADOW_ENABLED"
DSH_ALLOWLIST_FLAG = "DSH_AGENT_ALLOWLIST"
DSH_QUEUE = "dsh"
FROZEN_AGENTS = frozenset({"swara", "ananya"})


def _flag_on(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return bool(value) and value not in {"0", "false", "no", "off"}


def _allowlist() -> frozenset[str]:
    values = {
        item.strip().lower()
        for item in (os.getenv(DSH_ALLOWLIST_FLAG) or "").split(",")
        if item.strip()
    }
    return frozenset() if "*" in values else frozenset(values)


def rollout_wave(agent_id: str = "") -> str:
    if str(agent_id or "").strip().lower() in FROZEN_AGENTS:
        return "frozen"
    value = (os.getenv("DSH_ROLLOUT_WAVE") or "hold").strip().lower()
    return value if value in {"hold", "shadow", "read_only", "draft", "green", "amber"} else "hold"


def provider_for(agent_id: str) -> str:
    aid = str(agent_id or "").strip().lower()
    if aid in FROZEN_AGENTS or aid not in _allowlist():
        return "direct"
    if _flag_on(DSH_RUNTIME_FLAG):
        return "dsh"
    if _flag_on(DSH_SHADOW_FLAG):
        return "direct+shadow"
    return "direct"


def _dsh_run_id(request: WorkforceRequest, idempotency_key: str, *, shadow: bool) -> str:
    identity = json.dumps(
        [
            request.tenant_id,
            request.agent_id,
            request.action,
            idempotency_key,
            "shadow" if shadow else "authority",
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return "dshrun_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _dsh_input_refusal(request: WorkforceRequest) -> WorkforceResult | None:
    try:
        from app.platform.safe_ai_payload import (
            SafePayloadError,
            mask_customer_data,
            validate_no_secrets,
        )

        validate_no_secrets(request.payload)
        if mask_customer_data(request.payload) != request.payload:
            raise SafePayloadError("raw_customer_data")
        return None
    except Exception as exc:
        reason = (
            "raw_customer_data_refused_use_opaque_refs"
            if str(exc) == "raw_customer_data"
            else "secret_material_refused"
        )
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="blocked",
            provider="dsh",
            reason=reason,
            rollout_wave=rollout_wave(request.agent_id),
        )


async def _direct(request: WorkforceRequest) -> WorkforceResult:
    from app.platform import agent_runtime
    from app.platform.agent_runtime_workforce import ensure_workforce_registered

    ensure_workforce_registered()
    result = await agent_runtime.run_task(
        agent_runtime.AgentTask(
            agent_id=request.agent_id,
            action=request.action,
            payload=dict(request.payload),
            tenant_id=request.tenant_id,
            approval_ref=request.approval_ref,
            idempotency_key=request.idempotency_key,
            trigger=request.trigger,
            timeout_s=request.timeout_s,
            task_id=request.run_id,
            created_at=request.created_at,
        )
    )
    return WorkforceResult(
        run_id=result.task_id,
        agent_id=result.agent_id,
        action=result.action,
        status=result.status,
        provider="direct",
        reason=result.reason,
        output=result.output,
        error_class=result.error_class,
        error_message=result.error_message,
        attempts=result.attempts,
        duration_ms=result.duration_ms,
        mode=result.mode,
        lane=result.lane,
        escalation=result.escalation,
        dlq=result.dlq,
        lifecycle=list(result.lifecycle),
        usage=dict(result.usage),
        decision=result.decision,
        rollout_wave=rollout_wave(request.agent_id),
    )


def _dsh_preflight(request: WorkforceRequest) -> WorkforceResult | None:
    """Reuse production policy reasons before granting authoritative DSH work."""
    try:
        from app.platform import agent_runtime
        from app.platform.agent_runtime_workforce import ensure_workforce_registered

        ensure_workforce_registered()
        _contract, _capability, refusal = agent_runtime.evaluate_policy(
            agent_runtime.AgentTask(
                agent_id=request.agent_id,
                action=request.action,
                payload=dict(request.payload),
                tenant_id=request.tenant_id,
                approval_ref=request.approval_ref,
                idempotency_key=request.idempotency_key,
                trigger=request.trigger,
                timeout_s=request.timeout_s,
                task_id=request.run_id,
                created_at=request.created_at,
            )
        )
        if refusal is None:
            return None
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status=refusal.status,
            provider="dsh",
            reason=refusal.reason,
            decision=refusal.decision,
            rollout_wave=rollout_wave(request.agent_id),
        )
    except Exception as exc:
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="blocked",
            provider="dsh",
            reason=f"policy_eval_error:{type(exc).__name__}",
            rollout_wave=rollout_wave(request.agent_id),
        )


def _enqueue_dsh(request: WorkforceRequest, *, shadow: bool) -> WorkforceResult:
    timeout = max(30.0, min(float(request.timeout_s or 300), 540.0))
    deadline = time.time() + timeout
    idempotency_key = request.idempotency_key or f"dsh_{request.run_id}_{request.action}"
    run_id = _dsh_run_id(request, idempotency_key, shadow=shadow)
    try:
        row, created = run_store.create_run(
            run_id=run_id,
            agent_id=request.agent_id,
            tenant_id=request.tenant_id,
            action=request.action,
            idempotency_key=idempotency_key,
            approval_ref=request.approval_ref,
            trigger=request.trigger,
            timeout_s=request.timeout_s,
            provider="dsh",
            shadow=shadow,
            deadline=deadline,
            input_payload=dict(request.payload),
        )
        if not created:
            return WorkforceResult(
                run_id=run_id,
                agent_id=request.agent_id,
                action=request.action,
                status=str(row.get("status") or "queued"),
                provider="dsh",
                reason="duplicate_submission",
                queue=DSH_QUEUE,
                heartbeat_at=str(row.get("heartbeat_at") or ""),
                runtime_version=str(row.get("runtime_version") or "47f943859bef"),
                rollout_wave=rollout_wave(request.agent_id),
            )
        run_store.append_event(
            run_id,
            "workforce_dispatched",
            {"provider": "dsh", "shadow": shadow, "trigger": request.trigger[:80]},
        )
        from app.tasks.dsh_jobs import run_dsh_workforce

        queued = run_dsh_workforce.apply_async(args=[run_id], queue=DSH_QUEUE)
        run_store.update_run(run_id, queue_task_id=str(queued.id or ""))
        return WorkforceResult(
            run_id=run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="queued",
            provider="dsh",
            reason="shadow_queued" if shadow else "",
            queue=DSH_QUEUE,
            heartbeat_at=str(row.get("heartbeat_at") or ""),
            runtime_version="47f943859bef",
            rollout_wave=rollout_wave(request.agent_id),
        )
    except ValueError as exc:
        reason = (
            "idempotency_payload_mismatch"
            if str(exc) == "run_immutable_collision"
            else "invalid_dsh_submission"
        )
        return WorkforceResult(
            run_id=run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="blocked",
            provider="dsh",
            reason=reason,
            queue=DSH_QUEUE,
            rollout_wave=rollout_wave(request.agent_id),
        )
    except Exception as exc:
        logger.warning("[workforce_dispatch] DSH enqueue failed: %s", type(exc).__name__)
        try:
            run_store.update_run(
                run_id,
                status="failed",
                reason=f"enqueue_failed:{type(exc).__name__}",
            )
        except Exception:
            pass
        return WorkforceResult(
            run_id=run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="failed",
            provider="dsh",
            reason=f"enqueue_failed:{type(exc).__name__}",
            queue=DSH_QUEUE,
            rollout_wave=rollout_wave(request.agent_id),
        )


async def dispatch(request: WorkforceRequest) -> WorkforceResult:
    """Execute through exactly one authority path; optional DSH shadow is inert."""
    selected = provider_for(request.agent_id)
    if selected == "direct":
        return await _direct(request)
    if selected == "direct+shadow":
        authoritative = await _direct(request)
        shadow_request = WorkforceRequest(
            agent_id=request.agent_id,
            action=request.action,
            payload=dict(request.payload),
            tenant_id=request.tenant_id,
            approval_ref=request.approval_ref,
            idempotency_key=request.idempotency_key,
            trigger=request.trigger,
            timeout_s=request.timeout_s,
        )
        refusal = _dsh_input_refusal(shadow_request)
        shadow = refusal or _enqueue_dsh(shadow_request, shadow=True)
        authoritative.shadow_run_id = shadow.run_id if shadow.status == "queued" else ""
        authoritative.reason = authoritative.reason or (
            "" if shadow.status == "queued" else shadow.reason
        )
        return authoritative

    refusal = _dsh_preflight(request)
    if refusal is not None:
        return refusal
    refusal = _dsh_input_refusal(request)
    if refusal is not None:
        return refusal
    return _enqueue_dsh(request, shadow=False)


async def submit(
    agent_id: str,
    action: str,
    payload: dict[str, Any] | None = None,
    *,
    tenant_id: str = "",
    approval_ref: str = "",
    idempotency_key: str = "",
    trigger: str = "on_demand",
    timeout_s: float | None = None,
) -> WorkforceResult:
    return await dispatch(
        WorkforceRequest(
            agent_id=str(agent_id or "").strip().lower(),
            action=str(action or "").strip(),
            payload=dict(payload or {}),
            tenant_id=str(tenant_id or "").strip(),
            approval_ref=str(approval_ref or "").strip(),
            idempotency_key=str(idempotency_key or "").strip(),
            trigger=str(trigger or "on_demand").strip(),
            timeout_s=timeout_s,
        )
    )


def runtime_status() -> dict[str, Any]:
    from app.platform import agent_runtime
    from app.platform.agent_runtime_workforce import ensure_workforce_registered

    ensure_workforce_registered()
    status = agent_runtime.runtime_status()
    allowlist = sorted(_allowlist())
    status.update(
        {
            "provider": (
                "dsh"
                if _flag_on(DSH_RUNTIME_FLAG)
                else "direct+shadow"
                if _flag_on(DSH_SHADOW_FLAG)
                else "direct"
            ),
            "dsh_runtime_enabled": _flag_on(DSH_RUNTIME_FLAG),
            "dsh_shadow_enabled": _flag_on(DSH_SHADOW_FLAG),
            "dsh_agent_allowlist": allowlist,
            "dsh_queue": DSH_QUEUE,
            "dsh_runtime_version": "47f943859bef",
            "rollout_wave": rollout_wave(),
            "rollback": f"{DSH_RUNTIME_FLAG}=0",
            "frozen_agents": sorted(FROZEN_AGENTS),
        }
    )
    for row in status.get("agents") or []:
        aid = str(row.get("agent_id") or "")
        row["provider"] = provider_for(aid)
        row["rollout_wave"] = rollout_wave(aid)
    return status


__all__ = [
    "DSH_ALLOWLIST_FLAG",
    "DSH_RUNTIME_FLAG",
    "DSH_SHADOW_FLAG",
    "FROZEN_AGENTS",
    "dispatch",
    "provider_for",
    "rollout_wave",
    "runtime_status",
    "submit",
]
