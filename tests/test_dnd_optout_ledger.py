"""DND opt-out authority — compliance regression tests.

OPS-012b. Opt-outs used to live ONLY in an in-process dict with a 7-day expiry
and `add_to_local_dnd()` had ZERO callers, so a STOP was forgotten on restart
and after 7 days. TCCCPR 2018 requires opt-outs to be honoured; a lost opt-out
is the one failure mode that turns a compliant sender into a repeat offender.

DESIGN (cycle 6): this does NOT add a new store. There is exactly ONE canonical
cross-channel suppression authority — `app/telephony/consent_ledger.py` — and
DNDChecker delegates to it. An earlier revision created a second JSONL ledger;
that was a duplicate workflow and was removed. The last test here guards
against it coming back.

THESE TESTS ARE A COMPLIANCE GATE. If any fail, do NOT "fix" them by loosening
an assertion — a loosened assertion here is a compliance regression, not a
flake.
"""

import asyncio
import os
from datetime import datetime

import pytest

from app.utils import dnd_checker as dc
from app.utils.dnd_checker import DNDChecker, DNDCheckResult


class FakeAuthority:
    """Stand-in for app.telephony.consent_ledger."""

    def __init__(self):
        self.suppressed: set[str] = set()
        self.recorded: list[tuple] = []
        self.lifted: list[str] = []
        self.raise_on_check = False
        self.report_unpersisted = False

    def is_suppressed(self, phone: str) -> bool:
        if self.raise_on_check:
            raise RuntimeError("ledger unreachable")
        return phone in self.suppressed

    def record_opt_out(self, phone, reason="user_request", channel="voice", call_id=""):
        self.recorded.append((phone, reason, channel))
        if self.report_unpersisted:
            return {"phone": phone, "suppressed": False}
        self.suppressed.add(phone)
        return {"phone": phone, "suppressed": True}

    def suppression_list(self, limit: int = 500):
        return [
            {
                "phone": p,
                "reason": "user_request",
                "channel": "dnd_local",
                "at": "2026-09-07T00:00:00",
            }
            for p in self.suppressed
        ]

    def opt_back_in(self, phone, **_kw):
        self.lifted.append(phone)
        self.suppressed.discard(phone)


@pytest.fixture
def authority(monkeypatch):
    fake = FakeAuthority()
    monkeypatch.setattr(dc, "_suppression_authority", lambda: fake)
    DNDChecker._cache.clear()
    yield fake
    DNDChecker._cache.clear()


def test_suppressed_number_is_verified_dnd(authority):
    authority.suppressed.add("+919876543210")
    res = asyncio.run(DNDChecker().check_single("+919876543210"))
    assert res.is_dnd is True
    assert res.verified is True  # PROVEN opt-out, not an unverified unknown
    assert res.source == dc.OPTOUT_SOURCE


def test_not_suppressed_stays_fail_closed(authority):
    res = asyncio.run(DNDChecker().check_single("+919876543210"))
    # No provider wired => UNVERIFIED => promotional BLOCK. Opt-out status
    # being "clean" is NOT permission to send.
    assert res.verified is False
    assert res.source == "no_provider"


def test_unreachable_authority_blocks_not_crashes(authority):
    authority.raise_on_check = True
    res = asyncio.run(DNDChecker().check_single("+919876543210"))
    assert res.is_dnd is True, "an unreachable opt-out list must never read as 'not opted out'"


def test_optout_beats_stale_cached_non_dnd(authority):
    c = DNDChecker()
    c._cache["+919876543210"] = DNDCheckResult(
        phone="+919876543210",
        is_dnd=False,
        checked_at=datetime.now(),
        source="dnd_api",
        verified=True,
    )
    authority.suppressed.add("+919876543210")
    res = asyncio.run(c.check_single("+919876543210"))
    assert res.is_dnd is True, "a recorded STOP must never be overridden by cache"


def test_filter_dnd_excludes_opted_out(authority):
    authority.suppressed.add("+919876543210")
    kept = asyncio.run(DNDChecker().filter_dnd(["+919876543210", "+919999999999"]))
    assert "+919876543210" not in kept


def test_add_writes_through_to_canonical_ledger(authority):
    DNDChecker().add_to_local_dnd("+919876543210", category="stop_keyword")
    assert ("+919876543210", "stop_keyword", "dnd_local") in authority.recorded
    assert authority.is_suppressed("+919876543210") is True


def test_add_logs_when_persistence_fails(authority, caplog):
    authority.report_unpersisted = True
    with caplog.at_level("ERROR"):
        DNDChecker().add_to_local_dnd("+919876543210")
    assert "NOT persisted" in caplog.text


def test_remove_does_not_lift_a_real_optout(authority):
    c = DNDChecker()
    c.add_to_local_dnd("+919876543210")
    c.remove_from_local_dnd("+919876543210")
    # The durable opt-out must survive a cache clear.
    assert authority.lifted == []
    assert c.is_opted_out("+919876543210") is True


def test_is_opted_out_delegates(authority):
    authority.suppressed.add("+919876543210")
    c = DNDChecker()
    assert c.is_opted_out("+919876543210") is True
    assert c.is_opted_out("+919999999999") is False


def test_export_maps_canonical_rows(authority):
    authority.suppressed.add("+919876543210")
    rows = DNDChecker().export_local_dnd()
    assert [r["phone"] for r in rows] == ["+919876543210"]
    assert rows[0]["is_dnd"] is True
    assert rows[0]["checked_at"] == "2026-09-07T00:00:00"


def test_import_records_into_canonical_ledger(authority):
    DNDChecker().import_local_dnd(
        [
            {
                "phone": "+919876543210",
                "is_dnd": True,
                "checked_at": "2026-09-06T10:00:00",
                "source": "local",
                "category": "user_request",
            }
        ]
    )
    assert ("+919876543210", "user_request", "dnd_import") in authority.recorded


def test_no_duplicate_optout_store_is_created(authority, tmp_path, monkeypatch):
    """REGRESSION GUARD: DNDChecker must not own a second opt-out file."""
    target = tmp_path / "dnd_optouts.jsonl"
    monkeypatch.setenv("DND_OPTOUT_PATH", str(target))
    DNDChecker().add_to_local_dnd("+919876543210")
    DNDChecker().export_local_dnd()
    DNDChecker().import_local_dnd([{"phone": "+919111111111", "checked_at": "", "category": "x"}])
    assert not os.path.exists(target), (
        "DNDChecker wrote its own opt-out file — that is a duplicate of "
        "app.telephony.consent_ledger and must not come back"
    )
