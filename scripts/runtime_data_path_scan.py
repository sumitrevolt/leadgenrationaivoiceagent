#!/usr/bin/env python3
"""CLI for the mutable-path scanner.

    python scripts/runtime_data_path_scan.py scan      [--json]
    python scripts/runtime_data_path_scan.py validate  [--json]

`scan` reports what exists. `validate` is the gate: it fails when the allowlist
has drifted from the code.

Offline, deterministic, bounded, secret-safe. There is deliberately no
`--accept-current-state`, no auto-update and no bypass variable: a scanner that
can write its own exceptions is a scanner that always passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.platform import runtime_data_allowlist as _allow  # noqa: E402
from app.platform import runtime_data_scan as _scan  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _run_scan() -> tuple[list[dict], dict, dict]:
    entries = _allow.load()
    findings = _scan.scan_repo(REPO, allowlist=entries)
    return findings, _scan.summarise(findings), _allow.coverage(findings)


def _print_actionable(findings: list[dict], limit: int = 40) -> None:
    """A failure has to tell the reader what to DO, not just that it failed."""
    bad = [
        f
        for f in findings
        if f["classification"] in (_scan.UNDECLARED_MUTABLE_PATH, _scan.AMBIGUOUS_REQUIRES_REVIEW)
    ]
    for f in bad[:limit]:
        action = (
            "add an allowlist entry (store_id, owner, migration_tier, review_condition) "
            "or move the write behind app/platform/runtime_data.py"
            if f["classification"] == _scan.UNDECLARED_MUTABLE_PATH
            else "resolve the ambiguity: use an operation-time accessor, or declare the read"
        )
        print(f"  {f['file']}:{f['line']}  {f['operation']}")
        print(f"      path        : {f['path_expression'][:110]}")
        print(f"      class       : {f['classification']}")
        print(f"      required    : {action}")
    if len(bad) > limit:
        print(f"  ... and {len(bad) - limit} more (use --json for the full set)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Runtime-data mutable-path scanner")
    ap.add_argument("mode", choices=["scan", "validate"], nargs="?", default="scan")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    findings, summary, cov = _run_scan()
    problems = _allow.validate(findings=findings)

    if args.json:
        # No secrets, no records, no env values — path metadata only.
        print(
            json.dumps(
                {
                    "summary": summary,
                    "coverage": cov,
                    "allowlist_problems": problems,
                    "findings": findings,
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    else:
        print("=== runtime-data mutable-path scan ===")
        for k in sorted(summary):
            print(f"  {k:<28} {summary[k]}")
        print("\n  --- gate counters (derived) ---")
        for k in sorted(cov):
            print(f"  {k:<28} {cov[k]}")
        if problems:
            print("\n  ALLOWLIST PROBLEMS:")
            for p in problems:
                print(f"      x {p}")
        if args.mode == "validate":
            print("\n  UNDECLARED / AMBIGUOUS (actionable):")
            _print_actionable(findings)

    if args.mode == "scan":
        return 0
    # `validate` gates on allowlist COHERENCE, which is enforceable today.
    # The zero-undeclared gate is reported but not yet enforced, because the
    # declaration backlog is real and pretending otherwise would either block
    # every build or require a bypass flag. The count is printed every run so
    # it cannot quietly grow.
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
