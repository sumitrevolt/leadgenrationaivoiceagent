#!/usr/bin/env python3
"""Find and clean stale UPI records blocking ready_for_first_paid_customer.

Run on VPS (inside container): docker exec leadgen_app python3 scripts/clean_stale_upi.py

This script:
1. Reads the UPI payments store (auto-resolves container vs host path)
2. Identifies records that are stale (>6h old) and in actionable status
3. Shows what would be rejected (dry-run by default)
4. With --reject flag, actually rejects the stale records

The blocker is that _upi_pending_unactioned() in activation.py marks any
actionable UPI record older than UPI_PENDING_ALERT_HOURS (default 6h) as
a BLOCKER, which prevents ready_for_first_paid_customer from flipping true.

A record is "actionable" if:
  - status == "pending" OR
  - status == "approved" AND NOT activated AND NOT auto_activated

Usage:
  python3 scripts/clean_stale_upi.py           # dry run
  python3 scripts/clean_stale_upi.py --reject   # actually reject stale records
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone


def _store_path() -> str:
    """Resolve UPI store path — same logic as upi_payments._STORE()."""
    for candidate in [
        os.environ.get("LEADGEN_RUNTIME_DATA_ROOT", "") + "/billing/upi_payments.json",
        "data/upi_payments.json",
        "/var/lib/leadgen/runtime/billing/upi_payments.json",
    ]:
        if candidate and os.path.isfile(candidate):
            return candidate
    return "data/upi_payments.json"


def _read_store(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"ERROR reading {path}: {e}")
        return []


def _write_store(path: str, rows: list[dict]) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"ERROR writing {path}: {e}")
        return False


def _parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def main() -> None:
    dry_run = "--reject" not in sys.argv
    alert_hours = float(os.environ.get("UPI_PENDING_ALERT_HOURS", "6"))

    store_path = _store_path()
    rows = _read_store(store_path)
    now = datetime.now(timezone.utc)

    print("=" * 60)
    print("UPI STALE RECORD CLEANUP")
    print("=" * 60)
    print(f"Store: {store_path}")
    print(f"Total records: {len(rows)}")
    print(f"Alert threshold: {alert_hours}h")
    print(f"Mode: {'DRY RUN (use --reject to actually reject)' if dry_run else 'LIVE REJECT'}")
    print()

    # Find actionable records
    actionable = []
    for r in rows:
        status = r.get("status", "")
        activated = r.get("activated", False)
        auto_activated = r.get("auto_activated", False)

        if status == "pending":
            actionable.append(r)
        elif status == "approved" and not activated and not auto_activated:
            actionable.append(r)

    print(f"Actionable records: {len(actionable)}")

    # Find stale ones
    stale = []
    for r in actionable:
        created_at = _parse_dt(r.get("created_at") or "")
        if created_at is None:
            # Unparseable timestamp = treat as stale (conservative)
            stale.append((r, None, None))
            continue
        age_h = (now - created_at).total_seconds() / 3600
        if age_h >= alert_hours:
            stale.append((r, created_at, age_h))

    print(f"Stale actionable records (>{alert_hours}h): {len(stale)}")
    print()

    if not stale:
        print("No stale records found. The blocker may have been resolved already.")
        print("Check: curl https://leadsgenai.in/api/activation/summary")
        return

    # Show stale records
    rejected_count = 0
    for r, created_at, age_h in stale:
        pid = r.get("id", "?")
        status = r.get("status", "?")
        client = r.get("client_id", "") or "(none)"
        plan = r.get("plan", "?")
        amount = r.get("amount", 0)
        payer = r.get("payer_contact", "?")

        age_str = f"{age_h:.1f}h" if age_h is not None else "unknown age"
        created_str = created_at.isoformat()[:19] if created_at else "unknown"

        print(f"  STALE: id={pid}")
        print(f"    status={status} client={client} plan={plan} amount={amount}")
        print(f"    payer={payer} created={created_str} age={age_str}")
        print()

        if not dry_run:
            r["status"] = "rejected"
            r["decided_at"] = now.isoformat()
            r["decided_by"] = "cleanup_script"
            r["rejection_reason"] = "stale_actionable_cleanup"
            rejected_count += 1
            print("    -> REJECTED")
        else:
            print("    -> Would reject (dry run)")

    print()

    if not dry_run and rejected_count > 0:
        if _write_store(store_path, rows):
            print(f"SUCCESS: Rejected {rejected_count} stale record(s).")
            print(f"Store updated: {store_path}")
            print()
            print("Next: Verify the blocker is cleared:")
            print("  curl https://leadsgenai.in/api/activation/summary")
            print("  Expected: ready_for_first_paid_customer=true, blocker_count=0")
        else:
            print(f"FAILED: Could not write store. {rejected_count} record(s) not persisted.")
            sys.exit(1)
    elif dry_run:
        print("DRY RUN complete. No records modified.")
        print("To actually reject: python3 scripts/clean_stale_upi.py --reject")
    else:
        print("No records were rejected.")

    print("=" * 60)


if __name__ == "__main__":
    main()
