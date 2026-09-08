"""
Agent Runtime workforce factory — all 31 STAFF → real capability adapters.
==========================================================================

REUSE-not-duplicate: har capability EXISTING engine / staff wrapper ko call
karti hai. Naya queue, naya scheduler, naya command bus NAHI.

Swara / Ananya (RED): sirf ``frozen_transfer_status`` capability register —
voice modules / STT / TTS / dial paths ZERO touch. Dispatch RED lane pe
hamesha blocked (evaluate_policy). OpenClaw unhe Owner OS status se dekhta hai.

Wave-B dispatchable (PILOT_AGENTS widen): GREEN L0/L1 read/report engines +
nikhil delivery-assurance READ-ONLY scan. Customer-touch AMBER (rohan/priya/…)
capability register hote hain par pilot allowlist se bahar = intentionally
disabled until owner expands rollout.

Import-safe; ``ensure_workforce_registered()`` idempotent.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.platform.agent_runtime import (
    AgentCapability,
    AgentExecutionContext,
    SkipTask,
    register_capability,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Canonical action names (Owner OS / OpenClaw / tests share these).
ACTION_OWNED = "run_owned_workflow"
ACTION_FROZEN = "frozen_transfer_status"
ACTION_DELIVERY_SCAN = "scan_delivery_assurance"

# Voice / RED — OpenClaw transfer only; never dispatchable via runtime.
FROZEN_VOICE_AGENTS: frozenset[str] = frozenset({"swara", "ananya"})

# Customer-touch / inbound AMBER — capability wired, rollout OFF by default.
AMBER_HOLD_AGENTS: frozenset[str] = frozenset(
    {"rohan", "kiran", "priya", "anika", "ira", "riya", "raksha"}
)

# Voice-adjacent GREEN held this wave (Swara frozen mandate → no voice QA churn).
VOICE_HOLD_AGENTS: frozenset[str] = frozenset({"arjun", "meera", "tara"})

# GREEN engines that WRITE (DB/files/email/KB) — capability registered, NOT in
# PILOT_AGENTS until a dedicated mutating canary. side_effect honesty = internal.
GREEN_MUTATE_HOLD: frozenset[str] = frozenset(
    {"manager", "lekha", "neha", "ravi", "dev", "guru", "vikram"}
)


def _refuse_error_dict(out: Any, label: str) -> dict[str, Any]:
    """Staff/engine often return {"error": ...} without raising — refuse as fail."""
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(f"{label}:{out.get('error')}")
    if isinstance(out, dict):
        return out
    return {"value": out}


def _flag_skip(flag: str) -> None:
    import os

    v = (os.getenv(flag) or "").strip().lower()
    if not v or v in ("0", "false", "no", "off"):
        raise SkipTask(f"flag_off:{flag}")


# --------------------------------------------------------------------------- #
# Capability implementations (thin engine wraps)
# --------------------------------------------------------------------------- #
async def frozen_transfer_status(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Swara/Ananya OpenClaw transfer package — NO voice execution.

    Policy blocks RED before this runs; kept for capability inventory + tests
    that bypass lane only in unit isolation. Production path = blocked.
    """
    aid = ctx.task.agent_id
    return {
        "agent_id": aid,
        "openclaw_transfer": True,
        "status": "FROZEN",
        "modification_permission": "NONE",
        "calling": "RUNTIME_RED_BLOCKED",
        "runtime_dispatch": "blocked_red_lane",
        "note": (
            "Agent Runtime RED lane blocks Swara/Ananya dispatch here. "
            "This does NOT report platform_dial / voice_launch campaign posture — "
            "see owner_os.calling_posture() / runtime_status calling_badge for that. "
            "Voice code stays frozen; compliance gates unchanged."
        ),
        "side_effects": False,
    }


async def nikhil_scan_delivery_assurance(ctx: AgentExecutionContext) -> dict[str, Any]:
    """Read-only missed/at-risk paid-customer scan — no dunning sends."""
    _flag_skip("DELIVERY_ASSURANCE_AGENT")
    from app.marketing import delivery_assurance

    out = await asyncio.to_thread(
        delivery_assurance.scan_missed_deliverables,
        int(ctx.task.payload.get("limit") or 100),
        bool(ctx.task.payload.get("include_healthy") or False),
    )
    ctx.add_usage(api_calls=1)
    return {
        "check": "scan_delivery_assurance",
        "read_only": True,
        "customer_contacted": False,
        "result": out if isinstance(out, dict) else {"value": out},
    }


async def hermes_infra_snapshot(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("INFRA_HANDLER")
    from app.platform import infra_handler

    out = await infra_handler.snapshot()
    ctx.add_usage(api_calls=1)
    return {
        "check": "infra_snapshot",
        "read_only": True,
        "result": _refuse_error_dict(out, "hermes"),
    }


async def pranav_sre(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("SRE_AGENT")
    from app.platform import engineer_agents

    out = await asyncio.to_thread(engineer_agents.run_sre)
    ctx.add_usage(api_calls=1)
    return {"check": "sre", "read_only": True, "result": _refuse_error_dict(out, "pranav")}


async def vidya_finops(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("FINOPS_AGENT")
    from app.platform import engineer_agents

    out = await asyncio.to_thread(engineer_agents.run_finops)
    ctx.add_usage(api_calls=1)
    return {"check": "finops", "read_only": True, "result": _refuse_error_dict(out, "vidya")}


async def arnav_security(ctx: AgentExecutionContext) -> dict[str, Any]:
    # Runtime gate = SECURITY_POSTURE_AGENT (registry primary_flag). Do NOT
    # OR with scheduler-only SECURITY_AGENT; call ungated posture compute.
    _flag_skip("SECURITY_POSTURE_AGENT")
    from app.platform import engineer_agents

    out = await asyncio.to_thread(engineer_agents.compute_security_posture)
    ctx.add_usage(api_calls=1)
    return {"check": "security", "read_only": True, "result": _refuse_error_dict(out, "arnav")}


async def kabir_dbre(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("DBRE_AGENT")
    from app.platform import engineer_agents

    out = await asyncio.to_thread(engineer_agents.run_dbre)
    ctx.add_usage(api_calls=1)
    return {"check": "dbre", "read_only": True, "result": _refuse_error_dict(out, "kabir")}


async def diya_dataquality(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("DATA_INTEGRITY_AGENT")
    from app.platform import engineer_agents

    out = await asyncio.to_thread(engineer_agents.run_dataquality)
    ctx.add_usage(api_calls=1)
    return {
        "check": "dataquality",
        "read_only": True,
        "result": _refuse_error_dict(out, "diya"),
    }


async def aryan_deps(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("DEPS_AGENT")
    from app.platform import engineer_agents

    out = await asyncio.to_thread(engineer_agents.run_deps)
    ctx.add_usage(api_calls=1)
    return {
        "check": "deps_proposals",
        "read_only": True,
        "published": False,
        "result": _refuse_error_dict(out, "aryan"),
    }


async def arya_mcp(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("MCP_ENGINEER")
    from app.platform import mcp_engineer

    out = await asyncio.to_thread(mcp_engineer.run_mcp)
    ctx.add_usage(api_calls=1)
    return {"check": "mcp_health", "read_only": True, "result": _refuse_error_dict(out, "arya")}


async def manager_digest(ctx: AgentExecutionContext) -> dict[str, Any]:
    from app.agents import staff

    out = await staff.run_digest()
    ctx.add_usage(api_calls=1)
    return {"check": "daily_digest", "result": _refuse_error_dict(out, "manager")}


async def lekha_kpi(ctx: AgentExecutionContext) -> dict[str, Any]:
    from app.agents import staff

    out = await staff.run_lekha()
    ctx.add_usage(api_calls=1)
    return {"check": "call_kpi_digest", "result": _refuse_error_dict(out, "lekha")}


async def neha_pipeline(ctx: AgentExecutionContext) -> dict[str, Any]:
    from app.agents import staff

    out = await staff.run_neha()
    ctx.add_usage(api_calls=1)
    return {"check": "pipeline", "result": _refuse_error_dict(out, "neha")}


async def ravi_seo(ctx: AgentExecutionContext) -> dict[str, Any]:
    from app.agents import staff

    out = await staff.run_ravi()
    ctx.add_usage(api_calls=1)
    return {"check": "seo_pages", "result": _refuse_error_dict(out, "ravi")}


async def dev_onboarding(ctx: AgentExecutionContext) -> dict[str, Any]:
    from app.agents import staff

    out = await staff.run_dev()
    ctx.add_usage(api_calls=1)
    return {"check": "onboarding_sweep", "result": _refuse_error_dict(out, "dev")}


async def guru_skills(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("SKILL_PACK")
    from app.agents import staff

    out = await staff.run_guru()
    ctx.add_usage(api_calls=1)
    return {"check": "skill_ingest", "result": _refuse_error_dict(out, "guru")}


async def vikram_upgrader(ctx: AgentExecutionContext) -> dict[str, Any]:
    _flag_skip("CODE_UPGRADER")
    from app.agents import staff

    out = await staff.run_vikram()
    ctx.add_usage(api_calls=1)
    return {
        "check": "code_upgrade_proposals",
        "published": False,
        "result": _refuse_error_dict(out, "vikram"),
    }


def _staff_owned(member: str) -> Callable[[AgentExecutionContext], Awaitable[dict[str, Any]]]:
    """Generic owned-workflow wrap for hold-roster agents (capability inventory)."""

    async def _fn(ctx: AgentExecutionContext) -> dict[str, Any]:
        from app.agents import staff

        out = await staff.run_member(member)
        ctx.add_usage(api_calls=1)
        return {
            "check": "run_owned_workflow",
            "via": "staff.run_member",
            "member": member,
            "result": out if isinstance(out, dict) else {"value": out},
        }

    _fn.__name__ = f"owned_{member}"
    return _fn


# Explicit Wave-B maps. Pilots (kavya/isha/zara) stay in pilots.py.
# side_effect honesty: "none" only for true read-only; writers = "internal".
_WAVE_B_CAPS: list[tuple[str, str, Callable, str, bool, bool]] = [
    # agent_id, action, fn, side_effect, tenant_scoped, requires_approval
    ("hermes", ACTION_OWNED, hermes_infra_snapshot, "none", False, False),
    ("pranav", ACTION_OWNED, pranav_sre, "none", False, False),
    ("vidya", ACTION_OWNED, vidya_finops, "none", False, False),
    ("arnav", ACTION_OWNED, arnav_security, "none", False, False),
    ("kabir", ACTION_OWNED, kabir_dbre, "none", False, False),
    ("diya", ACTION_OWNED, diya_dataquality, "none", False, False),
    ("aryan", ACTION_OWNED, aryan_deps, "none", False, False),
    ("arya", ACTION_OWNED, arya_mcp, "none", False, False),
    ("nikhil", ACTION_DELIVERY_SCAN, nikhil_scan_delivery_assurance, "none", False, False),
    # Capability inventory — NOT in PILOT_AGENTS (GREEN_MUTATE_HOLD)
    ("manager", ACTION_OWNED, manager_digest, "internal", False, False),
    ("lekha", ACTION_OWNED, lekha_kpi, "internal", False, False),
    ("neha", ACTION_OWNED, neha_pipeline, "internal", False, False),
    ("ravi", ACTION_OWNED, ravi_seo, "internal", False, False),
    ("dev", ACTION_OWNED, dev_onboarding, "internal", False, False),
    ("guru", ACTION_OWNED, guru_skills, "internal", False, False),
    ("vikram", ACTION_OWNED, vikram_upgrader, "internal", False, False),
]


def ensure_workforce_registered() -> None:
    """Idempotent: pilots + sprint caps + Wave-B + frozen transfer + hold-roster."""
    from app.platform.agent_runtime_pilots import ensure_pilots_registered
    from app.platform.agent_runtime_sprint import ensure_sprint_registered
    from app.platform.team import STAFF

    ensure_pilots_registered()
    ensure_sprint_registered()

    for aid in FROZEN_VOICE_AGENTS:
        register_capability(
            AgentCapability(
                agent_id=aid,
                action=ACTION_FROZEN,
                fn=frozen_transfer_status,
                side_effect="none",
                tenant_scoped=False,
                description=f"{aid} OpenClaw frozen transfer status (RED — never dispatch)",
            )
        )

    for aid, action, fn, side, tenant, approval in _WAVE_B_CAPS:
        register_capability(
            AgentCapability(
                agent_id=aid,
                action=action,
                fn=fn,
                side_effect=side,
                tenant_scoped=tenant,
                requires_approval=approval,
                description=f"{aid} owned workflow via existing engine",
            )
        )

    from app.platform.agent_runtime import capabilities_for

    # Hold roster: capability inventory via staff.run_member (dispatch gated off).
    # AMBER customer-touch: side_effect=customer + requires_approval even while held
    # so a future allowlist mistake cannot silent-mutate.
    hold = AMBER_HOLD_AGENTS | VOICE_HOLD_AGENTS
    for aid in sorted(hold):
        if aid not in STAFF:
            continue
        amber = aid in AMBER_HOLD_AGENTS
        register_capability(
            AgentCapability(
                agent_id=aid,
                action=ACTION_OWNED,
                fn=_staff_owned(aid),
                side_effect="customer" if amber else "none",
                tenant_scoped=False,
                requires_approval=bool(amber),
                description=f"{aid} owned workflow (rollout hold — capability ready)",
            )
        )

    # Honesty gate: every STAFF id must have ≥1 capability after registration.
    for aid in STAFF:
        if capabilities_for(aid):
            continue
        register_capability(
            AgentCapability(
                agent_id=aid,
                action=ACTION_OWNED,
                fn=_staff_owned(aid),
                side_effect="none",
                description=f"{aid} fallback owned workflow",
            )
        )


def workforce_rollout_state() -> dict[str, Any]:
    """Machine-readable rollout projection for matrix / OpenClaw."""
    from app.platform import agent_registry as ar
    from app.platform import agent_runtime as rt

    reg = ar.build_registry()
    pilots = set(rt.PILOT_AGENTS)
    rows = []
    for aid, c in reg.items():
        caps = rt.capabilities_for(aid)
        if aid in FROZEN_VOICE_AGENTS:
            state = "intentionally_disabled"
        elif aid in pilots:
            state = "canary_ready"
        elif aid in GREEN_MUTATE_HOLD:
            state = "rollout_hold"
        elif caps:
            state = "rollout_hold"
        else:
            state = "capability_defined"
        rows.append(
            {
                "agent_id": aid,
                "name": c.name,
                "lane": c.lane,
                "mode": c.default_mode,
                "capabilities": caps,
                "pilot": aid in pilots,
                "rollout_state": state,
            }
        )
    return {
        "ok": True,
        "staff_count": len(rows),
        "pilots": sorted(pilots),
        "frozen_voice": sorted(FROZEN_VOICE_AGENTS),
        "agents": rows,
    }


__all__ = [
    "ACTION_DELIVERY_SCAN",
    "ACTION_FROZEN",
    "ACTION_OWNED",
    "AMBER_HOLD_AGENTS",
    "FROZEN_VOICE_AGENTS",
    "GREEN_MUTATE_HOLD",
    "VOICE_HOLD_AGENTS",
    "ensure_workforce_registered",
    "workforce_rollout_state",
]
