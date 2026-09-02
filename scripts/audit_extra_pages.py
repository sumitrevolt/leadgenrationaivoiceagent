#!/usr/bin/env python3
"""Quick audit for pages not in deep_wiring_audit PAGES list."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.deep_wiring_audit import audit_file, load_routes  # noqa: E402

EXTRA = [
    "frontend/marketing.html",
    "frontend/growth_tools.html",
    "frontend/outreach.html",
    "frontend/dialer.html",
    "frontend/ops.html",
    "frontend/journeys.html",
    "frontend/clients.html",
]


def main() -> int:
    routes = load_routes()
    total = 0
    for rel in EXTRA:
        path = ROOT / rel
        if not path.exists():
            print(f"SKIP {rel}")
            continue
        r = audit_file(path, routes)
        mh, ma, ma2 = len(r["missing_handlers"]), len(r["missing_apis"]), len(r["missing_anchors"])
        print(f"{r['file']}: missing_handlers={mh} missing_apis={ma} missing_anchors={ma2}")
        for h in r["missing_handlers"][:8]:
            print(f"  H {h}")
        for a in r["missing_apis"][:8]:
            print(f"  A {a}")
        total += mh + ma + ma2
    print(f"\nTOTAL GAPS: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
