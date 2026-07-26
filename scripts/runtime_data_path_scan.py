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
from app.platform import runtime_data_groups as _groups  # noqa: E402
from app.platform import runtime_data_ratchet as _ratchet  # noqa: E402
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
    ap.add_argument(
        "mode",
        choices=["scan", "validate", "ratchet", "groups"],
        nargs="?",
        default="scan",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    findings, summary, cov = _run_scan()
    problems = _allow.validate(findings=findings)
    verdict = _ratchet.evaluate(findings)

    if args.mode == "groups":
        # Analytical only: proposes candidates, declares nothing.
        groups = _groups.build(findings)
        rec = _groups.reconcile(findings)
        if args.json:
            print(
                json.dumps(
                    {
                        "reconciliation": rec,
                        "groups": [
                            {**g, "classifications": sorted(g["classifications"])} for g in groups
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
            )
            return 0
        print("=== declaration groups ===")
        for k in sorted(rec):
            print(f"  {k:<40} {rec[k]}")
        conf: dict[str, int] = {}
        for g in groups:
            conf[g["confidence"]] = conf.get(g["confidence"], 0) + 1
        print(f"\n  groups: {len(groups)}   confidence: {conf}")
        print("\n  top mutating groups:")
        for g in groups[:25]:
            print(
                f"  [{g['confidence']:<9}] {g['mutating_count']:>3} mut  "
                f"{g['path_root'][:32]:<32} {g['module'][:38]:<38} "
                f"{','.join(g['probable_store_ids']) or '<no candidate>'}"
            )
        return 0

    if args.json:
        # No secrets, no records, no env values — path metadata only.
        print(
            json.dumps(
                {
                    "summary": summary,
                    "coverage": cov,
                    "matrices": _scan.matrices(findings),
                    "allowlist_problems": problems,
                    "ratchet": {
                        k: (len(v) if isinstance(v, list) else v) for k, v in verdict.items()
                    },
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

    if args.mode == "ratchet":
        # Monotonic: existing frozen debt is tolerated, NEW unresolved debt and
        # classification regressions are not. Counts alone would not catch
        # "one dangerous writer added, one unrelated finding removed" — the
        # comparison is over fingerprints, so that trade shows up.
        print("\n=== debt ratchet ===")
        print(f"  baseline fingerprints : {verdict['baseline_fingerprints']}")
        print(f"  unresolved now        : {verdict['unresolved_now']}")
        print(f"  newly unresolved      : {len(verdict['new_unresolved'])}")
        print(f"  regressions           : {len(verdict['regressions'])}")
        print(f"  resolved since baseline: {len(verdict['resolved'])}")
        print(f"  removed since baseline : {len(verdict['removed'])}")
        if not verdict["ok"]:
            print("\n  RATCHET FAILED — new debt or classification regression:\n")
            for block in _ratchet.format_failures(verdict):
                print(block + "\n")
            return 1
        print("\n  RATCHET OK — no new unresolved findings, no regressions")
        return 0

    # `validate` gates on schema + allowlist coherence + baseline integrity.
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
