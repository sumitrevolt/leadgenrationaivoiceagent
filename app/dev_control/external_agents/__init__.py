"""External Agent Orchestrator — Cursor/Claude missions under Owner OS authority.

This package EXTENDS the existing Claude-managed engineering control plane
(`app/dev_control`). It is NOT a second control plane:

  * Owner OS (`app/platform/owner_os.py`) stays the sole action authority.
  * OpenClaw (`app/integrations/openclaw`) stays the orchestration/copilot edge;
    this package only adds GREEN read-only observation commands there.
  * File-ownership locking reuses `app.dev_control.locks`.
  * Secret redaction reuses `app.integrations.openclaw.policies.redact_secrets`.

HARD GATES (never relaxed here):
  * INERT unless `EXTERNAL_AGENT_ORCHESTRATOR=1` (default OFF).
  * The orchestrator NEVER executes shell, git, deploy, calling, billing or
    customer sends. It records missions, leases, evidence and verdicts; the
    human/agent executor performs work in its own bounded session.
  * RED missions are refused at creation and can never be resurrected.
  * AMBER missions can be fully prepared but stop at `OWNER_DECISION_REQUIRED`.
  * An executor can never mark its own mission COMPLETE (review separation).
"""

from app.dev_control.external_agents.schema import (  # noqa: F401
    FAILURE_STATES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    InvalidMissionTransition,
    Mission,
    MissionState,
    MissionValidationError,
    RiskClass,
)

__all__ = [
    "FAILURE_STATES",
    "InvalidMissionTransition",
    "Mission",
    "MissionState",
    "MissionValidationError",
    "RiskClass",
    "TERMINAL_STATES",
    "VALID_TRANSITIONS",
]
