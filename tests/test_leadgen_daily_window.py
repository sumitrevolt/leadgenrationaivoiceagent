"""Tests for app.platform.leadgen_daily_window — LeadGen IST 09:00–20:00 window,
5-channel concurrent allocation, retry budget, and self-heal.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.platform.leadgen_daily_window import (
    CHANNEL_CAP,
    ChannelAvailabilityLedger,
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


def test_window_inside_09_to_20():
    set_ist_time(2026, 9, 25, 12, 0)
    w = evaluate_window()
    assert w.in_window is True
    assert w.post_window_hard_stop is False
    assert w.reason == "inside_operational_window"
    assert w.ist_hour == 12


def test_window_before_09_is_outside_with_pre_window_ready():
    set_ist_time(2026, 9, 25, 8, 56)  # 4 min before 09:00
    w = evaluate_window()
    assert w.in_window is False
    assert w.pre_window_ready is True
    assert w.reason == "pre_window_ready"


def test_window_before_09_too_early_is_outside_only():
    set_ist_time(2026, 9, 25, 7, 0)
    w = evaluate_window()
    assert w.in_window is False
    assert w.pre_window_ready is False
    assert w.post_window_hard_stop is False
    assert w.reason == "outside_window"


def test_window_at_20_00_is_post_window_hard_stop():
    set_ist_time(2026, 9, 25, 20, 0)
    w = evaluate_window()
    assert w.in_window is False
    assert w.post_window_hard_stop is True
    assert w.reason == "post_window_hard_stop"


def test_window_at_20_30_is_post_window_hard_stop():
    set_ist_time(2026, 9, 25, 20, 30)
    w = evaluate_window()
    assert w.post_window_hard_stop is True


def test_window_at_08_55_is_pre_window_ready():
    set_ist_time(2026, 9, 25, 8, 55)
    w = evaluate_window()
    assert w.pre_window_ready is True
    assert w.in_window is False


def test_window_at_08_54_is_not_pre_window_ready():
    set_ist_time(2026, 9, 25, 8, 54)
    w = evaluate_window()
    assert w.pre_window_ready is False


# ----- Channel ledger: 5-channel concurrent allocation -----

@pytest.fixture
def tmp_ledgers(tmp_path):
    cl = ChannelAvailabilityLedger(path=tmp_path / "channels.json")
    rl = RetryLedger(path=tmp_path / "retries.json")
    yield cl, rl
    for p in (tmp_path / "channels.json", tmp_path / "retries.json"):
        if p.exists():
            p.unlink()


def test_channel_ledger_starts_with_5_available(tmp_ledgers):
    cl, _ = tmp_ledgers
    assert cl.available() == CHANNEL_CAP == 5


def test_channel_ledger_acquires_release_returns_to_5(tmp_ledgers):
    cl, _ = tmp_ledgers
    assert cl.acquire("DID_872", "lead_A") is True
    assert cl.available() == 4
    assert cl.release("DID_872", "lead_A") is True
    assert cl.available() == 5


def test_channel_ledger_caps_at_5_concurrent(tmp_ledgers):
    cl, _ = tmp_ledgers
    dids = ["DID_872", "DID_874", "DID_875", "DID_877", "DID_881"]
    for did in dids:
        assert cl.acquire(did, "lead_X") is True
    assert cl.available() == 0
    # 6th acquisition must fail
    assert cl.acquire("DID_999", "lead_X") is False


def test_channel_ledger_refuses_double_hold_same_did_to_other_lead(tmp_ledgers):
    cl, _ = tmp_ledgers
    assert cl.acquire("DID_872", "lead_A") is True
    assert cl.acquire("DID_872", "lead_B") is False


def test_channel_ledger_allows_same_lead_to_refresh(tmp_ledgers):
    cl, _ = tmp_ledgers
    assert cl.acquire("DID_872", "lead_A") is True
    # Refresh by same lead → still held, lease extended
    assert cl.acquire("DID_872", "lead_A") is True


# ----- Retry ledger -----

def test_retry_ledger_allows_3_attempts_then_blocks(tmp_ledgers):
    _, rl = tmp_ledgers
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    # 4th attempt must fail
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is False


def test_retry_ledger_separate_days_isolated(tmp_ledgers):
    _, rl = tmp_ledgers
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is True
    # New day → budget resets
    assert rl.attempt("lead_1", "DID_872", "2026-09-26") is True


def test_retry_ledger_separate_channels_isolated(tmp_ledgers):
    _, rl = tmp_ledgers
    # lead_1 burns budget on DID_872, but DID_874 is fresh
    for _ in range(3):
        rl.attempt("lead_1", "DID_872", "2026-09-25")
    assert rl.attempt("lead_1", "DID_872", "2026-09-25") is False
    assert rl.attempt("lead_1", "DID_874", "2026-09-25") is True


# ----- preflight -----

def test_preflight_passes_inside_window_with_capacity(tmp_ledgers):
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = tmp_ledgers
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is True
    assert res.channel_acquired is True
    assert res.retry_allowed is True
    assert res.window.in_window is True
    # Acknowledge the lease so other tests aren't affected
    ack("DID_872", "lead_1", (cl, rl))


def test_preflight_blocks_outside_window_even_if_capacity(tmp_ledgers):
    set_ist_time(2026, 9, 25, 21, 30)  # post-window
    cl, rl = tmp_ledgers
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert any("post-20:00 IST" in r for r in res.reasons_to_block)


def test_preflight_blocks_dnd_fail(tmp_ledgers):
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = tmp_ledgers
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=False, consent_check_passed=True,
        ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert "dnd_check_failed" in res.reasons_to_block


def test_preflight_blocks_consent_fail(tmp_ledgers):
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = tmp_ledgers
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=False,
        ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert "consent_check_failed" in res.reasons_to_block


def test_preflight_blocks_when_channel_unavailable(tmp_ledgers):
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = tmp_ledgers
    # Saturate
    for did in ["DID_872", "DID_874", "DID_875", "DID_877", "DID_881"]:
        cl.acquire(did, f"other_lead_{did}")
    res = preflight(
        channel_id="DID_999", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert any("channel_unavailable" in r or "cap_reached" in r for r in res.reasons_to_block)


def test_preflight_blocks_when_retry_budget_exhausted(tmp_ledgers):
    set_ist_time(2026, 9, 25, 12, 0)
    cl, rl = tmp_ledgers
    for _ in range(3):
        rl.attempt("lead_1", "DID_872", "2026-09-25")
    res = preflight(
        channel_id="DID_872", lead_id="lead_1", day="2026-09-25",
        dnd_check_passed=True, consent_check_passed=True,
        ledger=cl, retry_ledger=rl,
    )
    assert res.can_dial is False
    assert any("retry_budget_exhausted" in r for r in res.reasons_to_block)


# ----- self-heal -----

def test_safe_self_heal_releases_stale_leases(tmp_ledgers):
    cl, _ = tmp_ledgers
    cl.acquire("DID_872", "lead_1", ttl_seconds=1)
    import time
    time.sleep(1.2)
    # Now lease is stale
    released = safe_self_heal(cl)
    assert released == 1
    assert cl.available() == 5
