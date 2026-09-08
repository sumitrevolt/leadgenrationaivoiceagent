"""Thin wrap of ``external_agents.runner.worktrees`` — no new shell surface."""

from __future__ import annotations

from typing import Any

from app.dev_control.external_agents.runner import worktrees as wt


def allowed_root():
    return wt.allowed_worktree_root()


def ensure_worktree(
    *,
    repo_root: str,
    base_sha: str,
    branch: str,
    worktree: str,
) -> dict[str, Any]:
    """Delegate to the canonical worktree allocator."""
    return wt.ensure_mission_worktree(
        repo_root=repo_root,
        base_sha=base_sha,
        branch=branch,
        worktree=worktree,
    )
