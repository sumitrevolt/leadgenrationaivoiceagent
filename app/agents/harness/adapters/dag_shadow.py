"""DAG-engine shadow adapter — record-only observation of one real DAG node.

Wraps the typed executor boundary in app/agents/dag_engine.py:advance
(`process_library.execute_step` + `check_gate`). Each node/attempt that the DAG
executes once is copied here and evaluated by Harness.observe() in record-only
mode. This adapter NEVER executes the node, invokes the tool, alters the
journal, schedules a node, consumes the real idempotency key, or raises into the
DAG engine.

Eligibility (per-loop): shadow_loop_eligible(agent_id, "dag_engine") — requires
AGENT_HARNESS + AGENT_HARNESS_SHADOW on, ENFORCE off, agent in canary agents AND
"dag_engine" in AGENT_HARNESS_CANARY_LOOPS. Empty loop allowlist => no-op.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.agents.harness.adapters.shadow import shadow_loop_eligible
from app.agents.harness.contracts import SYSTEM_TENANT, RiskClass

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

_SOURCE_LOOP = "dag_engine"

# Explicit, deterministic step-type -> canonical (tool, version) mapping.
# The DAG node ID and arbitrary model-provided step labels are NOT trusted tool
# identities — only a stable process-library action listed here maps to a
# canonical tool. Unknown step types stay UNREGISTERED_TOOL (fail-open observe,
# never falsely "registered"). No dynamic construction, no callable scanning.
DAG_TOOL_MAP: dict[str, tuple[str, str]] = {
    "internal_calculation": ("workflow.dag.internal_calculation", "1.0.0"),
}


def resolve_dag_tool(step_action: str) -> tuple[str, str] | None:
    """Return (canonical_tool, version) for a stable DAG step action, or None."""
    return DAG_TOOL_MAP.get((step_action or "").strip())


def _valid_envelope(dag_run_id: str, node_id: str, attempt: int) -> str | None:
    """Strict DAG action-envelope guard (spec DagActionPayload). Returns an error
    string when malformed, else None. Bounds node_id/run_id; attempt >= 0."""
    if not (dag_run_id or "").strip():
        return "missing dag_run_id"
    nid = (node_id or "").strip()
    if not nid:
        return "missing node_id"
    if len(nid) > 200 or len(str(dag_run_id)) > 200:
        return "node_id/dag_run_id too long"
    try:
        if int(attempt) < 0:
            return "attempt must be non-negative"
    except Exception:
        return "attempt not an integer"
    return None


def _args_hash(args: Any) -> str:
    import hashlib
    import json

    try:
        return hashlib.sha1(
            json.dumps(args, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:16]
    except Exception:
        return "unhashable"


def observe_dag_action(
    *,
    dag_run_id: str,
    node_id: str,
    attempt: int,
    agent_id: str,
    tenant_id: str,
    tool_name: str,
    tool_version: str | None = None,
    arguments: dict | None = None,
    actual_result: Any = None,
    actual_error: Any = None,
    latency_ms: int = 0,
    dag_node_status: str = "",
    retry_scheduled: bool = False,
    execution_metadata: dict | None = None,
) -> dict | None:
    """Observe one DAG node execution attempt in shadow. Returns the record or
    None (ineligible / internal failure). NEVER raises into the DAG engine."""
    if not shadow_loop_eligible(agent_id, _SOURCE_LOOP):
        return None
    # Strict DAG action-envelope guard — malformed metadata is a diagnostic, never
    # an executed-action observation (and NEVER a false legacy failure).
    _env_err = _valid_envelope(dag_run_id, node_id, attempt)
    if _env_err:
        try:
            from app.agents.harness import audit
            from app.agents.harness.contracts import RunContext as _RC

            audit.record(
                _RC(agent=(agent_id or "").strip().lower(), run_id=(dag_run_id or "dag_unknown")),
                None,
                None,
                kind="shadow_error",
                extra={
                    "error": f"dag_envelope: {_env_err}",
                    "node_id": node_id,
                    "dag_run_id": dag_run_id,
                    "source_loop": _SOURCE_LOOP,
                    "comparison_verdict": "MISSING_CONTEXT",
                },
            )
        except Exception:
            pass
        return None
    try:
        from app.agents.harness import Harness, RunContext, ToolCall, ToolRegistry

        aid = (agent_id or "").strip().lower()
        # Canonical identity resolution: a stable process-library action maps to a
        # canonical (tool, version); an unmapped/legacy action stays UNREGISTERED.
        _canon = resolve_dag_tool(tool_name)
        if _canon:
            tool, _canon_ver = _canon
            _tver = _canon_ver
        else:
            tool = tool_name or f"dag.{node_id}"
            _tver = str(tool_version or "v1")
        args = arguments or {}
        # Read-only default: DAG task steps are internal compute; classify READ so
        # the shadow never falsely claims an approval/checkpoint was needed. (A
        # per-action risk map can refine this later without changing the seam.)
        risk = RiskClass.READ
        # Distinct, non-executable reference per node+attempt; linked to the run.
        shadow_ref = f"shadow:{dag_run_id}:{node_id}:{attempt}"

        # A permissive throwaway registry that classifies the tool; the tool fn is
        # a tripwire that must never be called by observe().
        from pydantic import BaseModel, ConfigDict

        class _AnyArgs(BaseModel):
            model_config = ConfigDict(extra="allow")

        async def _tripwire(**_: Any):
            raise AssertionError("dag shadow tool executor must never be invoked")

        reg = ToolRegistry(permission_fn=lambda a, t: True)
        reg.register(tool, _tripwire, _AnyArgs, risk)

        req = ToolCall(
            name=tool,
            args=args,
            reason="shadow observation of DAG node",
            tool_version=_tver,
            risk_class=risk,
            idempotency_key=shadow_ref,
            budget_scope="run",
            expected_effect=f"dag node {node_id} (attempt {attempt})",
        )
        ctx = RunContext(
            run_id=dag_run_id,
            task_id=dag_run_id,
            tenant_id=(tenant_id or SYSTEM_TENANT),
            agent=aid,
            actor_id="dag_scheduler",
            shadow_run_id=shadow_ref,
            source_loop=_SOURCE_LOOP,
        )
        meta = dict(execution_metadata or {})
        meta.update(
            {
                "latency_ms": latency_ms,
                "legacy_tool": tool,
                "side_effect_class": "internal",
                "dag_run_id": dag_run_id,
                "node_id": node_id,
                "attempt": attempt,
                "dag_node_status": dag_node_status,
                "retry_scheduled": bool(retry_scheduled),
                "actual_executor": "process_library.execute_step",
                "declared_tool": tool,
                "actual_arguments_hash": _args_hash(args),
                "source_run_id": dag_run_id,
                "source_node_id": node_id,
                "source_attempt": attempt,
                "step_type": (tool_name or ""),
                "canonical_tool": (tool if _canon else None),
                "tool_registry_status": (
                    "canonical_registered" if _canon else "unregistered_internal_action"
                ),
                "enforcement_applied": False,
            }
        )
        return Harness(registry=reg).observe(
            ctx,
            req,
            actual_result=actual_result,
            actual_error=actual_error,
            execution_metadata=meta,
        )
    except Exception as e:
        logger.warning("harness.dag_shadow: observation failed (DAG unaffected): %s", e)
        try:
            from app.agents.harness import audit
            from app.agents.harness.contracts import RunContext

            audit.record(
                RunContext(agent=(agent_id or "").strip().lower(), run_id=dag_run_id),
                None,
                None,
                kind="shadow_error",
                extra={
                    "error": str(e)[:200],
                    "agent": agent_id,
                    "node_id": node_id,
                    "dag_run_id": dag_run_id,
                    "source_loop": _SOURCE_LOOP,
                },
            )
        except Exception:
            pass
        return None
