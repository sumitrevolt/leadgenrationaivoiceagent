#!/usr/bin/env python3
"""Enable Track B admin + safe production-readiness flags on VPS (.env).

Run ON the VPS (or via ssh root@VPS 'python3 /opt/leadgen/scripts/...').
Idempotent — skips keys already set to the target value.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ENV_PATH = os.environ.get("LEADGEN_ENV", "/opt/leadgen/.env")

# No creds required — admin UX + observability + safe automation
WANT = {
    "REVENUE_TRENDS": "1",  # B1 MRR chart + daily snapshot job
    "CLIENT_TIMELINE": "1",  # B2 per-client activity drawer
    "SYS_HEALTH_DETAIL": "1",  # B3 CPU/mem/disk/queue gauges
    "EVAL_GATE": "1",  # regression guard on self-improve
    "CUSTOMER_WEBHOOKS": "1",  # H.1 product webhooks (inert until registered)
    "AUTOMATION_HEALTH_ALERTS": "1",  # dead-man email on overdue jobs
    "PLAN_RATE_LIMIT": "1",  # Starter/Growth/Advanced rpm caps
    "INTEGRATION_ALERTS": "1",  # SMTP/Qdrant/etc silent-failure email alerts
}


def _read_env() -> str:
    if os.path.isfile(ENV_PATH):
        return open(ENV_PATH, encoding="utf-8", errors="replace").read()
    return ""


def _set_kv(text: str, key: str, val: str) -> tuple[str, bool]:
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f"{key}={val}"
    if pat.search(text):
        if f"{key}={val}" in text:
            return text, False
        return pat.sub(line, text), True
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n", True


def main() -> int:
    text = _read_env()
    changed = False
    for k, v in WANT.items():
        text, ch = _set_kv(text, k, v)
        if ch:
            print(f"SET {k}={v}")
            changed = True
        else:
            print(f"OK  {k} already {v}")

    if not changed:
        print("No .env changes needed")
        return 0

    bak = ENV_PATH + ".bak_readiness_flags"
    if os.path.isfile(ENV_PATH):
        subprocess.run(["cp", ENV_PATH, bak], check=True)
        print(f"Backup -> {bak}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    # ADR-097: never recreate with compose default :latest
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app_version_pin import resolve_app_version_pin  # noqa: E402

    pin = resolve_app_version_pin()
    recreate = (
        f"cd /opt/leadgen && APP_VERSION={pin} docker compose "
        f"-f docker-compose.vps.yml --profile celery up -d --no-deps "
        f"app worker worker-heavy worker-video scheduler"
    )
    print(f"RECREATE with APP_VERSION={pin}")
    subprocess.run(["bash", "-lc", recreate], check=True)
    print("RECREATE app + celery stack OK")
    print("Verify: curl -s http://127.0.0.1:8000/api/activation/summary | head -c 400")
    print("Verify: /health.version must equal pin (not latest)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
