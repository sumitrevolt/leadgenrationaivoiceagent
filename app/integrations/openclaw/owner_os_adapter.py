"""Sole action path: OpenClaw → Owner OS typed services. No direct Celery/DB writes."""

from __future__ import annotations

import uuid
from typing import Any

from app.integrations.openclaw.audit import audit_openclaw
from app.integrations.openclaw.idempotency import MEMORY_STORE, get_store
from app.integrations.openclaw.policies import (
    command_permitted,
    durable_idempotency_ready,
    redact_secrets,
    require_approval_for_amber,
    safety_lane_for,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Back-compat for tests that clear in-process cache.
_IDEMPOTENCY = MEMORY_STORE
_GREEN_IDEMPOTENCY_TTL_S = 300


def _corr(explicit: str | None = None) -> str:
    return (explicit or "").strip() or ("oc_" + uuid.uuid4().hex[:16])


def prove_edge_receipt(
    *,
    actor: str = "mission-control-probe",
    command: str = "platform.status",
) -> dict[str, Any]:
    """Run one real GREEN Owner-Copilot command and return a durable receipt.

    This proves the in-process OpenClaw → Owner OS edge is callable. It is NOT
    an external OpenClaw Gateway session mint (LeadGen is inbound-only). The
    returned ``session_id`` is the live ``correlation_id`` / ``command_id`` from
    the executed handler — never a fabricated UUID.
    """
    from app.integrations.openclaw.policies import openclaw_enabled

    if not openclaw_enabled():
        return {
            "status": "flag_off",
            "session_id": None,
            "available": False,
            "note": "OPENCLAW_ENABLED off — edge not armed",
        }
    # Prefer mission.executors when registered (read-only), else platform.status.
    preferred = command
    try:
        from app.integrations.openclaw import commands as cmd_mod

        if preferred not in cmd_mod.HANDLERS and "platform.status" in cmd_mod.HANDLERS:
            preferred = "platform.status"
        elif preferred not in cmd_mod.HANDLERS and "mission.executors" in cmd_mod.HANDLERS:
            preferred = "mission.executors"
    except Exception:
        preferred = "platform.status"

    out = run_via_owner_os(
        preferred,
        {},
        actor=actor,
        idempotency_key=None,  # probe must mint a fresh receipt each time
        confirm=False,
    )
    ok = bool(out.get("ok")) and str(out.get("status") or "") == "SUCCEEDED"
    session_id = None
    if ok:
        session_id = str(out.get("correlation_id") or out.get("command_id") or "").strip() or None
    if ok and session_id:
        return {
            "status": "available",
            "session_id": session_id,
            "available": True,
            "command": preferred,
            "command_id": out.get("command_id"),
            "correlation_id": out.get("correlation_id"),
            "verified": bool(out.get("verified")),
            "safety_lane": out.get("safety_lane") or "GREEN",
            "note": (
                "In-process Owner-Copilot GREEN receipt (not an external OpenClaw Gateway session)"
            ),
            "receipt": {
                "status": out.get("status"),
                "next_action": out.get("next_action"),
            },
        }
    return {
        "status": "flag_on_no_session" if openclaw_enabled() else "flag_off",
        "session_id": None,
        "available": False,
        "command": preferred,
        "error": out.get("error") or out.get("status"),
        "note": "GREEN handler did not return SUCCEEDED receipt",
        "receipt": {"status": out.get("status"), "error": out.get("error")},
    }


def _idem_get(key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    # Prefer durable when available; otherwise memory (GREEN optimization only).
    store = get_store(prefer_durable=durable_idempotency_ready())
    return store.get(key)


def _idem_put(key: str | None, value: dict[str, Any]) -> None:
    if not key:
        return
    store = get_store(prefer_durable=durable_idempotency_ready())
    store.put(key, value, _GREEN_IDEMPOTENCY_TTL_S)
    # Keep memory mirror for local tests when durable path used.
    if store is not MEMORY_STORE:
        MEMORY_STORE.put(key, value, _GREEN_IDEMPOTENCY_TTL_S)


def run_via_owner_os(
    command: str,
    params: dict[str, Any] | None,
    *,
    actor: str,
    idempotency_key: str | None = None,
    confirm: bool = False,
    correlation_id: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Execute one typed command through Owner OS. Verified result only."""
    corr = _corr(correlation_id)
    params = dict(params or {})
    lane = safety_lane_for(command)

    cached = _idem_get(idempotency_key)
    if cached:
        out = {**cached, "deduped": True, "correlation_id": corr}
        audit_openclaw(
            actor,
            "command_deduped",
            command=command,
            safety_lane=lane,
            correlation_id=corr,
            detail={"status": out.get("status")},
        )
        return out

    ok, reason = command_permitted(command)
    if not ok:
        out = {
            "ok": False,
            "command": command,
            "command_id": None,
            "correlation_id": corr,
            "safety_lane": lane,
            "status": "REJECTED",
            "approval_required": False,
            "error": reason,
            "verified": True,
            "result": None,
            "evidence": {"refusal": True, "reason": reason},
            "next_action": (
                "Owner OS / existing admin workflow use karo"
                if lane == "RED"
                else "OPENCLAW_ENABLED=1 set karo (local/stage) ya allowlist expand karo"
            ),
        }
        audit_openclaw(
            actor,
            "command_rejected",
            command=command,
            safety_lane=lane,
            correlation_id=corr,
            detail={"status": "REJECTED", "error": reason, "params": redact_secrets(params)},
        )
        return out

    if lane == "AMBER" and require_approval_for_amber():
        # AMBER always parks — confirm means "submit approval request", never silent mutate.
        # (Legacy `confirm=false` early-return lived in /nl; adapter must not treat confirm as bypass.)
        return _amber_hold(
            command, params, actor=actor, corr=corr, text=text, idempotency_key=idempotency_key
        )

    try:
        result = _dispatch(command, params, actor=actor, corr=corr)
    except Exception as exc:
        logger.exception("openclaw owner_os dispatch failed")
        out = {
            "ok": False,
            "command": command,
            "command_id": None,
            "correlation_id": corr,
            "safety_lane": lane,
            "status": "FAILED",
            "approval_required": False,
            "error": f"{type(exc).__name__}",
            "verified": False,
            "result": None,
            "evidence": {"exception_type": type(exc).__name__},
            "next_action": "Owner OS health check karo; OpenClaw fail-closed raha",
        }
        audit_openclaw(
            actor,
            "command_failed",
            command=command,
            safety_lane=lane,
            correlation_id=corr,
            detail={"status": "FAILED", "error": type(exc).__name__},
        )
        return out

    out = {
        "ok": True,
        "command": command,
        "command_id": result.get("command_id") or ("ocmd_" + corr[-12:]),
        "correlation_id": corr,
        "safety_lane": lane,
        "status": result.get("status") or "SUCCEEDED",
        "approval_required": bool(result.get("approval_required")),
        "approval_id": result.get("approval_id"),
        "result": redact_secrets(result.get("result")),
        "evidence": redact_secrets(result.get("evidence") or result.get("result")),
        "error": result.get("error"),
        "verified": bool(result.get("verified", True)),
        "deduped": False,
        "next_action": result.get("next_action"),
    }
    if out["ok"] and out["status"] == "SUCCEEDED":
        _idem_put(idempotency_key, out)
    audit_openclaw(
        actor,
        "command_executed",
        command=command,
        safety_lane=lane,
        correlation_id=corr,
        detail={"status": out["status"], "verified": out["verified"]},
    )
    return out


def _amber_hold(
    command: str,
    params: dict[str, Any],
    *,
    actor: str,
    corr: str,
    text: str | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    """Park AMBER mutation as Owner OS approval-required command — no direct mutate."""
    from app.platform import owner_os

    nl = text or _command_to_nl(command, params)
    created = owner_os.create_command(
        nl,
        actor=actor,
        idempotency_key=idempotency_key or f"oc-amber-{corr}",
        confirm=False,
    )
    cmd = created.get("command") or {}
    cid = created.get("command_id") or cmd.get("command_id")
    # Owner OS may mark some pauses as SAFE/READY — OpenClaw AMBER must still
    # require explicit Owner OS approve/execute (never silent mutate).
    if cid and cmd.get("status") in ("READY", "VALIDATED", "QUEUED", "DRAFT"):
        try:
            owner_os._update_command(  # noqa: SLF001 — intentional force-park
                cid,
                status="APPROVAL_REQUIRED",
                approval_required=True,
                approval_state="required",
            )
            cmd = owner_os.get_command(cid) or cmd
        except Exception:
            pass
    out = {
        "ok": True,
        "command": command,
        "command_id": cid or cmd.get("command_id"),
        "correlation_id": corr,
        "safety_lane": "AMBER",
        "status": "APPROVAL_REQUIRED",
        "approval_required": True,
        "approval_id": cid or cmd.get("command_id"),
        "result": {
            "owner_os_command": cid or cmd.get("command_id"),
            "plan": created.get("plan"),
            "params": redact_secrets(params),
            "note": "AMBER — Owner OS pe approve/execute karo; OpenClaw ne mutate nahi kiya",
        },
        "evidence": {"parked": True},
        "verified": True,
        "next_action": "Owner OS Approvals / Commands se confirm karo",
    }
    audit_openclaw(
        actor,
        "amber_parked",
        command=command,
        safety_lane="AMBER",
        correlation_id=corr,
        detail={"status": "APPROVAL_REQUIRED", "command_id": cid or cmd.get("command_id")},
    )
    return out


def _command_to_nl(command: str, params: dict[str, Any]) -> str:
    agent = params.get("agent_id") or params.get("agent") or ""
    tenant = params.get("tenant_id") or params.get("client_id") or ""
    mapping = {
        "agent.pause": f"Pause Manual Runs for agent {agent}".strip(),
        "agent.resume": f"Resume Manual Runs for agent {agent}".strip(),
        "agent.drain": f"Drain agent {agent}".strip(),
        "agent.stop_claims": f"Stop claims for agent {agent}".strip(),
        "agent.assign_mission": f"Boss ko mission assign karo: {params.get('objective') or 'mission'}",
        "approval.decide": f"Approval decide {params.get('decision')} for {params.get('approval_id')}",
    }
    base = mapping.get(command) or f"OpenClaw typed command {command}"
    if tenant:
        base += f" tenant {tenant}"
    return base[:2000]


def _dispatch(command: str, params: dict[str, Any], *, actor: str, corr: str) -> dict[str, Any]:
    from app.integrations.openclaw import commands as cmd_mod

    handler = cmd_mod.HANDLERS.get(command)
    if not handler:
        raise ValueError(f"no handler for {command}")
    return handler(params, actor=actor, correlation_id=corr)
