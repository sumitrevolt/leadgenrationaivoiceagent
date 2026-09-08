"""Typed OpenClaw command catalogue — each handler calls Owner OS / read adapters only."""

from __future__ import annotations

import re
from typing import Any, Callable

from app.integrations.openclaw.context_builder import build_owner_context
from app.integrations.openclaw.policies import (
    AMBER_COMMANDS,
    GREEN_COMMANDS,
    RED_COMMANDS,
    safety_lane_for,
)

Handler = Callable[..., dict[str, Any]]


def list_command_catalogue() -> dict[str, Any]:
    rows = []
    for name in sorted(GREEN_COMMANDS | AMBER_COMMANDS | RED_COMMANDS):
        lane = safety_lane_for(name)
        rows.append(
            {
                "command": name,
                "safety_lane": lane,
                "permission": "super_admin",
                "approval_required": lane == "AMBER",
                "idempotent": lane == "GREEN" or name in ("agent.pause", "agent.resume"),
                "timeout_seconds": 12,
                "rollback": "n/a-read" if lane == "GREEN" else "resume_or_owner_os",
                "openclaw_executable": lane != "RED",
            }
        )
    return {"ok": True, "commands": rows, "count": len(rows)}


def _platform_status(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform import owner_os

    home = owner_os.owner_home()
    ctx = build_owner_context(tenant_id=params.get("tenant_id"))
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "owner_home_ok": bool(home.get("ok")),
            "calling_badge": home.get("calling_badge") or "Calling HARD OFF",
            "workforce": home.get("workforce"),
            "approvals_pending": home.get("approvals_pending"),
            "tasks": home.get("tasks"),
            "context": ctx,
        },
        "evidence": {
            "sources": ["owner_os.owner_home", "openclaw.context_builder"],
            "actor": actor,
            "correlation_id": correlation_id,
        },
        "next_action": (home.get("recommended") or [{}])[0].get("label")
        or "Pending approvals check karo",
    }


def _agents_list(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform import owner_os

    reg = owner_os.agent_registry()
    agents = reg.get("agents") or []
    slim = [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "status": a.get("status"),
            "paused": bool(a.get("paused")),
            "product": a.get("product"),
        }
        for a in agents
    ]
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "staff_count": reg.get("staff_count"),
            "inventory": reg.get("inventory"),
            "manager_explanation": reg.get("manager_explanation"),
            "agents": slim,
        },
        "evidence": {"count": len(slim), "correlation_id": correlation_id, "actor": actor},
        "next_action": "Unhealthy/paused agents review karo",
    }


def _agent_status(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform import owner_agent_execution as oae
    from app.platform import owner_os

    agent_id = str(params.get("agent_id") or params.get("agent") or "").strip()
    if not agent_id:
        return {"status": "FAILED", "verified": True, "error": "agent_id required", "result": None}
    reg = owner_os.agent_registry()
    hit = next((a for a in (reg.get("agents") or []) if a.get("id") == agent_id), None)
    if not hit:
        return {"status": "FAILED", "verified": True, "error": "agent not found", "result": None}
    ctrl = oae.control_view(agent_id)
    result: dict[str, Any] = {
        "agent": hit,
        "control": ctrl,
        "calling_hard_off": True,
    }
    # Swara / Ananya — OpenClaw transfer package (voice code untouched).
    if agent_id in ("swara", "ananya"):
        result["openclaw_transfer"] = {
            "status": "FROZEN",
            "modification_permission": "NONE",
            "calling": "HARD_OFF",
            "runtime_dispatch": "blocked_red_lane",
            "note": (
                "Fully configured voice agent — OpenClaw observes via Owner OS; "
                "no voice/STT/TTS/dial mutation through Copilot."
            ),
        }
    # Automation-Max agents — observe package (cadence/ops/content/outreach).
    try:
        from app.integrations.openclaw.automation_commands import automation_agent_package

        auto_pkg = automation_agent_package(agent_id)
        if auto_pkg:
            result["openclaw_automation"] = auto_pkg
    except Exception:
        pass
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": result,
        "evidence": {"agent_id": agent_id, "correlation_id": correlation_id, "actor": actor},
        "next_action": None,
    }


def _agents_unhealthy(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    """GREEN: list agents with bad/stale runtime health (Owner OS runtime board)."""
    from app.platform import agent_runtime
    from app.platform.agent_runtime_workforce import ensure_workforce_registered

    ensure_workforce_registered()
    status = agent_runtime.runtime_status()
    bad = {
        "stale_useful_work",
        "unknown",
        "blocked",
        "failed",
    }
    unhealthy = [
        a
        for a in (status.get("agents") or [])
        if str(a.get("health") or "") in bad
        or bool(a.get("last_error"))
        or bool(a.get("active_tasks"))
        and str(a.get("health") or "").startswith("fail")
    ]
    # Also surface kill-engaged + paused from Owner OS registry.
    from app.platform import owner_os

    reg = owner_os.agent_registry()
    paused = [a for a in (reg.get("agents") or []) if a.get("paused")]
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "unhealthy_runtime": unhealthy,
            "paused": [{"id": a.get("id"), "name": a.get("name")} for a in paused],
            "runtime_enabled": status.get("runtime_enabled"),
            "pilots": status.get("pilots"),
            "calling_hard_off": True,
        },
        "evidence": {
            "unhealthy_count": len(unhealthy),
            "paused_count": len(paused),
            "correlation_id": correlation_id,
            "actor": actor,
        },
        "next_action": (
            "Pause/drain via Owner OS approval path"
            if unhealthy or paused
            else "Fleet healthy / idle"
        ),
    }


def _runtime_status(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform import agent_runtime
    from app.platform.agent_runtime_workforce import (
        ensure_workforce_registered,
        workforce_rollout_state,
    )

    ensure_workforce_registered()
    status = agent_runtime.runtime_status()
    rollout = workforce_rollout_state()
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "runtime": {
                "ok": status.get("ok"),
                "runtime_enabled": status.get("runtime_enabled"),
                "pilots": status.get("pilots"),
                "agent_count": len(status.get("agents") or []),
            },
            "workforce_rollout": {
                "staff_count": rollout.get("staff_count"),
                "pilots": rollout.get("pilots"),
                "frozen_voice": rollout.get("frozen_voice"),
                "states": {
                    a["agent_id"]: a["rollout_state"] for a in (rollout.get("agents") or [])
                },
            },
            "calling_hard_off": True,
        },
        "evidence": {"correlation_id": correlation_id, "actor": actor, "source": "agent_runtime"},
        "next_action": "Owner OS Runtime tab for per-agent board",
    }


def _approvals_list(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform import owner_os

    inbox = owner_os.approvals_inbox()
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": inbox,
        "evidence": {"pending": inbox.get("pending"), "correlation_id": correlation_id},
        "next_action": (
            "Pending approvals decide karo (Owner OS Approvals tab)"
            if inbox.get("pending")
            else "Koi pending approval nahi"
        ),
    }


def _queues_status(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform.automation_health import queue_depth

    qd = queue_depth() or {}
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "celery": int(qd.get("celery") or 0),
            "dlq_failed": int(qd.get("dlq") or 0),
            "dlq_dead": int(qd.get("dead") or 0),
            "raw_keys": sorted(qd.keys())[:20],
        },
        "evidence": {"source": "automation_health.queue_depth", "correlation_id": correlation_id},
        "next_action": "DLQ review" if (qd.get("dlq") or qd.get("dead")) else None,
    }


def _delivery_status(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.marketing.clients_store import canonical_client_id, resolve_client
    from app.platform import owner_os

    raw = params.get("tenant_id") or params.get("client_id")
    if raw is None or not str(raw).strip():
        return {
            "status": "FAILED",
            "verified": True,
            "error": "tenant_id required",
            "result": None,
            "evidence": {"correlation_id": correlation_id, "actor": actor},
            "next_action": "Pass tenant_id (marketing id or billing alias)",
        }
    requested = str(raw).strip()
    rec = resolve_client(requested)
    if not rec:
        return {
            "status": "FAILED",
            "verified": True,
            "error": "unknown tenant",
            "result": None,
            "evidence": {
                "requested": requested[:80],
                "correlation_id": correlation_id,
                "actor": actor,
            },
            "next_action": "Use canonical marketing client id or known billing alias",
        }
    tenant = canonical_client_id(requested)
    # Reuse Owner OS safe status report — publish/notify forced off upstream.
    if hasattr(owner_os, "_build_status_report"):
        rep = owner_os._build_status_report(tenant)  # noqa: SLF001
    else:
        rep = {"tenant_id": tenant, "note": "status_report builder unavailable"}
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "tenant_id": tenant,
            "requested_tenant": requested,
            "report": rep,
            "publish_allowed": False,
            "customer_notify_allowed": False,
        },
        "evidence": {"tenant_id": tenant, "correlation_id": correlation_id, "actor": actor},
        "next_action": "Pending approvals / Meta connect (human)",
    }


def _daily_summary(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    ctx = build_owner_context(tenant_id=params.get("tenant_id"))
    home_bits = _platform_status(params, actor=actor, correlation_id=correlation_id)
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "summary_hinglish": _hinglish_summary(ctx),
            "context": ctx,
            "platform": (home_bits.get("result") or {}),
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": (ctx.get("next_actions") or [{}])[0].get("label"),
    }


def _next_actions(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    ctx = build_owner_context(tenant_id=params.get("tenant_id"))
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {"actions": ctx.get("next_actions") or [], "safety": ctx.get("safety")},
        "evidence": {"correlation_id": correlation_id, "actor": actor},
        "next_action": (ctx.get("next_actions") or [{}])[0].get("label"),
    }


def _hinglish_summary(ctx: dict[str, Any]) -> str:
    a = ctx.get("agents") or {}
    q = ctx.get("queues") or {}
    ap = ctx.get("approvals") or {}
    return (
        f"Platform {(ctx.get('platform') or {}).get('health')} · "
        f"agents {a.get('total')}/31 · paused_manual {a.get('paused_manual_run_count') or len(a.get('paused') or [])} · "
        f"approvals {ap.get('pending')} · "
        f"queues celery={q.get('pending')} dlq={q.get('failed')} dead={q.get('dead')} · "
        f"Calling HARD OFF."
    )


def _amber_stub(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    """Should not be reached without approval path — safety net."""
    return {
        "status": "APPROVAL_REQUIRED",
        "approval_required": True,
        "verified": True,
        "result": {"note": "AMBER must park via owner_os_adapter"},
        "evidence": {"correlation_id": correlation_id, "actor": actor},
    }


HANDLERS: dict[str, Handler] = {
    "platform.status": _platform_status,
    "agents.list": _agents_list,
    "agents.unhealthy": _agents_unhealthy,
    "agent.status": _agent_status,
    "approvals.list": _approvals_list,
    "queues.status": _queues_status,
    "delivery.status": _delivery_status,
    "business.daily_summary": _daily_summary,
    "owner.next_actions": _next_actions,
    "runtime.status": _runtime_status,
    "agent.pause": _amber_stub,
    "agent.resume": _amber_stub,
    "agent.drain": _amber_stub,
    "agent.stop_claims": _amber_stub,
    "agent.assign_mission": _amber_stub,
    "approval.decide": _amber_stub,
}

# --- Kavach harness handlers (additive; GREEN read + AMBER parked) ---
try:
    from app.integrations.openclaw.harness_commands import HARNESS_HANDLERS

    HANDLERS.update(HARNESS_HANDLERS)
except Exception:  # never break the base command surface
    pass

# --- Automation-Max handlers (additive GREEN observe) ---
try:
    from app.integrations.openclaw.automation_commands import AUTOMATION_HANDLERS

    HANDLERS.update(AUTOMATION_HANDLERS)
except Exception:
    pass

# --- External Agent Orchestrator handlers (additive GREEN observe) ---
try:
    from app.integrations.openclaw.external_agent_commands import EXTERNAL_AGENT_HANDLERS

    HANDLERS.update(EXTERNAL_AGENT_HANDLERS)
except Exception:
    pass

# --- Mission-control chat ingress (GREEN create/status + AMBER parked) ---
try:
    from app.integrations.openclaw.mission_commands import MISSION_HANDLERS

    HANDLERS.update(MISSION_HANDLERS)
except Exception:
    pass


def execute_typed_command(
    command: str,
    params: dict[str, Any] | None = None,
    *,
    actor: str = "admin",
    idempotency_key: str | None = None,
    confirm: bool = False,
    correlation_id: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    from app.integrations.openclaw.owner_os_adapter import run_via_owner_os

    return run_via_owner_os(
        command,
        params or {},
        actor=actor,
        idempotency_key=idempotency_key,
        confirm=confirm,
        correlation_id=correlation_id,
        text=text,
    )


def classify_nl(text: str) -> dict[str, Any]:
    """Deterministic NL → typed command. Ambiguous → read-only preference."""
    raw = (text or "").strip()
    low = raw.lower()
    params: dict[str, Any] = {}

    # RED phrases first — never escalate.
    if any(
        x in low
        for x in (
            "calling enable",
            "enable calling",
            "enable calls",
            "start calling",
            "call chalu",
            "platform_dial",
            "deploy prod",
            "production deploy",
            "refund",
            "billing activate",
            "upi activate",
            "bulk email",
            "mass whatsapp",
            "drop table",
            "rm -rf",
            "shell",
            "ssh root",
        )
    ):
        cmd = "calling.enable" if "call" in low or "dial" in low else "deploy.production"
        if "refund" in low or "billing" in low or "upi activate" in low:
            cmd = "billing.mutate"
        if "bulk" in low or "mass" in low:
            cmd = "customer.bulk_outreach"
        if "drop table" in low or "sql" in low:
            cmd = "sql.execute"
        if "shell" in low or "ssh" in low or "rm -rf" in low:
            cmd = "shell.execute"
        return {
            "ok": True,
            "command": cmd,
            "params": params,
            "safety_lane": "RED",
            "confidence": "high",
            "original": raw[:2000],
            "note": "RED — OpenClaw refuse; existing admin workflow use karo",
        }

    # Agent extract (reuse Owner OS helper when available). Never invent a tenant.
    try:
        from app.platform.owner_os import _extract_agent, _extract_tenant

        agent = _extract_agent(raw)
        tenant = _extract_tenant(raw)
        if agent:
            params["agent_id"] = agent
        if tenant:
            params["tenant_id"] = tenant
    except Exception:
        pass

    if re.search(r"\b(pause|rok)\b", low) and params.get("agent_id"):
        return _prop("agent.pause", params, raw, "AMBER")
    if re.search(r"\b(resume|chalu|unpause)\b", low) and params.get("agent_id"):
        return _prop("agent.resume", params, raw, "AMBER")
    if "drain" in low and params.get("agent_id"):
        return _prop("agent.drain", params, raw, "AMBER")
    if "approval" in low or "manzoori" in low:
        return _prop("approvals.list", params, raw, "GREEN")
    if any(x in low for x in ("queue", "celery", "dlq")):
        return _prop("queues.status", params, raw, "GREEN")
    if any(x in low for x in ("delivery", "deliverable")) and "mission" not in low:
        return _prop("delivery.status", params, raw, "GREEN")
    if any(x in low for x in ("next action", "highest-value", "kya karun", "priority")):
        return _prop("owner.next_actions", params, raw, "GREEN")
    if any(x in low for x in ("daily summary", "aaj ka", "business summary", "complete status")):
        return _prop("business.daily_summary", params, raw, "GREEN")
    if any(x in low for x in ("sab agents", "all agents", "workforce", "registry", "agents list")):
        return _prop("agents.list", params, raw, "GREEN")
    if any(x in low for x in ("currently active", "active agents", "kaun active", "which agents")):
        return _prop("agents.list", params, raw, "GREEN")
    if any(x in low for x in ("feature-flag", "feature flag", "flags state", "flag state")):
        return _prop("platform.status", params, raw, "GREEN")
    if any(
        x in low
        for x in (
            "automation status",
            "automation-max",
            "automation max",
            "cadence status",
            "ops watchdog",
            "band automations",
            "kaun sa engine on",
            "engines on",
        )
    ):
        return _prop("automation.status", params, raw, "GREEN")
    if any(
        x in low
        for x in (
            "automation agents",
            "cadence agent",
            "anika status",
            "kavya automation",
        )
    ):
        return _prop("automation.agents", params, raw, "GREEN")
    if any(
        x in low
        for x in (
            "unhealthy agents",
            "agents unhealthy",
            "missed heartbeat",
            "heartbeat miss",
            "kaun toot",
            "failed agents",
            "failed workflows",
            "failed workflow",
        )
    ):
        if "workflow" in low:
            return _prop("queues.status", params, raw, "GREEN")
        return _prop("agents.unhealthy", params, raw, "GREEN")
    if any(x in low for x in ("runtime status", "agent runtime", "pilot status", "rollout")):
        return _prop("runtime.status", params, raw, "GREEN")
    if params.get("agent_id") and any(x in low for x in ("status", "kaisa", "unhealthy", "frozen")):
        return _prop("agent.status", params, raw, "GREEN")
    if any(x in low for x in ("platform status", "health", "status batao", "pulse")):
        return _prop("platform.status", params, raw, "GREEN")
    if "mission" in low or "boss ko" in low:
        params["objective"] = raw[:500]
        return _prop("agent.assign_mission", params, raw, "AMBER")

    # Ambiguous → safest read.
    return _prop(
        "platform.status",
        params,
        raw,
        "GREEN",
        note="Ambiguous NL → read-only platform.status (fail-safe)",
        confidence="low",
    )


def _prop(
    command: str,
    params: dict[str, Any],
    raw: str,
    lane: str,
    *,
    note: str | None = None,
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "params": params,
        "safety_lane": lane,
        "confidence": confidence,
        "original": raw[:2000],
        "note": note,
        "approval_required": lane == "AMBER",
    }
