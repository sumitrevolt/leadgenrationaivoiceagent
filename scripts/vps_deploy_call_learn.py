#!/usr/bin/env python3
"""VPS one-shot: env arm → deploy pull optional → 1 live call → learn loop."""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = "/opt/leadgen"
os.chdir(ROOT)


def run(cmd: str) -> int:
    print(f"$ {cmd}")
    return subprocess.call(cmd, shell=True)


def main() -> int:
    # Recording + qualify + carrier DND scrub
    run(
        "python3 scripts/env_set.py "
        "VOBIZ_CALL_RECORD=1 AUTO_QUALIFY_CALLS=1 DND_CARRIER_SCRUB=1 "
        "TELEPHONY_PROVIDER=vobiz DLT_APPROVED=1"
    )
    run("docker compose -f docker-compose.vps.yml up -d --no-deps --force-recreate app worker")
    print("sleep 22...")
    import time

    time.sleep(22)
    if run("curl -sf http://127.0.0.1:8000/health") != 0:
        print("FAIL health")
        return 1
    # 1 live customer call + learn
    rc = run(
        "docker exec leadgen_app python3 scripts/voice_learn_from_calls.py "
        "--call-limit 1 --platform --wait 180 --limit 2"
    )
    run("docker exec leadgen_app python3 -m app.agents.staff 2>/dev/null || true")
    run("docker exec leadgen_app python3 scripts/agent_tester.py 2>/dev/null | tail -20 || true")
    return rc


if __name__ == "__main__":
    sys.exit(main())
