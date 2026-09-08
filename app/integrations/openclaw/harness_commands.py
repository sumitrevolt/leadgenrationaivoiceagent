"""Kavach harness command surface for OpenClaw.

Read-only (GREEN) handlers report real harness state; control (AMBER) handlers
park through Owner OS exactly like the existing agent.* AMBER stubs. Kavach
NEVER mutates directly — Owner OS remains sole authority. RED is impossible here
(no harness command mutates production, calling, billing, WhatsApp or secrets).

Slots into app/integrations/openclaw alongside commands.py. Register the command
names in policies.py (GREEN_COMMANDS / AMBER_COMMANDS) and the handlers in
commands.py HANDLERS (or import HARNESS_HANDLERS and update()).
"""

from __future__ import annotations

import os
from typing import Any

# GREEN — read-only harness introspection.
HARNESS_GREEN = frozenset(
    {
        "harness.status",
        "harness.explain",
        "harness.conformance",
        "harness.evaluate",
        "harness.replay",
        "harness.tools",
        "harness.tool",
        "harness.registry",
        "harness.registry.conformance",
        "harness.enforcement",
        "harness.coordinator.contract",
        "harness.coordinator.samples",
        "harness.coordinator.readiness",
        "harness.supervisor.contract",
        "harness.supervisor.samples",
        "harness.supervisor.readiness",
    }
)

# AMBER — control actions; every one parks for Owner OS approval.
HARNESS_AMBER = frozenset(
    {
        "harness.shadow.enable",
        "harness.shadow.disable",
        "harness.canary.enable",
        "harness.canary.disable",
        "harness.enforce.enable",
        "harness.enforce.disable",
        "harness.pause",
        "harness.resume",
        "harness.cancel",
        "harness.checkpoint",
        "harness.kill",
        "harness.restore",
    }
)


def _flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name) or default).strip().lower() in ("1", "true", "yes", "on")


def _harness_flags() -> dict[str, Any]:
    return {
        "OPENCLAW_HARNESS_AGENT": _flag("OPENCLAW_HARNESS_AGENT", "0"),
        "AGENT_HARNESS": _flag("AGENT_HARNESS", "0"),
        "AGENT_HARNESS_SHADOW": _flag("AGENT_HARNESS_SHADOW", "0"),
        "AGENT_HARNESS_ENFORCE": _flag("AGENT_HARNESS_ENFORCE", "0"),
        "CODE_EXEC": _flag("CODE_EXEC", "0"),
        "canary_agents": (os.getenv("AGENT_HARNESS_CANARY_AGENTS") or "").strip(),
    }


def _kill_state() -> dict[str, Any]:
    """Live fleet kill-switch state (Redis), read-only."""
    try:
        from app.agents.harness.stop import _redis

        r = _redis()
        if r is None:
            return {"redis": False, "fleet_kill": None}
        return {"redis": True, "fleet_kill": bool(r.get("harness:kill:all"))}
    except Exception:
        return {"redis": False, "fleet_kill": None}


def _registry_summary() -> dict[str, Any]:
    try:
        from app.agents.harness import REGISTRY

        names = REGISTRY.names()
        return {"registered_tools": len(names), "tools": names[:50]}
    except Exception as e:
        return {"registered_tools": 0, "tools": [], "note": f"registry unavailable: {e}"}


def _audit_backend_status() -> dict[str, Any]:
    """Durable-audit backend snapshot for harness.status (read-only, no secrets)."""
    try:
        from app.agents.harness import audit

        return audit.backend_status()
    except Exception as e:  # status must never break
        return {"backend": "unknown", "error": str(e)[:160]}


def _status(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    flags = _harness_flags()
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "flags": flags,
            "kill_switch": _kill_state(),
            "registry": _registry_summary(),
            "enforcement": (
                "enforce"
                if flags["AGENT_HARNESS_ENFORCE"]
                else "shadow"
                if flags["AGENT_HARNESS_SHADOW"]
                else "inert"
            ),
            "calling_hard_off": True,
            "conformance_level": _conformance_level(flags),
            "audit_backend": _audit_backend_status(),
        },
        "evidence": {
            "sources": [
                "env_flags",
                "harness.REGISTRY",
                "harness.stop.kill",
                "harness.audit_backend",
            ],
            "actor": actor,
            "correlation_id": correlation_id,
        },
        "next_action": (
            "Shadow evidence dekho (harness.explain <run_id>)"
            if flags["AGENT_HARNESS_SHADOW"]
            else "Stage A shadow enable karo (owner approval)"
        ),
    }


def _explain(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    run_id = str(params.get("run_id") or "").strip()
    if not run_id:
        return {"status": "FAILED", "verified": True, "error": "run_id required", "result": None}
    try:
        from app.agents.harness import audit

        events = audit.replay(run_id)
    except Exception as e:
        return {"status": "FAILED", "verified": True, "error": str(e), "result": None}

    def _layer(ev: dict) -> str:
        x = ev.get("extra") or {}
        kind = ev.get("kind")
        if kind == "enforce" or x.get("layer") == "enforcement":
            evt = x.get("event") or ""
            if "denied" in evt:
                return "enforcement_denial"
            if "completed" in evt or "started" in evt:
                return "enforcement_execution"
            return "enforcement_decision"
        if kind == "shadow" or x.get("mode") == "shadow":
            return "shadow_observation"
        return "legacy_execution"

    layers: dict[str, int] = {}
    for e in events:
        layers[_layer(e)] = layers.get(_layer(e), 0) + 1
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "run_id": run_id,
            "event_count": len(events),
            "layers": layers,  # shadow_observation vs enforcement_decision/execution/denial vs legacy
            "timeline": events,
            "control_trail": [e.get("control_trail") for e in events if e.get("control_trail")],
        },
        "evidence": {"source": "harness.audit.replay", "correlation_id": correlation_id},
        "next_action": None if events else "Is run_id ka koi audit event nahi mila",
    }


def _replay(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    # Read-only alias of explain (timeline reconstruction, no side effects).
    return _explain(params, actor=actor, correlation_id=correlation_id)


def _conformance_level(flags: dict[str, Any]) -> str:
    if flags["AGENT_HARNESS_ENFORCE"]:
        return "L3-enforcing"
    if flags["AGENT_HARNESS_SHADOW"]:
        return "L2-shadow"
    return "L1-inert"


def _conformance(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    flags = _harness_flags()
    controls = {
        "VA-01_schema_validation": "registry.validate",
        "VA-02_arg_bounds": "registry.validate + no-idempotency reject",
        "PM-01_least_privilege": "registry.permit (fail-closed)",
        "PM-03_approval_gate": "loop -> risk_approve / Owner OS",
        "SB-01_sandbox": "harness.sandbox (subprocess+rlimits; container backend hook)",
        "SB-04_checkpoint": "loop -> agent_checkpoints.snapshot",
        "DL-01_egress_scan": "loop egress scan before external send",
        "OB-01_trace": "audit + observability_llm",
        "OB-02_replayable_audit": "audit.replay(run_id)",
        "ST-01_budget": "stop.admit (fail-closed) + gateway.admit_cost",
        "ST-02_progress_stop": "stop.check (no-progress/iteration/wall-clock)",
        "ST-03_kill_switch": "stop.killed (live redis, no redeploy)",
    }
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "level": _conformance_level(flags),
            "controls": controls,
            "flags": flags,
            "code_exec_sandboxed_off": not flags["CODE_EXEC"],
        },
        "evidence": {"correlation_id": correlation_id, "actor": actor},
        "next_action": "P0 sandbox + fail-closed budget verify karo",
    }


def _evaluate(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    """Read latest eval status via the existing eval gate (read-only)."""
    try:
        from app.agents import eval_gate  # existing module

        snap = getattr(eval_gate, "latest_snapshot", None)
        data = snap() if callable(snap) else {"note": "eval_gate.latest_snapshot unavailable"}
    except Exception as e:
        data = {"note": f"eval read unavailable: {e}"}
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {"eval": data},
        "evidence": {"source": "agents.eval_gate", "correlation_id": correlation_id},
        "next_action": None,
    }


def _amber_stub(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    """AMBER harness control — must park via owner_os_adapter, never execute here."""
    return {
        "status": "APPROVAL_REQUIRED",
        "approval_required": True,
        "verified": True,
        "result": {"note": "Harness control AMBER — Owner OS approval required"},
        "evidence": {"correlation_id": correlation_id, "actor": actor},
    }


def _tools(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.agents.harness.registry import REGISTRY

    tools = REGISTRY.list_tools()
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {"tools": tools, "count": len(tools), "manifest_hash": REGISTRY.manifest_hash()},
        "evidence": {"source": "harness.registry", "correlation_id": correlation_id},
        "next_action": None,
    }


def _tool(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.agents.harness.registry import REGISTRY

    name = str(params.get("name") or params.get("tool") or "").strip()
    if not name:
        return {"status": "FAILED", "verified": True, "error": "name required", "result": None}
    d = REGISTRY.get(name)
    if not d:
        return {
            "status": "SUCCEEDED",
            "verified": True,
            "result": {"name": name, "registered": False, "versions": REGISTRY.list_versions(name)},
            "evidence": {"correlation_id": correlation_id},
            "next_action": "Tool not registered",
        }
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "registered": True,
            "definition": d.public_view(),
            "versions": REGISTRY.list_versions(name),
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


def _registry(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.agents.harness.registry import REGISTRY

    tools = REGISTRY.list_tools()
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "manifest_hash": REGISTRY.manifest_hash(),
            "tool_count": len(tools),
            "tools": [f"{t['name']}@{t['version']}" for t in tools],
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


def _registry_conformance(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    from app.agents.harness.registry import REGISTRY

    tools = REGISTRY.list_tools()
    batch_registered = any(t["name"].startswith("batch.") for t in tools)
    dag_registered = any(t["name"].startswith("workflow.dag.") for t in tools)
    staff_registered = any(t["name"].startswith("agent.nikhil.") for t in tools)
    coord_registered = any(t["name"].startswith("agent.delegate.") for t in tools)
    supervisor_registered = any(t["name"] == "agent.delegate.rohan" for t in tools)
    families = {
        "staff.run_member": ("registered" if staff_registered else "unregistered"),
        "dag_engine": ("registered" if dag_registered else "unregistered"),
        "coordinator": ("registered" if coord_registered else "unregistered"),
        "supervisor": ("registered" if supervisor_registered else "unregistered"),
        "batch_harness": ("registered" if batch_registered else "unregistered"),
    }
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "families": families,
            "registered_tools": len(tools),
            "manifest_hash": REGISTRY.manifest_hash(),
            "enforcement": "OFF",
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": "Registry-backed enforcement is OFF (shadow-only)",
    }


def _enforcement(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    """Read-only enforcement config + executor bindings + resolved batch mode.
    Reports OFF whenever enforcement is not fully allowlisted (fail-closed)."""
    try:
        from app.agents.harness.enforce import enforcement_state

        st = enforcement_state()
    except Exception as e:
        return {"status": "FAILED", "verified": True, "error": str(e), "result": None}
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {**st, "note": "enforcement INERT unless agent+loop+tool fully allowlisted"},
        "evidence": {
            "source": "harness.enforce.enforcement_state",
            "correlation_id": correlation_id,
        },
        "next_action": (
            "Owner-approved canary runbook: docs/runbooks/BATCH_HARNESS_ENFORCEMENT_CANARY.md"
        ),
    }


def _coord_contract(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    import os as _os

    try:
        from app.agents.harness.coordinator_contract import (
            CoordinatorActionType,
            CoordinatorPlanVerdict,
        )

        atypes = [t.value for t in CoordinatorActionType]
        verdicts = [v.value for v in CoordinatorPlanVerdict]
    except Exception as e:
        return {"status": "FAILED", "verified": True, "error": str(e), "result": None}
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "plan_schema": "CoordinatorPlanV1",
            "action_schema": "CoordinatorActionV1",
            "contract_version": "1.0",
            "action_types": atypes,
            "verdicts": verdicts,
            "structured_plan_flag": (_os.getenv("COORDINATOR_STRUCTURED_PLAN") or "0"),
            "structured_plan_shadow_flag": (
                _os.getenv("COORDINATOR_STRUCTURED_PLAN_SHADOW") or "0"
            ),
            "prohibited": [
                "arbitrary action_type",
                "raw prose as contract",
                "kavach delegation target",
                "unknown agent",
                "extra fields",
            ],
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


def _coord_samples(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    # Per-run samples live in harness.explain(<coordinator_run_id>); this reports
    # structural coverage (both executor boundaries) + registered coordinator actions.
    from app.agents.harness.adapters.coordinator_shadow import COORDINATOR_TOOL_MAP
    from app.agents.harness.registry import REGISTRY

    reg = [
        f"{t['name']}@{t['version']}"
        for t in REGISTRY.list_tools()
        if t["name"].startswith("agent.delegate.")
    ]
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "executor_boundaries_covered": ["_run_agent", "_expert_contribution"],
            "boundary_coverage": "2/2",
            "registered_delegations": reg,
            "mapped_delegations": [f"{k}->{v[0]}@{v[1]}" for k, v in COORDINATOR_TOOL_MAP.items()],
            "note": "per-run plan-match/mismatch/fallback stats via harness.explain(run_id)",
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


def _coord_readiness(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "coordinator": "STRUCTURED CONTRACT STABLE, BUT NOT READY FOR ENFORCEMENT",
            "registry_backed_actions": ["agent.delegate.dev@1.0.0"],
            "executor_boundaries_covered": "2/2",
            "enforcement": "OFF",
            "blockers": [
                "real provider-native structured planning is shadow-only/mocked",
                "most delegations remain UNREGISTERED (side-effect/LLM downstream)",
                "no executor binding; enforcement prohibited",
            ],
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


def _sup_contract(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    try:
        from app.agents.harness.adapters.supervisor_shadow import (
            SUPERVISOR_DELEGATION,
            SUPERVISOR_ROUTE_MAP,
        )
        from app.agents.harness.coordinator_contract import SelectionSource, SupervisorVerdict
    except Exception as e:
        return {"status": "FAILED", "verified": True, "error": str(e), "result": None}
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "reused_contract": "CoordinatorActionV1 (via SupervisorDecisionV1)",
            "contract_version": "1.0",
            "implementations": ["supervisor", "staff_supervisor"],
            "selection_sources": [s.value for s in SelectionSource],
            "verdicts": [v.value for v in SupervisorVerdict],
            "route_map": SUPERVISOR_ROUTE_MAP,
            "delegations": {k: f"{v[0]}@{v[1]}" for k, v in SUPERVISOR_DELEGATION.items()},
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


def _sup_samples(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.agents.harness.registry import REGISTRY

    reg = [
        f"{t['name']}@{t['version']}"
        for t in REGISTRY.list_tools()
        if t["name"] in ("agent.delegate.dev", "agent.delegate.rohan")
    ]
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "implementations_covered": {
                "supervisor": "real graph proof",
                "staff_supervisor": "structured-contract wired; real graph gated on optional deps",
            },
            "registered_delegations": reg,
            "note": "per-run samples via harness.explain(<graph_run_id>)",
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


def _sup_readiness(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "supervisor_family": "STRUCTURED CONTRACT STABLE, BUT NOT READY FOR ENFORCEMENT",
            "registry_backed_actions": [
                "agent.delegate.dev@1.0.0 (reused, GREEN)",
                "agent.delegate.rohan@1.0.0 (AMBER approval-required)",
            ],
            "enforcement": "OFF",
            "blockers": [
                "staff_supervisor real graph gated on langgraph-supervisor optional dep",
                "agent.delegate.rohan is AMBER (never autonomous enforcement)",
                "no executor binding; enforcement prohibited",
            ],
        },
        "evidence": {"correlation_id": correlation_id},
        "next_action": None,
    }


HARNESS_HANDLERS: dict[str, Any] = {
    "harness.status": _status,
    "harness.coordinator.contract": _coord_contract,
    "harness.coordinator.samples": _coord_samples,
    "harness.coordinator.readiness": _coord_readiness,
    "harness.supervisor.contract": _sup_contract,
    "harness.supervisor.samples": _sup_samples,
    "harness.supervisor.readiness": _sup_readiness,
    "harness.explain": _explain,
    "harness.replay": _replay,
    "harness.conformance": _conformance,
    "harness.evaluate": _evaluate,
    "harness.tools": _tools,
    "harness.tool": _tool,
    "harness.registry": _registry,
    "harness.registry.conformance": _registry_conformance,
    "harness.enforcement": _enforcement,
    # AMBER controls — parked for Owner OS approval:
    "harness.shadow.enable": _amber_stub,
    "harness.shadow.disable": _amber_stub,
    "harness.canary.enable": _amber_stub,
    "harness.canary.disable": _amber_stub,
    "harness.enforce.enable": _amber_stub,
    "harness.enforce.disable": _amber_stub,
    "harness.pause": _amber_stub,
    "harness.resume": _amber_stub,
    "harness.cancel": _amber_stub,
    "harness.checkpoint": _amber_stub,
    "harness.kill": _amber_stub,
    "harness.restore": _amber_stub,
}
