#!/usr/bin/env python3
"""Append one IST-day paid_today snapshot. Read-only. No secrets.

Usage:
    .venv\\Scripts\\python.exe scripts\\paid_today_watch.py
    .venv\\Scripts\\python.exe scripts\\paid_today_watch.py --dry-run

Reads daily_paid_activations() inside leadgen_app over SSH. Writes one JSON
line to docs/evidence/paid_today_watch.jsonl. 0 is an honest empty day.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "evidence" / "paid_today_watch.jsonl"
SSH = r"C:\PROGRA~1\Git\usr\bin\ssh.exe"
SSH_KEY = str(Path.home() / ".ssh" / "id_rsa")
VPS = "root@72.61.245.204"
IST = timezone(timedelta(hours=5, minutes=30))

REMOTE = (
    "docker exec leadgen_app python -c "
    '"from app.billing.paid_activations import daily_paid_activations as d; '
    "r=d(); print(','.join(str(r.get(k,'')) for k in "
    "('day','paid_today','activations_today','paid_gross_today_inr')))\""
)


def fetch() -> dict:
    r = subprocess.run(
        [SSH, "-i", SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", VPS, REMOTE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if r.returncode != 0:
        raise SystemExit(f"ssh failed rc={r.returncode}: {(r.stderr or '')[:200]}")
    line = (r.stdout or "").strip().splitlines()[-1]
    day, paid, acts, gross = line.split(",")
    return {
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ist_now": datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
        "day": day,
        "paid_today": int(paid or 0),
        "activations_today": int(acts or 0),
        "paid_gross_today_inr": int(float(gross or 0)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    row = fetch()
    print(json.dumps(row, sort_keys=True))
    if args.dry_run:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
