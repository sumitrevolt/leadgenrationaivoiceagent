"""Render-plane resume: network drop + worker restart → no duplicate, no loss (T05).

The local↔VPS render plane must survive an unreliable link and a worker restart
without either losing a video or producing it twice. The durable job ledger
(``app.render_plane.jobstore``) is the source of truth, so this suite drives the
REAL lease/reclaim/complete cycle against a real SQLite database and proves:

  * a worker that leases a job and then "drops" (its lease expires) does NOT lose
    it — the shared ``lease_policy`` reclaim requeues it with backoff;
  * a RESTARTED worker (a different owner) picks the requeued job back up once the
    backoff window has passed — the job is resumed, not orphaned;
  * completion is idempotent: a replayed completion of the SAME artifact succeeds
    and is flagged ``idempotent`` — the artifact count stays exactly ONE
    (no duplicate);
  * the SYNC reader ``recent_done()`` the health probe depends on reports the one
    real ``done`` job (a produced count, never a fabricated zero);
  * all three Celery tasks exist in ``app/tasks/video_jobs.py`` and DELEGATE to the
    right implementation — ``render_plane_lease_task`` →
    ``_render_plane_lease_async``, ``video_delivery_task`` →
    ``video_delivery.deliver_video``, ``video_delivery_retry_task`` →
    ``video_delivery.process_retries``.

Hermetic: file-backed aiosqlite, no network, no renderer, no app.main. The sync
reader shares the SAME database file as the async scenario, so its count is proof
about the very jobs this test created — not a second, unrelated fixture.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.render_plane import jobstore as js


class TestNetworkDropAndWorkerRestart(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.path = tmp.name
        self.aengine = create_async_engine(f"sqlite+aiosqlite:///{self.path}")
        async with self.aengine.begin() as conn:
            await conn.run_sync(js.RenderJobRow.__table__.create)
        self.make = async_sessionmaker(self.aengine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.aengine.dispose()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    async def test_drop_then_restart_resumes_without_duplicate_or_loss(self) -> None:
        # ---- 1. a job is queued, then worker-1 leases it ----------------------
        async with self.make() as db:
            created = await js.create_job(
                db, tenant_id="t1", creative_id="cr_a", revision=0, spec_hash="h" * 8
            )
        self.assertTrue(created["ok"] and created["created"] is True)
        jid = created["job"]["job_id"]

        async with self.make() as db:
            leased = await js.claim_next_job(db, "worker-1")
            self.assertTrue(leased["leased"])
            self.assertEqual(leased["job"]["job_id"], jid)

            # ---- 2. the network drops: worker-1 never completes. Its lease
            #         expires and the reconciler reclaims it. ------------------
            row = await db.get(js.RenderJobRow, jid)
            row.lease_until = datetime.utcnow() - timedelta(minutes=5)
            await db.commit()

            reclaimed = await js.reclaim_render_leases(db, max_retries=3)
            self.assertEqual(reclaimed["requeued"], 1, "an expired lease must be requeued, not lost")
            self.assertEqual(reclaimed["failed"], 0)
            after = await js.get_job(db, jid)
            self.assertEqual(after["job"]["state"], js.STATE_QUEUED)
            self.assertEqual(after["job"]["lease_owner"], "")
            self.assertGreater(after["job"]["next_eligible_at"], 0.0, "backoff must be scheduled")

        # ---- 3. worker restarts; TWO workers race for the requeued job after
        #         the backoff window. Exactly one wins (no duplicate work). ----
        after_backoff = datetime.utcnow() + timedelta(minutes=20)
        async with self.make() as db:
            first = await js.claim_next_job(db, "worker-2", now=after_backoff)
            second = await js.claim_next_job(db, "worker-3", now=after_backoff)
            self.assertTrue(first["leased"], "the restarted worker must resume the job")
            self.assertEqual(first["job"]["job_id"], jid)
            self.assertFalse(second["leased"], "a second worker must NOT get the same job")

            # ---- 4. the resumed worker completes, then replays its completion
            #         (e.g. the ack was lost). The replay is idempotent and the
            #         artifact count stays exactly one. ----------------------
            done = await js.complete_job(
                db, job_id=jid, worker="worker-2", revision=0, sha256="a" * 64, artifact_bytes=1000
            )
            self.assertTrue(done["ok"] and done["idempotent"] is False)
            self.assertEqual(done["job"]["state"], js.STATE_DONE)

            replay = await js.complete_job(
                db, job_id=jid, worker="worker-2", revision=0, sha256="a" * 64, artifact_bytes=1000
            )
            self.assertTrue(replay["ok"] and replay["idempotent"] is True)
            self.assertFalse(replay["conflict"])

            snap = await js.status_snapshot(db, tenant_id="t1")
            self.assertEqual(snap["total"], 1, "no loss: the job still exists")
            self.assertEqual(snap["done"], 1, "no duplicate: exactly one finished artifact")
            self.assertEqual(snap["in_flight"], 0)

        # ---- 5. the SYNC reader the health probe uses sees the same one job --
        await self.aengine.dispose()
        sync_engine = create_engine(f"sqlite:///{self.path}")
        Session = sessionmaker(bind=sync_engine)

        @contextmanager
        def _cm():
            with Session() as session:
                yield session

        with mock.patch("app.models.base.get_db_session", _cm):
            recent = js.recent_done(limit=50, tenant_id="t1")
        sync_engine.dispose()

        self.assertTrue(recent["ok"], f"sync reader degraded: {recent}")
        self.assertEqual(recent["done"], 1, "exactly one produced video — no duplicate")
        self.assertEqual(recent["count"], 1)
        self.assertEqual(recent["items"][0]["creative_id"], "cr_a")
        self.assertEqual(recent["items"][0]["state"], js.STATE_DONE)
        self.assertTrue(recent["items"][0]["artifact_sha256"])

    async def test_second_different_artifact_for_same_revision_is_a_conflict(self) -> None:
        """A slow worker must never overwrite a fast one's artifact (first wins)."""
        async with self.make() as db:
            created = await js.create_job(db, tenant_id="t1", creative_id="cr_b", revision=0)
            jid = created["job"]["job_id"]
            await js.claim_next_job(db, "worker-1")
            first = await js.complete_job(
                db, job_id=jid, worker="worker-1", revision=0, sha256="a" * 64
            )
            self.assertTrue(first["ok"])
            conflict = await js.complete_job(
                db, job_id=jid, worker="worker-1", revision=0, sha256="b" * 64
            )
            final = await js.get_job(db, jid)
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["error"], "artifact_conflict")
        self.assertTrue(conflict["conflict"])
        self.assertEqual(final["job"]["artifact_sha256"], "a" * 64)


class TestVideoJobTaskContract(unittest.TestCase):
    """All three Celery tasks exist and delegate to the right implementation.

    ``app/tasks/video_jobs.py`` has exactly one writer per wave (T02). This test
    pins the CONTRACT that separation must uphold: the lease task delegates to the
    render-plane async core, and the two delivery wrappers are thin delegations to
    ``app/marketing/video_delivery.py`` (T03's implementation) — not a re-impl.
    """

    def test_all_three_tasks_are_registered(self) -> None:
        import app.tasks.video_jobs as vj

        for name in ("render_plane_lease_task", "video_delivery_task", "video_delivery_retry_task"):
            self.assertTrue(hasattr(vj, name), f"missing Celery task: {name}")
        self.assertEqual(
            vj.render_plane_lease_task.name, "app.tasks.video_jobs.render_plane_lease_task"
        )
        self.assertEqual(
            vj.video_delivery_task.name, "app.tasks.video_jobs.video_delivery_task"
        )
        self.assertEqual(
            vj.video_delivery_retry_task.name, "app.tasks.video_jobs.video_delivery_retry_task"
        )

    def test_lease_task_delegates_to_the_render_plane_core(self) -> None:
        import app.tasks.video_jobs as vj

        seen: dict = {}

        async def _fake(**kwargs):
            seen.update(kwargs)
            return {"ok": True, "delegated": True}

        with mock.patch.object(vj, "_render_plane_lease_async", _fake):
            result = vj.render_plane_lease_task.apply(
                kwargs={"max_retries": 2, "limit": 7, "enqueue": False}
            ).get()
        self.assertTrue(result["delegated"])
        self.assertEqual(seen, {"max_retries": 2, "limit": 7, "enqueue": False})

    def test_delivery_task_delegates_to_video_delivery(self) -> None:
        import app.tasks.video_jobs as vj

        with mock.patch(
            "app.marketing.video_delivery.deliver_video", return_value={"ok": True, "sent": 1}
        ) as m:
            result = vj.video_delivery_task.apply(
                kwargs={"tenant_id": "t1", "creative_id": "cr_x", "revision": 3, "caption": "hi"}
            ).get()
        self.assertTrue(result["ok"])
        m.assert_called_once_with("t1", "cr_x", caption="hi", revision=3, actor="celery")

    def test_delivery_retry_task_delegates_to_video_delivery(self) -> None:
        import app.tasks.video_jobs as vj

        with mock.patch(
            "app.marketing.video_delivery.process_retries", return_value={"ok": True, "drained": 0}
        ) as m:
            result = vj.video_delivery_retry_task.apply(kwargs={"limit": 5}).get()
        self.assertTrue(result["ok"])
        m.assert_called_once_with(limit=5)


if __name__ == "__main__":
    unittest.main()
