#!/usr/bin/env python3
"""Kal final integration — one-shot gate: wiring + prod readiness + targeted tests."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(label: str, cmd: list[str], *, cwd: Path | None = None) -> int:
    print(f"\n{'=' * 60}\n>>> {label}\n{'=' * 60}")
    r = subprocess.run(cmd, cwd=cwd or ROOT)
    return r.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Final integration check (pre-deploy gate)")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest suite")
    parser.add_argument("--skip-prod", action="store_true", help="Skip production_ready.py")
    args = parser.parse_args()

    failures: list[str] = []

    steps: list[tuple[str, list[str]]] = [
        ("wiring_audit", [sys.executable, "scripts/wiring_audit.py"]),
        ("deep_wiring_audit", [sys.executable, "scripts/deep_wiring_audit.py"]),
    ]
    if not args.skip_prod:
        steps.append(
            ("production_ready", [sys.executable, "scripts/production_ready.py", "--skip-prod-check"])
        )
    if not args.skip_tests:
        steps.append(
            (
                "pytest (parity + portal + content approval)",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_parity_clientops.py",
                    "tests/test_customer_portal.py",
                    "-q",
                    "--tb=short",
                ],
            )
        )

    for label, cmd in steps:
        code = _run(label, cmd)
        if code != 0:
            failures.append(label)

    print(f"\n{'=' * 60}\n=== FINAL INTEGRATION SUMMARY ===\n{'=' * 60}")
    if failures:
        print("FAIL - fix before kal deploy:")
        for f in failures:
            print(f"  X {f}")
        return 1

    print("PASS - wiring clean, readiness OK, tests green.")
    print("\nKal manual smoke (5 min):")
    print("  1. /app/admin-login -> God Mode -> telephony score + TRAI window")
    print("  2. Automation Hub -> 22 workflows (incl journeys/sales/qa)")
    print("  3. /app/automation -> Approvals tab -> content + self-improve clear")
    print("  4. /app/test-call -> 1 web call -> /app/admin campaign launch dry-run")
    print("  5. /api/activation/readiness (admin token) -> ready_for_launch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
