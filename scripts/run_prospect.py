#!/usr/bin/env python3
"""run_prospect.py — manual one-shot Google-Maps prospecting + CSV export.

Container me: docker exec leadgen_app python scripts/run_prospect.py [limit_per_query]
Yeh wahi `prospector.run_prospecting` chalata jo daily 09:30 cron chalata (real
Google Maps leads: business + phone + rating + reviews). Phir list_prospects ko
data/prospect_export.csv me dump karta. Never-raise.
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from pathlib import Path

# Allow ``python scripts/run_prospect.py`` (as documented for `docker exec
# leadgen_app`) to import the `app` package regardless of the caller's CWD.
# Without this, the script fails with "No module named 'app'" when invoked
# from anywhere other than the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    try:
        from app.platform import prospector
    except Exception as e:
        print("IMPORT_ERROR:", e)
        return 0
    try:
        res = asyncio.run(prospector.run_prospecting(limit_per_query=lim))
        print("RUN_SUMMARY:", json.dumps(res, default=str)[:700])
    except Exception as e:
        print("RUN_ERROR (continuing to export existing):", e)
    try:
        rows = prospector.list_prospects(limit=200)
    except Exception as e:
        print("LIST_ERROR:", e)
        return 0
    print("TOTAL_PROSPECTS:", len(rows))
    if not rows:
        print("NO_PROSPECTS")
        return 0
    keys: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    out = "data/prospect_export.csv"
    try:
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in keys})
        print("CSV_WRITTEN:", out, "rows:", len(rows))
    except Exception as e:
        print("CSV_ERROR:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
