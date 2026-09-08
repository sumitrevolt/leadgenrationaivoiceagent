"""Durable Celery campaign launch (2026-07-02, P2-1).

Covers:
  - app/telephony/campaign_compliance.py — shared TRAI-window/readiness gate
    (single source of truth for both scripts/fire_calls.py and the Celery task).
  - app/tasks/calling.py::run_campaign_task — the durable replacement for the
    web-process asyncio-subprocess path, + the single-flight Redis lock.
  - app/api/admin_ops.py::launch_campaign — prefers Celery, falls back to
    subprocess on broker failure, refuses a second launch while one runs.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime

import pytest


@contextmanager
def _fake_ctx(session):
    yield session


# --------------------------------------------------------------------------- #
# campaign_compliance — shared gate
# --------------------------------------------------------------------------- #
def test_trai_window_ok_inside_promo_window(monkeypatch):
    from app.telephony.campaign_compliance import trai_window_ok

    monkeypatch.delenv("COMPLIANCE_PROMO_START", raising=False)
    monkeypatch.delenv("COMPLIANCE_PROMO_END", raising=False)
    # 12:00 IST = 06:30 UTC — inside default 10:00-19:00 IST promo window
    now_utc = datetime(2026, 1, 1, 6, 30)
    ok, reason = trai_window_ok(False, now_utc=now_utc)
    assert ok is True and reason == ""


def test_trai_window_blocks_outside_promo_window(monkeypatch):
    from app.telephony.campaign_compliance import trai_window_ok

    monkeypatch.delenv("COMPLIANCE_PROMO_START", raising=False)
    monkeypatch.delenv("COMPLIANCE_PROMO_END", raising=False)
    # 22:00 IST = 16:30 UTC — well outside 10:00-19:00 IST
    now_utc = datetime(2026, 1, 1, 16, 30)
    ok, reason = trai_window_ok(False, now_utc=now_utc)
    assert ok is False
    assert "TRAI window CLOSED" in reason


def test_trai_window_transactional_has_wider_hours(monkeypatch):
    from app.telephony.campaign_compliance import trai_window_ok

    monkeypatch.delenv("COMPLIANCE_TXN_START", raising=False)
    monkeypatch.delenv("COMPLIANCE_TXN_END", raising=False)
    # 20:00 IST = 14:30 UTC — inside transactional 9:00-21:00 IST, outside promo 10-19
    now_utc = datetime(2026, 1, 1, 14, 30)
    promo_ok, _ = trai_window_ok(False, now_utc=now_utc)
    txn_ok, _ = trai_window_ok(True, now_utc=now_utc)
    assert promo_ok is False
    assert txn_ok is True


def test_call_type_for():
    from app.telephony.campaign_compliance import call_type_for

    assert call_type_for(True) == "transactional"
    assert call_type_for(False) == "promotional"


def test_readiness_ok_never_raises(monkeypatch):
    from app.telephony import campaign_compliance as cc

    def boom():
        raise RuntimeError("readiness module down")

    import app.telephony.telephony_readiness as tr

    monkeypatch.setattr(tr, "run_checks", boom)
    ok, score, actions = cc.readiness_ok()
    # fails OPEN on its own bug — never blocks a campaign on a readiness-check crash
    assert ok is True and score == 100 and actions == []


# --------------------------------------------------------------------------- #
# run_campaign_task — lock + gates + dial loop (mocked DB/dial, no real Celery
# worker or network needed — a @shared_task is still callable via .run()).
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_redis():
    """Minimal in-memory stand-in for the redis-py client used by calling.py's
    lock/status helpers, so lock behaviour is deterministic in tests (the real
    REDIS_URL is deliberately unreachable in the test env — see conftest.py)."""

    class _Fake:
        def __init__(self):
            self.store: dict[str, str] = {}

        def ping(self):
            return True

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.store:
                return False
            self.store[key] = value
            return True

        def exists(self, key):
            return key in self.store

        def delete(self, key):
            self.store.pop(key, None)

        def setex(self, key, ttl, value):
            self.store[key] = value

        def get(self, key):
            return self.store.get(key)

    return _Fake()


def test_campaign_lock_single_flight(monkeypatch, fake_redis):
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: fake_redis)
    assert ct.campaign_lock_held() is False
    assert ct.acquire_campaign_lock() is True
    # second acquire while held must fail (single-flight dedup)
    assert ct.acquire_campaign_lock() is False
    assert ct.campaign_lock_held() is True
    ct.release_campaign_lock()
    assert ct.campaign_lock_held() is False


def test_campaign_lock_fails_open_without_redis(monkeypatch):
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: None)
    # Redis unavailable => never block a legitimate launch on our own infra gap
    assert ct.acquire_campaign_lock() is True
    assert ct.campaign_lock_held() is False


def test_run_campaign_task_blocks_outside_trai_window(monkeypatch, fake_redis):
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: fake_redis)
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok",
        lambda transactional, now_utc=None: (False, "TRAI window CLOSED (test)"),
    )
    result = ct.run_campaign_task.run(limit=5, dry_run=False)
    assert result["status"] == "blocked"
    assert "TRAI window CLOSED" in result["reason"]
    status = fake_redis.get(ct._CAMPAIGN_STATUS_KEY)
    assert status and '"status": "blocked"' in status
    # lock released even on the blocked path (finally)
    assert ct.campaign_lock_held() is False


def test_run_campaign_task_blocks_on_low_readiness(monkeypatch, fake_redis):
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: fake_redis)
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok",
        lambda transactional, now_utc=None: (True, ""),
    )
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.readiness_ok",
        lambda: (False, 40, ["fix VOBIZ_CALLER_ID"]),
    )
    result = ct.run_campaign_task.run(limit=5, dry_run=False)
    assert result["status"] == "blocked"
    assert "readiness" in result["reason"].lower()


def test_run_campaign_task_dry_run_skips_gates_and_dialing(monkeypatch, fake_redis):
    """dry_run must never call the compliance gates or place a real call."""
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: fake_redis)
    gate_called = []
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok",
        lambda *a, **k: gate_called.append(1) or (True, ""),
    )
    monkeypatch.setattr(ct, "get_db_session", lambda: _fake_ctx(object()))
    monkeypatch.setattr(ct, "_get_campaign_prospects", lambda db, limit, niche: [])
    result = ct.run_campaign_task.run(limit=5, dry_run=True)
    assert gate_called == []  # gate skipped entirely for dry_run
    assert result["status"] == "done"


def test_run_campaign_task_no_prospects_never_dials(monkeypatch, fake_redis):
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: fake_redis)
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok", lambda *a, **k: (True, "")
    )
    monkeypatch.setattr("app.telephony.campaign_compliance.readiness_ok", lambda: (True, 100, []))
    monkeypatch.setattr(ct, "get_db_session", lambda: _fake_ctx(object()))
    monkeypatch.setattr(ct, "_get_campaign_prospects", lambda db, limit, niche: [])
    dial_called = []
    monkeypatch.setattr(ct, "_dial_vobiz_campaign", lambda *a, **k: dial_called.append(1))
    result = ct.run_campaign_task.run(limit=5, dry_run=False)
    assert result == {"status": "done", "ok": 0, "skip": 0, "fail": 0}
    assert dial_called == []


def test_run_campaign_task_marks_placed_leads_and_releases_lock(monkeypatch, fake_redis):
    """run_campaign_task threads its db session through to _dial_vobiz_campaign
    (which now does the per-lead mark_called commit itself — see
    test_dial_vobiz_campaign_marks_call_attempts_inline_per_lead below for the
    crash-safety property of that inline commit)."""
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: fake_redis)
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok", lambda *a, **k: (True, "")
    )
    monkeypatch.setattr("app.telephony.campaign_compliance.readiness_ok", lambda: (True, 100, []))

    class _FakeLead:
        id = "lead_1"
        phone = "9876543210"
        niche = "salon"

    monkeypatch.setattr(ct, "_get_campaign_prospects", lambda db, limit, niche: [_FakeLead()])

    captured = {}

    async def _fake_dial(db, prospects, dry_run, call_type, client_id, platform):
        captured["db"] = db
        captured["prospect_ids"] = [p.id for p in prospects]
        return {"ok": 1, "skip": 0, "fail": 0, "placed_ids": ["lead_1"]}

    monkeypatch.setattr(ct, "_dial_vobiz_campaign", _fake_dial)

    sentinel_db = object()
    ct.acquire_campaign_lock()  # simulate the endpoint having already locked
    monkeypatch.setattr(ct, "get_db_session", lambda: _fake_ctx(sentinel_db))
    result = ct.run_campaign_task.run(limit=5, dry_run=False)
    assert result["status"] == "done"
    assert result["ok"] == 1
    assert captured["db"] is sentinel_db
    assert captured["prospect_ids"] == ["lead_1"]
    # lock released after the task finishes (whoever launched it can launch again)
    assert ct.campaign_lock_held() is False


@pytest.fixture
def fake_campaign_db():
    """Records every Lead.call_attempts update + commit call so tests can
    assert marking happens PER-CALL, not batched after the whole dial loop."""

    class _FakeQuery:
        def __init__(self, session):
            self._session = session

        def filter(self, *a, **k):
            return self

        def update(self, values, synchronize_session=False):
            self._session.updates.append(values)
            return 1

    class _FakeSession:
        def __init__(self):
            self.updates: list = []
            self.commits = 0
            self.rollbacks = 0

        def query(self, model):
            return _FakeQuery(self)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    return _FakeSession()


class _FakeCampaignLead:
    def __init__(self, id_, phone):
        self.id = id_
        self.phone = phone
        self.niche = "salon"


@pytest.fixture
def kill_disengaged(monkeypatch):
    """Opt-in: state the calling-safety precondition for tests about OTHER gates.

    The admin kill reader is fail-CLOSED — a missing, unreadable or malformed
    authority file ENGAGES the kill. The dialer tests below predate that and
    silently relied on "no kill file" meaning "safe to dial", so they were
    asserting call_attempts bookkeeping against a run in which no provider was
    ever invoked. Their failure was the reader working, not the bookkeeping
    breaking.

    ENV is final in the reader, so `0` is the explicit, valid, disengaged
    authority — the same shape tests/test_voice_launch.py already uses.

    Deliberately NOT autouse: a global disengage would re-open the fail-open
    hole for every future test in this file. The tests that PROVE an absent or
    malformed authority blocks dialing live in
    tests/test_voice_launch_kill_failclosed.py and must never take this fixture.
    """
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")


def test_dial_vobiz_campaign_marks_call_attempts_inline_per_lead(
    kill_disengaged, monkeypatch, fake_campaign_db
):
    """Each placed call commits its own Lead.call_attempts update immediately
    (fire_calls.py-style crash-safety) — not one batched update after the
    whole (possibly minutes-long) dial loop finishes. A batched-after approach
    loses every already-dialed lead's mark if the task is killed mid-run
    (e.g. campaign/stop's revoke(terminate=True)), causing a relaunch to
    re-dial people who were already contacted."""
    from app.tasks import calling as ct

    leads = [_FakeCampaignLead("lead_1", "9876543210"), _FakeCampaignLead("lead_2", "9876543211")]

    class _FakeVobizClient:
        def available(self):
            return True

    monkeypatch.setattr("app.telephony.vobiz_handler.VobizClient", _FakeVobizClient)

    async def _fake_start(
        to, niche="general", call_type="promotional", client_id=None, lead_id=None
    ):
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start)

    async def _fast_sleep(_):
        return None

    monkeypatch.setattr(ct.asyncio, "sleep", _fast_sleep)

    result = asyncio.run(
        ct._dial_vobiz_campaign(fake_campaign_db, leads, False, "promotional", "", False)
    )

    assert result["ok"] == 2
    assert result["placed_ids"] == ["lead_1", "lead_2"]
    # TWO independent commits, one per placed lead.
    assert fake_campaign_db.commits == 2
    assert len(fake_campaign_db.updates) == 2


def test_dial_vobiz_campaign_earlier_commits_survive_mid_loop_failure(
    kill_disengaged, monkeypatch, fake_campaign_db
):
    """If the 2nd call blows up mid-loop, lead_1's mark_called commit must
    already have happened — proving a crash/kill after this point does not
    lose lead_1's call_attempts (would otherwise get re-dialed on relaunch)."""
    from app.tasks import calling as ct

    leads = [_FakeCampaignLead("lead_1", "9876543210"), _FakeCampaignLead("lead_2", "9876543211")]

    class _FakeVobizClient:
        def available(self):
            return True

    monkeypatch.setattr("app.telephony.vobiz_handler.VobizClient", _FakeVobizClient)

    call_n = {"n": 0}

    async def _fake_start(
        to, niche="general", call_type="promotional", client_id=None, lead_id=None
    ):
        call_n["n"] += 1
        if call_n["n"] == 2:
            raise RuntimeError("simulated mid-run kill")
        return {"placed": True}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start)

    async def _fast_sleep(_):
        return None

    monkeypatch.setattr(ct.asyncio, "sleep", _fast_sleep)

    with pytest.raises(RuntimeError):
        asyncio.run(
            ct._dial_vobiz_campaign(fake_campaign_db, leads, False, "promotional", "", False)
        )

    assert fake_campaign_db.commits == 1
    assert len(fake_campaign_db.updates) == 1


def test_dial_vobiz_campaign_increments_null_call_attempts_against_real_db(
    kill_disengaged, monkeypatch
):
    """The mocked-query tests above (fake_campaign_db) only record the update
    dict passed to .update() — they never execute real SQL, so they can't
    catch `Lead.call_attempts + 1` compiling to `NULL + 1 = NULL` for a
    never-called lead (call_attempts IS NULL — exactly what the prospect
    filter's `or_(Lead.call_attempts.is_(None), ...)` admits). This test runs
    the real UPDATE against a real (in-memory) SQLite engine so a regression
    to the non-coalesced form would actually fail it."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.models.base import Base
    from app.models.lead import Lead
    from app.tasks import calling as ct

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        lead = Lead(
            id="lead_null_attempts",
            company_name="Never Called Co",
            phone="9876543212",
            niche="salon",
        )
        session.add(lead)
        session.commit()
        # Force a genuine NULL at the DB level (bulk-imported/pre-migration
        # row). Setting `lead.call_attempts = None` on the ORM object BEFORE
        # flush does NOT reproduce this — SQLAlchemy's column-level
        # `default=0` still fires and the row lands as 0, not NULL, which
        # would make this test pass trivially (0 + 1 = 1 needs no coalesce)
        # regardless of whether the fix is present. Raw SQL bypasses that.
        session.execute(
            text("UPDATE leads SET call_attempts = NULL WHERE id = :id"),
            {"id": "lead_null_attempts"},
        )
        session.commit()
        session.expire_all()
        assert (
            session.query(Lead).filter(Lead.id == "lead_null_attempts").one().call_attempts is None
        ), "test setup failed to produce a real NULL row"

        class _FakeVobizClient:
            def available(self):
                return True

        monkeypatch.setattr("app.telephony.vobiz_handler.VobizClient", _FakeVobizClient)

        async def _fake_start(
            to, niche="general", call_type="promotional", client_id=None, lead_id=None
        ):
            return {"placed": True}

        monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake_start)

        async def _fast_sleep(_):
            return None

        monkeypatch.setattr(ct.asyncio, "sleep", _fast_sleep)

        asyncio.run(ct._dial_vobiz_campaign(session, [lead], False, "promotional", "", False))

        session.expire_all()
        refreshed = session.query(Lead).filter(Lead.id == "lead_null_attempts").one()
        assert refreshed.call_attempts == 1, (
            "NULL call_attempts must become 1 (coalesced), not stay NULL — a "
            "NULL result means the lead stays re-selectable and gets re-dialed"
        )
    finally:
        session.close()


def test_run_campaign_task_never_raises_on_dial_exception(monkeypatch, fake_redis):
    """A crash inside the dial loop must still resolve to a graceful error
    status, never an unhandled exception bubbling out of the Celery task."""
    from app.tasks import calling as ct

    monkeypatch.setattr(ct, "_campaign_redis", lambda: fake_redis)
    monkeypatch.setattr(
        "app.telephony.campaign_compliance.trai_window_ok", lambda *a, **k: (True, "")
    )
    monkeypatch.setattr("app.telephony.campaign_compliance.readiness_ok", lambda: (True, 100, []))

    class _FakeLead:
        id = "lead_1"
        phone = "9876543210"
        niche = "salon"

    monkeypatch.setattr(ct, "_get_campaign_prospects", lambda db, limit, niche: [_FakeLead()])
    monkeypatch.setattr(ct, "get_db_session", lambda: _fake_ctx(object()))

    def _boom(*a, **k):
        raise RuntimeError("vobiz down")

    monkeypatch.setattr(ct, "_dial_vobiz_campaign", _boom)

    result = ct.run_campaign_task.run(limit=5, dry_run=False)
    assert result["status"] == "error"
    assert ct.campaign_lock_held() is False


# --------------------------------------------------------------------------- #
# process_callbacks — same NULL call_attempts class of bug, different (older,
# pre-existing) function. `lead.call_attempts += 1` on a real ORM object
# TypeErrors when the loaded value is None, aborting the loop's db.commit()
# for the WHOLE batch — including leads already dispatched via
# make_call_task.delay() earlier in the same run, whose last_called_at never
# gets persisted and so stay re-queuable on the next tick.
# --------------------------------------------------------------------------- #
def test_process_callbacks_handles_null_call_attempts_against_real_db(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.models.base import Base
    from app.models.lead import Lead, LeadStatus
    from app.tasks import calling as ct

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr(ct, "get_db_session", lambda: Session())

    session = Session()
    try:
        now = datetime.utcnow()
        session.add_all(
            [
                Lead(
                    id="cb_1",
                    company_name="A",
                    phone="9876500001",
                    niche="salon",
                    status=LeadStatus.CALLBACK,
                    next_call_at=now,
                ),
                Lead(
                    id="cb_2",
                    company_name="B",
                    phone="9876500002",
                    niche="salon",
                    status=LeadStatus.CALLBACK,
                    next_call_at=now,
                ),
            ]
        )
        session.commit()
        # cb_2 gets a genuine NULL call_attempts (bulk-imported row) — see the
        # note in test_dial_vobiz_campaign_increments_null_call_attempts_
        # against_real_db above on why ORM-attribute assignment can't fake this.
        session.execute(
            text("UPDATE leads SET call_attempts = NULL WHERE id = :id"), {"id": "cb_2"}
        )
        session.commit()
        session.close()

        delayed = []
        monkeypatch.setattr(ct.make_call_task, "delay", lambda data: delayed.append(data))

        result = ct.process_callbacks()

        assert result["status"] == "completed"
        assert result["callbacks_queued"] == 2
        assert len(delayed) == 2

        check = Session()
        try:
            cb1 = check.query(Lead).filter(Lead.id == "cb_1").one()
            cb2 = check.query(Lead).filter(Lead.id == "cb_2").one()
            # both commits must have landed — a TypeError on cb_2's None would
            # previously abort db.commit() for the whole batch, including cb_1.
            assert cb1.call_attempts == 1 and cb1.last_called_at is not None
            assert cb2.call_attempts == 1 and cb2.last_called_at is not None
        finally:
            check.close()
    finally:
        try:
            session.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# admin_ops.py::launch_campaign — Celery-preferred, subprocess-fallback, lock
# --------------------------------------------------------------------------- #
def test_launch_campaign_rejects_bad_limit(client):
    r = client.post("/api/admin/campaign/launch", json={"limit": 0})
    assert r.status_code == 400


def test_launch_campaign_prefers_celery(client, monkeypatch):
    class _FakeAsyncResult:
        id = "task-abc-123"

    class _FakeCeleryApp:
        def send_task(self, name, kwargs=None):
            assert name == "app.tasks.calling.run_campaign_task"
            assert kwargs["limit"] == 7
            return _FakeAsyncResult()

    import app.tasks.calling as ct
    import app.worker as worker_mod

    monkeypatch.setattr(ct, "campaign_lock_held", lambda: False)
    monkeypatch.setattr(ct, "acquire_campaign_lock", lambda ttl_s=400: True)
    monkeypatch.setattr(worker_mod, "celery_app", _FakeCeleryApp())

    r = client.post("/api/admin/campaign/launch", json={"limit": 7, "dry_run": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["queued"] is True
    assert data["via"] == "celery"
    assert data["task_id"] == "task-abc-123"


def test_launch_campaign_refuses_second_launch_while_running(client, monkeypatch):
    import app.tasks.calling as ct

    monkeypatch.setattr(ct, "campaign_lock_held", lambda: True)

    r = client.post("/api/admin/campaign/launch", json={"limit": 5})
    assert r.status_code == 409


def test_launch_campaign_falls_back_to_subprocess_when_celery_down(client, monkeypatch):
    import app.tasks.calling as ct
    import app.worker as worker_mod

    monkeypatch.setattr(ct, "campaign_lock_held", lambda: False)
    monkeypatch.setattr(ct, "acquire_campaign_lock", lambda ttl_s=400: True)

    class _BrokenCeleryApp:
        def send_task(self, *a, **k):
            raise RuntimeError("broker unreachable")

    monkeypatch.setattr(worker_mod, "celery_app", _BrokenCeleryApp())

    r = client.post("/api/admin/campaign/launch", json={"limit": 5, "dry_run": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["queued"] is True
    assert data["via"] == "subprocess_fallback"
