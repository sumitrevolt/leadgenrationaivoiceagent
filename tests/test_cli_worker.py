"""Smoke test for the reference headless CLI worker (app/workers/cli_worker.py).

Hermetic: points app.models.base.async_session at an in-memory SQLite DB, then runs
one bounded cycle and asserts the dev_workers row is registered + heartbeat is fresh.
Skipped (not faked) when SQLAlchemy/aiosqlite are unavailable.
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta

try:
    import sqlalchemy  # noqa: F401
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    _HAVE_SA = True
except Exception:  # pragma: no cover
    _HAVE_SA = False


@unittest.skipUnless(_HAVE_SA, "SQLAlchemy/aiosqlite unavailable")
class CliWorkerSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import app.models.base as base
        from app.models.base import Base

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._orig = base.async_session
        maker = async_sessionmaker(self.engine, expire_on_commit=False)
        base.async_session = lambda: maker  # monkeypatch the lazy factory

    async def asyncTearDown(self):
        import app.models.base as base

        base.async_session = self._orig
        await self.engine.dispose()

    async def test_one_cycle_registers_and_heartbeats(self):
        from app.models.base import async_session
        from app.models.dev_worker import snapshot
        from app.workers.cli_worker import run

        rc = await run("operations", once=True)
        self.assertEqual(rc, 0)

        maker = async_session()
        async with maker() as db:
            snap = await snapshot(db)
        self.assertTrue(snap["instrumented"])
        self.assertEqual(snap["total"], 1)
        w = snap["workers"][0]
        self.assertEqual(w["worker_id"], "cli_operations")
        self.assertEqual(w["supervisor_bot"], "operations")
        self.assertEqual(w["kind"], "cli")
        self.assertTrue(w["authoritative"])
        self.assertEqual(w["health"], "healthy")

    async def test_rejects_non_worker_supervisor(self):
        from app.workers.cli_worker import run

        with self.assertRaises(SystemExit):
            await run("board", once=True)


if __name__ == "__main__":
    unittest.main()
