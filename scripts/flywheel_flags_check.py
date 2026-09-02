#!/usr/bin/env python3
"""Verify enterprise flywheel recommended flags + attribution wiring."""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Recommended ON for full flywheel learning loop (Celery worker required for self_improve).
RECOMMENDED_ON = [
    "GROWTH_OPTIMIZER",
    "CHANNEL_EXPERIMENTS",
    "EVAL_GATE",
    "SELF_IMPROVE_LOOP",
    "PROCESS_AUTOSTART",
    "CAMPAIGN_OPTIMIZER",
    "NICHE_ROTATION",
    "LEAD_HARVESTER",
    "AUTO_EMAIL_OUTREACH",
    "REPLY_AGENT",
]

# Optional but valuable
OPTIONAL_ON = [
    "CADENCE_ENGINE",
    "SALES_TEAM",
    "CRM_SYNC",
    "SALES_ENGINE",
]


def _on(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def main() -> int:
    print("=== Enterprise Flywheel Flag Check ===\n")
    missing = []
    for flag in RECOMMENDED_ON:
        state = "ON" if _on(flag) else "OFF"
        print(f"  [{state}] {flag}")
        if not _on(flag):
            missing.append(flag)

    print("\n--- Optional ---")
    for flag in OPTIONAL_ON:
        print(f"  [{'ON' if _on(flag) else 'OFF'}] {flag}")

    # Attribution module smoke
    try:
        from app.marketing.content_feedback import tracked_link

        url = tracked_link("https://leadsgenai.in/audit", "email_outreach", "flywheel_check")
        ok_attr = "utm_source=" in url
        print(f"\n[{'OK' if ok_attr else 'FAIL'}] content_feedback.tracked_link attribution")
    except Exception as e:
        print(f"\n[FAIL] content_feedback import: {e}")
        ok_attr = False

    # Campaign optimizer import
    try:
        from app.agents import campaign_optimizer

        st = campaign_optimizer.status()
        print(f"[OK] campaign_optimizer.status interactions={st.get('interaction_count')}")
    except Exception as e:
        print(f"[FAIL] campaign_optimizer: {e}")
        return 1

    if missing:
        print(f"\nNote: {len(missing)} recommended flag(s) OFF — set in .env to enable full loop.")
        print("  " + " ".join(missing))
    else:
        print("\nAll recommended flywheel flags ON.")

    return 0 if ok_attr else 1


if __name__ == "__main__":
    sys.exit(main())
