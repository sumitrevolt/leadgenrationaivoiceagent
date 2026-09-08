"""Task-owned worktree lifecycle for the pilot (isolated, safe cleanup).

The pilot only ever touches ONE worktree per task: the path declared in the
manifest (or the deterministic default derived from the task id). Cleanup is
refused for anything that is not (a) inside the allowed worktree root, (b) a
registered worktree of this repo, (c) on the manifest's task branch, and
(d) matching the task's declared/derived path.

A per-task repository lock is held while the worktree is provisioned and while
the repair commit + push happen, so no two pilot runs mutate the same branch.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterator

from tools.pr_factory.pilot import guard
from tools.pr_factory.pilot.manifest import PilotTask

_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9/._-]{0,127}$")


class WorktreeGuardError(guard.GuardRefusal):
    """Worktree path/branch safety violation — refuse."""


def allowed_worktree_root() -> Path:
    raw = (os.getenv("EXTERNAL_AGENT_WORKTREE_ROOT") or "").strip()
    if raw:
        return Path(raw).resolve()
    return Path(r"C:\Users\Ratanshila\Documents\_leadgen_worktrees").resolve()


def task_worktree_path(task: PilotTask) -> Path:
    """Resolve the task-owned worktree path under the allowed root."""
    root = allowed_worktree_root()
    if task.worktree_path:
        candidate = Path(task.worktree_path).resolve()
    else:
        candidate = (root / f"pilot-{task.task_id}").resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise WorktreeGuardError("worktree_outside_allowed_root", str(candidate)) from exc
    return candidate


def _check_branch_safety(branch: str) -> None:
    if not _SAFE_BRANCH_RE.match(branch or ""):
        raise WorktreeGuardError("branch_name_unsafe", repr(branch))
    if branch == "main" or branch.lower() == "main":
        raise WorktreeGuardError("direct_main_refused", branch)


def _registered_worktrees(repo_root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise WorktreeGuardError("worktree_list_failed", completed.stderr.strip()[-200:])
    paths: list[Path] = []
    current: str | None = None
    for line in completed.stdout.splitlines():
        if line.startswith("worktree "):
            current = line[len("worktree ") :].strip()
        elif line.startswith("branch ") and current:
            paths.append(Path(current).resolve())
            current = None
    return paths


def _worktree_branch(repo_root: Path, worktree: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise WorktreeGuardError("worktree_branch_unreadable", str(worktree))
    return completed.stdout.strip()


def ensure_task_worktree(repo_root: str, task: PilotTask) -> dict[str, Any]:
    """Provision (or reuse) the task-owned worktree on the task branch."""
    _check_branch_safety(task.task_branch)
    repo = Path(repo_root).resolve()
    if not (repo / ".git").exists():
        raise WorktreeGuardError("repo_root_invalid", str(repo))
    wt = task_worktree_path(task)

    if wt.exists() and (wt / ".git").exists():
        branch = _worktree_branch(repo, wt)
        if branch != task.task_branch:
            raise WorktreeGuardError(
                "existing_worktree_branch_mismatch",
                f"{wt} is on {branch}, expected {task.task_branch}",
            )
        return {"ok": True, "created": False, "worktree": str(wt), "branch": task.task_branch}

    wt.parent.mkdir(parents=True, exist_ok=True)
    base_sha = task.expected_head_sha if task.expected_head_sha not in {"", "PENDING"} else None
    cmd = [
        "git",
        "-C",
        str(repo),
        "worktree",
        "add",
        "-b",
        task.task_branch,
        str(wt),
        base_sha or "HEAD",
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        cmd2 = ["git", "-C", str(repo), "worktree", "add", str(wt), task.task_branch]
        completed = subprocess.run(
            cmd2,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            raise WorktreeGuardError("worktree_create_failed", completed.stderr.strip()[-200:])
    return {"ok": True, "created": True, "worktree": str(wt), "branch": task.task_branch}


def push_task_branch(repo_root: str, task: PilotTask, *, remote: str = "origin") -> str:
    """Push only ``HEAD:<task_branch>`` from the task-owned worktree.

    Returns the remote branch SHA after the push (refreshed via rev-parse).
    """
    _check_branch_safety(task.task_branch)
    wt = task_worktree_path(task)
    if not (wt / ".git").exists():
        raise WorktreeGuardError("worktree_missing_for_push", str(wt))

    completed = subprocess.run(
        ["git", "-C", str(wt), "push", remote, f"HEAD:{task.task_branch}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise WorktreeGuardError("push_failed", completed.stderr.strip()[-300:])
    out = subprocess.run(
        ["git", "-C", str(wt), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if out.returncode != 0:
        raise WorktreeGuardError("local_sha_unreadable", out.stderr.strip()[-200:])
    return out.stdout.strip()


def remove_task_worktree(repo_root: str, task: PilotTask) -> dict[str, Any]:
    """Remove ONLY the task-owned worktree. Everything else is refused.

    Guards: path inside allowed root · registered worktree of this repo ·
    current branch == task branch · clean working tree (dirty = refuse,
    never force-remove). A manifest that points at a path this repo does not
    own (or that does not exist as a registered worktree) is refused as a
    path mismatch — never silently accepted.
    """
    repo = Path(repo_root).resolve()
    wt = task_worktree_path(task)
    registered = _registered_worktrees(repo)

    if wt not in registered:
        raise WorktreeGuardError(
            "cleanup_path_mismatch", f"{wt} is not a registered worktree of this repo"
        )
    if _worktree_branch(repo, wt) != task.task_branch:
        raise WorktreeGuardError("cleanup_branch_mismatch", str(wt))

    status = subprocess.run(
        ["git", "-C", str(wt), "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    if status.returncode == 0 and status.stdout.strip():
        raise WorktreeGuardError(
            "cleanup_worktree_dirty", "commit or stash before cleanup (force-remove refused)"
        )

    completed = subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", str(wt)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise WorktreeGuardError("cleanup_failed", completed.stderr.strip()[-200:])
    return {"ok": True, "removed": True, "worktree": str(wt)}


@contextlib.contextmanager
def repository_lock(
    repo_root: str, task: PilotTask, state_dir: str | Path | None = None
) -> Iterator[None]:
    """Per-task lock held across worktree mutation + push (no network inside)."""
    base = Path(state_dir or os.getenv("PR_FACTORY_PILOT_STATE_DIR") or ".git/leadgen-pr-pilot")
    lock_root = Path(base) if Path(base).is_absolute() else Path(repo_root) / base
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{task.task_id}.lock"

    handle = None
    try:
        try:
            handle = open(lock_path, "x", encoding="utf-8")
        except FileExistsError:
            raise WorktreeGuardError(
                "repository_locked", f"task {task.task_id} already in progress"
            )
        handle.write(f"pid={os.getpid()} task={task.task_id} branch={task.task_branch}\n")
        handle.flush()
        yield
    finally:
        if handle is not None:
            handle.close()
            with contextlib.suppress(OSError):
                lock_path.unlink()
