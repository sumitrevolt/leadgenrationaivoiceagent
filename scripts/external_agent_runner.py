"""CLI entry for the local/Windows EXTERNAL_AGENT_RUNNER canary.

Usage (PowerShell)::

    set EXTERNAL_AGENT_ORCHESTRATOR=1
    set EXTERNAL_AGENT_RUNNER=1
    set EXTERNAL_MISSION_DIR=%TEMP%\\ext_missions
    .venv\\Scripts\\python.exe scripts\\external_agent_runner.py --mission-id msn_...

Never deploys. Never flips production flags.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one external-agent mission unattended")
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--timeout-s", type=int, default=900)
    args = parser.parse_args()

    os.environ.setdefault("EXTERNAL_MISSION_CAS", "filelock")
    from app.dev_control.external_agents.runner import run_mission_once

    out = run_mission_once(args.mission_id, repo_root=args.repo_root, timeout_s=args.timeout_s)
    print(json.dumps(out, indent=2, default=str)[:20000])
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
