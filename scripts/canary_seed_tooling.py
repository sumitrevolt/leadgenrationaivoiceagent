#!/usr/bin/env python3
"""Seed canary *tooling* into an origin/main worktree without C1 deliverables.

P1 stays valid only if AGENT_TEAMS_CANARY.md and the contract test are ABSENT on
the worktree base. This copies SSOT + loader (+ optional F4 gate) from a tooling
ref (default: current PR checkout) into the worktree.

    python3 scripts/canary_seed_tooling.py --worktree /path/to/tm1-wt --from-ref HEAD

Exit 2 if deliverables already exist in the worktree (contamination) or if a
refused path would be copied.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Allowed tooling paths (relative). Never include TM1/TM2 deliverables.
ALLOW = (
    "docs/coordination/canary_frozen_paths.yml",
    "scripts/canary_frozen.py",
    "scripts/canary_f4_no_skip.py",
)
REFUSE = (
    "docs/coordination/AGENT_TEAMS_CANARY.md",
    "tests/test_agent_teams_canary_contract.py",
)


def _git_show(ref: str, rel: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{ref}:{rel}"],
        cwd=str(REPO),
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise FileNotFoundError(f"missing {ref}:{rel}")
    return completed.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", required=True, help="Absolute path to teammate worktree")
    parser.add_argument(
        "--from-ref",
        default="HEAD",
        help="Git ref that has SSOT/loader (PR tip). Default HEAD of this checkout.",
    )
    args = parser.parse_args(argv)
    wt = Path(args.worktree).resolve()
    if not (wt / ".git").exists() and not (wt / ".git").is_file():
        print(f"REFUSED: not a git worktree: {wt}", file=sys.stderr)
        return 2
    for bad in REFUSE:
        if (wt / bad).exists():
            print(f"REFUSED: deliverable already present (contaminated): {bad}", file=sys.stderr)
            return 2
    for rel in ALLOW:
        try:
            blob = _git_show(args.from_ref, rel)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        dest = wt / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        print(f"seeded {rel}")
    print(f"OK tooling seeded into {wt} from {args.from_ref} (deliverables not copied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
