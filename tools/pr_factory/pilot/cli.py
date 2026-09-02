"""CLI for the bounded PR-orchestration pilot.

Usage (all fail-closed; exit codes: 0 ok · 1 refusal/validation · 2 usage · 3 disabled):

    python -m tools.pr_factory.pilot.cli validate <manifest.json>
    python -m tools.pr_factory.pilot.cli diagnose <manifest.json> [--pr N]
    python -m tools.pr_factory.pilot.cli repair  <manifest.json> [--pr N]
    python -m tools.pr_factory.pilot.cli verify  <manifest.json> [--pr N]
    python -m tools.pr_factory.pilot.cli cleanup <manifest.json>

Repair/diagnose/verify require all three flags ON (PR_FACTORY_PILOT_ENABLED +
PR_FACTORY_ENABLED + EXTERNAL_AGENT_ORCHESTRATOR). Validate and cleanup refuse
nothing but still require the manifest to parse and the worktree to be
task-owned — they never mutate a non-task path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from tools.pr_factory import pilot as pilot_mod
from tools.pr_factory.pilot import github_ops as gh_mod
from tools.pr_factory.pilot.guard import RepairLedger
from tools.pr_factory.pilot.manifest import PilotManifestError, load_manifest
from tools.pr_factory.pilot.pilot import Pilot, PilotRefusal


def _default_repo() -> str:
    return os.getenv("PR_FACTORY_PILOT_REPO", "sumitrevolt/leadgenrationaivoiceagent")


def _repo_root() -> str:
    # The CLI is expected to run from a checkout; allow an explicit override.
    return os.getenv("PR_FACTORY_PILOT_REPO_ROOT") or str(Path.cwd())


def _emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, default=str, indent=2))
    return 0


def _refusal_payload(code: str, reason: str, detail: str = "") -> dict[str, Any]:
    return {"refused": True, "code": code, "reason": reason, "detail": detail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pr-factory-pilot", description="bounded PR orchestration pilot"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    for cmd in ("validate", "diagnose", "repair", "verify", "cleanup"):
        p = sub.add_parser(cmd)
        p.add_argument("manifest", type=str)
        p.add_argument("--pr", type=int, default=None)
        p.add_argument("--repo", type=str, default=None)

    args = parser.parse_args(argv)

    try:
        task = load_manifest(args.manifest)
    except PilotManifestError as exc:
        _emit(_refusal_payload(exc.code, str(exc), exc.detail))
        return 1

    if args.pr is not None:
        task.pr_number = int(args.pr)

    state = pilot_mod.describe_state()
    if args.cmd in ("repair", "diagnose", "verify") and not pilot_mod.pilot_enabled():
        payload = _refusal_payload(
            "flags_off",
            "pilot disabled (PR_FACTORY_PILOT_ENABLED / PR_FACTORY_ENABLED / EXTERNAL_AGENT_ORCHESTRATOR)",
            json.dumps(state),
        )
        _emit(payload)
        return 3

    if args.cmd == "validate":
        return _emit({"ok": True, "task": task.to_dict()})

    repo = args.repo or _default_repo()
    gh = gh_mod.GitHubOps(repo)
    ledger = RepairLedger()
    pilot = Pilot(
        manifest=task,
        gh=gh,
        ledger=ledger,
        repo_root=_repo_root(),
        code_runner=None,
        require_flags=False,
    )

    try:
        if args.cmd == "diagnose":
            return _emit(pilot.diagnose().to_dict())
        if args.cmd == "repair":
            if task.ci_mode == "diagnose_only":
                return _emit(_refusal_payload("diagnose_only", "manifest ci_mode forbids repair"))
            return _emit(pilot.repair().to_dict())
        if args.cmd == "verify":
            return _emit(pilot.verify().to_dict())
        if args.cmd == "cleanup":
            return _emit(pilot.cleanup())
    except (PilotRefusal, gh_mod.GitHubOpsError) as exc:
        if isinstance(exc, gh_mod.GitHubOpsError):
            return _emit(_refusal_payload("github_state_unverifiable", str(exc)))
        return _emit(exc.to_dict())

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
