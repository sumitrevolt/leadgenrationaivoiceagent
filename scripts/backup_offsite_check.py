#!/usr/bin/env python3
"""backup_offsite_check.py — offsite backup freshness SENSOR (G6 / agent-signal).

KYU: pg_backup.sh offsite copy karta (R2/B2), par "kya woh actually ho raha?"
ka koi check nahi tha. Ye script local + offsite dono ki LATEST backup ki age
dekhi — stale (> threshold) ho to ALERT (ntfy push agar configured). Kavya/
ops-watchdog isko cron/loop se call kar sakta (§4 of gap-analysis).

stdlib-only · never-raise · exit 0 (cron-spam nahi). RCLONE_REMOTE/rclone na ho
to offsite-check skip (local-only). Cron:  0 5 * * *  python3 scripts/backup_offsite_check.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

BACKUP_DIR = os.environ.get("BACKUP_DIR", "/opt/leadgen/backups")
RCLONE_REMOTE = os.environ.get("RCLONE_REMOTE", "").strip()
STALE_HOURS = float(os.environ.get("BACKUP_STALE_HOURS", "36"))
NTFY_URL = os.environ.get("NTFY_URL", "").strip()
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def _alert(msg: str) -> None:
    log("ALERT: " + msg)
    if NTFY_URL and NTFY_TOPIC:
        try:
            url = NTFY_URL.rstrip("/") + "/" + NTFY_TOPIC
            req = urllib.request.Request(
                url,
                data=msg.encode("utf-8"),
                headers={"Title": "Backup offsite check", "Priority": "high"},
            )
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as e:
            log(f"ntfy push failed: {e}")


def _latest_local_age_hours() -> float | None:
    try:
        files = [
            os.path.join(BACKUP_DIR, f)
            for f in os.listdir(BACKUP_DIR)
            if f.endswith(".gz") or f.endswith(".dump.gz")
        ]
        if not files:
            return None
        newest = max(files, key=os.path.getmtime)
        return (time.time() - os.path.getmtime(newest)) / 3600.0
    except Exception as e:
        log(f"local check error: {e}")
        return None


def _latest_offsite_age_hours() -> float | None:
    if not RCLONE_REMOTE:
        return None
    try:
        out = subprocess.run(
            ["rclone", "lsjson", RCLONE_REMOTE, "--max-depth", "1"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            log(f"rclone error: {out.stderr.strip()[:200]}")
            return None
        items = json.loads(out.stdout or "[]")
        times = []
        for it in items:
            ts = it.get("ModTime")
            if ts:
                try:
                    times.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except Exception:
                    pass
        if not times:
            return None
        newest = max(times)
        return (datetime.now(timezone.utc) - newest).total_seconds() / 3600.0
    except FileNotFoundError:
        log("rclone not installed — offsite check skipped")
        return None
    except Exception as e:
        log(f"offsite check error: {e}")
        return None


def main() -> int:
    local = _latest_local_age_hours()
    if local is None:
        _alert(f"No local backup found in {BACKUP_DIR}!")
    elif local > STALE_HOURS:
        _alert(f"Local backup STALE: {local:.1f}h old (> {STALE_HOURS}h).")
    else:
        log(f"local backup OK: {local:.1f}h old")

    if RCLONE_REMOTE:
        off = _latest_offsite_age_hours()
        if off is None:
            log(f"offsite ({RCLONE_REMOTE}) age unknown (rclone/remote issue) — verify config")
        elif off > STALE_HOURS:
            _alert(f"OFFSITE backup STALE: {off:.1f}h old on {RCLONE_REMOTE} (> {STALE_HOURS}h).")
        else:
            log(f"offsite backup OK: {off:.1f}h old on {RCLONE_REMOTE}")
    else:
        log(
            "RCLONE_REMOTE unset — offsite disabled (set it + rclone.conf to enable, see deploy/offsite/)"
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # never-raise
        log(f"fatal (ignored): {e}")
        sys.exit(0)
