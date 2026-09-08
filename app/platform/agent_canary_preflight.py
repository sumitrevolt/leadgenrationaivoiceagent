"""Agent Runtime canary preflight — read-only eligibility census + isolation guard.

WHY (2026-07-22): Nikhil canary correctly stopped because ``primary_flag=""`` plus
peer flags already ON in prod meant ``AGENT_RUNTIME=1`` would arm many pilots.
This module answers "if AGENT_RUNTIME were ON, who is eligible?" without flipping
any flags, and fails closed for single-agent canary isolation.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _flag_on(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return bool(v) and v not in ("0", "false", "no", "off")


def _role_label(aid: str, contract: Any) -> str:
    title = (getattr(contract, "title", None) or "").strip()
    name = (getattr(contract, "name", None) or aid).strip()
    if title:
        return f"{name} ({title})"
    return name


def agent_flag_census(*, assume_runtime_on: bool | None = None) -> dict[str, Any]:
    """Complete 31-agent flag census. Read-only. Never raises a hard error.

    ``assume_runtime_on``:
      None  → use current AGENT_RUNTIME env
      True  → project eligibility as if AGENT_RUNTIME=1
      False → project with runtime OFF (eligible set empty for dispatch)
    """
    from app.platform import agent_registry as ar
    from app.platform import agent_runtime as rt
    from app.platform.agent_runtime_workforce import (
        AMBER_HOLD_AGENTS,
        FROZEN_VOICE_AGENTS,
        GREEN_MUTATE_HOLD,
        VOICE_HOLD_AGENTS,
        ensure_workforce_registered,
    )
    from app.platform.team import STAFF

    try:
        ensure_workforce_registered()
    except Exception as e:
        logger.debug("workforce register skip: %s", e)

    runtime_env = _flag_on("AGENT_RUNTIME")
    runtime_effective = runtime_env if assume_runtime_on is None else bool(assume_runtime_on)

    reg = ar.build_registry()
    pilots = set(rt.PILOT_AGENTS)
    rows: list[dict[str, Any]] = []
    eligible: list[str] = []
    ungated_dispatchable: list[str] = []

    for aid in sorted(STAFF.keys()):
        c = reg.get(aid)
        flag = ((getattr(c, "primary_flag", None) or "") if c else "").strip()
        env_val = os.getenv(flag) if flag else None
        flag_on = _flag_on(flag) if flag else False
        dispatchable = aid in pilots
        if aid in FROZEN_VOICE_AGENTS:
            classification = "intentionally_disabled"
        elif dispatchable:
            classification = "canary_ready"
        elif aid in GREEN_MUTATE_HOLD or aid in AMBER_HOLD_AGENTS or aid in VOICE_HOLD_AGENTS:
            classification = "rollout_hold"
        else:
            classification = "rollout_hold"

        if dispatchable and not flag:
            ungated_dispatchable.append(aid)

        # Eligibility projection (policy-shaped, not a full evaluate_policy):
        # runtime ON + pilot + non-empty flag ON + not RED/hard_off.
        is_red = bool(c and (c.lane == ar.Lane.RED.value or c.default_mode == ar.HARD_OFF))
        eligible_now = bool(runtime_effective and dispatchable and flag and flag_on and not is_red)
        if eligible_now:
            eligible.append(aid)

        rows.append(
            {
                "agent_id": aid,
                "label": _role_label(aid, c) if c else aid,
                "name": getattr(c, "name", aid) if c else aid,
                "title": getattr(c, "title", "") if c else "",
                "dispatchable": dispatchable,
                "primary_flag": flag or None,
                "flag_default": False if flag else None,
                "env_value": env_val,
                "flag_effective_on": flag_on if flag else None,
                "runtime_eligible_if_projected": eligible_now,
                "lane": getattr(c, "lane", "") if c else "",
                "default_mode": getattr(c, "default_mode", "") if c else "",
                "classification": classification,
                "ungated_defect": bool(dispatchable and not flag),
            }
        )

    return {
        "ok": True,
        "canonical_count": len(STAFF),
        "boss_id": "manager",
        "boss_count": list(STAFF.keys()).count("manager"),
        "agent_runtime_env": runtime_env,
        "agent_runtime_projected": runtime_effective,
        "dispatchable_count": sum(1 for r in rows if r["dispatchable"]),
        "gated_dispatchable_count": sum(1 for r in rows if r["dispatchable"] and r["primary_flag"]),
        "ungated_dispatchable_count": len(ungated_dispatchable),
        "ungated_dispatchable": ungated_dispatchable,
        "eligible_agents_if_enabled": eligible,
        "agents": rows,
    }


def canary_isolation_preflight(
    expected_agent: str,
    *,
    assume_runtime_on: bool = True,
) -> dict[str, Any]:
    """Fail-closed single-agent canary guard. Read-only — never mutates env/flags.

    Returns allowed=True only when the projected eligible set is exactly
    ``{expected_agent}``.
    """
    aid = (expected_agent or "").strip().lower()
    census = agent_flag_census(assume_runtime_on=assume_runtime_on)
    eligible = list(census.get("eligible_agents_if_enabled") or [])
    unexpected = sorted(a for a in eligible if a != aid)
    missing = aid not in eligible
    ungated = list(census.get("ungated_dispatchable") or [])

    allowed = (
        not missing
        and not unexpected
        and not ungated
        and census.get("ungated_dispatchable_count") == 0
    )
    reason = ""
    if ungated:
        reason = "canary_agent_isolation_failed"
    elif missing and unexpected:
        reason = "canary_agent_isolation_failed"
    elif missing:
        reason = "expected_agent_not_eligible"
    elif unexpected:
        reason = "canary_agent_isolation_failed"

    return {
        "ok": True,
        "allowed": bool(allowed),
        "mode": "single_agent_canary",
        "expected_agent": aid,
        "eligible_agents": eligible,
        "unexpected_agents": unexpected,
        "reason_code": reason if not allowed else "",
        "ungated_dispatchable": ungated,
        "agent_runtime_projected": census.get("agent_runtime_projected"),
        "census_summary": {
            "canonical_count": census.get("canonical_count"),
            "dispatchable_count": census.get("dispatchable_count"),
            "gated_dispatchable_count": census.get("gated_dispatchable_count"),
            "ungated_dispatchable_count": census.get("ungated_dispatchable_count"),
        },
    }


__all__ = [
    "agent_flag_census",
    "canary_isolation_preflight",
]
