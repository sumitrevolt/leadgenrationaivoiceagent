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


def _intake_trace_path() -> Path:
    """Operation-time accessor - never a module-level constant.

    The runtime-data scanner tracks mutable-path writes at the local variable
    passed to ``open()``; a module-level ``Path(...)`` is invisible to it
    (scanner reports the declaration as "unbound").  ``store_dir`` creates
    the parent directory and returns the canonical path in one call, so the
    only mutable-path operation the scanner sees is the local variable plus
    ``open("a", ...)``.
    """
    from app.platform.runtime_data import store_dir

    return store_dir("typesafe_intake_trace.jsonl")


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
        trace_path = _intake_trace_path()
        with trace_path.open("a", encoding="utf-8") as fh:
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


# ---------- outcome review (Wave 8 P0 correction) ----------


@dataclass
class OutcomeVerdict:
    """Compact outcome judgment — never contains raw evidence or customer data.

    Per directive §6 / P0 correction: TypeSafe outcome evaluation must use
    actual execution evidence (task success, downstream effects), NOT the
    task's original intake decision. This is semantically distinct from intake.
    """

    decision_id: str  # prefixed "tso-" so traces are distinguishable from intake ("tsi-")
    verdict: str  # "met" | "partial" | "not_met" | "uncertain" | "skipped"
    rationale: str  # short reason; bounded by max 120 chars at the call site
    confidence: float  # 0.0-1.0; mirrors judge_task's distribution concentration
    next_action: str  # "proceed" | "retry" | "escalate" | "rollback"
    evidence_fingerprint: str  # sha256[:16] of evidence — NEVER raw evidence text
    consumed_calls: int  # 0 for SKIPPED/MOCK; 1 for REAL/CACHED
    source: str  # "REAL" | "MOCK" | "CACHED" | "SKIPPED"
    state_hash: str
    elapsed_ms: float


def outcome_review_enabled() -> bool:
    """True iff TYPESAFE_OUTCOME_REVIEW=1 in env.

    Per directive P0: outcome_review must be EXPLICITLY opt-in (not auto-on
    via TYPESAFE_INTAKE_GATE) so each stage's coverage is independently
    controllable. This prevents "one flag accidentally turns on 3 stages"
    blast-radius risk.
    """
    return os.getenv("TYPESAFE_OUTCOME_REVIEW", "0").strip().lower() in ("1", "true", "yes", "on")


def _safe_outcome_trace(row: dict[str, Any]) -> bool:
    """Append outcome trace row — never raises. Audit-grade."""
    try:
        trace_path = _intake_trace_path()
        with trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except Exception as exc:
        logger.debug("typesafe_intake_gate outcome trace append failed: %s", exc)
        return False


def _no_op_outcome_verdict(
    *,
    task_id: str,
    success: bool,
    evidence_fingerprint: str,
    source: str = "SKIPPED",
    reason: str = "policy_disabled",
    verdict: str | None = None,
    next_action: str | None = None,
) -> OutcomeVerdict:
    """No-op outcome verdict when the gate is OFF or credentials are missing.

    CRITICAL: When ``success=False``, we MUST NOT report verdict='met' regardless
    of what judge_task says (per directive P0: 'Verify that TypeSafe failures
    cannot silently turn a failed task into a successful one.'). The local
    `success` flag is authoritative for verdict='met'.
    """
    if verdict is None:
        verdict = "met" if success else "not_met"
    if next_action is None:
        next_action = "proceed" if success else "escalate"
    return OutcomeVerdict(
        decision_id=f"tso-{uuid.uuid4().hex[:12]}",
        verdict=verdict,
        rationale=reason,
        confidence=0.0,
        next_action=next_action,
        evidence_fingerprint=evidence_fingerprint,
        consumed_calls=0,
        source=source,
        state_hash="",
        elapsed_ms=0.0,
    )


def _map_route_to_verdict(route: str, success: bool) -> tuple[str, str]:
    """Map judge_task's canonical route to outcome verdict + next_action.

    Hard rule (per directive P0): judge_task's verdict is ADVISORY; the
    local ``success`` flag is AUTHORITATIVE for verdict='met'. A failed task
    can NEVER become 'met' via judge_task approval.
    """
    if not success:
        # Failed task: judge_task verdict cannot upgrade it.
        return ("not_met", "escalate")
    if route == "proceed":
        return ("met", "proceed")
    if route == "review":
        return ("partial", "escalate")
    # Unknown / exception route.
    return ("uncertain", "retry")


def evaluate_outcome(
    *,
    task_id: str,
    success: bool,
    evidence: str | None,
    downstream_result: str | None,
    customer_revenue_impact: str | None = "",
    error_message: str | None = "",
    acceptance_criteria_met: bool | None = None,
) -> OutcomeVerdict:
    """Evaluate the OUTCOME of a single task. Semantically distinct from intake.

    Per directive P0: outcome evaluation uses ACTUAL execution evidence, NOT
    the task's original intake decision.

    Behavior matrix (audit-grade):

      TYPESAFE_OUTCOME_REVIEW=0 (default) + success=True   → SKIPPED / met / proceed
      TYPESAFE_OUTCOME_REVIEW=0 (default) + success=False  → SKIPPED / not_met / escalate
      TYPESAFE_OUTCOME_REVIEW=1 + key present + success=True  → REAL / <judge_task>
      TYPESAFE_OUTCOME_REVIEW=1 + key present + success=False → REAL / not_met (CANNOT be upgraded)
      TYPESAFE_OUTCOME_REVIEW=1 + key absent + success=True   → MOCK / met (deterministic)
      TYPESAFE_OUTCOME_REVIEW=1 + key absent + success=False  → MOCK / not_met (deterministic)

    NEVER copies raw evidence, customer data, or credentials into the verdict.
    Only fingerprints (sha256[:16]) and bounded category labels.
    """
    started_at = time.monotonic()

    # Evidence fingerprint — SHA-256 of evidence string (NEVER raw).
    evidence_fingerprint = ""
    if evidence:
        evidence_fingerprint = hashlib.sha256(evidence.encode("utf-8")).hexdigest()[:16]

    # If gate is OFF: SKIPPED source, local success is authoritative verdict.
    if not outcome_review_enabled():
        verdict = _no_op_outcome_verdict(
            task_id=task_id,
            success=success,
            evidence_fingerprint=evidence_fingerprint,
            source="SKIPPED",
            reason="policy_disabled",
        )
        _safe_outcome_trace(
            {
                "kind": "outcome_decision",
                "decision_id": verdict.decision_id,
                "task_id": task_id,
                "success": success,
                "verdict": verdict.verdict,
                "rationale": verdict.rationale,
                "next_action": verdict.next_action,
                "evidence_fingerprint": verdict.evidence_fingerprint,
                "consumed_calls": verdict.consumed_calls,
                "source": verdict.source,
                "state_hash": "",
                "elapsed_ms": verdict.elapsed_ms,
                "ts": time.time(),
            }
        )
        return verdict

    # Gate is ON. Determine source: REAL if API key present + canonical client
    # enabled; MOCK otherwise.
    from app.platform import typesafe_integration as _ts

    client = _ts.get_typesafe_client()
    is_real = bool(getattr(client, "enabled", False))
    source = "REAL" if is_real else "MOCK"

    # Build minimal outcome state for hash + canonical client call.
    # CRITICAL: never include raw evidence, customer data, or credentials.
    raw_state = {
        "task_id": task_id,
        "success": bool(success),
        "acceptance_criteria_met": (
            bool(acceptance_criteria_met) if acceptance_criteria_met is not None else None
        ),
        "downstream_result": (downstream_result or "")[:60],  # bounded category
        "customer_revenue_impact": (customer_revenue_impact or "")[:60],
        "error_message_present": bool(error_message),
    }
    state_hash = hashlib.sha256(
        json.dumps(raw_state, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    decision_id = f"tso-{uuid.uuid4().hex[:12]}"
    route = "proceed"
    rationale = "credential_unavailable"
    consumed_calls = 0
    traced = False
    judge_reason = ""

    try:
        # IMPORTANT: import the MODULE (not the symbol) so monkeypatch.setattr on
        # ``app.platform.typesafe_session_policy.judge_task`` actually replaces the
        # function we call. ``from X import Y`` binds the local name at import time,
        # so later patches on X.Y are invisible to us.
        from app.platform import typesafe_session_policy as _tsp_module

        class _OutcomeContract:
            """Synthetic contract - neutral lane/mode so outcome review is not gated by intake rules."""

        class _OutcomeRecord:
            """Synthetic record carrying the outcome-relevant fields (set on the instance,
            because a Python class body cannot see the enclosing function's locals)."""

        contract = _OutcomeContract()
        contract.lane = None
        contract.default_mode = None

        record = _OutcomeRecord()
        record.task_id = task_id
        record.owner_bot = ""
        record.assigned_agent = ""
        record.priority = "OUTCOME"
        record.input_payload = {
            "success": bool(success),
            "acceptance_criteria_met": acceptance_criteria_met,
            "downstream_result": (downstream_result or "")[:60],
            "customer_revenue_impact": (customer_revenue_impact or "")[:60],
            "error_message_present": bool(error_message),
            "purpose": "outcome_review",
        }

        judge_result = _tsp_module.judge_task(record=record, contract=contract)
        route = judge_result.get("route", "proceed")
        judge_reason = judge_result.get("reason", "credential_unavailable")
        consumed_calls = 1
        # KEEP the outcome-side tso- prefix even on success. judge_task's
        # internal tss- prefix would obscure the stage distinction in traces;
        # the upstream decision_id is preserved in the trace row's
        # ``upstream_decision_id`` field instead.
        upstream_decision_id = judge_result.get("decision_id", "")
        traced = bool(judge_result.get("traced", False))
    except Exception as exc:
        logger.warning(
            "typesafe_intake_gate.evaluate_outcome failed for %s: %s",
            task_id,
            type(exc).__name__,
        )
        # Exception path: KEEP the default 'proceed' route (set at line 292).
        # Do NOT override with success-conditional logic — that would let a
        # judge_task failure silently flip the verdict. MOCK semantics are
        # surfaced via source='MOCK' (computed from client.enabled above),
        # not via route mutation here.
        # route is unchanged.

    # Map route to outcome verdict — local success is AUTHORITATIVE for 'met'.
    outcome_verdict, next_action = _map_route_to_verdict(route, success)

    elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
    # Build bounded rationale (max 120 chars).
    rationale = (judge_reason or "")[:120] or "policy_disabled"

    verdict = OutcomeVerdict(
        decision_id=decision_id,
        verdict=outcome_verdict,
        rationale=rationale,
        confidence=0.0,  # judge_task's Choice doesn't expose scalar confidence in this wrapper
        next_action=next_action,
        evidence_fingerprint=evidence_fingerprint,
        consumed_calls=consumed_calls,
        source=source,
        state_hash=state_hash,
        elapsed_ms=elapsed_ms,
    )

    _safe_outcome_trace(
        {
            "kind": "outcome_decision",
            "decision_id": verdict.decision_id,
            "task_id": task_id,
            "success": success,
            "verdict": verdict.verdict,
            "rationale": verdict.rationale,
            "next_action": verdict.next_action,
            "evidence_fingerprint": verdict.evidence_fingerprint,
            "consumed_calls": verdict.consumed_calls,
            "source": verdict.source,
            "state_hash": state_hash,
            "elapsed_ms": elapsed_ms,
            "traced": traced,
            "ts": time.time(),
        }
    )

    return verdict


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
    traced = (
        _safe_append_trace(
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
        )
        or traced
    )

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
    "OutcomeVerdict",
    "intake_gate_enabled",
    "outcome_review_enabled",
    "evaluate_intake",
    "evaluate_outcome",
    "annotate_input_payload",
]
