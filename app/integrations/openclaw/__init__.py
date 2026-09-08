"""OpenClaw Owner Copilot — optional edge layer over Owner OS.

Hierarchy (non-negotiable):
  Admin → OpenClaw Copilot → Owner OS → Boss/Manager → 31 agents → Celery

This package must NEVER:
- bypass Owner OS authorization
- enable calling / billing / deploy / bulk outreach
- execute shell, SQL, or arbitrary Python
- become a runtime dependency of core SaaS (OPENCLAW_ENABLED=0 = full off)
"""

from __future__ import annotations

from app.integrations.openclaw.commands import execute_typed_command, list_command_catalogue
from app.integrations.openclaw.policies import openclaw_enabled, safety_lane_for

__all__ = [
    "execute_typed_command",
    "list_command_catalogue",
    "openclaw_enabled",
    "safety_lane_for",
]
