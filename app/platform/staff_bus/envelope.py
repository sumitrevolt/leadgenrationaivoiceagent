"""Versioned STAFF bus envelopes — fail-closed validation."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "staff_bus.envelope.v1"

EVENT_TYPES: frozenset[str] = frozenset(
    {
        "task.proposed",
        "task.assigned",
        "task.accepted",
        "work.status",
        "artifact.ready",
        "handoff.requested",
        "decision.proposed",
        "second_brain.advice",
        "boss.verdict",
        "owner.review_required",
        "execution.authorized",
        "execution.refused",
        "audit.recorded",
        "task.completed",
        "task.failed",
    }
)

SENSITIVITY = frozenset({"public", "internal", "confidential", "restricted"})
AUTHORITY = frozenset({"none", "boss", "owner", "system_gate"})
TERMINAL = frozenset({"open", "accepted", "completed", "failed", "refused", "needs_owner"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def payload_hash(payload: dict[str, Any] | None) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_envelope(
    *,
    event_type: str,
    tenant_id: str,
    source_agent_id: str,
    destination: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    sensitivity: str = "internal",
    authority_requirement: str = "none",
    retry_count: int = 0,
    terminal_state: str = "open",
    audit_reference: str = "",
) -> dict[str, Any]:
    """Build one immutable envelope. Caller must validate before persist."""
    body = dict(payload or {})
    event_id = uuid.uuid4().hex
    corr = correlation_id or event_id
    idem = idempotency_key or f"{event_type}:{source_agent_id}:{corr}:{payload_hash(body)[:16]}"
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "correlation_id": corr,
        "causation_id": causation_id or "",
        "idempotency_key": idem,
        "timestamp": _now_iso(),
        "tenant_id": str(tenant_id or "").strip(),
        "source_agent_id": str(source_agent_id or "").strip().lower(),
        "destination": str(destination or "").strip(),
        "event_type": str(event_type or "").strip(),
        "payload": body,
        "payload_hash": payload_hash(body),
        "sensitivity": sensitivity,
        "authority_requirement": authority_requirement,
        "retry_count": int(retry_count or 0),
        "terminal_state": terminal_state,
        "audit_reference": audit_reference or "",
    }


def validate_envelope(env: dict[str, Any] | None) -> dict[str, Any]:
    """Fail-closed schema gate for unknown/malformed events."""
    if not isinstance(env, dict):
        return {"ok": False, "error": "not_object", "fail_closed": True}
    problems: list[str] = []
    if env.get("schema_version") != SCHEMA_VERSION:
        problems.append("schema_version")
    et = str(env.get("event_type") or "")
    if et not in EVENT_TYPES:
        problems.append("unknown_event_type")
    for req in (
        "event_id",
        "correlation_id",
        "idempotency_key",
        "timestamp",
        "tenant_id",
        "source_agent_id",
        "destination",
        "payload_hash",
    ):
        if not str(env.get(req) or "").strip():
            problems.append(f"missing:{req}")
    if str(env.get("sensitivity") or "") not in SENSITIVITY:
        problems.append("sensitivity")
    if str(env.get("authority_requirement") or "") not in AUTHORITY:
        problems.append("authority_requirement")
    if str(env.get("terminal_state") or "") not in TERMINAL:
        problems.append("terminal_state")
    payload = env.get("payload")
    if payload is not None and not isinstance(payload, dict):
        problems.append("payload_not_object")
    elif isinstance(payload, dict):
        if payload_hash(payload) != str(env.get("payload_hash") or ""):
            problems.append("payload_hash_mismatch")
    if problems:
        return {"ok": False, "error": "invalid_envelope", "problems": problems, "fail_closed": True}
    return {"ok": True, "event_id": env.get("event_id"), "event_type": et}
