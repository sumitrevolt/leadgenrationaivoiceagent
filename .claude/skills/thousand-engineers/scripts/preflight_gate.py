"""thousand-engineers preflight gate — local verify evidence runner.

Runs the repo's cheap local gates over a changed path set and prints one
evidence line per gate. Exit code 0 = all gates green, 1 = any gate red.
This is the executable companion of the skill's "Pre-ship gate" doctrine
("Here is the proof" — kabhi "should be fine" nahi).

Usage:
    python scripts/preflight_gate.py --paths app/foo.py tests/test_foo.py
    python scripts/preflight_gate.py --pytest tests/test_foo.py -q
    python scripts/preflight_gate.py --check-only          # tool self-check
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

GATES = ("ruff", "secrets", "pytest")


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=600)
        tail = "\n".join(proc.stdout.strip().splitlines()[-6:])
        return proc.returncode, tail
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timeout after 600s"


def _python() -> str:
    if (ROOT / ".venv" / "Scripts" / "python.exe").exists():
        return str(ROOT / ".venv" / "Scripts" / "python.exe")
    return "python"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paths", nargs="*", default=[], help="paths to lint/scan")
    ap.add_argument("--pytest", nargs="*", default=[], help="pytest file(s)/args")
    ap.add_argument("--check-only", action="store_true", help="self-check, no gates")
    args = ap.parse_args()

    if args.check_only:
        print(f"preflight: tool ok (root={ROOT.name})")
        return 0

    results: list[tuple[str, int, str]] = []

    if args.paths:
        rc, out = _run([_python(), "-m", "ruff", "check", *args.paths], ROOT)
        results.append(("ruff", rc, out or ("" if rc == 0 else "ruff failed")))
        rc, out = _run([_python(), "scripts/check_secrets.py", "--paths", *args.paths], ROOT)
        results.append(("secrets", rc, out or ("" if rc == 0 else "secrets scan failed")))

    if args.pytest:
        rc, out = _run([_python(), "-m", "pytest", *args.pytest, "-q"], ROOT)
        results.append(("pytest", rc, out or ("" if rc == 0 else "pytest failed")))

    if not results:
        print("preflight: nothing to run (give --paths and/or --pytest)")
        return 2

    ok = True
    for name, rc, out in results:
        mark = "PASS" if rc == 0 else "FAIL"
        ok = ok and rc == 0
        print(f"preflight {name}: {mark}")
        for line in out.splitlines()[-3:]:
            if line.strip():
                print(f"  {line}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
