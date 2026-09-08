#!/usr/bin/env python3
"""Clear stale Owner-OS agent scheduled_pause left by canary scripts.

Symptom (2026-07-25): OPS_WATCHDOG=1 / flags ON, but Celery beat still logged
  apply_async blocked job=watchdog reason=agent_scheduled_pause
because Kavya was left on scheduled_pause by prod-kavya-canary ("clear sticky").

This script resumes agents whose control row matches the canary sticky pattern.
It never touches dial / WA auto-send / sales-autopilot flags.

Run ON the VPS (inside app container or host with PYTHONPATH=/opt/leadgen):
  docker exec -w /app leadgen_app python /opt/leadgen/scripts/vps_clear_stale_canary_pauses.py
  docker exec -w /app leadgen_app python /opt/leadgen/scripts/vps_clear_stale_canary_pauses.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys

# Canary sticky pattern observed 2026-07-22 (ADR wave): reason exact + by suffix.
STICKY_REASON = "clear sticky"
CANARY_BY_SUFFIX = "-canary"


def _is_stale_canary(rec: dict) -> bool:
    if not rec.get("scheduled_pause"):
        return False
    if (rec.get("reason") or "").strip().lower() != STICKY_REASON:
        return False
    by = (rec.get("by") or rec.get("changed_by") or "").strip().lower()
    return by.endswith(CANARY_BY_SUFFIX)


def main() -> int:
    ap = argparse.ArgumentParser(description="Resume agents stuck on canary scheduled_pause")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from sqlalchemy import text

    from app.models.base import get_db_session
    from app.platform import owner_agent_execution as oae
    from app.platform import owner_os

    rows = []
    with get_db_session() as db:
        rows = [
            dict(r)
            for r in db.execute(
                text(
                    "SELECT agent_id, scheduled_pause, reason, changed_by, changed_at "
                    "FROM owner_agent_controls WHERE scheduled_pause IS TRUE"
                )
            )
            .mappings()
            .all()
        ]

    targets = [r for r in rows if _is_stale_canary(r)]
    print(f"scheduled_pause rows={len(rows)} stale_canary={len(targets)}")
    if not targets:
        print("OK — nothing to clear")
        return 0

    for r in targets:
        aid = str(r["agent_id"])
        jobs = sorted(oae.jobs_for_agent(aid))
        print(f"TARGET {aid} by={r.get('changed_by')} jobs={jobs}")
        if args.dry_run:
            continue
        out = oae.resume(
            aid,
            by="automation-max-fix",
            reason=f"clear stale canary pause ({r.get('changed_by')})",
        )
        print("  resumed", json.dumps(out.get("control", {}).get("effective_scope"), default=str))
        for job in jobs:
            allowed, reason = owner_os.scheduler_dispatch_allowed(job=job)
            print(f"  dispatch {job} allowed={allowed} reason={reason or '-'}")

    if args.dry_run:
        print("DRY-RUN — no writes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
