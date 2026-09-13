"""Reference headless CLI supervisor worker for the 24x7 plane.

Contract (docs/architecture/24X7_FINAL_DECISION_2026-09-12.md +
docs/architecture/24X7_ARCHITECTURE_RECORD.md section 3):

* registers itself in ``dev_workers`` with ``kind="cli"`` and its ``supervisor_bot``
* heartbeats every 60 s (lease TTL 600 s lives in ``app/dev_control/claims.py``)
* claims the highest-priority QUEUED ``DevTask`` via ``claim_next`` and reports the
  outcome with ``mark_result``
* graceful stop on --once / --cycles N (no orphan state)

SAFE BY DEFAULT: this reference worker performs **no side effects**. It claims and
releases; per-agent execution handlers are registered separately so no customer /
payment / voice action can ever run from an unaudited entrypoint. Nothing here
arms production unless it is explicitly launched.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sys
from typing import Any

from app.dev_control.claims import DEFAULT_LEASE_SECONDS, claim_next
from app.models.dev_worker import heartbeat as beat
from app.models.dev_worker import mark_result, register, snapshot

logger = logging.getLogger("app.workers.cli_worker")

# The 6 approved CLI workers (frozen decision). board / Pilot / hunter are NOT workers.
CLI_WORKERS = ("operations", "engineering", "platform", "guardian", "sales", "success")

HEARTBEAT_SECONDS = 60
VERSION = "24x7.final"
CAPABILITIES = ["devtask.claim", "dev_worker.heartbeat", "noop.executor"]


def _pid_host() -> str:
    return "%s:%s" % (socket.gethostname(), os.getpid())


def _session_factory():
    # Imported lazily so tests can monkeypatch app.models.base.async_session.
    from app.models.base import async_session

    return async_session()


def _task_id(claim: dict[str, Any]) -> str:
    return str(claim.get("id") or claim.get("task_id") or claim.get("dev_task_id") or "")


async def _cycle(db, worker_id: str) -> dict[str, Any]:
    """One claim/heartbeat/report cycle. Returns a small JSON-able result."""
    claim = await claim_next(db, worker_id, lease_seconds=DEFAULT_LEASE_SECONDS)
    if not claim:
        await beat(db, worker_id)
        await db.commit()
        return {"claimed": None}
    tid = _task_id(claim)
    await beat(db, worker_id, current_task_id=tid)
    await db.commit()
    # Reference executor: deliberately inert (no customer/payment/voice side effect).
    await mark_result(db, worker_id, success=True)
    await db.commit()
    logger.info("worker %s claimed task %s (no-op reference executor)", worker_id, tid)
    return {"claimed": tid, "ok": True}


async def run(
    supervisor_bot: str,
    *,
    worker_id: str | None = None,
    cycles: int | None = None,
    interval: int = HEARTBEAT_SECONDS,
    once: bool = False,
) -> int:
    """Run the worker loop. ``once``/``cycles`` give a bounded, testable run."""
    if supervisor_bot not in CLI_WORKERS:
        raise SystemExit("unknown supervisor_bot %r (expected one of %s)" % (supervisor_bot, CLI_WORKERS))
    session = _session_factory()
    worker_id = worker_id or ("cli_%s" % supervisor_bot)

    async with session() as db:
        await register(
            db, worker_id, kind="cli", supervisor_bot=supervisor_bot,
            capabilities=CAPABILITIES, version=VERSION, pid_host=_pid_host(),
        )
        await db.commit()
    logger.info("worker %s registered (supervisor_bot=%s, kind=cli)", worker_id, supervisor_bot)

    n = 0
    while True:
        try:
            async with session() as db:
                await _cycle(db, worker_id)
        except Exception as exc:  # noqa: BLE001 - a bad cycle must not kill the worker
            logger.warning("worker %s cycle error: %s", worker_id, exc)
            try:
                async with session() as db2:
                    await mark_result(db2, worker_id, success=False, error=str(exc)[:200])
                    await db2.commit()
            except Exception:  # noqa: BLE001
                pass
        n += 1
        if once or (cycles is not None and n >= cycles):
            break
        await asyncio.sleep(max(1, interval))

    async with session() as db:
        await beat(db, worker_id)
        await db.commit()
        snap = await snapshot(db)
    logger.info(
        "worker %s stopping after %d cycle(s); registry total=%s healthy=%s dead=%s",
        worker_id, n, snap.get("total"), snap.get("healthy"), snap.get("dead"),
    )
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="24x7 headless CLI supervisor worker")
    ap.add_argument("--supervisor", required=True, choices=CLI_WORKERS)
    ap.add_argument("--worker-id", default=None)
    ap.add_argument("--cycles", type=int, default=0, help="0 = run forever")
    ap.add_argument("--interval", type=int, default=HEARTBEAT_SECONDS)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return asyncio.run(
        run(
            args.supervisor,
            worker_id=args.worker_id,
            cycles=(1 if args.once else (args.cycles or None)),
            interval=args.interval,
            once=args.once,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
