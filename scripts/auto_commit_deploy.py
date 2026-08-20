#!/usr/bin/env python3
"""Governed software delivery autopilot — safe release helper.

Replaces the old unsafe auto-commit-deploy behavior. This is a HELPER, not an
auto-deploy: push NEVER deploys. Deployment is gated (deploy-vps.yml has
DEPLOY_ENABLED unset) and must be run explicitly through scripts/deploy_vps.sh
on the VPS with APP_VERSION=<sha> (never :latest).

Hard rules enforced here:
  * subprocess list-form only (shell=True is FORBIDDEN)
  * explicit-path staging only (git add -A is FORBIDDEN)
  * never commit directly on main (feature branch required)
  * never force push
  * git diff --check before any commit
  * verify exact head SHA before merge; verify origin/main after merge

Commands:
  status                     repo identity + branch + dirty inventory
  stage  --branch B --paths P... [--message M]
  commit --branch B --message M [--paths P...]
  push   --branch B
  pr     --branch B [--title T] [--body D]
  ci     --branch B [--timeout S]
  merge  --branch B --sha S
  deploy --sha S [--apply]

Evidence is appended to data/release_evidence.jsonl after every step.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "release_evidence.jsonl"
DEFAULT_BASE = "main"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(step: str, detail: dict[str, Any]) -> None:
    try:
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        with open(EVIDENCE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _now_iso(), "step": step, **detail}, default=str) + "\n")
    except OSError:
        pass


def run(
    argv: list[str], *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess:
    """List-form subprocess. shell=True is never used here."""
    print("[RUN] " + " ".join(argv))
    result = subprocess.run(argv, capture_output=capture, text=True)
    if capture:
        if result.stdout:
            print("[OUT] " + result.stdout.rstrip())
        if result.stderr:
            print("[ERR] " + result.stderr.rstrip())
    if check and result.returncode != 0:
        print("[FAIL] exit " + str(result.returncode) + ": " + " ".join(argv))
        sys.exit(result.returncode)
    return result


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], check=check, capture=True)


def _repo_root() -> str:
    r = git("rev-parse", "--show-toplevel")
    return r.stdout.strip()


def _current_branch() -> str:
    r = git("rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip()


def _require_not_main(branch: str) -> None:
    if branch == DEFAULT_BASE:
        print(
            "[FATAL] Committing directly on "
            + DEFAULT_BASE
            + " is forbidden. Use a feature branch."
        )
        sys.exit(1)


def cmd_status(_args) -> int:
    root = _repo_root()
    branch = _current_branch()
    head = git("rev-parse", "HEAD").stdout.strip()
    print("[INFO] repo=" + root)
    print("[INFO] branch=" + branch)
    print("[INFO] HEAD=" + head)
    print("[INFO] dirty inventory (porcelain):")
    git("status", "--porcelain=v1")
    print("[INFO] untracked:")
    git("ls-files", "--others", "--exclude-standard")
    return 0


def cmd_stage(args) -> int:
    _require_not_main(args.branch)
    if not args.paths:
        print("[FATAL] --paths required (explicit paths only; git add -A is forbidden).")
        sys.exit(1)
    if _current_branch() != args.branch:
        git("checkout", "-b", args.branch)
    print("[INFO] staging explicit paths:")
    for p in args.paths:
        print("  - " + p)
    git("add", "--", *args.paths)
    print("[INFO] staged diff (names):")
    git("diff", "--cached", "--name-status")
    print("[INFO] staged diff (stat):")
    git("diff", "--cached", "--stat")
    print("[INFO] git diff --check:")
    git("diff", "--cached", "--check")
    _log("stage", {"branch": args.branch, "paths": args.paths})
    return 0


def cmd_commit(args) -> int:
    _require_not_main(args.branch)
    if _current_branch() != args.branch:
        print("[FATAL] Not on branch " + args.branch + ". Run stage first.")
        sys.exit(1)
    staged = git("diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        print("[FATAL] Nothing staged. Use --paths to stage explicit files first.")
        sys.exit(1)
    git("diff", "--cached", "--check")
    msg = args.message or "chore: governed change by boss agent"
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    full = msg + " [governed " + ts + "]"
    git("commit", "-m", full)
    _log("commit", {"branch": args.branch, "message": full})
    return 0


def cmd_push(args) -> int:
    _require_not_main(args.branch)
    git("push", "-u", "origin", args.branch)  # never --force
    _log("push", {"branch": args.branch})
    print("[INFO] Pushed. NOTE: push does NOT deploy — deploy is gated + explicit.")
    return 0


def _gh_available() -> bool:
    r = subprocess.run(["gh", "--version"], capture_output=True, text=True)
    return r.returncode == 0


def cmd_pr(args) -> int:
    _require_not_main(args.branch)
    if not _gh_available():
        print("[FATAL] gh CLI not found — install/authenticate gh for PR automation.")
        sys.exit(1)
    title = args.title or ("governed: " + args.branch)
    body = (
        args.body
        or "Governed change via auto_commit_deploy (explicit paths, diff --check, CI-verified merge)."
    )
    run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            DEFAULT_BASE,
            "--head",
            args.branch,
            "--title",
            title,
            "--body",
            body,
        ],
        check=False,
    )
    _log("pr", {"branch": args.branch, "title": title})
    return 0


def cmd_ci(args) -> int:
    if not _gh_available():
        print("[FATAL] gh CLI not found.")
        sys.exit(1)
    timeout = max(0, int(args.timeout or 0))
    deadline = time.time() + timeout if timeout else 0
    print("[INFO] waiting for required checks on PR for " + args.branch + " ...")
    while True:
        r = run(["gh", "pr", "checks", args.branch], check=False, capture=True)
        text = r.stdout.strip()
        print(text or "(no checks reported)")
        if r.returncode == 0:
            _log("ci", {"branch": args.branch, "status": "green"})
            print("[INFO] checks green.")
            return 0
        if deadline and time.time() > deadline:
            print("[FATAL] CI wait timed out.")
            sys.exit(1)
        time.sleep(30)


def cmd_merge(args) -> int:
    if not _gh_available():
        print("[FATAL] gh CLI not found.")
        sys.exit(1)
    if not args.sha:
        print("[FATAL] --sha (exact PR head) required — never merge an unverified SHA.")
        sys.exit(1)
    r = run(
        ["gh", "pr", "view", args.branch, "--json", "headRefOid", "--jq", ".headRefOid"],
        capture=True,
        check=False,
    )
    head = r.stdout.strip()
    if head != args.sha:
        print("[FATAL] PR head " + head + " != proven SHA " + args.sha + ". Refusing to merge.")
        sys.exit(1)
    run(["gh", "pr", "merge", args.branch, "--squash", "--sha", args.sha], check=False)
    git("fetch", "origin", DEFAULT_BASE)
    merged = git("merge-base", "--is-ancestor", args.sha, "origin/" + DEFAULT_BASE)
    if merged.returncode != 0:
        print("[FATAL] SHA " + args.sha + " not found in origin/" + DEFAULT_BASE + " after merge.")
        sys.exit(1)
    _log("merge", {"branch": args.branch, "sha": args.sha, "base": DEFAULT_BASE})
    print("[INFO] Merged " + args.sha + " into " + DEFAULT_BASE + " and verified ancestry.")
    return 0


def cmd_deploy(args) -> int:
    if not args.sha:
        print("[FATAL] --sha required. Never deploy :latest.")
        sys.exit(1)
    host = os.getenv("DEPLOY_HOST", "72.61.245.204")
    key = os.getenv("DEPLOY_SSH_KEY", str(Path.home() / ".ssh" / "id_rsa"))
    cmd = [
        "ssh",
        "-i",
        key,
        "root@" + host,
        "cd /opt/leadgen && APP_VERSION=" + args.sha + " bash scripts/deploy_vps.sh",
    ]
    print("[INFO] Canonical deploy (APP_VERSION-mandatory; never :latest):")
    print("  " + " ".join(cmd))
    if not args.apply:
        print("[DRY-RUN] Use --apply to run the canonical deploy. Push does NOT deploy.")
        return 0
    run(cmd)
    _log("deploy", {"sha": args.sha, "host": host, "apply": True})
    print("[INFO] Deploy invoked. Verify /health.version == SHA before declaring success.")
    return 0


def amain() -> int:
    ap = argparse.ArgumentParser(prog="auto_commit_deploy")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    p_stage = sub.add_parser("stage")
    p_stage.add_argument("--branch", required=True)
    p_stage.add_argument("--paths", nargs="+", required=True)
    p_stage.set_defaults(fn=cmd_stage)

    p_commit = sub.add_parser("commit")
    p_commit.add_argument("--branch", required=True)
    p_commit.add_argument("--message", default="")
    p_commit.add_argument("--paths", nargs="+", default=[])
    p_commit.set_defaults(fn=cmd_commit)

    p_push = sub.add_parser("push")
    p_push.add_argument("--branch", required=True)
    p_push.set_defaults(fn=cmd_push)

    p_pr = sub.add_parser("pr")
    p_pr.add_argument("--branch", required=True)
    p_pr.add_argument("--title", default="")
    p_pr.add_argument("--body", default="")
    p_pr.set_defaults(fn=cmd_pr)

    p_ci = sub.add_parser("ci")
    p_ci.add_argument("--branch", required=True)
    p_ci.add_argument("--timeout", type=int, default=0)
    p_ci.set_defaults(fn=cmd_ci)

    p_merge = sub.add_parser("merge")
    p_merge.add_argument("--branch", required=True)
    p_merge.add_argument("--sha", required=True)
    p_merge.set_defaults(fn=cmd_merge)

    p_deploy = sub.add_parser("deploy")
    p_deploy.add_argument("--sha", required=True)
    p_deploy.add_argument("--apply", action="store_true")
    p_deploy.set_defaults(fn=cmd_deploy)

    args = ap.parse_args()
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(amain())
