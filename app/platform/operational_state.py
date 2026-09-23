"""10-state operational taxonomy (Wave 7 §3 deliverable).

Per §3 directive, every dashboard status must distinguish:

  REGISTERED, CONFIGURED, CONNECTED, RUNNING, VERIFIED_WORKING,
  DEGRADED, BLOCKED, FAILED, UNKNOWN, STALE

This module exposes:

  * ``OperationalState`` enum (the 10 states).
  * ``classify(...)`` — derives the state from raw inputs (heartbeat,
    success_count, last_success, env_flag, credential_present).
  * ``StateContract`` — per-state evidence contract (the 12 fields per §4).
  * ``evaluate_entity(...)`` — convenience helper that returns both.

Hard rule (per §3 directive):
  Missing data must NEVER default to ``healthy`` or ``running``.
  Stale heartbeat ≠ active worker.
  Empty DB ≠ zero business activity.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class OperationalState(str, Enum):
    """The 10 canonical states for any registered entity."""

    REGISTERED = "REGISTERED"  # config present, no heartbeat yet
    CONFIGURED = "CONFIGURED"  # env flag ON, code wired, no real execution
    CONNECTED = "CONNECTED"  # live process / heartbeat / lease
    RUNNING = "RUNNING"  # currently executing
    VERIFIED_WORKING = "VERIFIED_WORKING"  # has real evidence row
    DEGRADED = "DEGRADED"  # connected but sub-engines not green
    BLOCKED = "BLOCKED"  # waiting on owner/dependency
    FAILED = "FAILED"  # terminal failure, retry exhausted
    UNKNOWN = "UNKNOWN"  # cannot determine — credential absent or code inert
    STALE = "STALE"  # last heartbeat beyond freshness limit


# Default freshness limits per entity class (seconds).
DEFAULT_FRESHNESS = {
    "agent_execution": 120.0,  # 2 min
    "external_cli_run": 3600.0,  # 1 hour
    "telegram_poll": 60.0,  # 1 min
    "email_poll": 600.0,  # 10 min
    "video_render": 1800.0,  # 30 min
    "smartflo_call": 60.0,  # 1 min (during call)
    "smartflo_idle": 86400.0,  # 24h
    "ci_check": 600.0,  # 10 min
    "billing_poll": 43200.0,  # 12h
}


@dataclass
class StateContract:
    """Per-entity evidence contract (the 12 fields per §4)."""

    state: str
    entity_class: str
    source_system: str
    entity_id: str
    last_success_at: float | None
    heartbeat_at: float | None
    freshness_seconds: float
    expected_next_run_at: float | None
    input_ref: str
    output_ref: str
    downstream_result: str
    blocker: str
    customer_revenue_impact: str
    available_owner_action: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> float:
    return time.time()


def _is_stale(heartbeat_at: float | None, freshness: float) -> bool:
    """True iff a heartbeat existed AND is older than the freshness window.

    STALE means "had a heartbeat but it's old" — NEVER "no heartbeat yet".
    """
    if heartbeat_at is None:
        return False
    return (_now() - heartbeat_at) > freshness


def classify(
    *,
    entity_class: str,
    env_flag_on: bool | None = None,
    registered: bool = True,
    credential_present: bool | None = None,
    last_heartbeat_at: float | None = None,
    last_success_at: float | None = None,
    success_count: int = 0,
    is_running_now: bool = False,
    is_blocked: bool = False,
    is_failed_terminal: bool = False,
    is_degraded: bool = False,
    freshness_seconds: float | None = None,
) -> OperationalState:
    """Derive the 10-state value from raw inputs.

    Order of precedence (highest → lowest):

      1. ``is_failed_terminal``        → FAILED
      2. ``is_blocked``                → BLOCKED
      3. ``is_degraded``               → DEGRADED
      4. ``is_running_now``            → VERIFIED_WORKING if success_count > 0 else RUNNING
      5. credential_present=False      → UNKNOWN
      6. not registered                → UNKNOWN
      7. heartbeat existed but stale   → STALE
      8. success_count > 0             → VERIFIED_WORKING
      9. fresh heartbeat               → CONNECTED
     10. env flag on, no heartbeat     → CONFIGURED
     11. registered, nothing yet       → REGISTERED
     12. fallback                      → UNKNOWN (never healthy / running)
    """
    freshness = (
        freshness_seconds
        if freshness_seconds is not None
        else DEFAULT_FRESHNESS.get(entity_class, 300.0)
    )

    if is_failed_terminal:
        return OperationalState.FAILED
    if is_blocked:
        return OperationalState.BLOCKED
    if is_degraded:
        return OperationalState.DEGRADED
    if is_running_now:
        return OperationalState.VERIFIED_WORKING if success_count > 0 else OperationalState.RUNNING
    if credential_present is False:
        return OperationalState.UNKNOWN
    if not registered:
        return OperationalState.UNKNOWN
    if _is_stale(last_heartbeat_at, freshness):
        return OperationalState.STALE
    if success_count > 0 and last_success_at is not None:
        return OperationalState.VERIFIED_WORKING
    if last_heartbeat_at is not None:
        return OperationalState.CONNECTED
    if env_flag_on:
        return OperationalState.CONFIGURED
    if registered:
        return OperationalState.REGISTERED
    return OperationalState.UNKNOWN


def evaluate_entity(
    *,
    entity_id: str,
    entity_class: str,
    source_system: str,
    env_flag: str | None = None,
    input_ref: str = "",
    output_ref: str = "",
    downstream_result: str = "",
    blocker: str = "",
    customer_revenue_impact: str = "",
    available_owner_action: str = "",
    credential_present: bool | None = None,
    last_heartbeat_at: float | None = None,
    last_success_at: float | None = None,
    success_count: int = 0,
    is_running_now: bool = False,
    is_blocked: bool = False,
    is_failed_terminal: bool = False,
    is_degraded: bool = False,
    freshness_seconds: float | None = None,
    extra: dict[str, Any] | None = None,
) -> StateContract:
    """One-shot evaluator: derive state + build evidence contract."""
    env_flag_on: bool | None = None
    if env_flag:
        env_flag_on = os.getenv(env_flag, "0").strip().lower() in ("1", "true", "yes", "on")
    elif credential_present is not None:
        env_flag_on = credential_present

    state = classify(
        entity_class=entity_class,
        env_flag_on=env_flag_on,
        credential_present=credential_present,
        last_heartbeat_at=last_heartbeat_at,
        last_success_at=last_success_at,
        success_count=success_count,
        is_running_now=is_running_now,
        is_blocked=is_blocked,
        is_failed_terminal=is_failed_terminal,
        is_degraded=is_degraded,
        freshness_seconds=freshness_seconds,
    )

    return StateContract(
        state=state.value,
        entity_class=entity_class,
        source_system=source_system,
        entity_id=entity_id,
        last_success_at=last_success_at,
        heartbeat_at=last_heartbeat_at,
        freshness_seconds=freshness_seconds or DEFAULT_FRESHNESS.get(entity_class, 300.0),
        expected_next_run_at=(
            last_heartbeat_at + (freshness_seconds or DEFAULT_FRESHNESS.get(entity_class, 300.0))
            if last_heartbeat_at is not None
            else None
        ),
        input_ref=input_ref,
        output_ref=output_ref,
        downstream_result=downstream_result,
        blocker=blocker,
        customer_revenue_impact=customer_revenue_impact,
        available_owner_action=available_owner_action,
        extra=extra or {},
    )


__all__ = [
    "OperationalState",
    "StateContract",
    "DEFAULT_FRESHNESS",
    "classify",
    "evaluate_entity",
]
