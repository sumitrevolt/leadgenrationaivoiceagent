"""Shadow adapter — record-only observation of a real legacy agent execution.

Contract (mission Stage A):
  legacy path stays authoritative and executes exactly once; this adapter
  receives a COPY of the execution intent + result and asks the harness what it
  WOULD have decided. It never executes the tool, never mutates, never touches
  the legacy idempotency key, never activates a peer agent, and never raises
  into the caller.

Eligibility (ALL required):
  AGENT_HARNESS=1 AND AGENT_HARNESS_SHADOW=1 AND AGENT_HARNESS_ENFORCE=0
  AND normalized agent_id in AGENT_HARNESS_CANARY_AGENTS  (no wildcard).
Empty allowlist => nobody eligible. Flags read at call-time (repo convention).
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.agents.harness.contracts import SYSTEM_TENANT, RiskClass

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


def _flag_on(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return bool(v) and v not in ("0", "false", "no", "off")


def _canary_set() -> set[str]:
    raw = (os.getenv("AGENT_HARNESS_CANARY_AGENTS") or "").strip()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _loop_set() -> set[str]:
    raw = (os.getenv("AGENT_HARNESS_CANARY_LOOPS") or "").strip()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def shadow_eligible(agent_id: str) -> bool:
    """True only when shadow mode is on, enforcement is off, and the normalized
    agent is explicitly in the canary allowlist. Fail-safe: any doubt => False."""
    if not _flag_on("AGENT_HARNESS"):
        return False
    if not _flag_on("AGENT_HARNESS_SHADOW"):
        return False
    if _flag_on("AGENT_HARNESS_ENFORCE"):
        return False
    aid = (agent_id or "").strip().lower()
    if not aid:
        return False
    return aid in _canary_set()


def shadow_loop_eligible(agent_id: str, source_loop: str) -> bool:
    """Loop-scoped eligibility: agent eligible AND the source loop is explicitly
    allowlisted (AGENT_HARNESS_CANARY_LOOPS). Empty loop allowlist => False.
    Used by loop adapters (e.g. dag_engine) that opt in per-loop; the run_member
    adapter stays agent-only so it is unaffected by this gate."""
    if not shadow_eligible(agent_id):
        return False
    loops = _loop_set()
    return bool(loops) and (source_loop or "").strip().lower() in loops


# Honest per-agent classification of the run_member job's side-effect surface.
# nikhil = Revenue Ops COMPOSITE: revenue_digest + client_health + usage_alerts;
# usage_alerts CAN send customer upsell emails -> EXTERNAL_SEND (AMBER), NOT a
# simple internal write. Registry classification (AMBER) is authoritative.
_JOB_RISK = {"nikhil": RiskClass.EXTERNAL_SEND}


def _classify(agent_id: str) -> RiskClass:
    return _JOB_RISK.get((agent_id or "").strip().lower(), RiskClass.READ)


# Explicit, deterministic member -> canonical (tool, version) mapping. STAFF
# membership ALONE never registers a tool; only members listed here map to a
# canonical identity. Every other member stays UNREGISTERED_TOOL. No wildcard,
# no function-name identity, no model-selected identity, no auto-registration.
STAFF_TOOL_MAP: dict[str, tuple[str, str]] = {
    "nikhil": ("agent.nikhil.revenue_operations", "1.0.0"),
}


def resolve_staff_tool(member: str) -> tuple[str, str] | None:
    """Return (canonical_tool, version) for a mapped STAFF member, or None."""
    return STAFF_TOOL_MAP.get((member or "").strip().lower())


def _composite_summary(result) -> dict | None:
    """Bounded composite-operation summary for run_nikhil-style results. Honest
    partial-failure semantics: a component with an 'error' key is a failure."""
    if not isinstance(result, dict):
        return None
    comps = result.get("results")
    if not isinstance(comps, dict) or not comps:
        return None
    per = {}
    ok_n = fail_n = 0
    for name, r in list(comps.items())[:16]:
        c_ok = isinstance(r, dict) and not r.get("error")
        per[str(name)[:40]] = "ok" if c_ok else "error"
        ok_n += 1 if c_ok else 0
        fail_n += 0 if c_ok else 1
    return {
        "composite_action": True,
        "components": sorted(per.keys()),
        "component_count": len(per),
        "component_status": per,
        "components_ok": ok_n,
        "components_failed": fail_n,
        "partial_success": ok_n > 0 and fail_n > 0,
        "full_success": fail_n == 0 and ok_n > 0,
    }


class _JobArgs(BaseModel):
    """run_member jobs take no structured args; strict-empty schema."""

    model_config = ConfigDict(extra="forbid")


async def _noop(**_: Any) -> Any:  # never called by observe() — presence-only
    raise AssertionError("shadow tool executor must never be invoked")


def observe_legacy_run(
    agent_id: str,
    action: str | None = None,
    *,
    actual_result: Any = None,
    actual_error: Any = None,
    latency_ms: int | None = None,
    source_loop: str = "staff.run_member",
    actor_id: str = "operator",
    real_run_id: str | None = None,
    action_index: int = 0,
) -> dict | None:
    """Observe one legacy run in shadow. Returns the shadow record, or None when
    ineligible / on internal failure. NEVER raises into the caller."""
    if not shadow_eligible(agent_id):
        return None
    try:
        from app.agents.harness import Harness, RunContext, ToolCall, ToolRegistry

        aid = agent_id.strip().lower()
        risk = _classify(aid)
        rrid = real_run_id or ("run_" + uuid.uuid4().hex[:12])
        # Shadow-safe derived reference — NOT the legacy idempotency key.
        shadow_ref = f"shadow:{rrid}:{action_index}"
        legacy_tool = action or f"staff.run_{aid}"  # the REAL executor identity
        # Canonical identity resolution: a mapped STAFF member maps to a canonical
        # (tool, version); every unmapped member stays legacy => UNREGISTERED.
        _canon = resolve_staff_tool(aid)
        if _canon:
            tool, tver = _canon
        else:
            tool, tver = legacy_tool, "v1"

        req = ToolCall(
            name=tool,
            args={},
            reason="shadow observation of legacy staff run",
            tool_version=tver,
            risk_class=risk,
            idempotency_key=shadow_ref,
            expected_effect="internal revenue-ops digest/health/alerts",
            budget_scope="run",
        )
        # Throwaway registry: permits the canary agent and classifies the tool,
        # without touching or polluting any global registry.
        reg = ToolRegistry(permission_fn=lambda a, t: True)
        reg.register(tool, _noop, _JobArgs, risk)

        ctx = RunContext(
            run_id=rrid,
            task_id=rrid,
            tenant_id=SYSTEM_TENANT,
            agent=aid,
            actor_id=actor_id,
            shadow_run_id=shadow_ref,
            source_loop=source_loop,
        )
        _meta = {
            "latency_ms": latency_ms,
            "legacy_tool": legacy_tool,
            "side_effect_class": ("external_send" if _canon else "internal"),
            "step_type": aid,
            "canonical_tool": (tool if _canon else None),
            "tool_registry_status": (
                "canonical_registered" if _canon else "unregistered_internal_action"
            ),
            "enforcement_applied": False,
        }
        _comp = _composite_summary(actual_result)
        if _comp:
            _meta.update(_comp)
        rec = Harness(registry=reg).observe(
            ctx,
            req,
            actual_result=actual_result,
            actual_error=actual_error,
            execution_metadata=_meta,
        )
        return rec
    except Exception as e:
        # Observer failure must be VISIBLE (audited) but must NOT break legacy.
        logger.warning("harness.shadow: observation failed (legacy unaffected): %s", e)
        try:
            from app.agents.harness import audit
            from app.agents.harness.contracts import RunContext

            audit.record(
                RunContext(agent=(agent_id or "").strip().lower()),
                None,
                None,
                kind="shadow_error",
                extra={"error": str(e)[:200], "agent": agent_id, "source_loop": source_loop},
            )
        except Exception:
            pass
        return None
