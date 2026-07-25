#!/usr/bin/env python3
"""Enable Automation-Max safe flags on VPS (.env) — draft/ops/ops-health only.

Philosophy (user mandate 2026-07-25): maximize automation so humans only approve
high-impact/external actions. This script flips SAFE engines. It never enables
ban/compliance killers.

Run ON the VPS:
  python3 /opt/leadgen/scripts/vps_enable_automation_max_flags.py
  python3 /opt/leadgen/scripts/vps_enable_automation_max_flags.py --with-email
  LEADGEN_APP_VERSION=<sha> python3 ...   # if leadgen_app is on :latest

Idempotent. Backs up .env before write. Recreates app + celery stack so env reloads.
ADR-097: recreate ALWAYS pins APP_VERSION (never compose default :latest).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from app_version_pin import resolve_app_version_pin  # noqa: E402

ENV_PATH = os.environ.get("LEADGEN_ENV", "/opt/leadgen/.env")

# SAFE — draft / schedule / ops / health. Channel auto-send still gated per-channel.
WANT_SAFE = {
    "OPS_WATCHDOG": "1",
    "CADENCE_ENGINE": "1",
    "JOURNEY_ENGINE": "1",
    "REPLY_AGENT": "1",
    "NICHE_ROTATION": "1",
    "AUTO_ONBOARD": "1",
    "SALES_ENGINE": "1",
    "GROWTH_OPTIMIZER": "1",
    "CHANNEL_EXPERIMENTS": "1",
    "SELF_IMPROVE_LOOP": "1",
    "LEAD_HARVESTER": "1",
    "DUNNING_ENGINE": "1",
    "HOT_QUEUE_BRIEF_DAILY": "1",
    "AUTOMATION_HEALTH_ALERTS": "1",
    "APPROVAL_EMAIL_NOTIFY": "1",
    "INTEGRATION_ALERTS": "1",
}

WANT_EMAIL = {
    "AUTO_EMAIL_OUTREACH": "true",
}

NEVER = frozenset(
    {
        "WHATSAPP_AUTO_SEND",
        "PLATFORM_DIAL_DAILY",
        "REPLY_AUTO_SEND",
        "SALES_AUTOPILOT_ENABLED",
        "MISSED_CALL_CALLBACK",
        "SMS_DLT_ENABLED",
        "OPENCLAW_ALLOW_RED_ACTIONS",
        "DEPLOY_ENABLED",
    }
)


def _read_env() -> str:
    if os.path.isfile(ENV_PATH):
        return open(ENV_PATH, encoding="utf-8", errors="replace").read()
    return ""


def set_kv(text: str, key: str, val: str) -> tuple[str, bool]:
    if key in NEVER:
        raise SystemExit(f"REFUSED: {key} is on the NEVER list")
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f"{key}={val}"
    if pat.search(text):
        if re.search(rf"^{re.escape(key)}={re.escape(val)}$", text, re.M):
            return text, False
        return pat.sub(line, text), True
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n", True


def main() -> int:
    ap = argparse.ArgumentParser(description="Automation-Max safe VPS flag enabler")
    ap.add_argument(
        "--with-email",
        action="store_true",
        help="Also set AUTO_EMAIL_OUTREACH=true (check deliverability first)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes; do not write .env or recreate",
    )
    args = ap.parse_args()

    want = dict(WANT_SAFE)
    if args.with_email:
        want.update(WANT_EMAIL)

    text = _read_env()
    changed = False
    for k, v in want.items():
        text, ch = set_kv(text, k, v)
        if ch:
            print(f"SET {k}={v}")
            changed = True
        else:
            print(f"OK  {k} already {v}")

    print("NEVER (left untouched): " + ", ".join(sorted(NEVER)))

    if not changed:
        print("No .env changes needed")
        return 0

    if args.dry_run:
        print("DRY-RUN — no write / no recreate")
        return 0

    bak = ENV_PATH + ".bak_automation_max"
    if os.path.isfile(ENV_PATH):
        subprocess.run(["cp", ENV_PATH, bak], check=True)
        print(f"Backup -> {bak}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    pin = resolve_app_version_pin()
    recreate = (
        f"cd /opt/leadgen && APP_VERSION={pin} docker compose "
        f"-f docker-compose.vps.yml --profile celery up -d --no-deps "
        f"app worker worker-heavy worker-video scheduler"
    )
    print(f"RECREATE with APP_VERSION={pin}")
    subprocess.run(["bash", "-lc", recreate], check=True)
    print("RECREATE app + celery stack OK")
    print("Verify: /health.version must equal pin (not latest)")
    print(
        "NEXT: clear stale canary agent pauses if ops/watchdog still blocked — "
        "docker exec -w /app leadgen_app python "
        "/opt/leadgen/scripts/vps_clear_stale_canary_pauses.py"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
