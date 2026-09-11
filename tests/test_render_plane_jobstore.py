"""Render-plane data-plane proofs (T02 acceptance: no duplicate, no loss).

The job ledger is the durable source of truth for the local↔VPS render plane, so
its lease/idempotency semantics ARE the correctness guarantee. This suite proves,
against a real in-memory SQLite, the exact properties the design promises:

  * **lease** — one winner, no steal, idle returns ``job=None``;
  * **completion is idempotent on ``(job_id, revision, sha256)``** — a replayed
    completion succeeds, and a *different* artifact for the same revision is a
    conflict where the FIRST wins (a slow worker cannot overwrite a fast one);
  * **worker restart / crash** — an expired lease is reclaimed by the shared
    ``lease_policy`` (requeue with backoff, then fail past the cap) so a poison
    job cannot hot-loop and no job is lost;
  * **tenant isolation** — a cross-tenant id is ``tenant_mismatch``, never a leak;
  * every public entry returns a dict and never raises on garbage input.

Hermetic: in-memory aiosqlite, no app.main, no network, no renderer.
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


class _JobStoreCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as conn:
            await conn.run_sync(js.RenderJobRow.__table__.create)
        self.make = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _create(self, tenant: str = "t1", creative: str = "cr_abc", rev: int = 0):
        async with self.make() as db:
            return await js.create_job(
                db, tenant_id=tenant, creative_id=creative, revision=rev, spec_hash="h" * 8
            )


class TestCreateAndLease(_JobStoreCase):
    async def test_create_is_idempotent(self):
        async with self.make() as db:
            first = await js.create_job(db, tenant_id="t1", creative_id="cr_a", revision=0)
            second = await js.create_job(db, tenant_id="t1", creative_id="cr_a", revision=0)
        self.assertTrue(first["ok"] and first["created"] is True)
        self.assertTrue(second["ok"] and second["created"] is False)
        self.assertEqual(first["job"]["job_id"], second["job"]["job_id"])
        self.assertEqual(first["job"]["state"], js.STATE_QUEUED)

    async def test_create_rejects_missing_ids(self):
        async with self.make() as db:
            res = await js.create_job(db, tenant_id="", creative_id="cr_a")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "invalid_request")

    async def test_lease_has_exactly_one_winner(self):
        await self._create()
        async with self.make() as db:
            first = await js.claim_next_job(db, "worker-1")
            second = await js.claim_next_job(db, "worker-2")
        self.assertTrue(first["leased"])
        self.assertEqual(first["job"]["state"], js.STATE_LEASED)
        self.assertEqual(first["job"]["lease_owner"], "worker-1")
        self.assertTrue(first["lease_token"])
        self.assertFalse(second["leased"], "an idle queue must not hand out a second lease")
        self.assertIsNone(second["job"])

    async def test_heartbeat_refuses_a_steal(self):
        await self._create()
        async with self.make() as db:
            leased = await js.claim_next_job(db, "worker-1")
            jid = leased["job"]["job_id"]
            steal = await js.heartbeat_job(db, jid, "worker-2")
            own = await js.heartbeat_job(db, jid, "worker-1", lease_seconds_=3600)
        self.assertTrue(steal["ok"] and steal["extended"] is False)
        self.assertTrue(own["ok"] and own["extended"] is True)

    async def test_lease_token_binds_job_worker_attempt(self):
        await self._create()
        async with self.make() as db:
            leased = await js.claim_next_job(db, "worker-1")
        jid, attempt = leased["job"]["job_id"], leased["job"]["attempt"]
        self.assertTrue(js.verify_lease_token(jid, "worker-1", attempt, leased["lease_token"]))
        self.assertFalse(js.verify_lease_token(jid, "worker-2", attempt, leased["lease_token"]))
        self.assertFalse(js.verify_lease_token(jid, "worker-1", attempt + 1, leased["lease_token"]))


class TestCompletionIdempotency(_JobStoreCase):
    async def _leased(self, worker: str = "worker-1"):
        await self._create()
        async with self.make() as db:
            leased = await js.claim_next_job(db, worker)
        return leased["job"]["job_id"]

    async def test_complete_then_replay_is_idempotent(self):
        jid = await self._leased()
        async with self.make() as db:
            done = await js.complete_job(
                db, job_id=jid, worker="worker-1", revision=0, sha256="a" * 64, artifact_bytes=100
            )
            replay = await js.complete_job(
                db, job_id=jid, worker="worker-1", revision=0, sha256="a" * 64, artifact_bytes=100
            )
        self.assertTrue(done["ok"] and done["idempotent"] is False)
        self.assertEqual(done["job"]["state"], js.STATE_DONE)
        self.assertTrue(replay["ok"] and replay["idempotent"] is True)
        self.assertFalse(replay["conflict"])

    async def test_second_different_artifact_is_a_conflict_first_wins(self):
        jid = await self._leased()
        async with self.make() as db:
            await js.complete_job(db, job_id=jid, worker="worker-1", revision=0, sha256="a" * 64)
            conflict = await js.complete_job(
                db, job_id=jid, worker="worker-1", revision=0, sha256="b" * 64
            )
            final = await js.get_job(db, jid)
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["error"], "artifact_conflict")
        self.assertTrue(conflict["conflict"])
        self.assertEqual(final["job"]["artifact_sha256"], "a" * 64, "the first artifact must win")

    async def test_complete_requires_the_lease_owner(self):
        jid = await self._leased("worker-1")
        async with self.make() as db:
            res = await js.complete_job(db, job_id=jid, worker="worker-9", revision=0, sha256="a" * 64)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "lease_not_owned")
        self.assertTrue(res["stale_attempt"])

    async def test_inflight_transitions_require_ownership(self):
        jid = await self._leased("worker-1")
        async with self.make() as db:
            wrong = await js.mark_rendering(db, jid, "worker-2")
            right = await js.mark_rendering(db, jid, "worker-1")
            up = await js.mark_uploading(db, jid, "worker-1")
        self.assertFalse(wrong["ok"])
        self.assertEqual(wrong["error"], "lease_not_owned")
        self.assertEqual(right["job"]["state"], js.STATE_RENDERING)
        self.assertEqual(up["job"]["state"], js.STATE_UPLOADING)


class TestReclaimAndFailure(_JobStoreCase):
    async def test_expired_lease_is_requeued_then_failed(self):
        await self._create()
        async with self.make() as db:
            leased = await js.claim_next_job(db, "dead-worker")
            jid = leased["job"]["job_id"]
            row = await db.get(js.RenderJobRow, jid)
            row.lease_until = datetime.utcnow() - timedelta(minutes=5)
            await db.commit()

            first = await js.reclaim_render_leases(db, max_retries=1)
            after = await js.get_job(db, jid)
            self.assertEqual(first["requeued"], 1)
            self.assertEqual(after["job"]["state"], js.STATE_QUEUED)
            self.assertEqual(after["job"]["lease_owner"], "")
            self.assertGreater(after["job"]["next_eligible_at"], 0.0, "backoff must be scheduled")

            # Second death past the retry cap -> FAILED, not an infinite loop.
            row = await db.get(js.RenderJobRow, jid)
            row.state = js.STATE_LEASED
            row.lease_owner = "dead-worker"
            row.lease_until = datetime.utcnow() - timedelta(minutes=5)
            row.next_eligible_at = None
            await db.commit()
            second = await js.reclaim_render_leases(db, max_retries=1)
            final = await js.get_job(db, jid)
        self.assertEqual(second["failed"], 1)
        self.assertEqual(final["job"]["state"], js.STATE_FAILED)

    async def test_retryable_failure_requeues_with_backoff(self):
        await self._create()
        async with self.make() as db:
            leased = await js.claim_next_job(db, "worker-1")
            jid = leased["job"]["job_id"]
            res = await js.fail_job(db, job_id=jid, worker="worker-1", error="boom", retryable=True)
        self.assertTrue(res["ok"])
        self.assertTrue(res["requeued"])
        self.assertEqual(res["job"]["state"], js.STATE_QUEUED)
        self.assertGreater(res["job"]["next_eligible_at"], 0.0)

    async def test_permanent_failure_stops_retrying(self):
        await self._create()
        async with self.make() as db:
            leased = await js.claim_next_job(db, "worker-1")
            jid = leased["job"]["job_id"]
            res = await js.fail_job(db, job_id=jid, worker="worker-1", error="fatal", retryable=False)
        self.assertFalse(res["requeued"])
        self.assertEqual(res["job"]["state"], js.STATE_FAILED)


class TestIsolationAndRobustness(_JobStoreCase):
    async def test_cross_tenant_read_is_refused(self):
        await self._create(tenant="tenant-a", creative="cr_a")
        async with self.make() as db:
            jid = js.job_id_for("tenant-a", "cr_a", 0)
            leak = await js.get_job(db, jid, tenant_id="tenant-b")
            own = await js.get_job(db, jid, tenant_id="tenant-a")
        self.assertFalse(leak["ok"])
        self.assertEqual(leak["error"], "tenant_mismatch")
        self.assertTrue(own["ok"])

    async def test_public_entries_never_raise_on_garbage(self):
        async with self.make() as db:
            for res in (
                await js.get_job(db, ""),
                await js.get_job(db, "nope"),
                await js.complete_job(db, job_id="", worker="w", sha256="x"),
                await js.fail_job(db, job_id=""),
                await js.heartbeat_job(db, "", "w"),
                await js.mark_rendering(db, "", "w"),
                await js.list_jobs(db, limit=0),
                await js.status_snapshot(db),
            ):
                self.assertIsInstance(res, dict)

    async def test_status_snapshot_counts_states(self):
        await self._create(tenant="t1", creative="cr_a")
        await self._create(tenant="t1", creative="cr_b")
        async with self.make() as db:
            await js.claim_next_job(db, "worker-1")
            snap = await js.status_snapshot(db, tenant_id="t1")
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["total"], 2)
        self.assertEqual(snap["in_flight"], 1)
        self.assertEqual(snap["queued"], 1)


class TestRecentDoneSync(unittest.TestCase):
    """The SYNC completion-reader the health probe needs (the fake-green fix).

    ``video_health.probe_local_render`` runs outside an event loop, so it cannot
    ``await`` ``list_jobs``. ``recent_done()`` is the sync seam that lets the probe
    report a REAL ``produced`` count — while still degrading honestly (``ok:
    False``) when the store is genuinely unreadable, never a fabricated ``0``.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._engine = create_engine(f"sqlite:///{self._tmp.name}")
        js.RenderJobRow.__table__.create(bind=self._engine)
        self.Session = sessionmaker(bind=self._engine)

    def tearDown(self) -> None:
        self._engine.dispose()
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    @contextmanager
    def _patched(self, session):
        """Point ``recent_done``'s lazily-imported session factory at ``session``."""

        @contextmanager
        def _cm():
            yield session

        with mock.patch("app.models.base.get_db_session", _cm):
            yield

    def _seed(self, db, *, tenant: str, creative: str, state: str, when: datetime) -> None:
        jid = js.job_id_for(tenant, creative, 0)
        db.add(
            js.RenderJobRow(
                id=jid,
                idempotency_key=jid,
                tenant_id=tenant,
                creative_id=creative,
                revision=0,
                state=state,
                artifact_path=f"/tmp/{creative}.mp4",
                artifact_sha256="a" * 64,
                artifact_bytes=123,
                created_at=when,
                updated_at=when,
            )
        )
        db.commit()

    def test_empty_store_is_ok_zero_not_an_error(self):
        with self.Session() as db, self._patched(db):
            res = js.recent_done()
        self.assertTrue(res["ok"], "an empty-but-readable store is a real zero")
        self.assertEqual(res["count"], 0)
        self.assertEqual(res["done"], 0)
        self.assertEqual(res["items"], [])

    def test_counts_only_completed_jobs_newest_first(self):
        base = datetime.utcnow() - timedelta(hours=2)
        with self.Session() as db:
            self._seed(db, tenant="t1", creative="cr_old", state=js.STATE_DONE, when=base)
            self._seed(
                db, tenant="t1", creative="cr_new", state=js.STATE_DONE, when=base + timedelta(hours=1)
            )
            self._seed(
                db, tenant="t1", creative="cr_pending", state=js.STATE_QUEUED, when=base
            )
            with self._patched(db):
                res = js.recent_done()
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2, "queued work must not count as produced")
        self.assertEqual(res["items"][0]["creative_id"], "cr_new", "newest finished first")
        self.assertEqual(res["items"][0]["state"], js.STATE_DONE)
        self.assertTrue(res["items"][0]["artifact_sha256"])
        self.assertGreater(res["items"][0]["finished_at"], 0.0)

    def test_read_is_tenant_scoped(self):
        now = datetime.utcnow()
        with self.Session() as db:
            self._seed(db, tenant="tenant-a", creative="cr_a", state=js.STATE_DONE, when=now)
            self._seed(db, tenant="tenant-b", creative="cr_b", state=js.STATE_DONE, when=now)
            with self._patched(db):
                scoped = js.recent_done(tenant_id="tenant-a")
                unscoped = js.recent_done()
        self.assertEqual(scoped["count"], 1)
        self.assertEqual(scoped["items"][0]["tenant_id"], "tenant-a")
        self.assertEqual(unscoped["count"], 2)

    def test_unreadable_store_is_never_a_fake_zero(self):
        @contextmanager
        def _boom():
            raise RuntimeError("Database not configured")
            yield  # pragma: no cover

        with mock.patch("app.models.base.get_db_session", _boom):
            res = js.recent_done()
        self.assertFalse(res["ok"], "unreadable store must NOT masquerade as a zero")
        self.assertTrue(str(res["error"]).startswith("recent_done_failed:"))

    def test_limit_is_clamped_and_never_raises(self):
        now = datetime.utcnow()
        with self.Session() as db:
            self._seed(db, tenant="t1", creative="cr_a", state=js.STATE_DONE, when=now)
            with self._patched(db):
                low = js.recent_done(limit=0)
                high = js.recent_done(limit=10_000)
        self.assertTrue(low["ok"] and high["ok"])
        self.assertEqual(low["count"], 1)


class TestProbeLocalRenderGhostArtifact(unittest.TestCase):
    """`probe_local_render` must NOT grade a done row green when its artifact is gone.

    Adversarial QA found this hole in ``app/marketing/video_health.py``: the probe
    set ``produced`` from the done-row COUNT alone, and a missing artifact yielded
    ``artifact_age_s=None`` which the staleness rule (``age is not None and ...``)
    treated as *fresh* — a green "render succeeded" tile with no file on disk. A
    done ROW is not a produced ARTIFACT. These cases pin the ghost-artifact hole
    and its mirror (a real file on disk is still green) against the real probe.
    """

    def _probe(self, items):
        payload = {"ok": True, "items": items, "count": len(items), "done": len(items)}
        with mock.patch.dict(os.environ, {"CREATIVE_RENDER_PLANE_ENABLED": "1"}), mock.patch(
            "app.platform.automation_health._load_beats", return_value={}
        ), mock.patch("app.render_plane.jobstore.recent_done", return_value=payload):
            from app.marketing import video_health

            return video_health.probe_local_render()

    def test_probe_rejects_a_done_row_whose_artifact_is_missing(self):
        ghost = os.path.join(tempfile.gettempdir(), "leadgen_ghost_artifact_missing.mp4")
        if os.path.exists(ghost):
            os.unlink(ghost)
        r = self._probe([{"job_id": "j2", "artifact_path": ghost, "artifact_sha256": "b" * 64}])
        self.assertFalse(r["produced"], r)  # a done row with no file is NOT produced
        self.assertNotEqual(r["status"], "ok", r)  # ...and must never grade green
        self.assertFalse(r["verified"], r)  # ...nor claim evidence
        self.assertTrue(r.get("artifact_missing"), r)  # ...but must SAY so, not a silent zero

    def test_probe_accepts_a_done_row_with_a_real_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "real.mp4")
            with open(real, "wb") as fh:
                fh.write(b"rendered")
            r = self._probe([{"job_id": "j3", "artifact_path": real, "artifact_sha256": "c" * 64}])
        self.assertTrue(r["produced"], r)
        self.assertEqual(r["status"], "ok", r)
        self.assertTrue(r["verified"], r)
        self.assertNotIn("artifact_missing", r)


if __name__ == "__main__":
    unittest.main()
