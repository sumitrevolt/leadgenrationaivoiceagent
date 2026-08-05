"""Wrap ``runner/cursor_exec`` — no new shell surface."""

from __future__ import annotations

from typing import Any

from app.dev_control.external_agents.runner import cursor_exec
from app.dev_control.external_agents.schema import Mission


def invoke_executor(
    mission: Mission,
    packet: dict[str, Any],
    *,
    allowed_root: str,
    timeout_s: int = 900,
    heartbeat=None,
):
    return cursor_exec.invoke_cursor(
        mission,
        packet,
        allowed_root=allowed_root,
        timeout_s=timeout_s,
        heartbeat=heartbeat,
    )
