"""Coordinator shadow adapter — record-only observation of one real coordinator
action, taken from the coordinator's OWN normalized selection (never raw prose).

Wraps the shared normalized-action boundary in app/agents/coordinator.py:_run_agent
(`res = await _TOOLS[agent](task, goal)`), where `agent` is the parsed action the
coordinator actually chose and `res` is the real result. The adapter maps that
normalized action into a typed ActionRequest and calls Harness.observe() only. It
never calls the LLM, executes the action, alters arguments, chooses a different
tool, delegates, or changes the coordinator's return.

The raw LLM response is NEVER stored in full — only a bounded hash/summary and a
parser-confidence label (the coordinator's `_extract_list` normalization is
heuristic JSON/regex extraction, so the honest default is HEURISTIC).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from app.agents.harness.adapters.shadow import shadow_loop_eligible
from app.agents.harness.contracts import SYSTEM_TENANT, RiskClass

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

_SOURCE_LOOP = "coordinator"

# Explicit, deterministic delegated-agent -> canonical (tool, version) map. Only
# TWO honestly-safe delegations are mapped: dev -> agent.delegate.dev (downstream
# _tool_dev = hashtags.research, read-only) and isha -> agent.delegate.isha
# (_tool_isha = post_generator.generate_post, pure content-gen, read-only).
# Every other delegated agent (kavya/arjun/meera + side-effect agents) stays
# legacy => UNREGISTERED_TOOL. No wildcard, no auto-registration, no model identity.
COORDINATOR_TOOL_MAP: dict[str, tuple[str, str]] = {
    "dev": ("agent.delegate.dev", "1.0.0"),
    "isha": ("agent.delegate.isha", "1.0.0"),
}


def resolve_coordinator_tool(delegated_agent: str) -> tuple[str, str] | None:
    return COORDINATOR_TOOL_MAP.get((delegated_agent or "").strip().lower())


def _hash(obj: Any) -> str:
    try:
        return hashlib.sha1(
            json.dumps(obj, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:16]
    except Exception:
        return "unhashable"


def observe_coordinator_action(
    *,
    coordinator_run_id: str,
    orchestration_path: str,
    action_index: int,
    agent_id: str,
    tenant_id: str,
    normalized_action: dict,
    actual_executor: str,
    actual_result: Any = None,
    actual_error: Any = None,
    latency_ms: float = 0.0,
    raw_response_hash: str | None = None,
    fallback_used: bool = False,
    delegated_agent: str | None = None,
    parent_run_id: str | None = None,
    boundary: str = "_run_agent",
    execution_metadata: dict | None = None,
) -> dict | None:
    """Observe one coordinator normalized action in shadow. agent_id is the REAL
    delegated agent the coordinator invoked (a _TOOLS key). Returns the record or
    None (ineligible / internal failure). NEVER raises into the coordinator."""
    if not shadow_loop_eligible(agent_id, _SOURCE_LOOP):
        return None
    try:
        from pydantic import BaseModel, ConfigDict

        from app.agents.harness import Harness, RunContext, ToolCall, ToolRegistry

        aid = (agent_id or "").strip().lower()
        na = normalized_action or {}
        args = {k: v for k, v in na.items() if k != "tool"}
        # Canonical delegation identity: a mapped delegated agent (dev) resolves to
        # a canonical tool; every other agent stays legacy => UNREGISTERED_TOOL.
        _canon = resolve_coordinator_tool(aid)
        if _canon:
            tool, _tver = _canon
        else:
            tool = str(na.get("tool") or aid or "coordinator.action")
            _tver = "v1"
        # Coordinator internal actions (post draft, research, ops/qa/trainer
        # snapshots) are internal/read-only -> classify READ (no false approval).
        risk = RiskClass.READ
        crid = coordinator_run_id or ("coord_" + _hash((orchestration_path, action_index)))
        shadow_ref = f"shadow:{crid}:{orchestration_path}:{action_index}"

        class _AnyArgs(BaseModel):
            model_config = ConfigDict(extra="allow")

        async def _tripwire(**_: Any):
            raise AssertionError("coordinator shadow executor must never be invoked")

        reg = ToolRegistry(permission_fn=lambda a, t: True)
        reg.register(tool, _tripwire, _AnyArgs, risk)

        req = ToolCall(
            name=tool,
            args=args,
            reason="shadow observation of coordinator action",
            tool_version=_tver,
            risk_class=risk,
            idempotency_key=shadow_ref,
            budget_scope="run",
            expected_effect=f"coordinator {orchestration_path}[{action_index}]",
        )
        ctx = RunContext(
            run_id=crid,
            task_id=crid,
            tenant_id=(tenant_id or SYSTEM_TENANT),
            agent=aid,
            actor_id="coordinator",
            shadow_run_id=shadow_ref,
            source_loop=_SOURCE_LOOP,
        )
        meta = dict(execution_metadata or {})
        # Honest verdict override for observed (non-policy) coordinator outcomes.
        override = None
        if delegated_agent:
            override = "DELEGATION_OBSERVED"
        elif fallback_used:
            override = "FALLBACK_OBSERVED"
        elif str(meta.get("parser_confidence", "")).upper() in ("FAILED", "FALLBACK"):
            override = "PARSER_AMBIGUITY"
        meta.update(
            {
                "latency_ms": latency_ms,
                "legacy_tool": tool,
                "side_effect_class": "internal",
                "coordinator_run_id": crid,
                "orchestration_path": orchestration_path,
                "action_index": action_index,
                "actual_executor": actual_executor or f"_TOOLS[{aid}]",
                "raw_response_hash": raw_response_hash,
                "normalized_tool": tool,
                "normalized_arguments_hash": _hash(args),
                "actual_arguments_hash": _hash(args),
                "parser_type": meta.get("parser_type", "_extract_list"),
                "parser_confidence": meta.get("parser_confidence", "HEURISTIC"),
                "fallback_used": bool(fallback_used),
                "delegated_agent": delegated_agent,
                "parent_run_id": parent_run_id,
                "parent_action_id": f"{crid}:{action_index}",
                "tool_registry_status": (
                    "canonical_registered" if _canon else "unregistered_internal_action"
                ),
                "source_run_id": crid,
                "step_type": aid,
                "canonical_tool": (tool if _canon else None),
                "executor_boundary": boundary,
                "enforcement_applied": False,
            }
        )
        if override:
            meta["verdict_override"] = override
        return Harness(registry=reg).observe(
            ctx,
            req,
            actual_result=actual_result,
            actual_error=actual_error,
            execution_metadata=meta,
        )
    except Exception as e:
        logger.warning(
            "harness.coordinator_shadow: observation failed (coordinator unaffected): %s", e
        )
        try:
            from app.agents.harness import audit
            from app.agents.harness.contracts import RunContext

            audit.record(
                RunContext(agent=(agent_id or "").strip().lower(), run_id=coordinator_run_id or ""),
                None,
                None,
                kind="shadow_error",
                extra={
                    "error": str(e)[:200],
                    "agent": agent_id,
                    "orchestration_path": orchestration_path,
                    "source_loop": _SOURCE_LOOP,
                },
            )
        except Exception:
            pass
        return None
