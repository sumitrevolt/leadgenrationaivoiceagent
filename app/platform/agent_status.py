"""Honest fleet health for the non-voice Agent-OS workforce (read-only).

WHY (2026-07-20, Agent-OS upgrade): the canonical registry (agent_registry) knows
each agent's *contract* but not whether it is actually doing useful work right now.
And the existing team feed marks an agent by process-level activity, which is the
exact anti-pattern the mandate calls out: "do not mark an agent healthy merely
because the scheduler process is alive." This module adds the missing layer — an
HONEST per-agent health that reflects useful work within the agent's allowed
window, plus enabled / gated-off / kill-switched state.

DERIVE-not-duplicate. Composes existing sources, stores nothing new:
  - contract (lane / autonomy / primary_flag / useful_work_gap_min / kill_switches
    / jobs / trigger_types)                    <- app.platform.agent_registry
  - last activity, today actions/errors, state <- app.platform.team.team_status
  - overdue / dead-man jobs                    <- app.platform.automation_health
  - enabled / disabled                         <- env flag of primary_flag
  - killed                                     <- app.platform.owner_os kill board

Two distinct health concepts (as the mandate requires):
  - ``runtime_state`` = process-level heartbeat (the team feed's live state)
  - ``health``        = useful-work heartbeat (did the agent do its expected work
                        within useful_work_gap_min, or is it a ready event-driven
                        agent) — the honest signal.

Scope: the 23 NON-VOICE agents (platform + marketing). The voice team (Swara & co.)
is intentionally EXCLUDED — voice health is managed by its own stack and this module
never imports or touches any voice/telephony runtime.

Pure READ. Never raises. No sends, no mutation.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_NON_VOICE_TEAMS = frozenset({"platform", "marketing"})
_TRUE = frozenset({"1", "true", "yes", "on"})

# Sort weight so the operator sees trouble first.
_HEALTH_ORDER = {
    "failed": 0,
    "killed": 1,
    "stale": 2,
    "idle": 3,
    "disabled": 4,
    "healthy": 5,
    "unknown": 6,
}
# The states an operator should act on (disabled/idle are intentional, not alerts).
_ATTENTION = frozenset({"failed", "killed", "stale"})


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _flag_enabled(flag: str, *, require_explicit: bool = False) -> bool:
    """Blank primary_flag: historical 'ungated/core' for non-dispatchable inventory.

    Dispatchable pilots must not use blank flags (validate_registry + evaluate_policy).
    When require_explicit=True (pilots), blank ≠ always-on — project disabled.
    """
    if not flag:
        return not require_explicit
    return os.environ.get(flag, "").strip().lower() in _TRUE


def _is_dispatchable_pilot(agent_id: str) -> bool:
    """True iff agent is in the runtime PILOT_AGENTS allowlist. Fail-open False."""
    try:
        from app.platform.agent_runtime import PILOT_AGENTS

        return bool(agent_id) and agent_id in PILOT_AGENTS
    except Exception:
        return False


def _kill_engaged(keys: tuple[str, ...]) -> str | None:
    """First engaged owner_os kill switch covering this agent, else None. Fail-open."""
    try:
        from app.platform import owner_os
    except Exception:
        return None
    for k in keys or ():
        try:
            if owner_os.kill_engaged(k):
                return k
        except Exception:
            continue
    return None


def _team_status_by_key() -> dict[str, dict[str, Any]]:
    try:
        from app.platform import team

        ts = team.team_status() or {}
        return {m.get("key"): m for m in ts.get("members", []) if m.get("key")}
    except Exception as exc:
        logger.debug("agent_status team_status skip: %s", exc)
        return {}


def _overdue_job_names() -> set[str]:
    """Names of overdue / dead-man jobs from automation_health. Defensive on shape."""
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        out: set[str] = set()
        for x in h.get("overdue") or []:
            if isinstance(x, dict):
                name = x.get("job") or x.get("name") or x.get("id")
                if name:
                    out.add(str(name))
            else:
                out.add(str(x))
        return out
    except Exception as exc:
        logger.debug("agent_status automation_health skip: %s", exc)
        return set()


def resolve_agent_health(
    contract: Any,
    member: dict[str, Any] | None,
    overdue_jobs: set[str],
    killed_key: str | None,
) -> dict[str, Any]:
    """Honest health for one agent contract + its live signals. Pure, never raises."""
    primary_flag = getattr(contract, "primary_flag", "")
    agent_id = getattr(contract, "id", "") or ""
    # Pilots: blank flag fail-closed. Core/hold inventory (e.g. Neha): blank = ungated.
    enabled = _flag_enabled(
        primary_flag,
        require_explicit=_is_dispatchable_pilot(agent_id),
    )
    last_mins = None
    today_actions = 0
    today_errors = 0
    runtime_state = "offline"
    if member:
        last_mins = member.get("last_active_mins")
        today_actions = int(member.get("today_actions") or 0)
        today_errors = int(member.get("today_errors") or 0)
        runtime_state = member.get("state") or "offline"

    jobs = set(getattr(contract, "jobs", ()) or ())
    agent_overdue = sorted(jobs & overdue_jobs)
    gap = getattr(contract, "useful_work_gap_min", None)  # None = event-driven
    event_driven = gap is None

    # Priority: kill > disabled(gated) > failing > overdue > (event idle) > periodic window
    if killed_key:
        health = "killed"
    elif not enabled:
        health = "disabled"
    elif today_actions > 0 and today_errors >= today_actions:
        health = "failed"
    elif agent_overdue:
        health = "stale"
    elif event_driven:
        # healthy-idle: an event/on-demand agent with no recent event is READY,
        # not broken. Only "idle", never "offline"/"stale".
        if today_actions > 0 or (last_mins is not None and last_mins <= 1560):
            health = "healthy"
        else:
            health = "idle"
    else:
        # periodic agent: must have done useful work inside its window
        if last_mins is not None and last_mins <= gap:
            health = "healthy"
        elif last_mins is None and today_actions == 0:
            health = "stale"
        else:
            health = "stale"

    return {
        "id": getattr(contract, "id", ""),
        "name": getattr(contract, "name", ""),
        "team": getattr(contract, "team", ""),
        "lane": getattr(contract, "lane", ""),
        "autonomy": getattr(contract, "autonomy", ""),
        "enabled": enabled,
        "primary_flag": primary_flag,
        "health": health,
        "runtime_state": runtime_state,
        "useful_work_gap_min": gap,
        "last_active_mins": last_mins,
        "today_actions": today_actions,
        "today_errors": today_errors,
        "overdue_jobs": agent_overdue,
        "killed_by": killed_key,
        "kill_switches": list(getattr(contract, "kill_switches", ()) or ()),
        "escalation": getattr(contract, "escalation", "owner"),
        "trigger_types": list(getattr(contract, "trigger_types", ()) or ()),
    }


def agent_health(agent_id: str) -> dict[str, Any] | None:
    """Honest health for a single agent id. None if unknown. Never raises."""
    try:
        from app.platform import agent_registry as ar

        c = ar.get_contract(agent_id)
        if c is None:
            return None
        members = _team_status_by_key()
        overdue = _overdue_job_names()
        return resolve_agent_health(
            c, members.get(agent_id), overdue, _kill_engaged(c.kill_switches)
        )
    except Exception as exc:
        logger.debug("agent_status agent_health(%s) err: %s", agent_id, exc)
        return None


def fleet_health(include_voice: bool = False) -> dict[str, Any]:
    """Honest health rollup for the non-voice workforce. Admin-consumable.

    include_voice=False (default) reports the 23 platform+marketing agents; voice
    is out-of-scope (managed separately). Never raises.
    """
    result: dict[str, Any] = {
        "generated_at": _iso(),
        "scope": "all" if include_voice else "non_voice",
        "total": 0,
        "counts": {},
        "needs_attention": [],
        "agents": [],
        "error": None,
    }
    try:
        from app.platform import agent_registry as ar

        reg = ar.build_registry()
    except Exception as exc:
        logger.warning("agent_status fleet_health registry err: %s", exc)
        result["error"] = str(exc)[:160]
        return result

    members = _team_status_by_key()
    overdue = _overdue_job_names()
    agents: list[dict[str, Any]] = []
    for aid, c in reg.items():
        if not include_voice and getattr(c, "team", "") not in _NON_VOICE_TEAMS:
            continue
        killed = _kill_engaged(c.kill_switches)
        agents.append(resolve_agent_health(c, members.get(aid), overdue, killed))

    counts: dict[str, int] = {}
    for a in agents:
        counts[a["health"]] = counts.get(a["health"], 0) + 1
    agents.sort(key=lambda a: (_HEALTH_ORDER.get(a["health"], 9), a["id"]))

    result["total"] = len(agents)
    result["counts"] = counts
    result["needs_attention"] = [a["id"] for a in agents if a["health"] in _ATTENTION]
    result["agents"] = agents
    return result


__all__ = ["agent_health", "fleet_health", "resolve_agent_health"]
