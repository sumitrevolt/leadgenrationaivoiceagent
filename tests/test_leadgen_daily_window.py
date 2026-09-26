"""Tests for app.platform.leadgen_daily_window — LeadGen IST 09:00–20:00 window,
5-channel concurrent allocation, retry budget, and self-heal.

REWRITE 2026-09-25: durable state lives in two new SQLite tables inside
the existing approved ``data/orchestrator_ledger.db`` (NOT in
``data/leadgen_*.json``). Tests use the real DB, not mocks — the SQLite
guarantees that two workers / processes cannot accidentally over-allocate.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from app.platform.leadgen_daily_window import (
    CHANNEL_CAP,
    DB_PATH,
    ChannelLedger,
    RetryLedger,
    ack,
    evaluate_window,
    preflight,
    safe_self_heal,
)


def set_ist_time(year, month, day, hour, minute=0, second=0):
    iso = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"
    os.environ["IST_OVERRIDE"] = iso


@pytest.fixture(autouse=True)
def _clear_ist():
    os.environ.pop("IST_OVERRIDE", None)
    yield
    os.environ.pop("IST_OVERRIDE", None)


# Per-test isolation: clear the two new tables.
@pytest.fixture(autouse=True)
def _clean_tables():
    from app.platform.leadgen_daily_window import _conn, _ensure_schema
    _ensure_schema()
    conn = _conn()
    try:
        conn.execute("DELETE FROM leadgen_channel_leases")
        conn.execute("DELETE FROM leadgen_retry_budget")
    finally:
        conn.close()
    yield


def test_db_path_is_the_approved_orchestrator_ledger():
    # Sanity: our DB is the already-approved canonical store
    assert "orchestrator_ledger.db" in DB_PATH


def test_window_inside_09_to_20():
    set_ist_time(2026, 9, 25, 12, 0)
    w = evaluate_window()
    assert w.in_window is True
    assert w.post_window_hard_stop is False
    assert w.reason == "inside_operational_window"


def test_window_before_09_is_outside_with_pre_window_ready():
    set_ist_time(2026, 9, 25, 8, 56)
    w = evaluate_window()
    assert w.pre_window_ready is True
    assert w.reason == "pre_window_ready"


def test_window_at_20_00_is_post_window_hard_stop():
    set_ist_time(2026, 9, 25, 20, 0)
    w = evaluate_window()
    assert w.post_window_hard_stop is True
    assert w.reason == "post_window_hard_stop"


def test_window_at_08_54_is_not_pre_window_ready():
    set_ist_time(2026, 9, 25, 8, 54)
    w = evaluate_window()
    assert w.pre_window_ready is False


# ----- Channel ledger: 5-channel concurrent allocation -----

def test_channel_ledger_starts_with_5_available():
    cl = ChannelLedger()
    assert cl.available() == CHANNEL_CAP == 5


def test_channel_ledger_acquires_release_returns_to_5():
    cl = ChannelLedger()
    assert cl.acquire("DID_872", "lead_A") is True
    assert cl.available() == 4
    assert cl.release("DID_872", "lead_A") is True
    assert cl.available() == 5


def test_channel_ledger_caps_at_5_concurrent():
    cl = ChannelLedger()
    dids = ["DID_872", "DID_874", "DID_875", "DID_877", "DID_881"]
    for did in dids:
        assert cl.acquire(did, "lead_X") is True
    assert cl.available() == 0
    assert cl.acquire("DID_999", "lead_X") is False


def test_channel_ledger_refuses_double_hold_same_did_to_other_lead():
    cl = ChannelLedger()
    assert cl.acquire("DID_872", "lead_A") is True
    assert cl.acquire("DID_872", "lead_B") is False


def test_channel_ledger_allows_same_lead_to_refresh():
    cl = ChannelLedger()
    assert cl.acquire("DID_872", "lead_A") is True
    assert cl.acquire("DID_872", "lead_A") is True


def test_channel_ledger_durable_across_ChannelLedger_instances():
    """The data is in SQLite; a second ChannelLedger() sees the same row."""
    cl1 = ChannelLedger()
    assert cl1.acquire("DID_872", "lead_A") is True
    cl2 = ChannelLedger()
    assert cl2.available() == 4
    assert cl2.release("DID_872", "lead_A") is True
    cl3 = ChannelLedger()
    assert cl3.available() == 5


def test_channel_ledger_two_threads_no_overallocation():
    """Simulates two workers contending for the same channel concurrently.

    SQLite's BEGIN IMMEDIATE + the module-level lock + INSERT ... PRIMARY KEY
    guarantee that only one of the two competing acquires succeeds.
    """
    cl = ChannelLedger()
    results: list[bool] = []
    barrier = threading.Barrier(2)

    def worker(lead_id: str) -> None:
        barrier.wait()
        ok = cl.acquire("DID_872", lead_id)
        results.append(ok)

    t1 = threading.Thread(target=worker, args=("lead_A",))
    t2 = threading.Thread(target=worker, args=("lead_B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = sum(1 for r in results if r)
    assert successes == 1, f"expected exactly 1 success, got {results}"


# ----- Retry ledger -----

def test_retry_ledger_allows_3_attempts_then_blocks():
    rl = RetryLedger()
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is False


def test_retry_ledger_separate_days_isolated():
    rl = RetryLedger()
    for _ in range(3):
        rl.attempt("lead_1", "DID_872", "2026-09-25")
    assert rl.attempt("lead_1", "DID_872", "2026-09-26") is True


def test_retry_ledger_separate_channels_isolated():
    rl = RetryLedger()
    for _ in range(3):
        rl.attempt("lead_1", "DID_872", "2026-09-25")
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is False
    assert rl.attempt("lead_1", "DID_874", "2026-09-25") is True


def test_retry_ledger_remaining_calculation():
    rl = RetryLedger()
    assert rl.remaining("lead_1", "DID_872", "2026-09-25") == 3
    rl.attempt("lead_1", "DID_872", "2026-09-25")
    assert rl.remaining("lead_1", "DID_872", "2026-09-25") == 2


# ----- preflight -----

def test_preflight_passes_inside_window_with_capacity():
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = ChannelLedger(), RetryLedger()
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        channel_ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is True
    assert res.channel_acquired is True
    assert res.retry_allowed is True
    assert res.window.in_window is True
    ack("DID_872", "lead_1", (cl, rl))


def test_preflight_blocks_outside_window():
    set_ist_time(2026, 9, 25, 21, 30)
    cl, rl = ChannelLedger(), RetryLedger()
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        channel_ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert any("post-20:00 IST" in r for r in res.reasons_to_block)


def test_preflight_blocks_dnd_fail():
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = ChannelLedger(), RetryLedger()
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=False, consent_check_passed=True,
        channel_ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert "dnd_check_failed" in res.reasons_to_block


def test_preflight_blocks_consent_fail():
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = ChannelLedger(), RetryLedger()
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=False,
        channel_ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert "consent_check_failed" in res.reasons_to_block


def test_preflight_blocks_when_channel_unavailable():
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = ChannelLedger(), RetryLedger()
    for did in ["DID_872", "DID_874", "DID_875", "DID_877", "DID_881"]:
        cl.acquire(did, f"other_lead_{did}")
    res = preflight(
        channel_id="DID_999", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        channel_ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert any("channel_unavailable" in r or "cap_reached" in r
               for r in res.reasons_to_block)


def test_preflight_blocks_when_retry_budget_exhausted():
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = ChannelLedger(), RetryLedger()
    for _ in range(3):
        rl.attempt("lead_1", "DID_872", "2026-09-25")
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        channel_ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert any("retry_budget_exhausted" in r for r in res.reasons_to_block)


# ----- self-heal -----

def test_safe_self_heal_releases_stale_leases():
    cl = ChannelLedger()
    cl.acquire("DID_872", "lead_1", ttl_seconds=1)
    time.sleep(1.2)
    released = safe_self_heal(cl)
    assert released >= 1
    assert cl.available() == 5
