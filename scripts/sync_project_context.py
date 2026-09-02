#!/usr/bin/env python3
"""sync_project_context.py — refresh the persistent, secret-safe project-context
store (app/graphify-out/project_context.json) + human snapshot CONTEXT_SNAPSHOT.md.

Idempotent: re-running with no source change writes nothing. Never ingests
secrets; never reads .env*. Degrades over missing sources.

  python scripts/sync_project_context.py --dry-run
  python scripts/sync_project_context.py
  python scripts/sync_project_context.py --changed-since HEAD~1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_context as pc  # noqa: E402


def main(argv=None) -> int:
    pc.force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="compute + report, write nothing")
    ap.add_argument(
        "--changed-since", metavar="REF", help="only refresh nodes whose source changed since REF"
    )
    ap.add_argument("--store", default=str(pc.DEFAULT_STORE))
    ap.add_argument("--snapshot", default=str(pc.DEFAULT_SNAPSHOT))
    args = ap.parse_args(argv)

    store_path = Path(args.store)
    snapshot_path = Path(args.snapshot)

    store = pc.build_store()
    if args.changed_since:
        old = pc.load_store(store_path)
        if old:
            changed = pc.changed_files(args.changed_since)
            store = pc.merge_changed(old, store, changed)
            print(f"[context] changed-since {args.changed_since}: {len(changed)} files changed")

    m = store["meta"]
    print(
        f"[context] HEAD={m['head_sha'][:8]} nodes={m['node_count']} edges={m['edge_count']} "
        f"hash={m['content_hash'][:12]}"
    )

    if args.dry_run:
        existing = pc.load_store(store_path)
        same = existing and existing.get("meta", {}).get("content_hash") == m["content_hash"]
        print(f"[context] DRY-RUN — would {'skip (unchanged)' if same else 'write'} {store_path}")
        return 0

    written = pc.write_store(store, store_path, snapshot_path)
    print(f"[context] {'WROTE' if written else 'UNCHANGED (skipped write)'}: {store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
