#!/usr/bin/env python3
"""Run synthetic 31/31 STAFF bus canaries and write evidence JSON.

Usage:
  .venv\\Scripts\\python.exe scripts/staff_bus_canary.py
  .venv\\Scripts\\python.exe scripts/staff_bus_canary.py --out docs/evidence/staff_bus_canary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="31/31 STAFF bus synthetic canaries")
    parser.add_argument(
        "--out",
        default="docs/evidence/staff_bus_canary_latest.json",
        help="Evidence JSON output path (repo-relative)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from app.platform.staff_bus import run_all_staff_canaries
    from app.platform.staff_bus.canary import refuse_unknown_and_replay
    from app.platform.staff_bus.manifest import validate_manifest

    neg = refuse_unknown_and_replay()
    result = run_all_staff_canaries()
    payload = {
        "manifest": validate_manifest(),
        "negative_gates": neg,
        "canary": {
            "ok": result.get("ok"),
            "run_id": result.get("run_id"),
            "tenant_id": result.get("tenant_id"),
            "go_count": result.get("go_count"),
            "total": result.get("total"),
            "elapsed_s": result.get("elapsed_s"),
            "protected_side_effects": result.get("protected_side_effects"),
            "comb_in_staff": result.get("comb_in_staff"),
            "rows": result.get("rows"),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": bool(result.get("ok") and neg.get("ok") and payload["manifest"].get("ok")),
                "go_count": result.get("go_count"),
                "total": result.get("total"),
                "out": str(out),
                "run_id": result.get("run_id"),
            },
            indent=2,
        )
    )
    return 0 if result.get("ok") and neg.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
