#!/usr/bin/env python3
"""Re-seed client KB with contextual ingest ON (activation for USE_CONTEXTUAL_INGEST).

Reads clients with `website` and re-runs onboarding KB website seed (best-effort).
Run on VPS after flags ON:

  docker exec leadgen_app python scripts/kb_contextual_reingest.py

Dry-run: --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("USE_CONTEXTUAL_INGEST", "1")


async def _run(limit: int, dry_run: bool) -> int:
    from app.marketing import clients_store, onboarding

    clients = clients_store.list_clients() or []
    done = 0
    for c in clients[: max(1, limit)]:
        cid = c.get("id") or c.get("client_id")
        web = (c.get("website") or "").strip()
        if not cid or not web:
            continue
        if dry_run:
            print(f"would_reingest client={cid} web={web[:50]}")
            done += 1
            continue
        try:
            out = await onboarding._seed_kb_from_website(str(cid), web)
            print(f"ok client={cid} kb_chunks={out.get('kb_chunks', 0)}")
            done += 1
        except Exception as e:
            print(f"skip client={cid} err={e}")
    print(f"total={done}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    return asyncio.run(_run(args.limit, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
