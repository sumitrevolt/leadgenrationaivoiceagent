"""Unattended Cursor/Claude runner slice (LOCAL/WINDOWS canary).

Extends the External Agent Orchestrator. Does NOT replace Owner OS, OpenClaw,
or the mission store. Defaults OFF via ``EXTERNAL_AGENT_RUNNER``.

The orchestrator records missions; this package may *invoke* allowlisted
executors (Cursor Agent CLI / Claude Code CLI) when both flags are ON in an
isolated environment. Production stays OFF until a separate owner gate.
"""

from app.dev_control.external_agents.runner.flags import runner_enabled
from app.dev_control.external_agents.runner.loop import run_mission_once, run_review_once
from app.dev_control.external_agents.runner.status import runner_status

__all__ = ["runner_enabled", "run_mission_once", "run_review_once", "runner_status"]
