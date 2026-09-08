#!/usr/bin/env python3
"""Enable Safe Launch canary flags on VPS (.env) — simulation / lab only.

Authorized scope (owner 2026-07-31):
  - SALES_AUTOPILOT_ENABLED=1 with DRY_RUN=1 (zero real outbound)
  - CREATIVE_OS_ENABLED=1 lab/canary generation only (no GPU/Comfy/auto-publish)
  - AGENT_RUNTIME=1 GREEN-lane pilots only
  - SELF_IMPROVE_LOOP=0 containment forced

HARD OFF (forced + NEVER-list refuse to raise):
  PLATFORM_DIAL_DAILY, WHATSAPP_AUTO_SEND, REPLY_AUTO_SEND,
  AUTO_EMAIL_OUTREACH, UPI_AUTO_ACTIVATE, SALES_AUTOPILOT live channels,
  CREATIVE GPU/Comfy, VIDEO social auto-publish, OPENCLAW_ALLOW_RED_ACTIONS

Run ON the VPS:
  python3 /opt/leadgen/scripts/vps_enable_safe_launch_canary.py
  python3 /opt/leadgen/scripts/vps_enable_safe_launch_canary.py --dry-run

Idempotent. Backs up .env. Recreate pins APP_VERSION (ADR-097, never :latest).
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

# Canary / simulation only — never live outbound.
WANT_CANARY = {
    "SALES_AUTOPILOT_ENABLED": "1",
    "SALES_AUTOPILOT_DRY_RUN": "1",
    "SALES_AUTOPILOT_CANARY_BATCH": "1",
    "SALES_AUTOPILOT_WHATSAPP_ENABLED": "0",
    "SALES_AUTOPILOT_EMAIL_ENABLED": "0",
    "CREATIVE_OS_ENABLED": "1",
    "CREATIVE_GPU_LAB_ENABLED": "0",
    "CREATIVE_COMFYUI_ENABLED": "0",
    "AGENT_RUNTIME": "1",
    "SELF_IMPROVE_LOOP": "0",
    # Core Marketing containment — keep hard-off explicit after recreate.
    "PLATFORM_DIAL_DAILY": "0",
    "WHATSAPP_AUTO_SEND": "0",
    "REPLY_AUTO_SEND": "0",
    "AUTO_EMAIL_OUTREACH": "0",
    "UPI_AUTO_ACTIVATE": "0",
    "VIDEO_SOCIAL_PUBLISH_ENABLED": "0",
    "OPENCLAW_ALLOW_RED_ACTIONS": "0",
}

# Keys this script will NEVER set to an "on" / live value.
NEVER_LIVE = frozenset(
    {
        "PLATFORM_DIAL_DAILY",
        "WHATSAPP_AUTO_SEND",
        "REPLY_AUTO_SEND",
        "AUTO_EMAIL_OUTREACH",
        "UPI_AUTO_ACTIVATE",
        "SALES_AUTOPILOT_WHATSAPP_ENABLED",
        "SALES_AUTOPILOT_EMAIL_ENABLED",
        "CREATIVE_GPU_LAB_ENABLED",
        "CREATIVE_COMFYUI_ENABLED",
        "VIDEO_SOCIAL_PUBLISH_ENABLED",
        "OPENCLAW_ALLOW_RED_ACTIONS",
        "DEPLOY_ENABLED",
        "MISSED_CALL_CALLBACK",
        "SMS_DLT_ENABLED",
    }
)

_LIVE_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _read_env() -> str:
    if os.path.isfile(ENV_PATH):
        return open(ENV_PATH, encoding="utf-8", errors="replace").read()
    return ""


def set_kv(text: str, key: str, val: str) -> tuple[str, bool]:
    """Set key=val. Refuse turning NEVER_LIVE keys to truthy/live."""
    if key in NEVER_LIVE and str(val).strip().lower() in _LIVE_TRUTHY:
        raise SystemExit(
            f"REFUSED: {key}={val} is live/outbound — not allowed by safe-launch canary"
        )
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
    ap = argparse.ArgumentParser(description="Safe Launch canary VPS flag enabler")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes; do not write .env or recreate",
    )
    ap.add_argument(
        "--no-recreate",
        action="store_true",
        help="Write .env only (operator must pin-recreate manually)",
    )
    args = ap.parse_args()

    text = _read_env()
    changed = False
    for k, v in WANT_CANARY.items():
        text, ch = set_kv(text, k, v)
        if ch:
            print(f"SET {k}={v}")
            changed = True
        else:
            print(f"OK  {k} already {v}")

    print("NEVER_LIVE (cannot arm to on via this script): " + ", ".join(sorted(NEVER_LIVE)))

    if not changed:
        print("No .env changes needed")
        return 0

    if args.dry_run:
        print("DRY-RUN — no write / no recreate")
        return 0

    bak = ENV_PATH + ".bak_safe_launch_canary"
    if os.path.isfile(ENV_PATH):
        subprocess.run(["cp", ENV_PATH, bak], check=True)
        print(f"Backup -> {bak}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    if args.no_recreate:
        print("Wrote .env; skipped recreate (--no-recreate)")
        return 0

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
    print("NOTE: recreate resets soak clock — Core Marketing live, stability soak restarts")
    print(
        "HELD: live sales send · cold email · reply-auto · WA auto · platform_dial · "
        "UPI auto-activate · creative GPU/Comfy · video social auto-publish"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
