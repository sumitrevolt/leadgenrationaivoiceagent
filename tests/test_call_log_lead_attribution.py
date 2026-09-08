"""Lead attribution on the campaign call path (2026-08-06).

Regression cover for a silent, expensive gap: every `call_logs` row written by
the Vobiz stream teardown landed with ``lead_id = NULL``. The dialer had the
prospect's ``Lead.id`` in scope (``app/tasks/calling.py``) but
``start_stream_call`` had no lead-id parameter, so the id died at that boundary
— minutes later, in a possibly different worker, the CallLog writer only knew
the phone number.

Two things broke as a result:
  1. calls were unattributable to leads (no campaign ROI, no per-lead history);
  2. ``niche_database.update_after_call()`` — the ONLY code that moves a lead to
     QUALIFIED / CALLBACK / NOT_INTERESTED / DND / WRONG_NUMBER — is keyed on a
     lead id, so lead categorisation never ran on a single real call.

These tests pin the whole rail: dialer -> start_stream_call -> pending/answer-url
-> WS session -> persist_call_log -> CallLog.lead_id.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

from app.telephony import post_call_hooks as pch


# --------------------------------------------------------------------------- #
# build_call_log — the column that was always NULL
# --------------------------------------------------------------------------- #
def test_build_call_log_sets_lead_id(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    row = pch.build_call_log(
        call_id="sid-lead-1",
        provider="vobiz",
        phone="+919812345678",
        lead_id="lead-abc-123",
        duration_s=30.0,
        user_turns=4,
        outcome="completed",
    )
    assert row is not None
    assert row.lead_id == "lead-abc-123"
    # raw value is ALSO stashed in qualification_data, so attribution survives
    # even when the FK guard blanks the column for an unknown/stale id.
    assert "raw_lead_id" in (row.qualification_data or "")
    assert "lead-abc-123" in (row.qualification_data or "")


def test_build_call_log_lead_id_defaults_to_none(monkeypatch):
    """Omitting lead_id must stay valid — inbound and unknown-token WS
    reconnects genuinely have no lead in scope and must remain NULL-tolerant."""
    monkeypatch.setenv("CALL_LOG_DB", "1")
    row = pch.build_call_log(
        call_id="sid-lead-2",
        provider="vobiz",
        phone="+919812345678",
        outcome="completed",
    )
    assert row is not None
    assert row.lead_id is None


def test_build_call_log_blank_lead_id_is_none(monkeypatch):
    """Empty string must become NULL, never a bogus '' foreign key."""
    monkeypatch.setenv("CALL_LOG_DB", "1")
    row = pch.build_call_log(
        call_id="sid-lead-3",
        provider="vobiz",
        phone="+919812345678",
        lead_id="   ",
        outcome="completed",
    )
    assert row is not None
    assert row.lead_id is None


# --------------------------------------------------------------------------- #
# the answer-url rail that carries the id to the WS worker
# --------------------------------------------------------------------------- #
def test_answer_stream_qs_carries_crm_lead_id():
    from app.api.telephony_vobiz import _answer_stream_qs

    qs = parse_qs(_answer_stream_qs("salon", "c1", lead_phone="+919812345678", lead_id="lead-xyz"))
    assert qs["crm_lead_id"] == ["lead-xyz"]
    assert qs["lead_phone"] == ["+919812345678"]


def test_answer_stream_qs_omits_absent_lead_id():
    from app.api.telephony_vobiz import _answer_stream_qs

    qs = parse_qs(_answer_stream_qs("salon", "c1", lead_phone="+919812345678"))
    assert "crm_lead_id" not in qs


def test_wire_key_is_not_lead_id():
    """`lead_id` is already a PHONE alias in the WS customParameters loop
    (`vobiz_stream` treats it as _lead_phone). Shipping the CRM id under that
    name would silently overwrite the dialed number, so the wire key must stay
    `crm_lead_id`."""
    from app.api.telephony_vobiz import _answer_stream_qs

    qs = parse_qs(_answer_stream_qs("salon", None, lead_id="lead-xyz"))
    assert "lead_id" not in qs
    assert qs["crm_lead_id"] == ["lead-xyz"]


# --------------------------------------------------------------------------- #
# start_stream_call — the boundary where the id used to die
# --------------------------------------------------------------------------- #
def test_start_stream_call_threads_lead_id(monkeypatch):
    import app.api.telephony_vobiz as tv

    stored: dict[str, dict] = {}
    captured: dict[str, str] = {}

    class _FakeClient:
        def available(self):
            return True

        async def place_call(self, **kwargs):
            captured.update(answer_url=kwargs.get("answer_url", ""))
            return {"status_code": 200}

    async def _fake_store(token, data):
        stored[token] = data

    monkeypatch.setattr(tv, "VobizClient", _FakeClient)
    monkeypatch.setattr(tv, "_store_pending", _fake_store)

    res = asyncio.run(
        tv.start_stream_call(
            to="+919812345678", niche="salon", call_type="promotional", lead_id="lead-777"
        )
    )
    assert res["placed"] is True
    # survives BOTH rails: the cross-process pending blob and the answer-url
    # query string (either one alone is lost on a worker/reconnect race).
    assert list(stored.values())[0]["crm_lead_id"] == "lead-777"
    assert "crm_lead_id=lead-777" in captured["answer_url"]


def test_start_stream_call_without_lead_id_still_works(monkeypatch):
    """Backward compatibility: existing callers pass 4 args and must keep working."""
    import app.api.telephony_vobiz as tv

    stored: dict[str, dict] = {}

    class _FakeClient:
        def available(self):
            return True

        async def place_call(self, **kwargs):
            return {"status_code": 200}

    async def _fake_store(token, data):
        stored[token] = data

    monkeypatch.setattr(tv, "VobizClient", _FakeClient)
    monkeypatch.setattr(tv, "_store_pending", _fake_store)

    res = asyncio.run(tv.start_stream_call(to="+919812345678", niche="salon"))
    assert res["placed"] is True
    assert list(stored.values())[0]["crm_lead_id"] == ""


# --------------------------------------------------------------------------- #
# WS session holds the id under a name that cannot collide with the phone
# --------------------------------------------------------------------------- #
def test_stream_session_keeps_crm_lead_id_separate_from_phone():
    from app.telephony.vobiz_stream import VobizStreamSession

    s = VobizStreamSession(
        websocket=None,
        niche="salon",
        lead_phone="+919812345678",
        crm_lead_id="lead-999",
    )
    assert s._crm_lead_id == "lead-999"
    assert s._lead_phone == "+919812345678"


def test_stream_session_crm_lead_id_optional():
    from app.telephony.vobiz_stream import VobizStreamSession

    s = VobizStreamSession(websocket=None, niche="salon", lead_phone="+919812345678")
    assert s._crm_lead_id is None


# --------------------------------------------------------------------------- #
# persist_call_log — FK safety. A stale/unknown lead id must NOT abort the
# analytics INSERT; it must degrade to NULL and keep the raw value in
# qualification_data. Same contract client_id already had.
# --------------------------------------------------------------------------- #
class _FakeSession:
    """Records what would be committed; `get` decides whether the FK 'exists'."""

    def __init__(self, known_ids: set[str] | None = None):
        self.known = known_ids or set()
        self.added: list = []

    def get(self, _model, pk):
        return object() if pk in self.known else None

    def query(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return None  # no existing row for this call_sid -> not a duplicate

    def add(self, row):
        self.added.append(row)


def _patch_session(monkeypatch, session):
    import contextlib

    import app.models.base as mb

    @contextlib.contextmanager
    def _fake_ctx():
        yield session

    monkeypatch.setattr(mb, "get_db_session", _fake_ctx, raising=False)


def test_persist_call_log_keeps_known_lead_id(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    sess = _FakeSession(known_ids={"lead-real"})
    _patch_session(monkeypatch, sess)

    asyncio.run(
        pch.persist_call_log(
            call_id="sid-fk-1",
            provider="vobiz",
            phone="+919812345678",
            lead_id="lead-real",
            outcome="completed",
        )
    )
    assert len(sess.added) == 1
    assert sess.added[0].lead_id == "lead-real"


def test_persist_call_log_blanks_unknown_lead_id_and_still_inserts(monkeypatch):
    """The row is analytics data — losing it because of a stale FK would be a
    worse bug than the missing attribution it was meant to fix."""
    monkeypatch.setenv("CALL_LOG_DB", "1")
    sess = _FakeSession(known_ids=set())  # lead does NOT exist
    _patch_session(monkeypatch, sess)

    asyncio.run(
        pch.persist_call_log(
            call_id="sid-fk-2",
            provider="vobiz",
            phone="+919812345678",
            lead_id="lead-ghost",
            outcome="completed",
        )
    )
    assert len(sess.added) == 1, "row must still be written"
    assert sess.added[0].lead_id is None, "unknown FK must degrade to NULL"
    # attribution intent is not lost — raw id survives for later backfill
    assert "lead-ghost" in (sess.added[0].qualification_data or "")


# --------------------------------------------------------------------------- #
# Regression: the OTHER CallLog writer (call_manager, context-based) already
# set lead_id and must keep doing so — this fix threads a second rail, it does
# not replace that one.
# --------------------------------------------------------------------------- #
def test_call_manager_writer_still_sets_lead_id_from_context():
    import inspect

    from app.telephony import call_manager as cm

    src = inspect.getsource(cm)
    assert 'lead_id=getattr(context, "lead_id", None)' in src, (
        "call_manager's CallLog writer must keep sourcing lead_id from CallContext"
    )
