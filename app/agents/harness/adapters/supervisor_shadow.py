"""Supervisor-family shadow adapter — record-only observation of the LangGraph
`supervisor` and `staff_supervisor` implementations (one loop family).

Boundary observed: the graph's NORMALIZED routing/selection object after the
graph finishes a step (supervisor.py: `out["route"]` -> a worker node;
staff_supervisor.py: the supervisor's routed reply). These are structured
routing decisions, not raw prose. When no structured selection is available the
record is MISSING_CONTEXT — never a guessed tool.

Never calls the model, executes the selected node/agent, alters graph state,
consumes the real tool-call id, or raises into LangGraph. Includes replay/
checkpoint deduplication so a repeated callback for the same
(graph_run_id, graph_step, tool_call_id, attempt) does not write twice.
"""

from __future__ import annotations

import collections
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

_SOURCE_LOOP = "supervisor"

# supervisor.py route label -> real target STAFF agent (deterministic; no wildcard).
SUPERVISOR_ROUTE_MAP: dict[str, str] = {
    "data_agent": "dev",
    "leads_agent": "rohan",
}

# target agent -> (canonical tool, version, claimed RiskClass). Dev REUSES the
# coordinator's agent.delegate.dev (GREEN read-only). Rohan = agent.delegate.rohan
# classified AMBER (EXTERNAL_SEND) by Rohan's broadest capability (outreach) — the
# claimed risk is raised to match the registry so REGISTRY_MATCH is honest, never
# lowered. Every unmapped agent stays UNREGISTERED.
SUPERVISOR_DELEGATION: dict[str, tuple[str, str, RiskClass]] = {
    "dev": ("agent.delegate.dev", "1.0.0", RiskClass.READ),
    "rohan": ("agent.delegate.rohan", "1.0.0", RiskClass.EXTERNAL_SEND),
}


def resolve_supervisor_delegation(agent_id: str):
    return SUPERVISOR_DELEGATION.get((agent_id or "").strip().lower())


# Bounded in-memory dedup of shadow WRITES only (never touches legacy execution).
_SEEN: collections.OrderedDict[str, int] = collections.OrderedDict()
_SEEN_MAX = 2048


def _hash(obj: Any) -> str:
    try:
        return hashlib.sha1(
            json.dumps(obj, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:16]
    except Exception:
        return "unhashable"


def _dedup_seen(key: str) -> bool:
    if key in _SEEN:
        return True
    _SEEN[key] = 1
    if len(_SEEN) > _SEEN_MAX:
        _SEEN.popitem(last=False)
    return False


def observe_supervisor_action(
    *,
    supervisor_run_id: str,
    graph_run_id: str,
    graph_step: int,
    tool_call_id: str | None,
    supervisor_implementation: str,
    actor_id: str,
    delegated_agent_id: str | None,
    tenant_id: str,
    tool_name: str,
    tool_arguments: dict | None = None,
    actual_executor: str = "",
    actual_result: Any = None,
    actual_error: Any = None,
    latency_ms: float = 0.0,
    attempt: int = 0,
    graph_metadata: dict | None = None,
) -> dict | None:
    """Observe one supervisor-family normalized action in shadow. Eligibility keys
    on the REAL delegated/executing agent identity (not the supervisor/manager
    actor). Returns the record, or None (ineligible / deduped / internal error).
    NEVER raises into LangGraph."""
    # Canary is based on the genuine delegated/executing agent (per mission).
    gate_agent = (delegated_agent_id or "").strip().lower()
    if not shadow_loop_eligible(gate_agent, _SOURCE_LOOP):
        return None

    dedup_key = f"{_SOURCE_LOOP}:{graph_run_id}:{graph_step}:{tool_call_id or 'idx'}:{attempt}"
    if _dedup_seen(dedup_key):
        # Bounded diagnostic — a duplicate callback/replay was suppressed.
        try:
            from app.agents.harness import audit
            from app.agents.harness.contracts import RunContext

            audit.record(
                RunContext(agent=gate_agent, run_id=graph_run_id),
                None,
                None,
                kind="shadow_dedup",
                extra={
                    "dedup_key": dedup_key,
                    "source_loop": _SOURCE_LOOP,
                    "replay_suppressed": True,
                },
            )
        except Exception:
            pass
        return None

    try:
        from pydantic import BaseModel, ConfigDict

        from app.agents.harness import Harness, RunContext, ToolCall, ToolRegistry

        args = tool_arguments or {}
        # Canonical delegation identity from the REAL delegated agent (never the
        # route label or prose). Dev=GREEN reuse, Rohan=AMBER. Unmapped=legacy.
        _canon = resolve_supervisor_delegation(gate_agent)
        if _canon:
            tool, _tver, risk = _canon
        else:
            tool = tool_name or f"supervisor.{supervisor_implementation}"
            _tver = "v1"
            risk = RiskClass.READ  # routing/draft = internal read-only
        srid = supervisor_run_id or graph_run_id or ("sup_" + _hash((graph_run_id, graph_step)))
        shadow_ref = f"shadow:{graph_run_id}:{graph_step}:{tool_call_id or attempt}"

        class _AnyArgs(BaseModel):
            model_config = ConfigDict(extra="allow")

        async def _tripwire(**_: Any):
            raise AssertionError("supervisor shadow executor must never be invoked")

        reg = ToolRegistry(permission_fn=lambda a, t: True)
        reg.register(tool, _tripwire, _AnyArgs, risk)

        req = ToolCall(
            name=tool,
            args=args,
            reason="shadow observation of supervisor action",
            tool_version=_tver,
            risk_class=risk,
            idempotency_key=shadow_ref,
            budget_scope="run",
            expected_effect=f"{supervisor_implementation} step {graph_step}",
        )
        ctx = RunContext(
            run_id=srid,
            task_id=srid,
            tenant_id=(tenant_id or SYSTEM_TENANT),
            agent=gate_agent,
            actor_id=(actor_id or "manager"),
            shadow_run_id=shadow_ref,
            source_loop=_SOURCE_LOOP,
        )
        gm = dict(graph_metadata or {})
        _route_label = gm.pop("route_label", None)
        _sel_source = str(gm.pop("selection_source", "") or "UNKNOWN").upper()
        _actual_node = gm.pop("actual_node", None) or actual_executor or tool
        # Route/node vs target agreement (supervisor.py: route -> expected target).
        _expected = SUPERVISOR_ROUTE_MAP.get(str(_route_label or "").strip().lower())
        _route_node_mismatch = bool(_expected and _expected != gate_agent)
        override = None
        # A heuristic/unknown structured selection is NOT trusted (blocks readiness);
        # a genuine route/node disagreement is surfaced (never guessed).
        if not _canon and _sel_source == "UNKNOWN":
            override = "MISSING_CONTEXT"
        elif not _canon and _sel_source == "HEURISTIC":
            override = "PARSER_AMBIGUITY"
        meta = {
            "latency_ms": latency_ms,
            "legacy_tool": tool,
            "side_effect_class": "internal",
            "supervisor_implementation": supervisor_implementation,
            "graph_run_id": graph_run_id,
            "graph_step": graph_step,
            "tool_call_id": tool_call_id,
            "actual_executor": actual_executor or tool,
            "normalized_tool": tool,
            "normalized_arguments_hash": _hash(args),
            "actual_arguments_hash": _hash(args),
            "delegated_agent": gate_agent,
            "delegated_agent_id": gate_agent,
            "parent_run_id": srid,
            "parent_action_id": f"{srid}:{graph_step}",
            "source_run_id": srid,
            "tool_registry_status": (
                "canonical_registered" if _canon else "unregistered_internal_action"
            ),
            "attempt": attempt,
            "replay_suppressed": False,
            "canonical_tool": (tool if _canon else None),
            "step_type": gate_agent,
            "enforcement_applied": False,
            "selection_source": _sel_source,
            "route_label": _route_label,
            "actual_node": _actual_node,
            "route_node_mismatch": _route_node_mismatch,
        }
        meta.update({f"graph_{k}": v for k, v in gm.items()})
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
        logger.warning("harness.supervisor_shadow: observation failed (graph unaffected): %s", e)
        try:
            from app.agents.harness import audit
            from app.agents.harness.contracts import RunContext

            audit.record(
                RunContext(agent=gate_agent, run_id=graph_run_id or ""),
                None,
                None,
                kind="shadow_error",
                extra={
                    "error": str(e)[:200],
                    "delegated_agent": gate_agent,
                    "supervisor_implementation": supervisor_implementation,
                    "source_loop": _SOURCE_LOOP,
                },
            )
        except Exception:
            pass
        return None
