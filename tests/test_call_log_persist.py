"""Tests for the post-call CallLog persistence hook (roadmap P1 analytics DB).

Covers the pure mapping (`build_call_log`) and the never-raise / idempotent
insert (`persist_call_log`) without needing a live database — `persist_call_log`
runs its sync insert through a fake session injected via monkeypatch.
"""

from __future__ import annotations

import os

from app.telephony import post_call_hooks as pch


# --------------------------------------------------------------------------- #
# build_call_log — pure mapping
# --------------------------------------------------------------------------- #
def test_build_call_log_qualified_mapping(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    from app.models.call_log import CallOutcome

    q = {
        "interest_score": 4,  # 1-5 → 0-100 (×20) = 80
        "qualified": True,
        "appointment_requested": False,
        "summary": "Customer interested in growth plan",
    }
    row = pch.build_call_log(
        call_id="sid-1",
        provider="vobiz",
        phone="+919812345678",
        client_id="c1",
        niche="salon",
        duration_s=42.0,
        user_turns=6,
        outcome="completed",
        q=q,
    )
    assert row is not None
    assert row.call_sid == "sid-1"
    assert row.provider == "vobiz"
    assert row.to_number == "+919812345678"
    assert row.lead_score == 80
    assert row.is_hot_lead is True
    assert row.outcome == CallOutcome.INTERESTED
    assert row.duration_seconds == 42
    assert "Customer interested" in (row.summary or "")
    # raw id is stashed inside qualification_data (FK-safe — column left NULL here)
    assert "raw_client_id" in (row.qualification_data or "")


def test_build_call_log_appointment_outcome(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    from app.models.call_log import CallOutcome

    q = {"interest_score": 5, "qualified": True, "appointment_requested": True, "summary": "Booked"}
    row = pch.build_call_log(
        call_id="sid-2",
        provider="phone",
        phone="+910000000000",
        duration_s=30.0,
        user_turns=4,
        outcome="completed",
        q=q,
    )
    assert row is not None
    assert row.outcome == CallOutcome.APPOINTMENT
    assert row.appointment_scheduled is True
    assert row.lead_score == 100


def test_build_call_log_none_q_no_answer(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    from app.models.call_log import CallOutcome

    # No qualification, zero user turns → NO_ANSWER, empty phone → NOT-NULL fallback.
    row = pch.build_call_log(
        call_id="sid-3",
        provider="vobiz",
        phone="",
        duration_s=3.0,
        user_turns=0,
        outcome="no_answer",
        q=None,
    )
    assert row is not None
    assert row.outcome == CallOutcome.NO_ANSWER
    assert row.lead_score == 0
    assert row.is_hot_lead is False
    assert row.to_number == "unknown"  # column is NOT NULL
    assert row.summary is None


def test_build_call_log_flag_off_returns_none(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "0")
    row = pch.build_call_log(
        call_id="sid-x",
        provider="vobiz",
        phone="+91",
        duration_s=1.0,
        user_turns=1,
        q=None,
    )
    assert row is None


# --------------------------------------------------------------------------- #
# persist_call_log — never-raise + idempotent (fake session)
# --------------------------------------------------------------------------- #
class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._result


class _FakeSession:
    """Minimal stand-in for the get_db_session context manager."""

    def __init__(self, existing_first=None):
        self.added: list = []
        self._existing_first = existing_first

    def query(self, *a, **k):
        return _FakeQuery(self._existing_first)

    def get(self, *a, **k):
        return None  # FK existence check → not found → client_id stays NULL

    def add(self, row):
        self.added.append(row)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


async def test_persist_call_log_inserts(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    fake = _FakeSession(existing_first=None)
    monkeypatch.setattr("app.models.base.get_db_session", lambda: fake)

    await pch.persist_call_log(
        call_id="ins-1",
        provider="vobiz",
        phone="+9111",
        client_id="missing",
        duration_s=10.0,
        user_turns=2,
        outcome="completed",
        q={"interest_score": 3, "qualified": True, "summary": "ok"},
    )
    assert len(fake.added) == 1
    # dangling client_id was NOT linked (FK-safe): stays NULL on the row
    assert fake.added[0].client_id is None


async def test_persist_call_log_idempotent(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    fake = _FakeSession(existing_first=("already-here",))  # call_sid already present
    monkeypatch.setattr("app.models.base.get_db_session", lambda: fake)

    await pch.persist_call_log(
        call_id="dup-1",
        provider="vobiz",
        phone="+9111",
        duration_s=10.0,
        user_turns=2,
        outcome="completed",
        q=None,
    )
    assert fake.added == []  # no duplicate insert


async def test_persist_call_log_never_raises_on_db_error(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")

    def _boom():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("app.models.base.get_db_session", _boom)
    # Must swallow the error — call teardown must never break on analytics.
    await pch.persist_call_log(
        call_id="err-1",
        provider="vobiz",
        phone="+9111",
        duration_s=5.0,
        user_turns=1,
        outcome="completed",
        q=None,
    )


async def test_persist_call_log_flag_off_noop(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "0")
    fake = _FakeSession(existing_first=None)
    monkeypatch.setattr("app.models.base.get_db_session", lambda: fake)
    await pch.persist_call_log(
        call_id="off-1",
        provider="vobiz",
        phone="+9111",
        duration_s=5.0,
        user_turns=1,
        outcome="completed",
        q=None,
    )
    assert fake.added == []  # flag off → build returns None → no DB touch
