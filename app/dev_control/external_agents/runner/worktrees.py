"""Dedicated branch/worktree allocation under an allowlisted root."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from app.dev_control.external_agents.runner.process_safe import ProcessSafetyError

_BRANCH_RE = re.compile(r"^feat/ext-[a-z0-9-]{3,48}$")


def allowed_worktree_root() -> Path:
    raw = (os.getenv("EXTERNAL_AGENT_WORKTREE_ROOT") or "").strip()
    if raw:
        return Path(raw).resolve()
    # Default: sibling of repo under _leadgen_worktrees
    return Path(r"C:\Users\Ratanshila\Documents\_leadgen_worktrees").resolve()


def ensure_mission_worktree(
    *,
    repo_root: str,
    base_sha: str,
    branch: str,
    worktree: str,
) -> dict[str, Any]:
    """Create or verify a dedicated worktree for a mission.

    Uses ``git`` via argument arrays (git is NOT an executor allowlist entry —
    worktree provisioning is a parent-process privilege, not child-executor).
    """
    if not _BRANCH_RE.match(branch or ""):
        raise ProcessSafetyError("branch_name_refused")
    root = allowed_worktree_root()
    wt = Path(worktree).resolve()
    try:
        wt.relative_to(root)
    except ValueError as exc:
        raise ProcessSafetyError("worktree_outside_allowed_root") from exc
    repo = Path(repo_root).resolve()
    if not (repo / ".git").exists():
        raise ProcessSafetyError("repo_root_invalid")

    if wt.exists() and (wt / ".git").exists():
        # Verify branch
        out = subprocess.run(
            ["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            check=False,
        )
        if out.returncode != 0 or out.stdout.strip() != branch:
            raise ProcessSafetyError("existing_worktree_branch_mismatch")
        _disable_push_remotes(wt)
        return {"ok": True, "created": False, "worktree": str(wt), "branch": branch}

    wt.parent.mkdir(parents=True, exist_ok=True)
    # Fetch not required if base_sha is local; try worktree add from repo.
    cmd = [
        "git",
        "-C",
        str(repo),
        "worktree",
        "add",
        "-b",
        branch,
        str(wt),
        base_sha or "HEAD",
    ]
    completed = subprocess.run(
        cmd, capture_output=True, text=True, shell=False, timeout=120, check=False
    )
    if completed.returncode != 0:
        # Branch may already exist — try without -b
        cmd2 = ["git", "-C", str(repo), "worktree", "add", str(wt), branch]
        completed = subprocess.run(
            cmd2, capture_output=True, text=True, shell=False, timeout=120, check=False
        )
        if completed.returncode != 0:
            raise ProcessSafetyError(f"worktree_create_failed:{completed.stderr.strip()[:200]}")
    _disable_push_remotes(wt)
    return {"ok": True, "created": True, "worktree": str(wt), "branch": branch}


def _disable_push_remotes(wt: Path) -> None:
    """Prevent push from this worktree without mutating shared remotes.

    Linked worktrees share ``remote.*`` with the primary repo. Never
    ``git remote remove`` here — that would delete origin for every worktree.
    Instead enable worktree-local config and set a disabled pushurl.
    """
    subprocess.run(
        ["git", "-C", str(wt), "config", "extensions.worktreeConfig", "true"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=15,
        check=False,
    )
    listed = subprocess.run(
        ["git", "-C", str(wt), "remote"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=30,
        check=False,
    )
    for name in (listed.stdout or "").splitlines():
        name = name.strip()
        if not name:
            continue
        subprocess.run(
            [
                "git",
                "-C",
                str(wt),
                "config",
                "--worktree",
                f"remote.{name}.pushurl",
                "disabled://no-push",
            ],
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            check=False,
        )
