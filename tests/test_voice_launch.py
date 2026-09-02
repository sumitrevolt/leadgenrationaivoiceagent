"""Tests for the controlled voice-calling launch spine (app/telephony/voice_launch.py).

Covers: NUP/disposition canonicalization + counting policy, atomic daily cap
(fail-CLOSED when counter unavailable), 30-call training boundaries, per-lead
eligibility fail-CLOSED composition, and the campaign-state resolver.

Async checks via asyncio.run() (no pytest-asyncio plugin needed) — matches
tests/test_compliance.py convention.
"""

import asyncio

import pytest

from app.telephony import voice_launch as vl
from app.telephony.voice_launch import CampaignState, SkipReason, VoiceDisposition


def _run(coro):
    return asyncio.run(coro)


class _FakeRedis:
    """In-process async redis stand-in: incr/get/set/expire/delete + SET NX (for
    session idempotency claims)."""

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


@pytest.fixture
def kill_disengaged(_clean_env, monkeypatch):
    """Opt-in: disengage the admin kill for tests about OTHER gates.

    Depends on `_clean_env` explicitly: that autouse fixture DELETES
    VOICE_LAUNCH_KILL, so without the ordering dependency it could wipe this
    setting right after it is applied.

    The kill reader is fail-CLOSED — a missing/unreadable/malformed authority
    file engages it. These tests predate that and relied on "no kill file"
    meaning "safe to dial", which is exactly the assumption this workstream
    removed. Rather than weaken the reader, each affected test now states its
    precondition explicitly.

    Deliberately NOT autouse: a global disengage would silently re-open the
    fail-open hole for every future test in this file.
    """
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    for k in (
        "VOICE_LAUNCH_KILL",
        "VOICE_DAILY_CALL_CAP",
        "VOICE_CALLS_PER_SESSION",
        "VOICE_TEST_DAILY_CAP",
        "VOICE_CALL_CONCURRENCY",
        "VOICE_TRAIN_BATCH",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


# --------------------------------------------------------------------------- #
# NUP + disposition canonicalization / counting policy
# --------------------------------------------------------------------------- #
def test_nup_aliases_map_to_nup():
    for raw in ("NUP", "unobtainable", "unallocated", "number_unobtainable", "congestion"):
        assert vl.normalize_disposition(raw) is VoiceDisposition.NUP


def test_unknown_disposition_is_failed_and_counts():
    assert vl.normalize_disposition("wat_is_this") is VoiceDisposition.FAILED
    assert vl.disposition_counts_toward_cap("wat_is_this") is True


def test_every_provider_accepted_attempt_counts_toward_cap():
    # answered / nup / busy / failed / rejected / no_answer all count
    for raw in ("answered", "nup", "busy", "failed", "rejected", "no_answer", "voicemail"):
        assert vl.disposition_counts_toward_cap(raw) is True, raw


def test_pre_dial_skip_does_not_count():
    assert vl.disposition_counts_toward_cap("skipped") is False
    assert vl.disposition_counts_toward_cap(VoiceDisposition.SKIPPED) is False


def test_only_answered_is_connect():
    assert vl.disposition_is_connect("answered") is True
    assert vl.disposition_is_connect("nup") is False
    assert vl.disposition_is_connect("no_answer") is False


# --------------------------------------------------------------------------- #
# Daily cap (atomic + fail-CLOSED) + training boundaries
# --------------------------------------------------------------------------- #
def test_daily_cap_default_and_ceiling(monkeypatch):
    assert vl.daily_cap("campaign") == 100
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "500")  # over ceiling
    assert vl.daily_cap("campaign") == 100  # hard-clamped
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "40")
    assert vl.daily_cap("campaign") == 40
    assert vl.daily_cap("test") == 25  # separate quota


def test_reserve_call_slot_enforces_cap(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "3")

    r1 = _run(vl.reserve_call_slot("campaign"))
    r2 = _run(vl.reserve_call_slot("campaign"))
    r3 = _run(vl.reserve_call_slot("campaign"))
    r4 = _run(vl.reserve_call_slot("campaign"))
    assert (r1.ok, r2.ok, r3.ok) == (True, True, True)
    assert r1.count == 1 and r3.count == 3
    assert r4.ok is False and r4.reason == "daily_limit_reached"
    # counter must not stay inflated past the cap after a rejected reservation
    assert _run(vl.attempts_today("campaign")) == 3


def test_campaign_and_test_counters_are_separate(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    _run(vl.reserve_call_slot("campaign"))
    _run(vl.reserve_call_slot("test"))
    _run(vl.reserve_call_slot("test"))
    assert _run(vl.attempts_today("campaign")) == 1
    assert _run(vl.attempts_today("test")) == 2


def test_daily_cap_fail_closed_when_counter_unavailable(monkeypatch):
    async def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(vl, "_redis", lambda: _boom())
    # attempts unknown -> -1; cap considered reached (block)
    assert _run(vl.attempts_today("campaign")) == -1
    assert _run(vl.daily_cap_reached("campaign")) is True
    slot = _run(vl.reserve_call_slot("campaign"))
    assert slot.ok is False and slot.reason == "counter_unavailable"


def test_training_pause_boundaries():
    assert vl.training_batch_size() == 30
    assert vl.training_pause_due(30) is True
    assert vl.training_pause_due(60) is True
    assert vl.training_pause_due(90) is True
    assert vl.training_pause_due(31) is False
    assert vl.training_pause_due(0) is False
    assert vl.next_training_boundary(0) == 30
    assert vl.next_training_boundary(30) == 60
    assert vl.next_training_boundary(90) is None  # cap=100, next would be 120 > cap


# --------------------------------------------------------------------------- #
# Per-lead eligibility — fail-CLOSED composition
# --------------------------------------------------------------------------- #
def test_admin_kill_switch_blocks_everything(monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "1")
    res = _run(vl.is_lead_eligible_for_voice_call("+919876543210", "promotional"))
    assert res.eligible is False and res.reason == SkipReason.ADMIN_KILL


def test_no_phone_ineligible(kill_disengaged):
    res = _run(vl.is_lead_eligible_for_voice_call("", "promotional"))
    assert res.eligible is False and res.reason == SkipReason.NO_PHONE


def test_invalid_phone_ineligible(kill_disengaged):
    res = _run(vl.is_lead_eligible_for_voice_call("12345", "promotional"))
    assert res.eligible is False and res.reason == SkipReason.INVALID_PHONE


def test_promotional_blocked_by_dial_test_mode(kill_disengaged, monkeypatch):
    # dial_gate test-mode ON (default) + not allowlisted => promotional blocked
    monkeypatch.setenv("DIAL_TEST_MODE", "1")
    monkeypatch.setenv("DIAL_TEST_ALLOWLIST", "")
    res = _run(vl.is_lead_eligible_for_voice_call("+919876500000", "promotional"))
    assert res.eligible is False
    assert res.reason == SkipReason.DIAL_TEST_MODE


def test_allowlisted_promotional_reaches_compliance(kill_disengaged, monkeypatch):
    # allowlisted in dial_gate AND compliance -> eligibility decided by compliance.
    # Keep DLT unapproved so promotional is blocked at compliance (DLT), proving
    # the compliance chokepoint is actually consulted (not bypassed).
    monkeypatch.setenv("DIAL_TEST_MODE", "1")
    monkeypatch.setenv("DIAL_TEST_ALLOWLIST", "9876500000")
    monkeypatch.setenv("COMPLIANCE_ENABLED", "1")
    monkeypatch.setenv("COMPLIANCE_ALLOWLIST", "")
    monkeypatch.setenv("DLT_APPROVED", "0")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "")
    res = _run(vl.is_lead_eligible_for_voice_call("+919876500000", "promotional"))
    assert res.eligible is False
    assert res.reason in (
        SkipReason.DLT_NOT_APPROVED,
        SkipReason.DND_LOOKUP_FAILED,
        SkipReason.NO_CALLER_ID,
        SkipReason.OUTSIDE_WINDOW,
    )


# --------------------------------------------------------------------------- #
# Campaign-state resolver
# --------------------------------------------------------------------------- #
def test_state_disabled_when_flag_off(kill_disengaged, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "0")
    assert vl.resolve_campaign_state(configured=CampaignState.RUNNING) == CampaignState.DRAFT


def test_state_admin_kill_precedence(monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "1")
    assert (
        vl.resolve_campaign_state(configured=CampaignState.RUNNING) == CampaignState.PAUSED_BY_ADMIN
    )


def test_state_precedence_chain(kill_disengaged, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    assert (
        vl.resolve_campaign_state(configured=CampaignState.RUNNING, compliance_ok=False)
        == CampaignState.COMPLIANCE_BLOCKED
    )
    assert (
        vl.resolve_campaign_state(configured=CampaignState.RUNNING, circuit_open=True)
        == CampaignState.PAUSED_BY_CIRCUIT_BREAKER
    )
    assert (
        vl.resolve_campaign_state(configured=CampaignState.RUNNING, attempts=100, cap=100)
        == CampaignState.DAILY_LIMIT_REACHED
    )
    assert (
        vl.resolve_campaign_state(configured=CampaignState.RUNNING, training_pause=True)
        == CampaignState.PAUSED_FOR_TRAINING
    )
    assert vl.resolve_campaign_state(configured=CampaignState.PILOT) == CampaignState.PILOT


# --------------------------------------------------------------------------- #
# Runtime helpers: slot rollback, dispositions/NUP tally, circuit, recording
# --------------------------------------------------------------------------- #
def test_release_call_slot_rolls_back(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    _run(vl.reserve_call_slot("campaign"))
    _run(vl.reserve_call_slot("campaign"))
    assert _run(vl.attempts_today("campaign")) == 2
    _run(vl.release_call_slot("campaign"))
    assert _run(vl.attempts_today("campaign")) == 1


def test_disposition_tally_counts_nup(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    _run(vl.record_disposition("NUP", "campaign"))
    _run(vl.record_disposition("unobtainable", "campaign"))  # also NUP
    _run(vl.record_disposition("busy", "campaign"))
    counts = _run(vl.disposition_counts_today("campaign"))
    assert counts.get("nup") == 2
    assert counts.get("busy") == 1


def test_circuit_breaker_trips_on_failure_spike(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    monkeypatch.setenv("VOICE_CIRCUIT_FAIL_THRESHOLD", "3")
    assert _run(vl.circuit_open()) is False
    _run(vl.record_provider_result(False, "boom"))
    _run(vl.record_provider_result(False, "boom"))
    tripped = _run(vl.record_provider_result(False, "boom"))  # 3rd -> trip
    assert tripped is True
    assert _run(vl.circuit_open()) is True
    # a success resets the consecutive-failure streak
    _run(vl.reset_circuit())
    assert _run(vl.circuit_open()) is False


def test_compliance_blocked_is_not_a_provider_failure(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    monkeypatch.setenv("VOICE_CIRCUIT_FAIL_THRESHOLD", "2")
    _run(vl.record_provider_result(False, "compliance_blocked"))
    _run(vl.record_provider_result(False, "compliance_blocked"))
    assert _run(vl.circuit_open()) is False  # never counts as provider failure


def test_recording_gate_blocks_only_when_required(monkeypatch):
    # not required (default) -> ok regardless of health
    assert vl.recording_gate_ok()[0] is True
    monkeypatch.setenv("VOICE_RECORDING_REQUIRED", "1")
    monkeypatch.setattr(vl, "recording_path_healthy", lambda: False)
    ok, reason = vl.recording_gate_ok()
    assert ok is False and reason == "recording_path_unhealthy"
    monkeypatch.setattr(vl, "recording_path_healthy", lambda: True)
    assert vl.recording_gate_ok()[0] is True


def test_launch_status_shape(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "100")
    st = _run(vl.launch_status())
    for key in (
        "campaign_enabled",
        "admin_kill_engaged",
        "daily_cap",
        "attempts_today",
        "remaining_today",
        "concurrency_limit",
        "next_training_boundary",
        "circuit_open",
        "recording_ok",
        "state",
        "dispositions_today",
        "nup_today",
    ):
        assert key in st, key
    assert st["daily_cap"] == 100
    assert st["concurrency_limit"] == 1


# --------------------------------------------------------------------------- #
# Dialer integration — spine wired into _dial_vobiz_campaign
# --------------------------------------------------------------------------- #
def _prospects(n):
    from types import SimpleNamespace

    return [
        SimpleNamespace(id=f"lead{i}", phone=f"+9198765{i:05d}", niche="ai_marketing")
        for i in range(n)
    ]


def _wire_dialer(monkeypatch, fake, *, placed=True, error=""):
    """Common monkeypatches: fresh atomic counter, always-eligible, fast no-sleep,
    vobiz available, and a canned start_stream_call result."""
    import app.tasks.calling as calling

    monkeypatch.setattr(vl, "_redis", lambda: _async(fake))

    async def _elig(*a, **k):
        return vl.EligibilityResult(True, vl.SkipReason.NONE, {})

    monkeypatch.setattr(vl, "is_lead_eligible_for_voice_call", _elig)

    async def _ssc(*a, **k):
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


def test_dialer_kill_switch_blocks_before_any_call(monkeypatch):
    fake = _FakeRedis()
    calling = _wire_dialer(monkeypatch, fake)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "1")
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(3), False, "promotional", "", True)
    )
    assert out["ok"] == 0
    assert out.get("state") == "paused_by_admin"


def test_dialer_enforces_daily_cap(kill_disengaged, monkeypatch):
    fake = _FakeRedis()
    calling = _wire_dialer(monkeypatch, fake)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "3")
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(5), False, "promotional", "", True)
    )
    assert out["ok"] == 3  # cap stops the loop after 3 placed
    assert out.get("state") == "daily_limit_reached"
    assert _run(vl.attempts_today("campaign")) == 3


def test_dialer_training_pause_at_boundary(kill_disengaged, monkeypatch):
    fake = _FakeRedis()
    calling = _wire_dialer(monkeypatch, fake)
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "100")
    monkeypatch.setenv("VOICE_TRAIN_BATCH", "5")  # min batch floor is 5 -> pause at call 5
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(10), False, "promotional", "", True)
    )
    assert out["ok"] == 5
    assert out.get("state") == "paused_for_training"


def test_dialer_inert_when_flag_off_does_not_call_spine(kill_disengaged, monkeypatch):
    fake = _FakeRedis()
    calling = _wire_dialer(monkeypatch, fake)
    monkeypatch.delenv("VOICE_LAUNCH_CAMPAIGN", raising=False)  # spine OFF
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "0")

    def _boom(*a, **k):
        raise AssertionError("eligibility must NOT run when spine is INERT")

    monkeypatch.setattr(vl, "is_lead_eligible_for_voice_call", _boom)
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(2), False, "promotional", "", True)
    )
    assert out["ok"] == 2  # existing behaviour unchanged, all placed
    assert "state" not in out


def test_dialer_compliance_block_rolls_back_slot(monkeypatch):
    fake = _FakeRedis()
    # placed=False, error=compliance_blocked -> slot reserved then released
    calling = _wire_dialer(monkeypatch, fake, placed=False, error="compliance_blocked")
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")
    monkeypatch.delenv("VOICE_LAUNCH_KILL", raising=False)
    monkeypatch.setenv("VOICE_DAILY_CALL_CAP", "100")
    out = _run(
        calling._dial_vobiz_campaign(_fake_db(), _prospects(2), False, "promotional", "", True)
    )
    assert out["ok"] == 0 and out["skip"] == 2
    # every reservation rolled back -> cap not consumed by pre-dial blocks
    assert _run(vl.attempts_today("campaign")) == 0


def _async(value):
    async def _coro():
        return value

    return _coro()
