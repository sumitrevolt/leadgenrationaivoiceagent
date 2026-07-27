"""Dual-gate flags for the unattended runner."""

from __future__ import annotations

import os

from app.dev_control.external_agents import policy as orch_policy

RUNNER_FLAG = "EXTERNAL_AGENT_RUNNER"


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def runner_enabled() -> bool:
    """Runner may execute only when BOTH orchestrator and runner flags are ON."""
    return orch_policy.orchestrator_enabled() and _truthy(RUNNER_FLAG)


def runner_flag_alone() -> bool:
    """Raw runner env (for UI). Useless without orchestrator."""
    return _truthy(RUNNER_FLAG)
