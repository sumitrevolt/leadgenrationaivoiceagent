#!/usr/bin/env python3
"""One-shot VPS deploy smoke for workflow parity ship (run via SSH on VPS)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request

def main() -> int:
    steps = [
        "cd /opt/leadgen",
        "git fetch --all -q",
        "git reset --hard origin/main -q",
        "git log -1 --oneline",
        "docker compose -f docker-compose.vps.yml build app",
        "docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker scheduler",
    ]
    cmd = "set -o pipefail && " + " && ".join(steps)
    print("=== DEPLOY ===")
    r = subprocess.run(["bash", "-lc", cmd], check=False)
    if r.returncode != 0:
        print("DEPLOY FAIL", r.returncode)
        return 1
    print("=== WAIT 18s ===")
    time.sleep(18)
    ok = 0
    for i in range(2):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=15) as resp:
                body = json.loads(resp.read().decode())
                env = body.get("environment", body)
                print(f"health[{i+1}]", resp.status, env)
                if resp.status == 200 and str(env).find("production") >= 0:
                    ok += 1
        except Exception as e:
            print(f"health[{i+1}] ERR", e)
        time.sleep(3)
    print("=== CELERY QUEUE ===")
    subprocess.run(
        ["bash", "-lc", "docker exec leadgen_redis redis-cli llen celery || true"],
        check=False,
    )
    return 0 if ok >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
