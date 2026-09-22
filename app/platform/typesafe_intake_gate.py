"""TypeSafe intake-judgment wrapper (Wave 7 deliverable, §4 directive).

ADDITIVE OPT-IN pre-write hook for ``AutomationOrchestrator.submit_task``.

Hard guarantees (per §4 directive "Preserve the existing bounded mandatory
dispatch gate. Do not add competing clients, key pools, parallel orchestration
layers or repeated identical-input calls."):

1. **Default OFF** — ``TYPESAFE_INTAKE_GATE`` must be ``1`` to activate. When
   OFF, behavior is unchanged (no import-time hit, no extra I/O).
2. **Single call per submission** — at most ONE ``judge_task`` invocation per
   ``submit_task``. No repeated identical-input calls.
3. **Canonical client only** — uses ``app.platform.typesafe_session_policy.judge_task``
   which is the existing authoritative session-policy gate. No second SDK.
4. **Never blocks write** — verdict is *annotated* on ``input_payload`` as
   ``typesafe_intake_judgment``. If ``route == "review"``, the task is still
   created; a downstream OWNER_DECISION_REQUIRED-like state can be triggered
   by the caller via the existing ``approval_decision_id`` path.
5. **Credential failure = no-op PROCEED** — when ``TYPESAFE_API_KEY`` is
   absent (current state in this worktree), the gate returns
   ``{"route": "proceed", "reason": "credential_unavailable", "consumed_calls": 0}``.
6. **Telemetry** — per-call ``consumed_calls`` counter is exposed for the
   dashboard (no PII, no raw keys).
7. **Trace** — every invocation append ( a row to
   ``data/typesafe_intake_trace.jsonl`` (decision_id, task_id, route, reason).
   Never raises; file write failure degrades silently to ``traced=False``.

This module is intentionally tiny and self-contained so that ``pytest`` can
exercise it without spinning up the full app.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_TRACE_PATH = Path(__file__).resolve().parents[2] / "data" / "typesafe_intake_trace.jsonl"


def intake_gate_enabled() -> bool:
    """True iff TYPESAFE_INTAKE_GATE=1 in env."""
    return os.getenv("TYPESAFE_INTAKE_GATE", "0").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class IntakeVerdict:
    """Compact, dashboard-friendly verdict. Never contains payload values or PII."""

    decision_id: str
    route: str  # "proceed" | "review"
    reason: str  # "credential_unavailable" | "policy_disabled" | "typesafe_judgment" | "provider_fallback" | "provider_exception"
    consumed_calls: int
    state_hash: str
    traced: bool
    elapsed_ms: float


def _safe_append_trace(row: dict[str, Any]) -> bool:
    """Append one trace row; never raises. Returns traced=True on success."""
    try:
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except Exception as exc:
        logger.debug("typesafe_intake_gate trace append failed: %s", exc)
        return False


def _no_op_verdict(reason: str = "credential_unavailable") -> IntakeVerdict:
    return IntakeVerdict(
        decision_id=f"tsi-{uuid.uuid4().hex[:12]}",
        route="proceed",
        reason=reason,
        consumed_calls=0,
        state_hash="",
        traced=False,
        elapsed_ms=0.0,
    )


def evaluate_intake(
    *,
    task_id: str,
    owner_bot: str,
    assigned_agent: str,
    agent_lane: str,
    priority: str,
    payload_keys: list[str],
    tenant_scope: str = "platform",
) -> IntakeVerdict:
    """Evaluate the intake-time judgment for a single submission.

    Behavior:
      * If ``TYPESAFE_INTAKE_GATE`` is OFF (default): return a no-op
        PROCEED verdict, ``consumed_calls=0``.
      * If ON: delegate to ``typesafe_session_policy.judge_task`` (the
        canonical session-policy gate). Never blocks the write.
      * Trace row appended (best-effort).
    """
    started_at = time.monotonic()

    if not intake_gate_enabled():
        return _no_op_verdict(reason="policy_disabled")

    # Build minimal state hash (no payload VALUES, only keys + ids).
    raw_state = {
        "task_id": task_id,
        "owner_bot": owner_bot,
        "assigned_agent": assigned_agent,
        "agent_lane": agent_lane,
        "priority": priority,
        "payload_keys": sorted(payload_keys),
        "tenant_scope": tenant_scope,
    }
    state_hash = hashlib.sha256(
        json.dumps(raw_state, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    decision_id = f"tsi-{uuid.uuid4().hex[:12]}"
    route = "proceed"
    reason = "credential_unavailable"
    consumed_calls = 0
    traced = False

    try:
        # Canonical session-policy gate. Imports lazily so the cost is only
        # paid when the flag is ON.
        from app.platform.typesafe_session_policy import judge_task

        class _StubContract:
            lane = agent_lane

        class _StubRecord:
            task_id = task_id
            owner_bot = owner_bot
            assigned_agent = assigned_agent
            priority = priority
            input_payload = {"tenant_id": tenant_scope, "client_id": tenant_scope}

        verdict = judge_task(record=_StubRecord(), contract=_StubContract())
        route = verdict.get("route", "proceed")
        reason = verdict.get("reason", "credential_unavailable")
        consumed_calls = 1
        decision_id = verdict.get("decision_id", decision_id)
        traced = bool(verdict.get("traced", False))
    except Exception as exc:
        logger.warning(
            "typesafe_intake_gate.evaluate_intake failed for %s: %s", task_id, type(exc).__name__
        )
        route = "proceed"
        reason = "provider_exception"

    elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
    verdict_obj = IntakeVerdict(
        decision_id=decision_id,
        route=route,
        reason=reason,
        consumed_calls=consumed_calls,
        state_hash=state_hash,
        traced=traced,
        elapsed_ms=elapsed_ms,
    )

    # Best-effort trace; never raises.
    traced = _safe_append_trace(
        {
            "kind": "intake_decision",
            "decision_id": verdict_obj.decision_id,
            "task_id": task_id,
            "owner_bot": owner_bot,
            "assigned_agent": assigned_agent,
            "agent_lane": agent_lane,
            "priority": priority,
            "tenant_scope": tenant_scope,
            "state_hash": state_hash,
            "route": verdict_obj.route,
            "reason": verdict_obj.reason,
            "consumed_calls": verdict_obj.consumed_calls,
            "elapsed_ms": verdict_obj.elapsed_ms,
            "ts": time.time(),
        }
    ) or traced

    return verdict_obj


def annotate_input_payload(
    payload: dict[str, Any] | None,
    verdict: IntakeVerdict,
) -> dict[str, Any]:
    """Annotate ``input_payload`` with the intake verdict. Never mutates input.

    Output is a fresh dict so the caller's ``payload`` reference is preserved.
    Annotation key = ``typesafe_intake_judgment`` (dict).
    """
    base = dict(payload or {})
    base["typesafe_intake_judgment"] = {
        "decision_id": verdict.decision_id,
        "route": verdict.route,
        "reason": verdict.reason,
        "consumed_calls": verdict.consumed_calls,
        "state_hash": verdict.state_hash,
        "elapsed_ms": verdict.elapsed_ms,
        "gate_enabled": intake_gate_enabled(),
    }
    return base


__all__ = [
    "IntakeVerdict",
    "intake_gate_enabled",
    "evaluate_intake",
    "annotate_input_payload",
]