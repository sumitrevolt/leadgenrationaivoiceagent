#!/usr/bin/env python3
"""Production readiness audit — run before launch or after .env changes.

Usage:
    python scripts/production_ready.py
    python scripts/production_ready.py --json

Exit 0 = zero BLOCKERs (marketing launch green; UPI armed = paid-customer ready).
Exit 1 = one or more BLOCKERs remain.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _run_prod_check() -> bool:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prod_check.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.returncode == 0


def _activation_snapshot() -> dict:
    from app.api import activation as ax

    items = [p() for p in ax._PROBES]
    blockers = [it for it in items if it["status"] == ax._BLOCKER]
    warns = [it for it in items if it["status"] == ax._WARN]
    wizard = None  # computed via _PHASES walk below
    next_step = None
    for phase_n, phase_name, keys in ax._PHASES:
        for key in keys:
            probe = ax._PROBE_BY_KEY.get(key)
            if not probe:
                continue
            result = probe()
            if ax._item_is_actionable(result):
                next_step = {**result, "phase": {"n": phase_n, "name": phase_name}}
                break
        if next_step:
            break

    payments_ready = _payments_ready()
    return {
        "ready_for_launch": not blockers,
        "production_ready": not blockers,
        "ready_for_first_paid_customer": not blockers and payments_ready,
        "payments_ready": payments_ready,
        "payments_deferred": not payments_ready,
        "blocker_count": len(blockers),
        "warn_count": len(warns),
        "blockers": [
            {"key": b["key"], "label": b["label"], "action": b["action"]} for b in blockers
        ],
        "warns": [{"key": w["key"], "label": w["label"], "action": w["action"]} for w in warns],
        "next_step": next_step,
    }


def _payments_ready() -> bool:
    try:
        from app.api import activation as ax

        return ax._payments_ready()
    except Exception:
        vpa = (os.environ.get("UPI_VPA") or "").strip()
        return bool(vpa and "@" in vpa)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="LeadGen AI production readiness audit")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    parser.add_argument("--skip-prod-check", action="store_true")
    args = parser.parse_args()

    prod_ok = True
    if not args.skip_prod_check:
        if not args.json:
            print("=== prod_check ===")
        prod_ok = _run_prod_check()

    snap = _activation_snapshot()
    out = {"prod_check_ok": prod_ok, **snap}

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("\n=== ACTIVATION READINESS ===")
        launch = snap["ready_for_launch"]
        paid = snap["ready_for_first_paid_customer"]
        print(f"production_ready: {'YES' if launch else 'NO'}  (marketing + ops)")
        print(f"ready_for_launch: {'YES' if launch else 'NO'}")
        if snap.get("payments_deferred"):
            print("payments: deferred (optional)")
        print(f"blockers: {snap['blocker_count']}  warns: {snap['warn_count']}")
        if snap["blockers"]:
            print("\nBLOCKERS (fix before launch):")
            for b in snap["blockers"]:
                print(f"  • {b['label']} ({b['key']})")
                if b["action"]:
                    print(f"    → {b['action']}")
        if snap["warns"]:
            print("\nWARNINGS (recommended):")
            for w in snap["warns"][:6]:
                print(f"  • {w['label']}")
                if w["action"]:
                    print(f"    → {w['action']}")
        ns = snap.get("next_step")
        if ns:
            print(f"\nNEXT STEP (Phase {ns['phase']['n']} · {ns['phase']['name']}):")
            print(f"  {ns['label']} — {ns['status']}")
            if ns.get("action"):
                print(f"  → {ns['action']}")
        elif launch:
            print("\nPRODUCTION READY — marketing + ops launch green.")
        print("\nDetail: /app/dashboards or /api/activation/readiness (admin token)")

    if not prod_ok or not snap["ready_for_launch"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
