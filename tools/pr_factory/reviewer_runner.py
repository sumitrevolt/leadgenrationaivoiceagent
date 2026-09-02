"""Enforce executor ≠ reviewer before invoking independent review."""

from __future__ import annotations

from typing import Any

from app.dev_control.external_agents.schema import Mission
from tools.pr_factory import claude_runner


class ReviewSeparationError(ValueError):
    """Executor attempted to review its own work."""


def assert_independent(*, executor: str, reviewer: str) -> None:
    ex = (executor or "").strip().lower()
    rev = (reviewer or "").strip().lower()
    if not ex or not rev:
        raise ReviewSeparationError("executor_or_reviewer_missing")
    if ex == rev:
        raise ReviewSeparationError("executor_equals_reviewer")


def run_independent_review(
    mission: Mission,
    *,
    result_manifest: dict[str, Any],
    diff_text: str,
    allowed_root: str,
    timeout_s: int = 600,
):
    assert_independent(executor=mission.executor, reviewer=mission.reviewer)
    # Wave 1: Claude is the canonical independent reviewer path.
    if (mission.reviewer or "").strip().lower() != "claude":
        raise ReviewSeparationError("wave1_reviewer_must_be_claude")
    return claude_runner.invoke_review(
        mission,
        result_manifest=result_manifest,
        diff_text=diff_text,
        allowed_root=allowed_root,
        timeout_s=timeout_s,
    )
