#!/usr/bin/env python3
"""Create / list / remove isolated git worktrees for Claude Code Agent Teams.

ADR-172: teammates must not share the chronically dirty primary checkout.
Allowlisted root mirrors external_agents (EXTERNAL_AGENT_WORKTREE_ROOT) with an
optional AGENT_TEAM_WORKTREE_ROOT override.

    python3 scripts/agent_team_worktree.py create --name review-auth --base origin/main
    python3 scripts/agent_team_worktree.py list
    python3 scripts/agent_team_worktree.py remove --name review-auth

Exit codes: 0 ok · 1 usage/error · 2 refused (path/policy).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
_DEFAULT_WIN = Path(r"C:\Users\Ratanshila\Documents\_leadgen_worktrees")


def allowed_root() -> Path:
    raw = (os.getenv("AGENT_TEAM_WORKTREE_ROOT") or "").strip()
    if not raw:
        raw = (os.getenv("EXTERNAL_AGENT_WORKTREE_ROOT") or "").strip()
    if raw:
        return Path(raw).resolve()
    if os.name == "nt":
        return _DEFAULT_WIN.resolve()
    # POSIX / cloud agents: sibling of repo
    return (REPO.parent / "_leadgen_worktrees").resolve()


def _slug_ok(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug or ""))


def branch_for(slug: str) -> str:
    return f"claude/agent-team-{slug}"


def worktree_path(slug: str) -> Path:
    return (allowed_root() / f"agent-team-{slug}").resolve()


def _assert_under_root(path: Path) -> None:
    root = allowed_root()
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"REFUSED: worktree outside allowed root ({root}): {path}") from exc


def _run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=120,
        check=False,
    )


def cmd_create(args: argparse.Namespace) -> int:
    slug = (args.name or "").strip().lower()
    if not _slug_ok(slug):
        print("usage: --name must be 2–41 chars [a-z0-9-] (start alnum)", file=sys.stderr)
        return 1
    base = (args.base or "HEAD").strip() or "HEAD"
    wt = worktree_path(slug)
    branch = branch_for(slug)
    _assert_under_root(wt)
    if wt.exists():
        print(f"REFUSED: path already exists: {wt}", file=sys.stderr)
        return 2
    allowed_root().mkdir(parents=True, exist_ok=True)
    completed = _run_git(["worktree", "add", "-b", branch, str(wt), base])
    if completed.returncode != 0:
        # Branch may already exist — try attaching without -b
        completed = _run_git(["worktree", "add", str(wt), branch])
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "").strip()[:300]
            print(f"worktree_create_failed: {err}", file=sys.stderr)
            return 1
    print(f"CREATED worktree={wt} branch={branch} base={base}")
    print("Next: cd into the worktree; buzzlock claim before edit; Agent Teams teammate cwd = this path.")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    root = allowed_root()
    print(f"allowed_root={root}")
    if not root.exists():
        print("(empty — root does not exist yet)")
        return 0
    found = sorted(p for p in root.glob("agent-team-*") if p.is_dir())
    if not found:
        print("(no agent-team-* worktrees)")
        return 0
    for p in found:
        head = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=p)
        branch = head.stdout.strip() if head.returncode == 0 else "?"
        print(f"{p.name}\tbranch={branch}\tpath={p}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    slug = (args.name or "").strip().lower()
    if not _slug_ok(slug):
        print("usage: --name must match create slug", file=sys.stderr)
        return 1
    wt = worktree_path(slug)
    _assert_under_root(wt)
    if not wt.exists():
        print(f"missing: {wt}", file=sys.stderr)
        return 1
    force = ["--force"] if args.force else []
    completed = _run_git(["worktree", "remove", *force, str(wt)])
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()[:300]
        print(f"worktree_remove_failed: {err}", file=sys.stderr)
        return 1
    # Best-effort delete local branch (may be checked out elsewhere — ignore fail)
    _run_git(["branch", "-D", branch_for(slug)])
    print(f"REMOVED worktree={wt}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Add an isolated agent-team worktree")
    p_create.add_argument("--name", required=True, help="Short slug (a-z0-9-)")
    p_create.add_argument("--base", default="HEAD", help="Base ref/sha (default HEAD)")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="List agent-team-* worktrees under allowed root")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="Remove an agent-team worktree")
    p_remove.add_argument("--name", required=True)
    p_remove.add_argument("--force", action="store_true")
    p_remove.set_defaults(func=cmd_remove)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
