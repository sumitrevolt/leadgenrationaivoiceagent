"""OPS-014 PoC — inbound-session predicate (MEASUREMENT ONLY).

Research for OPS-010 found that customer-triggered ("Service Implicit") messages
are exempt from NCPR/DND scrubbing while promotional ones are not. If we ever
send into an inbound-initiated thread, the decision needs PROOF that the
customer opened it.

These tests pin the strictness of that predicate. Absence of proof must be
False — a "probably" here would be a compliance regression.

NOTE: this module is deliberately NOT wired into any send gate. A test that
makes it gate something is a spec change (OPS-014), not a test change.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.platform import wa_conversation as wc


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "wa_conversations.jsonl"
    monkeypatch.setattr(wc, "_CONV_FILE", str(path))
    yield path


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(number, direction, hours_ago):
    at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return {"from": number, "dir": direction, "text": "x", "at": at, "mid": ""}


def test_empty_store_has_no_session(store):
    assert wc.has_inbound_session("+919876543210") is False
    assert wc.last_inbound_at("+919876543210") is None
    assert wc.session_age_hours("+919876543210") is None


def test_recent_inbound_opens_session(store):
    _write(store, [_row("9876543210", "in", 1)])
    assert wc.has_inbound_session("+919876543210") is True


def test_expired_inbound_does_not_open_session(store):
    _write(store, [_row("9876543210", "in", 48)])
    assert wc.has_inbound_session("+919876543210") is False
    assert wc.session_age_hours("+919876543210") == pytest.approx(48, abs=0.2)


def test_outbound_only_does_not_open_session(store):
    # WE messaging first must never count as customer-initiated.
    _write(store, [_row("9876543210", "out", 1)])
    assert wc.has_inbound_session("+919876543210") is False


def test_number_variants_match_the_same_thread(store):
    _write(store, [_row("919876543210", "in", 1)])
    for variant in ("+919876543210", "9876543210", "9876543210@c.us"):
        assert wc.has_inbound_session(variant) is True, variant


def test_unusable_timestamp_is_not_proof(store):
    _write(store, [{"from": "9876543210", "dir": "in", "text": "x", "at": "not-a-date"}])
    assert wc.has_inbound_session("+919876543210") is False


def test_corrupt_rows_do_not_crash(store):
    with open(store, "w", encoding="utf-8") as fh:
        fh.write("{not json}\n")
        fh.write("\n")
        fh.write(json.dumps(_row("9876543210", "in", 2)) + "\n")
    assert wc.has_inbound_session("+919876543210") is True


def test_proof_shape_and_scope_note(store):
    _write(store, [_row("9876543210", "in", 3)])
    proof = wc.inbound_session_proof("+919876543210")
    assert proof["has_session"] is True
    assert proof["phone_key"] == "9876543210"
    assert proof["window_hours"] == wc.DEFAULT_SESSION_HOURS
    assert proof["source"] == "wa_conversation"
    assert "MEASUREMENT ONLY" in proof["note"]


def test_record_then_session(store):
    wc.record("+919876543210", "hello", "in", "mid-1")
    assert os.path.exists(store)
    assert wc.has_inbound_session("+919876543210") is True
    # And an outbound-only thread still never opens a window.
    store.unlink()
    wc.record("+919111111111", "hi", "out", "mid-2")
    assert wc.has_inbound_session("+919111111111") is False


def test_custom_window(store):
    _write(store, [_row("9876543210", "in", 5)])
    assert wc.has_inbound_session("+919876543210", hours=1) is False
    assert wc.has_inbound_session("+919876543210", hours=24) is True
