"""Wrap ``runner/claude_exec`` — no new shell surface."""

from __future__ import annotations

from typing import Any

from app.dev_control.external_agents.runner import claude_exec
from app.dev_control.external_agents.schema import Mission


def auth_preflight() -> dict[str, Any]:
    return claude_exec.auth_ok()


def invoke_review(
    mission: Mission,
    *,
    result_manifest: dict[str, Any],
    diff_text: str,
    allowed_root: str,
    timeout_s: int = 600,
    heartbeat=None,
    expected_head: str | None = None,
):
    return claude_exec.invoke_claude_review(
        mission,
        result_manifest=result_manifest,
        diff_text=diff_text,
        allowed_root=allowed_root,
        timeout_s=timeout_s,
        heartbeat=heartbeat,
        expected_head=expected_head,
    )
