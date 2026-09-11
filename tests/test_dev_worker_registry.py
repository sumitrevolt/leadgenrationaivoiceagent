"""Tests for the 24x7 worker identity registry (dev_workers).

Split into three layers on purpose, because this repo's ``.venv`` is frequently
missing (see COORDINATION_BROADCAST.md §5):

1. ``WorkerHealthMathTests`` — pure liveness math, **stdlib only**, always runs.
2. ``SchemaShapeTests`` — AST-level contract on ``app/models/dev_worker.py`` and
   ``alembic/versions/027_add_dev_workers.py``, **stdlib only**, always runs.
   Proves the ORM columns and the migration agree without importing SQLAlchemy.
3. ``RegistryDbTests`` — real async round-trip on SQLite; **skipped** when
   SQLAlchemy/aiosqlite are unavailable rather than faking a pass.

Run:  python -m unittest tests.test_dev_worker_registry
"""

from __future__ import annotations

import ast
import os
import unittest
from datetime import datetime, timedelta

from app.platform.worker_health import (
    DEAD_AFTER_SECONDS,
    DEGRADE_AFTER_SECONDS,
    HEALTH_DEAD,
    HEALTH_DEGRADED,
    HEALTH_HEALTHY,
    HEALTH_UNKNOWN,
    KIND_CLI,
    KIND_DESKTOP,
    classify_health,
    decode_capabilities,
    encode_capabilities,
    is_authoritative,
    is_stale,
    normalise_kind,
    worker_to_dict,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(REPO_ROOT, "app", "models", "dev_worker.py")
MIGRATION_PATH = os.path.join(
    REPO_ROOT, "alembic", "versions", "027_add_dev_workers.py"
)

NOW = datetime(2026, 9, 10, 12, 0, 0)


def _ago(seconds: float) -> datetime:
    return NOW - timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# 1. Pure liveness math
# ---------------------------------------------------------------------------


class WorkerHealthMathTests(unittest.TestCase):
    def test_fresh_beat_is_healthy(self):
        self.assertEqual(classify_health(_ago(0), NOW), HEALTH_HEALTHY)
        self.assertEqual(classify_health(_ago(59), NOW), HEALTH_HEALTHY)

    def test_one_and_two_missed_beats_still_healthy(self):
        # heartbeat every 60s; degrade starts at 180s (3 missed beats).
        self.assertEqual(classify_health(_ago(120), NOW), HEALTH_HEALTHY)
        self.assertEqual(classify_health(_ago(179), NOW), HEALTH_HEALTHY)

    def test_degrades_at_three_missed_beats(self):
        self.assertEqual(classify_health(_ago(180), NOW), HEALTH_DEGRADED)
        self.assertEqual(classify_health(_ago(420), NOW), HEALTH_DEGRADED)

    def test_dead_at_lease_expiry(self):
        self.assertEqual(classify_health(_ago(600), NOW), HEALTH_DEAD)
        self.assertEqual(classify_health(_ago(86400), NOW), HEALTH_DEAD)

    def test_boundaries_match_declared_constants(self):
        self.assertEqual(DEGRADE_AFTER_SECONDS, 180)
        self.assertEqual(DEAD_AFTER_SECONDS, 600)
        self.assertEqual(
            classify_health(_ago(DEGRADE_AFTER_SECONDS - 1), NOW), HEALTH_HEALTHY
        )
        self.assertEqual(classify_health(_ago(DEAD_AFTER_SECONDS - 1), NOW), HEALTH_DEGRADED)

    def test_registered_but_never_beat_is_unknown_not_dead(self):
        """A just-registered worker must NOT be reported dead — false alarm."""
        self.assertEqual(classify_health(None, NOW), HEALTH_UNKNOWN)
        self.assertFalse(is_stale(None, NOW))

    def test_clock_skew_treated_as_alive(self):
        """A beat stamped in the future is proof of life, just skewed."""
        future = NOW + timedelta(seconds=30)
        self.assertEqual(classify_health(future, NOW), HEALTH_HEALTHY)

    def test_is_stale_mirrors_dead(self):
        self.assertTrue(is_stale(_ago(601), NOW))
        self.assertFalse(is_stale(_ago(599), NOW))

    def test_is_stale_accepts_custom_window(self):
        self.assertTrue(is_stale(_ago(31), NOW, dead_after=30))
        self.assertFalse(is_stale(_ago(29), NOW, dead_after=30))

    def test_desktop_rows_are_never_authoritative(self):
        self.assertTrue(is_authoritative("cli"))
        self.assertTrue(is_authoritative("api"))
        self.assertFalse(is_authoritative(KIND_DESKTOP))
        # Unknown kind must fail closed to the authoritative default, not to desktop.
        self.assertTrue(is_authoritative("nonsense"))
        self.assertTrue(is_authoritative(None))

    def test_normalise_kind_clamps_garbage(self):
        self.assertEqual(normalise_kind("desktop"), KIND_DESKTOP)
        self.assertEqual(normalise_kind("bogus"), KIND_CLI)
        self.assertEqual(normalise_kind(None), KIND_CLI)

    def test_capabilities_roundtrip(self):
        encoded = encode_capabilities(["python", "sql", "python"])
        self.assertEqual(decode_capabilities(encoded), ["python", "sql"])

    def test_capabilities_none_stays_none(self):
        self.assertIsNone(encode_capabilities(None))
        self.assertEqual(decode_capabilities(None), [])

    def test_corrupt_capabilities_degrade_to_empty(self):
        self.assertEqual(decode_capabilities("{not json"), [])

    def test_worker_to_dict_is_secret_free_by_shape(self):
        row = worker_to_dict(
            {
                "worker_id": "wkr_1",
                "kind": "cli",
                "heartbeat_ts": _ago(5),
                "health": "healthy",
                "queue_depth": None,
            },
            now=NOW,
        )
        banned = ("token", "secret", "password", "api_key", "apikey", "credential")
        for key in row:
            self.assertNotIn(key.lower(), banned)
        self.assertEqual(row["worker_id"], "wkr_1")
        self.assertEqual(row["health"], HEALTH_HEALTHY)
        self.assertEqual(row["queue_depth"], 0)
        self.assertTrue(row["authoritative"])

    def test_worker_to_dict_recomputes_health_not_trusting_stored_value(self):
        stale = worker_to_dict(
            {"worker_id": "wkr_2", "kind": "cli", "heartbeat_ts": _ago(900), "health": "healthy"},
            now=NOW,
        )
        self.assertEqual(stale["stored_health"], "healthy")  # what the row claims
        self.assertEqual(stale["health"], HEALTH_DEAD)  # what the math says


# ---------------------------------------------------------------------------
# 2. Schema shape — ORM model vs migration must agree, proven via AST
# ---------------------------------------------------------------------------


def _load_module_ast(path: str) -> ast.Module:
    with open(path, "r", encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


class SchemaShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_tree = _load_module_ast(MODEL_PATH)
        cls.migration_tree = _load_module_ast(MIGRATION_PATH)

    def _model_columns(self) -> set[str]:
        cols: set[str] = set()
        for node in ast.walk(self.model_tree):
            if isinstance(node, ast.ClassDef) and node.name == "DevWorker":
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                        func = stmt.value.func
                        if getattr(func, "id", None) == "Column":
                            cols.add(stmt.targets[0].id)
        return cols

    def _migration_columns(self) -> set[str]:
        cols: set[str] = set()
        for node in ast.walk(self.migration_tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "Column"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                cols.add(str(node.args[0].value))
        return cols

    def test_model_tablename(self):
        names = [
            n.value.value
            for n in ast.walk(self.model_tree)
            if isinstance(n, ast.Assign)
            and getattr(n.targets[0], "id", None) == "__tablename__"
            and isinstance(n.value, ast.Constant)
        ]
        self.assertEqual(names, ["dev_workers"])

    def test_model_has_contract_columns(self):
        required = {
            "worker_id", "kind", "supervisor_bot", "capabilities", "version",
            "started_at", "heartbeat_ts", "lease_id", "current_task_id",
            "queue_depth", "success_count", "failure_count", "combo_id",
            "health", "pid_host",
        }
        self.assertEqual(required - self._model_columns(), set())

    def test_migration_and_model_columns_agree(self):
        """Prevents the classic drift: model adds a column, migration forgets it."""
        self.assertEqual(
            self._migration_columns() - self._model_columns(), set(),
            "migration has columns the ORM model does not define",
        )
        self.assertEqual(
            self._model_columns() - self._migration_columns(), set(),
            "ORM model has columns the migration never creates",
        )

    def test_migration_chains_onto_026(self):
        values = {}
        for node in ast.walk(self.migration_tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                values[getattr(node.targets[0], "id", "")] = node.value.value
        self.assertEqual(values.get("revision"), "027_add_dev_workers")
        self.assertEqual(values.get("down_revision"), "026_add_dev_task_events")

    def test_migration_has_downgrade(self):
        funcs = {
            n.name for n in self.migration_tree.body if isinstance(n, ast.FunctionDef)
        }
        self.assertIn("upgrade", funcs)
        self.assertIn("downgrade", funcs)

    def test_model_has_no_secret_column(self):
        banned_substrings = ("token", "secret", "password", "api_key", "credential")
        for col in self._model_columns():
            for bad in banned_substrings:
                self.assertNotIn(bad, col.lower(), f"column {col} looks like a secret")


# ---------------------------------------------------------------------------
# 3. Real DB round-trip (skipped, not faked, when deps are absent)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - depends on environment
    import sqlalchemy as _sa  # noqa: F401
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: F401

    _HAVE_SQLALCHEMY = True
except Exception:  # pragma: no cover
    _HAVE_SQLALCHEMY = False


@unittest.skipUnless(_HAVE_SQLALCHEMY, "SQLAlchemy/aiosqlite unavailable (no .venv)")
class RegistryDbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.models.base import Base
        from app.models.dev_worker import DevWorker

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        self.DevWorker = DevWorker

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_register_heartbeat_and_reap(self):
        from app.models.dev_worker import heartbeat, reap_stale, register, snapshot

        async with self.Session() as db:
            await register(db, "wkr_a", kind="cli", supervisor_bot="hunter")
            await db.commit()

            ok = await heartbeat(db, "wkr_a", current_task_id="t1")
            self.assertTrue(ok)
            await db.commit()

            missing = await heartbeat(db, "wkr_ghost")
            self.assertFalse(missing)

            snap = await snapshot(db, now=NOW)
            self.assertTrue(snap["instrumented"])
            self.assertEqual(snap["total"], 1)

            # Age the beat out and reap.
            async with self.Session() as db2:
                row = await db2.get(self.DevWorker, "wkr_a")
                row.heartbeat_ts = _ago(DEAD_AFTER_SECONDS + 1)
                await db2.commit()

            async with self.Session() as db3:
                reaped = await reap_stale(db3, now=NOW)
                self.assertEqual(reaped, ["wkr_a"])
                await db3.commit()

            async with self.Session() as db4:
                snap2 = await snapshot(db4, now=NOW)
                self.assertEqual(snap2["dead"], 1)
                self.assertEqual(snap2["stuck"][0]["current_task_id"], "t1")

    async def test_snapshot_reports_not_instrumented_when_empty(self):
        from app.models.dev_worker import snapshot

        async with self.Session() as db:
            snap = await snapshot(db, now=NOW)
        self.assertFalse(snap["instrumented"])
        self.assertEqual(snap["total"], 0)
        self.assertEqual(snap["workers"], [])


if __name__ == "__main__":
    unittest.main()
