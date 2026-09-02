"""Smoke — lead harvester live. Run: docker exec leadgen_worker python scripts/smoke_harvest.py"""

from __future__ import annotations

import asyncio
import json


def main() -> None:
    from app.platform import lead_harvester as lh

    print("SOURCES", json.dumps(lh.source_status(), ensure_ascii=False))
    res = asyncio.run(lh.run_harvest(limit=5))
    print(
        "HARVEST",
        json.dumps(
            {k: res.get(k) for k in ("ok", "niche", "city", "new_leads", "deduped", "enrich")},
            ensure_ascii=False,
        ),
    )
    for s, d in (res.get("sources") or {}).items():
        print(f"  src {s}: {json.dumps(d, ensure_ascii=False)[:140]}")
    print("RUNS", len(lh.recent_runs(5)))
    print("SMOKE_HARVEST_PASS" if res.get("ok") else "SMOKE_HARVEST_FAIL")


if __name__ == "__main__":
    main()
