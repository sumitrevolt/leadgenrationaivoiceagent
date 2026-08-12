#!/usr/bin/env python3
"""Final integration gate — wiring + prod readiness + tests + live smoke."""

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
    parser.add_argument("--skip-live", action="store_true", help="Skip live URL smoke (offline CI)")
    args = parser.parse_args()

    failures: list[str] = []

    steps: list[tuple[str, list[str]]] = [
        ("prod_check", [sys.executable, "scripts/prod_check.py"]),
        ("wiring_audit", [sys.executable, "scripts/wiring_audit.py"]),
        ("deep_wiring_audit", [sys.executable, "scripts/deep_wiring_audit.py"]),
        ("cross_path_audit", [sys.executable, "scripts/cross_path_audit.py"]),
        ("eval_guardrail", [sys.executable, "scripts/eval_guardrail.py"]),
    ]
    if not args.skip_live:
        steps.append(
            ("live_integration_smoke", [sys.executable, "scripts/live_integration_smoke.py"])
        )
    if not args.skip_prod:
        steps.append(
            (
                "production_ready",
                [sys.executable, "scripts/production_ready.py", "--skip-prod-check"],
            )
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
        print("FAIL - fix before ship:")
        for f in failures:
            print(f"  X {f}")
        return 1

    print("PASS - PRODUCTION READY (wiring + tests + live smoke).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
