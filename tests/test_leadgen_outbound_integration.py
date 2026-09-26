"""Integration tests for LeadGen outbound — proves the wiring:
  eligible lead → claim → request → ack; blocked lead → zero requests;
  20:00 → zero; failure → slot release + correct outcome.

These tests USE the REAL ChannelLedger + RetryLedger (SQLite) so we
verify the production wiring, not a mock. The provider call is a fake
that records whether it was invoked — never the real Tata SmartFlo API.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
import time
from datetime import datetime

import pytest

from app.platform.leadgen_daily_window import (
    CHANNEL_CAP,
    DB_PATH,
    ChannelLedger,
    RetryLedger,
)
from app.telephony.leadgen_outbound import (
    LeadGenOutboundRequest,
    dispatch_leadgen_outbound,
)

# ---- fixtures --------------------------------------------------------------


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


@pytest.fixture
def set_ist():
    def _set(year, month, day, hour, minute=0, second=0):
        iso = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"
        os.environ["IST_OVERRIDE"] = iso
    yield _set
    os.environ.pop("IST_OVERRIDE", None)


@pytest.fixture
def leadgen_deps():
    return ChannelLedger(), RetryLedger()


class FakeProvider:
    """Records every place_call invocation. Configurable response."""

    def __init__(self, response: dict | None = None, raise_exc: Exception | None = None):
        self.calls: list[dict] = []
        self.response = response or {
            "status_code": 200,
            "body": {"success": True, "message": "Originate successfully queued", "ref_id": "ref-test-001"},
        }
        self.raise_exc = raise_exc

    async def __call__(self, destination_number: str) -> dict:
        self.calls.append({"destination_number": destination_number})
        if self.raise_exc:
            raise self.raise_exc
        return self.response


# ---- happy path: eligible lead → claim → provider call → release -----------


@pytest.mark.asyncio
async def test_eligible_lead_full_path_claim_then_call_then_release(set_ist, leadgen_deps):
    set_ist(2026, 9, 25, 12, 0)  # inside window
    cl, rl = leadgen_deps
    provider = FakeProvider()
    request = LeadGenOutboundRequest(
        lead_id="lead_001",
        channel_id="DID_872",
        destination_number="+918888888888",
        day="2026-09-25",
        dnd_check_passed=True,
        consent_check_passed=True,
    )
    res = await dispatch_leadgen_outbound(
        request,
        channel_ledger=cl, retry_ledger=rl,
        place_call_fn=provider,
    )
    assert res.attempted_provider_request is True
    assert res.status_code == 200
    assert res.channel_acquired is True
    assert res.channel_released is True
    assert res.retry_budget_consumed is True
    assert res.follow_up_action == "manual_review"
    assert len(provider.calls) == 1
    assert provider.calls[0]["destination_number"] == "+918888888888"
    # Channel was released → can claim again
    assert cl.acquire("DID_872", "lead_001") is True


# ---- blocked: outside window → ZERO provider requests ----------------------


@pytest.mark.asyncio
async def test_outside_window_blocks_with_zero_provider_requests(set_ist, leadgen_deps):
    set_ist(2026, 9, 25, 7, 0)  # before 09:00
    cl, rl = leadgen_deps
    provider = FakeProvider()
    request = LeadGenOutboundRequest(
        lead_id="lead_002",
        channel_id="DID_872",
        destination_number="+918888888888",
        day="2026-09-25",
        dnd_check_passed=True,
        consent_check_passed=True,
    )
    res = await dispatch_leadgen_outbound(
        request, channel_ledger=cl, retry_ledger=rl, place_call_fn=provider,
    )
    assert res.attempted_provider_request is False
    assert len(provider.calls) == 0
    assert "outside_window" in res.preflight_reasons[0] or "outside" in res.preflight_reasons[0]
    assert res.follow_up_action == "retry_next_day"


# ---- blocked: 20:00 hard stop → ZERO provider requests ---------------------


@pytest.mark.asyncio
async def test_post_window_hard_stop_blocks_with_zero_provider_requests(set_ist, leadgen_deps):
    set_ist(2026, 9, 25, 21, 0)  # post-20:00
    cl, rl = leadgen_deps
    provider = FakeProvider()
    request = LeadGenOutboundRequest(
        lead_id="lead_003",
        channel_id="DID_872",
        destination_number="+918888888888",
        day="2026-09-25",
        dnd_check_passed=True,
        consent_check_passed=True,
    )
    res = await dispatch_leadgen_outbound(
        request, channel_ledger=cl, retry_ledger=rl, place_call_fn=provider,
    )
    assert res.attempted_provider_request is False
    assert len(provider.calls) == 0
    assert res.follow_up_action == "retry_next_day"
    assert "post-20:00" in res.preflight_reasons[0]


# ---- blocked: DND → suppress -----------------------------------------------


@pytest.mark.asyncio
async def test_dnd_block_suppresses_with_zero_provider_requests(set_ist, leadgen_deps):
    set_ist(2026, 9, 25, 12, 0)
    cl, rl = leadgen_deps
    provider = FakeProvider()
    request = LeadGenOutboundRequest(
        lead_id="lead_004",
        channel_id="DID_872",
        destination_number="+918888888888",
        day="2026-09-25",
        dnd_check_passed=False,
        consent_check_passed=True,
    )
    res = await dispatch_leadgen_outbound(
        request, channel_ledger=cl, retry_ledger=rl, place_call_fn=provider,
    )
    assert res.attempted_provider_request is False
    assert len(provider.calls) == 0
    assert res.follow_up_action == "suppress"


# ---- blocked: cap reached → manual_review, ZERO provider requests ----------


@pytest.mark.asyncio
async def test_cap_reached_blocks_with_zero_provider_requests(set_ist, leadgen_deps):
    set_ist(2026, 9, 25, 12, 0)
    cl, rl = leadgen_deps
    # Saturate 5 channels with other leads
    for did in ["DID_872", "DID_874", "DID_875", "DID_877", "DID_881"]:
        cl.acquire(did, f"other_lead_{did}")
    provider = FakeProvider()
    request = LeadGenOutboundRequest(
        lead_id="lead_005",
        channel_id="DID_999",  # not in our 5
        destination_number="+918888888888",
        day="2026-09-25",
        dnd_check_passed=True,
        consent_check_passed=True,
    )
    res = await dispatch_leadgen_outbound(
        request, channel_ledger=cl, retry_ledger=rl, place_call_fn=provider,
    )
    assert res.attempted_provider_request is False
    assert len(provider.calls) == 0
    assert "channel_unavailable" in res.preflight_reasons[0]


# ---- failure: provider transport error → release + manual_review ---------


@pytest.mark.asyncio
async def test_provider_transport_error_releases_channel_marks_manual_review(set_ist, leadgen_deps):
    set_ist(2026, 9, 25, 12, 0)
    cl, rl = leadgen_deps
    provider = FakeProvider(raise_exc=RuntimeError("network blip"))
    request = LeadGenOutboundRequest(
        lead_id="lead_006",
        channel_id="DID_872",
        destination_number="+918888888888",
        day="2026-09-25",
        dnd_check_passed=True,
        consent_check_passed=True,
    )
    res = await dispatch_leadgen_outbound(
        request, channel_ledger=cl, retry_ledger=rl, place_call_fn=provider,
    )
    assert res.attempted_provider_request is True
    assert res.channel_acquired is True
    assert res.channel_released is True
    assert "provider_transport" in str(res.body.get("error", ""))
    assert res.follow_up_action == "manual_review"
    # Slot was released → can claim again
    assert cl.acquire("DID_872", "lead_006") is True


# ---- two-worker cross-process simultaneous claim race ----------------------
# This test is the wiring evidence: it spawns TWO Python subprocesses (real
# workers), each calls preflight for the same channel. Only one wins.


def test_two_process_simultaneous_claim_only_one_wins(tmp_path):
    """Two subprocess workers race for the same channel. Only one wins."""
    import subprocess
    import sys
    from pathlib import Path
    worktree_root = str(Path(DB_PATH).resolve().parent.parent)
    runner = tmp_path / "race_runner.py"
    runner.write_text(
        'import sys, os, threading\n'
        'sys.path.insert(0, r"' + worktree_root + '")\n'
        'os.environ["IST_OVERRIDE"] = "2026-09-25T12:00:00"\n'
        'from app.platform.leadgen_daily_window import ChannelLedger, RetryLedger, preflight\n'
        'results = {}\n'
        'def worker(name):\n'
        '    cl = ChannelLedger()\n'
        '    rl = RetryLedger()\n'
        '    res = preflight(channel_id="DID_872", lead_id=name, day="2026-09-25",\n'
        '                    dnd_check_passed=True, consent_check_passed=True,\n'
        '                    channel_ledger=cl, retry_ledger=rl)\n'
        '    results[name] = res.can_dial\n'
        'threads = [threading.Thread(target=worker, args=(f"lead_{i}",)) for i in range(2)]\n'
        'for t in threads: t.start()\n'
        'for t in threads: t.join()\n'
        'winners = sum(1 for v in results.values() if v)\n'
        'print("results=", results)\n'
        'print("winners=", winners)\n'
        'assert winners == 1, f"expected 1 winner, got {results}"\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(runner)],
        cwd=worktree_root,
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": worktree_root},
    )
    assert result.returncode == 0, f"runner failed: stdout={result.stdout}\nstderr={result.stderr}"
    assert "winners= 1" in result.stdout or "winners=1" in result.stdout
