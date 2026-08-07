"""Bounded PR-orchestration pilot (PR Factory Wave 2) — additive, INERT by default.

Decision (ADR-166): the external "Bernstein" orchestrator was evaluated and
rejected as a second control plane for this repository (see docs/adr/
ADR-166-pr-orchestration-pilot.md). Its proven safety rails — bounded repair
attempts, per-task opt-in, expected-head-SHA pinning, fresh-CI requirement,
transient-retry-before-code-change, audit receipt, no merge, no deploy — are
re-implemented here against the existing PR Factory substrate so they never
introduce a second mission store or a second orchestrator authority.

All behaviour is OFF unless *all* of the following env flags are truthy:
    PR_FACTORY_PILOT_ENABLED=1
    PR_FACTORY_ENABLED=1
    EXTERNAL_AGENT_ORCHESTRATOR=1
None of these may ever be ON in production (CANARY_ONLY / local/Windows).
"""

from __future__ import annotations

import os
from typing import Any

from tools.pr_factory import factory_enabled

__all__ = [
    "FLAG",
    "MAX_REPAIR_ATTEMPTS",
    "pilot_enabled",
]

FLAG = "PR_FACTORY_PILOT_ENABLED"

#: Hard ceiling for automated repair attempts per PR (Bernstein-inspired rail:
#: "MAX_ATTEMPTS_PER_PUSH" capped to avoid a retry-forever path). Never raise.
MAX_REPAIR_ATTEMPTS = 2


def pilot_enabled() -> bool:
    """Triple-gate: pilot flag AND existing factory dual-gate. Default OFF."""
    pilot = (os.getenv(FLAG) or "0").strip().lower() in ("1", "true", "yes", "on")
    return bool(pilot and factory_enabled())


def describe_state() -> dict[str, Any]:
    """Fail-closed diagnostics for operators / tests."""
    from app.dev_control.external_agents import policy

    return {
        "pilot_flag": (os.getenv(FLAG) or "0").strip().lower(),
        "pilot_enabled": pilot_enabled(),
        "factory_enabled": factory_enabled(),
        "orchestrator_enabled": policy.orchestrator_enabled(),
        "max_repair_attempts": MAX_REPAIR_ATTEMPTS,
    }
