"""Tests for the tamper-evident DevTask audit trail (app.models.dev_task_event).

This is the foundation that the control-plane lifecycle in ``app/api/dev_tasks.py``
now writes into (create / claim / claim-next / heartbeat / transition / report all
call ``_record_audit`` -> ``append_event``). Before these tests existed, the
``DevTaskEvent`` model + ``append_event`` + ``verify_task_chain`` were BUILT but
never exercised anywhere in ``app/`` — the gap closed during the 24x7 migration.

Split into two layers on purpose (same discipline as test_dev_worker_registry.py):

1. ``LedgerHashTests`` — pure chain math, **stdlib only**, always runs. Proves
   ``verify_event_chain`` accepts a valid chain and REJECTS a tampered one.
2. ``AuditTrailDbTests`` — real async round-trip on SQLite; **skipped** when
   SQLAlchemy/aiosqlite are unavailable rather than faking a pass.

Run:  python -m pytest tests/test_dev_task_audit.py -q
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta

from app.dev_control.ledger_hash import (
    GENESIS_HASH,
    compute_event_hash,
    verify_event_chain,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NOW = datetime(2026, 9, 12, 10, 0, 0)
NOW2 = NOW + timedelta(minutes=1)


def _make_event(*, seq, prev_hash, from_state, to_state, payload, created_at):
    """Build a dict-shaped chain row using the canonical hasher."""
    return {
        "seq": seq,
        "prev_hash": prev_hash,
        "event_hash": compute_event_hash(
            prev_hash=prev_hash,
            payload=payload,
            from_state=from_state,
            to_state=to_state,
            seq=seq,
            created_at=created_at,
        ),
        "from_state": from_state,
        "to_state": to_state,
        "payload": payload,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# 1. Pure chain math (always runs; ledger_hash is stdlib-only)
# ---------------------------------------------------------------------------


class LedgerHashTests(unittest.TestCase):
    def test_compute_event_hash_is_deterministic(self):
        a = compute_event_hash(
            prev_hash=GENESIS_HASH, payload={"x": 1}, from_state=None,
            to_state="PROPOSED", seq=1, created_at=NOW,
        )
        b = compute_event_hash(
            prev_hash=GENESIS_HASH, payload={"x": 1}, from_state=None,
            to_state="PROPOSED", seq=1, created_at=NOW,
        )
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_empty_chain_verifies(self):
        self.assertEqual(verify_event_chain([]), (True, "empty"))

    def test_valid_two_event_chain_verifies(self):
        e1 = _make_event(
            seq=1, prev_hash=GENESIS_HASH, from_state=None, to_state="PROPOSED",
            payload={"idempotency_key": "k1"}, created_at=NOW,
        )
        e2 = _make_event(
            seq=2, prev_hash=e1["event_hash"], from_state="PROPOSED",
            to_state="CLAIMED", payload={"lease": "w1"}, created_at=NOW2,
        )
        ok, reason = verify_event_chain([e1, e2])
        self.assertTrue(ok, reason)

    def test_tampered_payload_is_rejected(self):
        e1 = _make_event(
            seq=1, prev_hash=GENESIS_HASH, from_state=None, to_state="PROPOSED",
            payload={"idempotency_key": "k1"}, created_at=NOW,
        )
        e2 = _make_event(
            seq=2, prev_hash=e1["event_hash"], from_state="PROPOSED",
            to_state="CLAIMED", payload={"lease": "w1"}, created_at=NOW2,
        )
        bad = [dict(e1), dict(e2)]
        bad[1]["payload"] = {"lease": "attacker"}  # mutated, hash NOT recomputed
        ok, reason = verify_event_chain(bad)
        self.assertFalse(ok)
        self.assertIn("event_hash mismatch", reason)

    def test_out_of_order_seq_is_rejected(self):
        e1 = _make_event(
            seq=1, prev_hash=GENESIS_HASH, from_state=None, to_state="PROPOSED",
            payload={}, created_at=NOW,
        )
        e2 = _make_event(
            seq=3, prev_hash=e1["event_hash"], from_state="PROPOSED",
            to_state="CLAIMED", payload={}, created_at=NOW2,
        )
        ok, reason = verify_event_chain([e1, e2])
        self.assertFalse(ok)
        self.assertIn("seq gap", reason)

    def test_broken_prev_hash_link_is_rejected(self):
        e1 = _make_event(
            seq=1, prev_hash=GENESIS_HASH, from_state=None, to_state="PROPOSED",
            payload={}, created_at=NOW,
        )
        e2 = _make_event(
            seq=2, prev_hash="deadbeef" * 8, from_state="PROPOSED",
            to_state="CLAIMED", payload={}, created_at=NOW2,
        )
        ok, reason = verify_event_chain([e1, e2])
        self.assertFalse(ok)
        self.assertIn("prev_hash mismatch", reason)


# ---------------------------------------------------------------------------
# 2. Real DB round-trip (skipped, not faked, when deps are absent)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - depends on environment
    import sqlalchemy as _sa  # noqa: F401
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: F401

    _HAVE_SQLALCHEMY = True
except Exception:  # pragma: no cover
    _HAVE_SQLALCHEMY = False


@unittest.skipUnless(_HAVE_SQLALCHEMY, "SQLAlchemy/aiosqlite unavailable (no .venv)")
class AuditTrailDbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.models.base import Base
        from app.models.dev_task_event import DevTaskEvent

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        self.DevTaskEvent = DevTaskEvent

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_append_builds_genesis_then_chains(self):
        from sqlalchemy import select

        from app.models.dev_task_event import append_event, verify_task_chain

        tid = "task_chain_1"
        async with self.Session() as db:
            e1 = await append_event(db, tid, "admin", None, "PROPOSED",
                                    {"idempotency_key": "k1"}, now=NOW)
            e2 = await append_event(db, tid, "worker", "PROPOSED", "CLAIMED",
                                    {"lease": "w1"}, now=NOW2)
            await db.commit()

        self.assertEqual(e1.seq, 1)
        self.assertEqual(e1.prev_hash, GENESIS_HASH)
        self.assertEqual(e2.seq, 2)
        self.assertEqual(e2.prev_hash, e1.event_hash)

        async with self.Session() as db:
            ok, reason = await verify_task_chain(db, tid)
            self.assertTrue(ok, reason)
            count = (await db.execute(
                select(self.DevTaskEvent).where(self.DevTaskEvent.task_id == tid)
            )).scalars().all()
            self.assertEqual(len(count), 2)

    async def test_verify_rejects_tampered_row(self):
        from sqlalchemy import select

        from app.models.dev_task_event import append_event, verify_task_chain

        tid = "task_chain_2"
        async with self.Session() as db:
            await append_event(db, tid, "admin", None, "PROPOSED", {"idempotency_key": "k1"}, now=NOW)
            await append_event(db, tid, "worker", "PROPOSED", "CLAIMED", {"lease": "w1"}, now=NOW2)
            await db.commit()

        async with self.Session() as db:
            rows = (await db.execute(
                select(self.DevTaskEvent).where(self.DevTaskEvent.task_id == tid)
            )).scalars().all()
            rows[1].payload = {"lease": "attacker"}  # mutate WITHOUT recomputing hash
            await db.flush()
            ok, reason = await verify_task_chain(db, tid)
            self.assertFalse(ok)
            self.assertIn("event_hash mismatch", reason)

    async def test_append_event_flushes_but_does_not_commit(self):
        """Caller owns the transaction: an uncommitted append must not persist."""
        from sqlalchemy import select

        from app.models.dev_task_event import append_event

        tid = "task_nocommit"
        async with self.Session() as db:
            await append_event(db, tid, "admin", None, "PROPOSED", {})
            # deliberately NO commit

        async with self.Session() as db2:
            rows = (await db2.execute(
                select(self.DevTaskEvent).where(self.DevTaskEvent.task_id == tid)
            )).scalars().all()
            self.assertEqual(len(rows), 0, "append_event must not auto-commit")

    async def test_api_audit_helper_writes_valid_chain(self):
        """The exact helper wired into app/api/dev_tasks.py must write a verifiable event."""
        from sqlalchemy import select

        from app.api.dev_tasks import _record_audit
        from app.models.dev_task_event import DevTaskEvent, verify_task_chain

        tid = "task_api_wire"
        async with self.Session() as db:
            await _record_audit(db, tid, "admin", None, "PROPOSED",
                                {"idempotency_key": "api-k"})
            await db.commit()

        async with self.Session() as db:
            ok, reason = await verify_task_chain(db, tid)
            self.assertTrue(ok, reason)
            row = (await db.execute(
                select(DevTaskEvent).where(DevTaskEvent.task_id == tid)
            )).scalars().one()
            self.assertEqual(row.actor, "admin")
            self.assertEqual(row.to_state, "PROPOSED")


if __name__ == "__main__":
    unittest.main()
