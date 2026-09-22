"""One bounded TypeSafe judgment per substantial orchestrator task/session.

System safety/compliance gates remain authoritative. TypeSafe may route an
otherwise-eligible task to human review, but provider failure never bypasses a
deterministic gate and never crashes dispatch.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.platform.typesafe_integration import Choice, Noul, get_typesafe_client
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
_TRACE = Path("logs/typesafe_session_decisions.jsonl")
_LOCK = threading.Lock()


def _enabled() -> bool:
    # Reuse the canonical integration switch. A second flag would let the
    # gateway appear armed while session governance silently stayed disabled.
    return os.getenv("TYPESAFE_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}


def _append(path: Path, row: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except Exception as exc:
        logger.warning("TypeSafe session trace write failed: %s", exc)
        return False


def judge_task(*, record: Any, contract: Any, client: Any | None = None, trace_path: Path | None = None) -> dict[str, Any]:
    """Return a compact dispatch verdict; task payload values/PII never leave."""
    decision_id = f"tss-{uuid.uuid4().hex[:12]}"
    base = {"decision_id": decision_id, "route": "proceed", "reason": "policy_disabled", "traced": False}
    if not _enabled():
        return base
    api = client or get_typesafe_client()
    if not getattr(api, "enabled", False):
        return {**base, "reason": "credential_unavailable"}
    tenant_scope = str((record.input_payload or {}).get("tenant_id") or (record.input_payload or {}).get("client_id") or "platform")
    state = {
        "task_id": record.task_id,
        "tenant_scope": tenant_scope,
        "purpose": "substantial_agent_session_dispatch",
        "owner_bot": record.owner_bot,
        "assigned_agent": record.assigned_agent,
        "agent_lane": str(getattr(contract, "lane", "")),
        "priority": str(getattr(record.priority, "value", record.priority)),
        "payload_keys": sorted(str(k) for k in (record.input_payload or {}) if not str(k).startswith("_")),
        "evidence_refs": [f"data/orchestrator_ledger.db#task_records:{record.task_id}"],
    }
    questions = {
        "route": Choice(
            "Should this governed task proceed or require owner review?",
            {
                "proceed": "Task is sufficiently scoped and safe under existing deterministic gates",
                "review": "Semantic uncertainty or business-risk merits owner review before execution",
            },
        ),
        "material": Noul("Will this task materially change a customer, revenue, or operational outcome?"),
    }
    reason = ""
    try:
        response = api.system_one(
            state,
            questions,
            connect_timeout_sec=2.0,
            read_timeout_sec=5.0,
            max_attempts=1,
        )
        response_success = bool(response.success)
        resolved_model = response.model
        answer = (response.answers or {}).get("route") or {}
        route = str(answer.get("choice") or "proceed").strip().lower()
    except Exception as exc:
        logger.warning("TypeSafe session judgment failed for %s: %s", record.task_id, type(exc).__name__)
        response_success = False
        resolved_model = None
        route = "proceed"
        reason = "provider_exception"
    if not response_success or route not in {"proceed", "review"}:
        route = "proceed"
        reason = reason if reason == "provider_exception" else "provider_fallback"
    else:
        reason = "typesafe_judgment"
    raw = json.dumps({"state": state, "questions": sorted(questions)}, sort_keys=True, default=str)
    row = {
        "kind": "session_decision",
        "decision_id": decision_id,
        "task_id": record.task_id,
        "tenant_scope": tenant_scope,
        "purpose": state["purpose"],
        "state_hash": hashlib.sha256(raw.encode()).hexdigest()[:16],
        "evidence_refs": state["evidence_refs"],
        "requested_model": getattr(api, "model", "jev-latest"),
        "resolved_model": resolved_model,
        "route": route,
        "reason": reason,
        "success": response_success,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    traced = _append(trace_path or _TRACE, row)
    return {"decision_id": decision_id, "route": route, "reason": reason, "traced": traced}


def judge_task_multipass(
    *,
    record: Any,
    contract: Any,
    artifact: dict[str, Any] | None = None,
    options: list[str] | None = None,
    downstream_action: str = "dispatch",
    side_effect_id: str | None = None,
    observed_outcome: Any = None,
    trace_path: Path | None = None,
) -> dict[str, Any]:
    """5-stage multi-pass lifecycle for substantial agent sessions.

    ADDITIVE to `judge_task` (the bounded 1-call ADR-199 gate). This is the
    optional M00A richer lifecycle for sessions that have:
      - non-trivial evidence to assess (intake)
      - a small set of next-action candidates (plan)
      - a draft artifact worth QA (intermediate_qa)
      - a planned downstream action (final)
      - an observed outcome to record (outcome)

    The legacy `judge_task` route decision is PRESERVED here as the AUTHORITY
    on dispatch — multipass never weakens it. If the legacy gate returns
    `route=review`, multipass is SKIPPED and the existing review verdict wins.

    Deterministic / mock fallback: when `TYPESAFE_API_KEY` is ABSENT the
    multipass consumer returns the deterministic mock for every stage, so the
    full lifecycle is reproducible in CI / local without a real key. ABSENT is
    recorded in the trace summary (`mock_calls`) so audit consumers can tell.

    Trace contract (per M00A + ADR-201):
      decision_id: str
      task_id: str
      tenant_scope: str
      verdict: {"route": "proceed"|"review", "reason": str, "traced": bool}
      consumed_calls: int
      by_kind: {real, mock, cached, skipped}
      by_stage: {intake, plan, intermediate_qa, final, outcome}
      legacy_decision_id: str  # the bounded gate's decision_id, for audit
    """
    # Honour the legacy bounded gate FIRST. Provider failure there already
    # degrades to proceed; we never weaken it, never replace it.
    legacy = judge_task(record=record, contract=contract, trace_path=trace_path)
    if legacy.get("route") == "review":
        return {
            "decision_id": legacy["decision_id"],
            "task_id": record.task_id,
            "tenant_scope": str((record.input_payload or {}).get("tenant_id") or (record.input_payload or {}).get("client_id") or "platform"),
            "verdict": legacy,
            "consumed_calls": 0,
            "by_kind": {"real": 0, "mock": 0, "cached": 0, "skipped": 5},
            "by_stage": {},
            "legacy_decision_id": legacy["decision_id"],
            "reason": "legacy_review_short_circuit",
        }

    # Try to import the multipass consumer; if the module is unavailable
    # (e.g. partial deploy) we degrade gracefully without raising.
    try:
        from app.platform.typesafe_multipass import multipass_consumer
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[typesafe_session] multipass consumer unavailable: %s", exc)
        return {
            "decision_id": legacy["decision_id"],
            "task_id": record.task_id,
            "tenant_scope": "platform",
            "verdict": legacy,
            "consumed_calls": 0,
            "by_kind": {"real": 0, "mock": 0, "cached": 0, "skipped": 5},
            "by_stage": {},
            "legacy_decision_id": legacy["decision_id"],
            "reason": "multipass_module_unavailable",
        }

    tenant_scope = str((record.input_payload or {}).get("tenant_id") or (record.input_payload or {}).get("client_id") or "platform")
    cons = multipass_consumer(task_id=record.task_id, tenant_scope=tenant_scope)

    evidence = (record.input_payload or {}).get("evidence", {})
    cons.intake_pass(evidence=evidence, task=str(record.assigned_agent or ""), evidence_refs=[f"agent:{record.assigned_agent}"])

    plan_options = options or ["dispatch", "review", "skip"]
    cons.plan_pass(task=str(record.assigned_agent or ""), options=plan_options, evidence_refs=[f"agent:{record.assigned_agent}"])

    if artifact is not None:
        cons.qa_pass(artifact={"kind": "session_artifact", **(artifact or {})}, stage_label="intermediate_qa", evidence_refs=[f"agent:{record.assigned_agent}"])
        cons.final_pass(artifact={"kind": "session_artifact", **(artifact or {})}, downstream_action=downstream_action, evidence_refs=[f"agent:{record.assigned_agent}"])

    if side_effect_id is not None:
        cons.outcome_pass(side_effect_id=side_effect_id, observed_outcome=observed_outcome)

    summary = cons.summary()

    # Persist a compact trace row alongside the legacy one.
    trace_row = {
        "kind": "session_decision_multipass",
        "decision_id": legacy["decision_id"],
        "task_id": record.task_id,
        "tenant_scope": tenant_scope,
        "purpose": "substantial_agent_session_multipass",
        "owner_bot": record.owner_bot,
        "assigned_agent": record.assigned_agent,
        "agent_lane": str(getattr(contract, "lane", "")),
        "consumed_calls": summary["consumed_total"],
        "by_kind": summary["by_kind"],
        "by_stage": summary["by_stage"],
        "legacy_decision_id": legacy["decision_id"],
        "verdict_route": legacy["route"],
        "verdict_reason": legacy["reason"],
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    traced = _append(trace_path or _TRACE, trace_row)

    return {
        "decision_id": legacy["decision_id"],
        "task_id": record.task_id,
        "tenant_scope": tenant_scope,
        "verdict": legacy,
        "consumed_calls": summary["consumed_total"],
        "by_kind": summary["by_kind"],
        "by_stage": summary["by_stage"],
        "legacy_decision_id": legacy["decision_id"],
        "traced": traced,
        "reason": "multipass_complete",
    }


__all__ = ["judge_task", "judge_task_multipass"]
