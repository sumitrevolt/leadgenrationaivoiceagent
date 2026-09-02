"""Read-only dev-task control-plane status for a tmux/ops window (Phase 4).

    python scripts/dev_control_status.py            # print snapshot (read-only)
    python scripts/dev_control_status.py --reconcile  # also reclaim dead leases

Reconcile only runs when DEV_ORCHESTRATOR=1 AND DEV_WORKER_ENABLED=1, so this
script is safe to leave in a monitoring pane on any environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

# Direct `python scripts/dev_control_status.py` run me repo-root sys.path pe nahi
# hota -> `No module named 'app'`. prod_check.py jaisa root-bootstrap (2026-07-10).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def _worker_enabled() -> bool:
    def _f(n: str) -> bool:
        return os.getenv(n, "0").strip().lower() in {"1", "true", "yes", "on"}

    return _f("DEV_ORCHESTRATOR") and _f("DEV_WORKER_ENABLED")


async def _main(do_reconcile: bool) -> int:
    from app.dev_control.reconcile import reconcile_leases, render_status_line, status_snapshot
    from app.models.base import get_async_session

    async with get_async_session() as db:
        if do_reconcile and _worker_enabled():
            print("reconcile:", json.dumps(await reconcile_leases(db)))
        elif do_reconcile:
            print("reconcile: skipped (DEV_ORCHESTRATOR/DEV_WORKER_ENABLED off)")
        snap = await status_snapshot(db)
        print(render_status_line(snap))
        print(json.dumps(snap, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main("--reconcile" in sys.argv)))
