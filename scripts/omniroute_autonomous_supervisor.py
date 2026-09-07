"""Scheduled local supervisor for OmniRoute and desktop coordination.

Runs the truthful all-14 combo probe and the config/gateway self-healing cycle
in one bounded process.  No credentials, sends, calls, or production actions
are performed by this supervisor.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("LEADGEN_PYTHON", sys.executable)
COMBO = REPO_ROOT / "scripts" / "omniroute_combo_watchdog.py"
SELF_HEAL = REPO_ROOT / "scripts" / "omniroute_self_healing_watchdog.py"
COMBO_TIMEOUT_S = 60
COMBO_WORKERS = 1
COMBO_PROCESS_TIMEOUT_S = 600


def _run(script: Path, *args: str, timeout: int) -> int:
    result = subprocess.run(
        [PYTHON, str(script), *args],
        cwd=REPO_ROOT,
        timeout=timeout,
        check=False,
    )
    return result.returncode


def main() -> int:
    # Free-tier opencode lanes can legitimately take ~40s.  An 8s probe
    # created false failures and unnecessary remediation during that latency.
    # OmniRoute admits one heavy anonymous inference at a time; parallel
    # watchdog probes otherwise starve desktop clients and cause 503 sheds.
    combo_rc = _run(
        COMBO,
        "--quiet",
        "--timeout",
        str(COMBO_TIMEOUT_S),
        "--workers",
        str(COMBO_WORKERS),
        timeout=COMBO_PROCESS_TIMEOUT_S,
    )
    self_heal_rc = _run(SELF_HEAL, timeout=180)

    # A failed combo pass gets one post-remediation all-14 recheck.  The
    # self-heal cycle itself already retries gateway/config/canary remediation.
    if combo_rc != 0:
        combo_rc = _run(
            COMBO,
            "--quiet",
            "--timeout",
            str(COMBO_TIMEOUT_S),
            "--workers",
            str(COMBO_WORKERS),
            timeout=COMBO_PROCESS_TIMEOUT_S,
        )

    return 0 if combo_rc == 0 and self_heal_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
