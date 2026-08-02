"""Session-scoped call limiter tests (app/telephony/voice_launch.py + dialer).

Mission contract:
  * EXACTLY VOICE_CALLS_PER_SESSION (default 30) provider-attempts per session
  * counter Redis-backed → worker/scheduler restart RESET nahi karta
  * reset SIRF canonical create_voice_session() lifecycle se
  * attempt 31 provider boundary se PEHLE blocked (session_limit_reached)
  * concurrent dispatches → at most cap provider calls
  * emergency session stop blocks new reservations
  * attempted/connected/answered/failed/retried/completed counted ALAG se
  * operator-visible used / cap / remaining

Same conventions as tests/test_voice_launch.py: async via asyncio.run(), fake
in-process redis (extended with SET NX for idempotency).
"""

import asyncio

import pytest

from app.telephony import voice_launch as vl
from app.telephony.voice_launch import CampaignState, VoiceDisposition


def _run(coro):
    return asyncio.run(coro)


class _FakeRedis:
    """In-process async redis: incr/get/set(ex,nx)/expire/delete."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        v = int(self.store.get(key, "0")) + 1
        self.store[key] = str(v)
        return v

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.ttl[key] = ex
        return True

    async def expire(self, key: str, seconds: int):
        self.ttl[key] = seconds

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
            self.ttl.pop(k, None)


def _async(value):
    async def _coro():
        return value

    return _coro()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "VOICE_LAUNCH_CAMPAIGN",
        "VOICE_LAUNCH_KILL",
        "VOICE_DAILY_CALL_CAP",
        "VOICE_CALLS_PER_SESSION",
        "VOICE_TEST_DAILY_CAP",
        "VOICE_CALL_CONCURRENCY",
        "VOICE_TRAIN_BATCH",
        "VOICE_CIRCUIT_FAIL_THRESHOLD",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    yield


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def test_session_cap_default_and_ceiling(monkeypatch):
    assert vl.session_cap() == 30
    monkeypatch.setenv("VOICE_CALLS_PER_SESSION", "500")  # over ceiling
    assert vl.session_cap() == 200  # hard-clamped
    monkeypatch.setenv("VOICE_CALLS_PER_SESSION", "12")
    assert vl.session_cap() == 12


# --------------------------------------------------------------------------- #
# Session lifecycle: create / current / reset semantics
# --------------------------------------------------------------------------- #
def test_create_session_sets_current_and_zero_counter(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="alice", niche="coaching", label="launch"))
    assert sid.startswith("S")
    assert _run(vl.current_session_id()) == sid
    assert _run(vl.session_attempts(sid)) == 0
    meta = _run(vl.get_session_meta(sid))
    assert meta.get("owner") == "alice"
    assert meta.get("niche") == "coaching"
    assert meta.get("cap") == 30


def test_worker_restart_does_not_reset_counter(monkeypatch):
    """Counter Redis-backed hai — 'restart' = same redis, koi lifecycle call nahi
    → count preserve. SIRF create_voice_session reset karta hai."""
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))
    for _ in range(7):
        _run(vl.reserve_session_slot(sid))
    assert _run(vl.session_attempts(sid)) == 7
    # worker 'restart': koi create/reset nahi
    assert _run(vl.session_attempts(sid)) == 7
    assert _run(vl.current_session_id()) == sid


def test_new_session_lifecycle_resets_counter(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid1 = _run(vl.create_voice_session(owner="test"))
    for _ in range(10):
        _run(vl.reserve_session_slot(sid1))
    assert _run(vl.session_attempts(sid1)) == 10
    # canonical reset = new lifecycle (new sid, counter 0, current points there)
    sid2 = _run(vl.create_voice_session(owner="test"))
    assert sid2 != sid1
    assert _run(vl.current_session_id()) == sid2
    assert _run(vl.session_attempts(sid2)) == 0


# --------------------------------------------------------------------------- #
# Atomic reservation: exactly cap, then block at cap+1 with clear reason
# --------------------------------------------------------------------------- #
def test_exactly_cap_reservations_then_31st_blocked(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))
    results = [_run(vl.reserve_session_slot(sid)) for _ in range(31)]
    assert all(r.ok for r in results[:30])
    assert results[29].count == 30
    blocked = results[30]
    assert blocked.ok is False
    assert blocked.reason == "session_limit_reached"
    # counter pin + no over-count (rollback)
    assert _run(vl.session_attempts(sid)) == 30


def test_concurrent_reservations_still_exactly_cap(monkeypatch):
    """Concurrent dispatch (asyncio.gather, 2x cap attempts) → at most cap ok."""
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))

    async def _hammer():
        return await asyncio.gather(*(vl.reserve_session_slot(sid) for _ in range(60)))

    out = _run(_hammer())
    ok = [r for r in out if r.ok]
    blocked = [r for r in out if not r.ok]
    assert len(ok) == 30
    assert len(blocked) == 30
    assert all(r.reason == "session_limit_reached" for r in blocked)
    assert _run(vl.session_attempts(sid)) == 30


def test_no_session_fail_closed(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    slot = _run(vl.reserve_session_slot(None))
    assert slot.ok is False and slot.reason == "no_session"


def test_redis_down_fail_closed(monkeypatch):
    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(vl, "_redis", lambda: _boom())
    sid = "S20260802-deadbeef"
    slot = _run(vl.reserve_session_slot(sid))
    assert slot.ok is False and slot.reason == "counter_unavailable"
    assert _run(vl.session_attempts(sid)) == -1


# --------------------------------------------------------------------------- #
# Emergency stop
# --------------------------------------------------------------------------- #
def test_session_stop_blocks_new_reservations(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))
    _run(vl.reserve_session_slot(sid))
    assert _run(vl.session_is_stopped(sid)) is False
    assert _run(vl.session_stop(sid)) is True
    assert _run(vl.session_is_stopped(sid)) is True
    slot = _run(vl.reserve_session_slot(sid))
    assert slot.ok is False and slot.reason == "session_stopped"
    # used count not inflated by blocked reservation
    assert _run(vl.session_attempts(sid)) == 1


def test_session_status_reflects_stop(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))
    _run(vl.session_stop(sid))
    st = _run(vl.session_status(sid))
    assert st["stopped"] is True
    assert st["state"] == "session_stopped"
    assert st["active"] is False


# --------------------------------------------------------------------------- #
# Idempotency keys (survive worker restart via Redis)
# --------------------------------------------------------------------------- #
def test_idem_claim_once_then_duplicate_blocked(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))
    assert _run(vl.session_idem_claim(sid, "lead:1001")) is True
    assert _run(vl.session_idem_claim(sid, "lead:1001")) is False  # duplicate/retry
    assert _run(vl.session_idem_claim(sid, "lead:1002")) is True  # different key ok
    _run(vl.session_idem_release(sid, "lead:1001"))
    assert _run(vl.session_idem_claim(sid, "lead:1001")) is True  # re-claimable


def test_idem_claim_fail_closed_on_redis_down(monkeypatch):
    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(vl, "_redis", lambda: _boom())
    assert _run(vl.session_idem_claim("s", "lead:1")) is False  # fail-closed


# --------------------------------------------------------------------------- #
# Disposition tally (attempted/connected/answered/failed/retried separate)
# --------------------------------------------------------------------------- #
def test_session_disposition_and_retry_counts(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))
    _run(vl.reserve_session_slot(sid))
    _run(vl.reserve_session_slot(sid))
    _run(vl.record_session_disposition(sid, "answered"))
    _run(vl.record_session_disposition(sid, "answered"))
    _run(vl.record_session_disposition(sid, "failed"))
    _run(vl.record_session_retry_blocked(sid))
    _run(vl.record_session_retry_blocked(sid))
    st = _run(vl.session_status(sid))
    assert st["used"] == 2
    assert st["attempted"] == 2
    assert st["answered"] == 2
    assert st["connected"] == 2
    assert st["completed"] == 2
    assert st["failed"] == 1
    assert st["retried_blocked"] == 2
    assert st["dispositions"]["answered"] == 2
    assert st["dispositions"]["failed"] == 1


def test_session_status_shape_running_then_limit(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    sid = _run(vl.create_voice_session(owner="test"))
    st = _run(vl.session_status(sid))
    assert st["session_id"] == sid
    assert st["cap"] == 30
    assert st["used"] == 0
    assert st["remaining"] == 30
    assert st["state"] == "running"
    assert st["active"] is True
    for _ in range(30):
        _run(vl.reserve_session_slot(sid))
    st = _run(vl.session_status(sid))
    assert st["used"] == 30 and st["remaining"] == 0
    assert st["state"] == "session_limit_reached"


# --------------------------------------------------------------------------- #
# Dialer integration — session cap wired at the dispatch boundary
# --------------------------------------------------------------------------- #
def _prospects(n):
    from types import SimpleNamespace

    return [
        SimpleNamespace(id=f"lead{i}", phone=f"+9198765{i:05d}", niche="ai_marketing")
        for i in range(n)
    ]


def _wire_dialer(monkeypatch, fake, *, placed=True, error="", ssc_calls=None):
    """Common monkeypatches: fresh atomic counter, always-eligible, fast no-sleep,
    vobiz available, canned start_stream_call (records calls if ssc_calls list)."""
    import app.tasks.calling as calling

    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))

    async def _elig(*a, **k):
        return vl.EligibilityResult(True, vl.SkipReason.NONE, {})

    monkeypatch.setattr(vl, "is_lead_eligible_for_voice_call", _elig)

    async def _ssc(*a, **k):
        if ssc_calls is not None:
            ssc_calls.append(a)
        return {"placed": placed, "error": error}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _ssc)
    monkeypatch.setattr("app.telephony.vobiz_handler.VobizClient.available", lambda self: True)

    async def _nosleep(*a, **k):
        return None

    monkeypatch.setattr(calling.asyncio, "sleep", _nosleep)
    return calling


def _fake_db():
    from unittest.mock import MagicMock

    return MagicMock()


def test_dialer_enforces_session_cap(monkeypatch):
    fake = _FakeRedis()
    calling = _wire_dialer(monkeypatch, fake)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    monkeypatch.setenv("VOICE_CALLS_PER_SESSION", "2")
    sid = _run(vl.create_voice_session(owner="test"))
    assert _run(vl.current_session_id()) == sid
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(5), False, "promotional", "", True)
    )
    assert out["ok"] == 2
    assert out.get("state") == "session_limit_reached"
    assert _run(vl.session_attempts(sid)) == 2


def test_dialer_31st_blocked_before_any_provider_request(monkeypatch):
    """Session exhausted (30 pre-reserved) → loop ke andar attempt 31 provider
    boundary se PEHLE block — start_stream_call kabhi call nahi hota."""
    fake = _FakeRedis()
    ssc_calls: list = []
    calling = _wire_dialer(monkeypatch, fake, ssc_calls=ssc_calls)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    monkeypatch.setenv("VOICE_CALLS_PER_SESSION", "30")
    sid = _run(vl.create_voice_session(owner="test"))
    for _ in range(30):
        _run(vl.reserve_session_slot(sid))
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(3), False, "promotional", "", True)
    )
    assert out["ok"] == 0
    assert out.get("state") == "session_limit_reached"
    assert ssc_calls == []  # provider request NEVER fired
    assert _run(vl.session_attempts(sid)) == 30


def test_dialer_session_stop_blocks_dispatch(monkeypatch):
    fake = _FakeRedis()
    ssc_calls: list = []
    calling = _wire_dialer(monkeypatch, fake, ssc_calls=ssc_calls)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    sid = _run(vl.create_voice_session(owner="test"))
    _run(vl.session_stop(sid))
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(2), False, "promotional", "", True)
    )
    assert out["ok"] == 0
    assert out.get("state") == "session_stopped"
    assert ssc_calls == []


def test_dialer_idempotency_prevents_redial_after_restart(monkeypatch):
    """Worker crash between claim and provider call simulated: claim already held
    (same session Redis) → lead SKIPPED, at-most-once, no double provider call."""
    fake = _FakeRedis()
    ssc_calls: list = []
    calling = _wire_dialer(monkeypatch, fake, ssc_calls=ssc_calls)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    sid = _run(vl.create_voice_session(owner="test"))
    # crash-after-claim: lead0 ka claim pehle hi held hai
    assert _run(vl.session_idem_claim(sid, "lead:lead0")) is True
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(2), False, "promotional", "", True)
    )
    assert out["ok"] == 1  # sirf lead1 dialed
    assert out["skip"] == 1  # lead0 duplicate blocked
    assert len(ssc_calls) == 1
    assert _run(vl.session_attempts(sid)) == 1  # daily+session released for lead0


def test_dialer_compliance_block_releases_session_slot(monkeypatch):
    fake = _FakeRedis()
    calling = _wire_dialer(monkeypatch, fake, placed=False, error="compliance_blocked")
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    sid = _run(vl.create_voice_session(owner="test"))
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(2), False, "promotional", "", True)
    )
    assert out["ok"] == 0 and out["skip"] == 2
    assert _run(vl.session_attempts(sid)) == 0  # reserved-but-never-dispatched rolled back


def test_dialer_daily_cap_still_enforced_before_session(monkeypatch):
    """Daily cap lower than session cap → daily wins (aggregate backstop)."""
    fake = _FakeRedis()
    calling = _wire_dialer(monkeypatch, fake)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "2")
    monkeypatch.setenv("VOICE_CALLS_PER_SESSION", "30")
    sid = _run(vl.create_voice_session(owner="test"))
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(5), False, "promotional", "", True)
    )
    assert out["ok"] == 2
    assert out.get("state") == "daily_limit_reached"
    assert _run(vl.session_attempts(sid)) == 2
