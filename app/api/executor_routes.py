"""Executor handshake protocol — HMAC-authenticated endpoints for external
desktop executors (Hermes Desktop, Agnes Desktop, etc.) to participate in
the canonical task authority.

Architecture:
- Tool identity (`hermes`, `agnes`, `cursor`, `claude`, ...) is authenticated via
  HMAC using the existing ``app.platform.coordination_hub_auth`` machinery.
  ``COORD_HUB_TOOL_<NAME>_SECRET`` env var (or ``COORD_HUB_BUZZ_SECRET`` for
  buzz) is the per-tool shared secret. ``_KNOWN_TOOLS`` enforces the
  whitelist at validator-time.
- Each request carries tool_id, event_type, body_sha256, issued_at, nonce, signature.
  Replay protection via the nonce file. Anti-replay via max-age 300s.
- The route then DELEGATES to ``app.platform.automation_orchestrator`` for
  the canonical task lifecycle (claim, heartbeat, submit, complete).

Per AGENTS.md §3 + M020:
- This is NOT a second orchestrator. It is a thin HMAC-authenticated adapter
  to the existing ``AutomationOrchestrator`` task authority.
- Hermes / Agnes are external executors; this surface lets them claim,
  heartbeat, and complete assigned tasks without shared filesystem or
  local-network access. Outbound-only from the desktop.
- Never expose the secret, never bypass deterministic gates.

Per M018 §3 "Label runtime enrollment BLOCKED, not COMPLETE":
  Until a real Hermes Desktop session actually posts to this surface, no task
  claim has occurred. Callers must verify task_id claims against the ledger.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.platform import coordination_hub_auth as hub_auth

router = APIRouter(tags=["executor"])


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #


@dataclass
class ToolIdentity:
    """Authenticated tool identity extracted from a request's HMAC headers."""

    tool_id: str
    issued_at: int
    nonce: str
    signature: str
    body_sha256: str
    event_type: str

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - float(self.issued_at))


def _check_hub_enabled() -> None:
    """Reject all executor calls if the hub is administratively disabled."""
    if not hub_auth.hub_enabled():
        raise HTTPException(status_code=503, detail="coordination_hub_disabled")


def _check_known_tool(tool_id: str) -> None:
    """Reject calls for tools not in the registered `_KNOWN_TOOLS` whitelist."""
    if tool_id not in hub_auth._KNOWN_TOOLS:  # noqa: SLF001 — accessing module constant intentionally
        raise HTTPException(
            status_code=404,
            detail=f"unknown_tool_id: {tool_id!r} (not in registered tool list)",
        )


def _check_secret_configured(tool_id: str) -> str:
    """Return the configured secret for the tool, raising if absent."""
    secret = hub_auth._configured_secret(tool_id)  # noqa: SLF001
    if not secret:
        raise HTTPException(
            status_code=503,
            detail=(
                f"tool_{tool_id}_secret_unset — owner must provision "
                f"COORD_HUB_TOOL_{tool_id.upper()}_SECRET (or COORD_HUB_BUZZ_SECRET for buzz) "
                f"in env before this tool can call the executor handshake"
            ),
        )
    return secret


def _replay_protection(nonce: str) -> None:
    """Reject re-used nonces (existing nonce_fps.jsonl ledger)."""
    fp = hub_auth.nonce_fingerprint(nonce)
    if hub_auth._nonce_seen(fp):  # noqa: SLF001
        raise HTTPException(status_code=409, detail="nonce_replay_detected")
    hub_auth._record_nonce(fp)  # noqa: SLF001


def _check_window(identity: ToolIdentity) -> None:
    """Reject timestamps outside the +/-300s attestation window."""
    max_age = hub_auth.MAX_PAST_AGE_SECONDS
    max_future = hub_auth.MAX_FUTURE_SKEW_SECONDS
    now = time.time()
    if now - identity.issued_at > max_age:
        raise HTTPException(status_code=401, detail="token_expired")
    if identity.issued_at - now > max_future:
        raise HTTPException(status_code=401, detail="token_in_future")
    if not hub_auth._NONCE_RE.match(identity.nonce):  # noqa: SLF001
        raise HTTPException(status_code=400, detail="bad_nonce_format")
    if not hub_auth._SHA256_RE.match(identity.signature):  # noqa: SLF001
        raise HTTPException(status_code=400, detail="bad_signature_format")
    if not hub_auth._TOOL_RE.match(identity.tool_id):  # noqa: SLF001
        raise HTTPException(status_code=400, detail="bad_tool_id_format")


def _verify_hmac(identity: ToolIdentity, secret: str, raw_body: bytes) -> None:
    """Verify that the signature matches the canonical HMAC construction."""
    expected = hub_auth.build_tool_signature(
        secret=secret,
        tool_id=identity.tool_id,
        event_type=identity.event_type,
        body_sha256=identity.body_sha256,
        issued_at=identity.issued_at,
        nonce=identity.nonce,
    )
    if expected != identity.signature:
        raise HTTPException(status_code=401, detail="hmac_signature_invalid")


async def _require_tool_identity(
    request: Request,
    x_tool_id: str = Header(...),
    x_event_type: str = Header(...),
    x_body_sha256: str = Header(...),
    x_issued_at: int = Header(...),
    x_nonce: str = Header(...),
    x_signature: str = Header(...),
) -> ToolIdentity:
    """Validate a desktop executor against the actual request bytes.

    The canonical Coordination Hub verifier owns timestamp, nonce replay and
    HMAC checks. Binding the declared body hash to request.body() prevents a
    correctly signed header set from being replayed with different JSON content.
    """
    _check_hub_enabled()
    _check_known_tool(x_tool_id)
    raw_body = await request.body()
    actual_body_sha = hub_auth.body_sha256(raw_body)
    if actual_body_sha != str(x_body_sha256).strip().lower():
        raise HTTPException(status_code=400, detail="body_sha256_mismatch")

    verified = hub_auth.verify_tool_attestation(
        tool_id=x_tool_id,
        event_type=x_event_type,
        body=raw_body,
        issued_at=x_issued_at,
        nonce=x_nonce,
        signature=x_signature,
        consume_nonce=True,
    )
    if not verified.get("ok"):
        reason = str(verified.get("reason") or "attestation_failed")
        status = {
            "secret_unconfigured": 503,
            "tool_unknown": 404,
            "timestamp_outside_window": 401,
            "signature_invalid": 401,
            "nonce_replay": 409,
            "attestation_malformed": 400,
        }.get(reason, 401)
        raise HTTPException(status_code=status, detail=reason)

    return ToolIdentity(
        tool_id=x_tool_id,
        issued_at=int(x_issued_at),
        nonce=x_nonce,
        signature=x_signature,
        body_sha256=actual_body_sha,
        event_type=x_event_type,
    )


# --------------------------------------------------------------------------- #
# Task authorization
# --------------------------------------------------------------------------- #


def _allowed_agents(tool_id: str) -> list[str]:
    """Return the ordered specialist roles this authenticated tool may execute."""
    roles = [tool_id]
    extras = os.getenv(f"EXECUTOR_{tool_id.upper()}_ALLOWED_AGENTS", "")
    for raw in extras.split(","):
        role = raw.strip()
        if role and role not in roles:
            roles.append(role)
    return roles


def _require_task_assignment(task: Any, tool_id: str) -> None:
    """Fail closed when an executor attempts another role's task."""
    assigned = str(getattr(task, "assigned_agent", "") or "").strip()
    if assigned not in _allowed_agents(tool_id):
        raise HTTPException(status_code=403, detail="task_assigned_to_other_role")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/api/executor/handshake/status")
async def handshake_status() -> dict[str, Any]:
    """Public handshake endpoint — returns the registered tool list.

    Does NOT require HMAC (it's an unauthenticated probe). The secret fingerprint
    of each tool is intentionally NOT returned. The body tells an external
    executor which tool ids to ask for enrollment.
    """
    _check_hub_enabled()
    status = hub_auth.tool_auth_status()
    return {
        "ok": True,
        "hub_enabled": True,
        "known_tools": status["known_tools"],
        "tools_configured": status["tools_configured"],
        "attestation_version": status["attestation_version"],
        "max_past_age_seconds": hub_auth.MAX_PAST_AGE_SECONDS,
        "max_future_skew_seconds": hub_auth.MAX_FUTURE_SKEW_SECONDS,
        "note": "Send POST requests to /api/executor/<tool_id>/<next-task|heartbeat|claim|complete>",
    }


@router.post("/api/executor/{tool_id}/next-task")
async def next_task(
    tool_id: str,
    request: Request,
    identity: ToolIdentity = Depends(_require_tool_identity),
) -> dict[str, Any]:
    """Return the next READY task assigned to this tool's specialist role
    (or to a wildcard role-list). HMAC-required.
    """
    # The tool id from path MUST match the identity
    if identity.tool_id != tool_id:
        raise HTTPException(status_code=403, detail="tool_id_mismatch")

    # Map tool → specialist role(s). Hermes/Agnes/etc. each back a single
    # specialist role. We allow either "tool_id==assigned_agent" (1:1) or
    # a private registry of tool→roles in env. Default to 1:1.
    candidate_roles = _allowed_agents(tool_id)

    from app.platform.automation_orchestrator import AutomationOrchestrator

    orch = AutomationOrchestrator()
    for role in candidate_roles:
        # The orchestrator's get_metrics + get_kanban_board return per-role slices.
        # For a real "give me next task" call, we walk the kanban board.
        try:
            for status_name in ("ready", "blocked"):  # prefer ready; fall back to blocked (observed-not-running)
                tasks = orch.store.all_tasks()
                for task in tasks:
                    if (
                        task.assigned_agent == role
                        and task.status.value.lower() == status_name
                        and not task.fencing_token
                        and (task.error_message or "").strip() == ""
                    ):
                        # Hand the task back as a draft; the executor MUST
                        # explicitly call /claim to acquire the lease.
                        return {
                            "ok": True,
                            "tool_id": tool_id,
                            "candidate_role": role,
                            "task_id": task.task_id,
                            "task_status": task.status.value,
                            "task_version": task.version,
                            "input_payload": task.input_payload,
                            "evidence_refs": [
                                f"data/orchestrator_ledger.db#task_records:{task.task_id}",
                                "executor_routes.next_task — READY listing",
                            ],
                            "claim_via": f"POST /api/executor/{tool_id}/claim {{'task_id': {task.task_id!r}}}",
                        }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ledger_read_error: {exc}")

    return {
        "ok": True,
        "tool_id": tool_id,
        "candidate_roles": candidate_roles,
        "task_id": None,
        "task_status": None,
        "note": "no READY task for this tool right now — caller may heartbeat to poll",
    }


@router.post("/api/executor/{tool_id}/heartbeat")
async def heartbeat(
    tool_id: str,
    request: Request,
    identity: ToolIdentity = Depends(_require_tool_identity),
) -> dict[str, Any]:
    """Refresh the executor's heartbeat. Updates last_heartbeat on the
    currently-claimed task (if any). HMAC-required.
    """
    if identity.tool_id != tool_id:
        raise HTTPException(status_code=403, detail="tool_id_mismatch")

    # Body should contain {"task_id": ..., "last_heartbeat": ...}
    body_data: dict[str, Any] = {}
    try:
        body_bytes = await request.body()
        if isinstance(body_bytes, bytes) and body_bytes:
            import json
            body_data = json.loads(body_bytes.decode("utf-8") or "{}")
    except Exception:
        body_data = {}

    task_id = body_data.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id_required_in_body")

    from app.platform.automation_orchestrator import AutomationOrchestrator

    orch = AutomationOrchestrator()
    task = orch.store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found_in_ledger")
    _require_task_assignment(task, tool_id)

    # Update last_heartbeat
    task.last_heartbeat = time.time()
    task.updated_at = time.time()
    try:
        orch.store.save(task)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"heartbeat_save_failed: {exc}")

    return {
        "ok": True,
        "tool_id": tool_id,
        "task_id": task_id,
        "fencing_token": task.fencing_token,
        "version": task.version,
        "last_heartbeat": task.last_heartbeat,
    }


@router.post("/api/executor/{tool_id}/claim")
async def claim(
    tool_id: str,
    request: Request,
    identity: ToolIdentity = Depends(_require_tool_identity),
) -> dict[str, Any]:
    """Transition a READY task into RUNNING via CAS + claim lease. Returns the
    fencing_token. HMAC-required.
    """
    if identity.tool_id != tool_id:
        raise HTTPException(status_code=403, detail="tool_id_mismatch")

    import json
    body_data: dict[str, Any] = {}
    try:
        raw = await request.body() if hasattr(request, "body") else b""
        if isinstance(raw, bytes):
            body_data = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        body_data = {}

    task_id = body_data.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id_required_in_body")

    from app.platform.automation_orchestrator import AutomationOrchestrator

    orch = AutomationOrchestrator()
    task = orch.store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found_in_ledger")
    _require_task_assignment(task, tool_id)

    try:
        dispatched = orch.dispatch_task(task_id)  # READY → RUNNING + fencing_token
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"claim_failed: {exc}")

    task = orch.store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_vanished")
    if not dispatched:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "claim_refused",
                "task_id": task_id,
                "task_status": task.status.value,
                "task_error_message": task.error_message,
                "hint": "TypeSafe session policy may be routing to review; consult /api/executor/hermes/state for full snapshot",
            },
        )

    # dispatch_task() is the single lease authority: it returns True only
    # after CAS + governor.acquire succeeded. Never double-acquire here.
    lease_acquired = bool(dispatched and task.fencing_token)

    return {
        "ok": True,
        "tool_id": tool_id,
        "task_id": task_id,
        "fencing_token": task.fencing_token,
        "task_version": task.version,
        "lease_acquired": lease_acquired,
        "evidence_refs": [
            f"data/orchestrator_ledger.db#task_records:{task_id}",
            "AutomationOrchestrator.dispatch_task → RUNNING",
        ],
    }


@router.post("/api/executor/{tool_id}/complete")
async def complete(
    tool_id: str,
    request: Request,
    identity: ToolIdentity = Depends(_require_tool_identity),
) -> dict[str, Any]:
    """Mark a claimed task DONE with structured evidence. HMAC-required.
    Body: ``{"task_id": ..., "fencing_token": ..., "evidence": {...}, "success": true}``
    """
    if identity.tool_id != tool_id:
        raise HTTPException(status_code=403, detail="tool_id_mismatch")

    import json
    body_data: dict[str, Any] = {}
    try:
        raw = await request.body() if hasattr(request, "body") else b""
        if isinstance(raw, bytes):
            body_data = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        body_data = {}

    task_id = body_data.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id_required_in_body")

    evidence = body_data.get("evidence") or {}
    success = bool(body_data.get("success", True))
    error_msg = body_data.get("error_msg")
    fencing_token = body_data.get("fencing_token")

    from app.platform.automation_orchestrator import AutomationOrchestrator

    orch = AutomationOrchestrator()
    task = orch.store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found_in_ledger")
    _require_task_assignment(task, tool_id)

    try:
        completed = orch.verify_and_complete(
            task_id=task_id,
            execution_evidence=evidence,
            is_success=success,
            error_msg=error_msg,
            fencing_token=fencing_token,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"complete_failed: {exc}")

    if completed is None:
        raise HTTPException(status_code=404, detail="task_not_found_after_complete")
    return {
        "ok": True,
        "tool_id": tool_id,
        "task_id": completed.task_id,
        "task_status": completed.status.value,
        "task_version": completed.version,
        "evidence_refs": [
            f"data/orchestrator_ledger.db#task_records:{completed.task_id}",
            "AutomationOrchestrator.verify_and_complete → DONE | FAILED | REVIEW",
        ],
    }
