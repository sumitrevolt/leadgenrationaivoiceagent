#!/usr/bin/env python3
"""One-shot VPS deploy smoke — pull, rebuild app, verify endpoints."""
import json
import subprocess
import sys
import time
import urllib.request

SSH = [
    r"C:\PROGRA~1\Git\usr\bin\ssh.exe",
    "-i",
    r"C:\Users\Ratanshila\.ssh\id_rsa",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=20",
    "root@72.61.245.204",
]
REMOTE = (
    "set -e; cd /opt/leadgen && "
    "git fetch --all -q && git reset --hard origin/main -q && "
    "docker compose -f docker-compose.vps.yml build app && "
    "docker compose -f docker-compose.vps.yml up -d --no-deps app && "
    "sleep 16 && "
    "curl -sf http://127.0.0.1:8000/health && echo && "
    "curl -sf http://127.0.0.1:8000/api/admin/revenue-analytics | head -c 200 && echo"
)


def main() -> int:
    print("=== VPS PULL + BUILD + RECREATE ===")
    r = subprocess.run(SSH + [REMOTE], capture_output=True, text=True, timeout=900)
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.returncode != 0:
        print(f"REMOTE_EXIT_{r.returncode}")
        return r.returncode

    print("=== PUBLIC HEALTH ===")
    for attempt in range(3):
        try:
            with urllib.request.urlopen("https://leadsgenai.in/health", timeout=20) as resp:
                data = json.loads(resp.read().decode())
                print(json.dumps(data, indent=2))
                env = data.get("environment") or data.get("env")
                if env == "production":
                    print("HEALTH_OK production")
                    break
        except Exception as e:
            print(f"health attempt {attempt+1} fail: {e}")
            time.sleep(8)
    else:
        print("HEALTH_WARN check manually")
        return 1

    print("=== SPOT CHECKS ===")
    for path in (
        "/app/admin",
        "/api/admin/revenue-analytics",
        "/api/customer/speed-to-lead",
    ):
        try:
            req = urllib.request.Request(f"https://leadsgenai.in{path}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"{path} -> {resp.status}")
        except urllib.error.HTTPError as e:
            print(f"{path} -> HTTP {e.code} (expected for auth routes)")
        except Exception as e:
            print(f"{path} -> ERR {e}")

    print("DEPLOY_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
