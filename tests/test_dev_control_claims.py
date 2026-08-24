"""Atomic-claim / heartbeat / claim-next / lease-reclaim proofs (real SQLite).

The old API claim was read->validate->write (lost-update race). These tests
prove the conditional-UPDATE semantics: exactly one winner, no lease steal,
priority-ordered polling, and reconcile requeue/fail on expired leases.
Hermetic: in-memory aiosqlite, no app.main, no network.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.dev_control.claims import atomic_claim, atomic_heartbeat, claim_next
from app.dev_control.reconcile import reconcile_leases
from app.dev_control.service import TaskState
from app.models.dev_task import DevTask


def _run(coro):
    return asyncio.run(coro)


async def _session_factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(DevTask.__table__.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _task(
    state: str = TaskState.QUEUED.value,
    priority: int = 50,
    created_at: datetime | None = None,
    **kw,
) -> DevTask:
    now = datetime.utcnow()
    return DevTask(
        id=str(uuid.uuid4()),
        idempotency_key=f"idem-{uuid.uuid4()}",
        parent_objective="test objective",
        priority=priority,
        state=state,
        retry_count=0,
        created_at=created_at or now,
        updated_at=now,
        **kw,
    )


def test_claim_has_exactly_one_winner():
    async def go():
        engine, make = await _session_factory()
        try:
            async with make() as db:
                task = _task()
                db.add(task)
                await db.commit()
                # Both workers saw state=queued before either wrote (the old race).
                first = await atomic_claim(db, task.id, "worker-1")
                second = await atomic_claim(db, task.id, "worker-2")
                fresh = await db.get(DevTask, task.id)
                await db.refresh(fresh)
                assert first is True
                assert second is False, "second concurrent claim must lose"
                assert fresh.lease_owner == "worker-1"
                assert fresh.state == TaskState.CLAIMED.value
        finally:
            await engine.dispose()

    _run(go())


def test_claim_refused_outside_queued():
    async def go():
        engine, make = await _session_factory()
        try:
            async with make() as db:
                task = _task(state=TaskState.PROPOSED.value)
                db.add(task)
                await db.commit()
                assert await atomic_claim(db, task.id, "worker-1") is False
        finally:
            await engine.dispose()

    _run(go())


def test_heartbeat_refuses_non_owner():
    async def go():
        engine, make = await _session_factory()
        try:
            async with make() as db:
                task = _task()
                db.add(task)
                await db.commit()
                assert await atomic_claim(db, task.id, "worker-1") is True
                claimed = await db.get(DevTask, task.id)
                await db.refresh(claimed)  # update() bypasses the identity map
                before = claimed.lease_until
                assert before is not None
                assert await atomic_heartbeat(db, task.id, "worker-2") is False, (
                    "lease steal must be refused"
                )
                assert await atomic_heartbeat(db, task.id, "worker-1", lease_seconds=3600) is True
                fresh = await db.get(DevTask, task.id)
                await db.refresh(fresh)
                assert fresh.lease_owner == "worker-1"
                assert fresh.lease_until > before
        finally:
            await engine.dispose()

    _run(go())


def test_claim_next_orders_by_priority_then_age():
    async def go():
        engine, make = await _session_factory()
        try:
            old = datetime.utcnow() - timedelta(hours=2)
            async with make() as db:
                low = _task(priority=10)
                high_old = _task(priority=90, created_at=old)
                high_new = _task(priority=90)
                db.add_all([low, high_old, high_new])
                await db.commit()

                first = await claim_next(db, "worker-1")
                second = await claim_next(db, "worker-1")
                third = await claim_next(db, "worker-1")
                fourth = await claim_next(db, "worker-1")
                assert first and first["task_id"] == high_old.id, "highest priority + oldest first"
                assert second and second["task_id"] == high_new.id
                assert third and third["task_id"] == low.id
                assert fourth is None, "empty queue -> None, no busy spin"
        finally:
            await engine.dispose()

    _run(go())


def test_claim_next_skips_rows_lost_to_another_worker():
    async def go():
        engine, make = await _session_factory()
        try:
            async with make() as db:
                a = _task(priority=90)
                b = _task(priority=50)
                db.add_all([a, b])
                await db.commit()
                assert await atomic_claim(db, a.id, "rival") is True  # rival wins the top row
                won = await claim_next(db, "worker-1")
                assert won and won["task_id"] == b.id, "poller must move to the next candidate"
        finally:
            await engine.dispose()

    _run(go())


def test_reconcile_requeues_then_fails_expired_leases():
    async def go():
        engine, make = await _session_factory()
        try:
            async with make() as db:
                expired = datetime.utcnow() - timedelta(minutes=5)
                task = _task(
                    state=TaskState.CLAIMED.value, lease_owner="dead-worker", lease_until=expired
                )
                task.retry_count = 0
                db.add(task)
                await db.commit()

                out = await reconcile_leases(db, max_retries=1)
                fresh = await db.get(DevTask, task.id)
                await db.refresh(fresh)
                assert out["requeued"] == 1 and fresh.state == TaskState.QUEUED.value
                assert fresh.lease_owner is None

                # Second death after the retry cap -> FAILED, not an infinite loop.
                fresh.state = TaskState.CLAIMED.value
                fresh.lease_owner = "dead-worker"
                fresh.lease_until = expired
                await db.commit()
                out2 = await reconcile_leases(db, max_retries=1)
                await db.refresh(fresh)
                assert out2["failed"] == 1 and fresh.state == TaskState.FAILED.value
        finally:
            await engine.dispose()

    _run(go())
