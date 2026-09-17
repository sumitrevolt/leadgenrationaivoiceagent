#!/usr/bin/env python
"""Hourly owner-feed digest cron entry (M4 T03).

Run by a systemd timer (NOT PM2 — ARCH §M6). It:
  1. bridges live sources into the canonical feed (owner_feed_bridge), and
  2. runs one digest pass (P0 immediate + hourly digest).

Never raises out of main(); always exits 0 so a cron/timer unit is not marked failed
for a transient probe error. egress-only — no Telegram getUpdates.
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Owner feed digest cron (hourly).")
    parser.add_argument("--dry-run", action="store_true", help="Do not send; report only.")
    parser.add_argument("--no-bridge", action="store_true", help="Skip source bridging.")
    args = parser.parse_args(argv)

    out: dict[str, object] = {}
    try:
        if not args.no_bridge:
            from app.platform.owner_feed_bridge import bridge_all

            out["bridge"] = bridge_all()
    except Exception as e:
        out["bridge_error"] = str(e)

    try:
        from app.platform.owner_feed_digest import run_digest

        out["digest"] = run_digest(dry_run=args.dry_run)
    except Exception as e:
        out["digest_error"] = str(e)

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
