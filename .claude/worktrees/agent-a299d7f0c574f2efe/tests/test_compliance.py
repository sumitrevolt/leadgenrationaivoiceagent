"""
Tests for the telephony ComplianceGate (TCCCPR/TRAI pre-dial chokepoint).

Async checks are driven via asyncio.run() so no pytest-asyncio plugin is needed.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.telephony.compliance import IST, CallType, ComplianceGate


def _run(coro):
    return asyncio.run(coro)


class _FakeDND:
    """Stand-in for DNDChecker — returns a fixed is_dnd verdict."""

    def __init__(self, is_dnd: bool = False):
        self._v = is_dnd

    async def check_single(self, phone: str):
        return SimpleNamespace(is_dnd=self._v)


IN_HOURS = datetime(2026, 6, 7, 12, 0, tzinfo=IST)  # noon IST — inside both windows
LATE = datetime(2026, 6, 7, 22, 0, tzinfo=IST)  # 22:00 IST — outside both windows


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Deterministic defaults: gate ON, no allowlist, DLT pending."""
    monkeypatch.setenv("COMPLIANCE_ENABLED", "1")
    monkeypatch.setenv("COMPLIANCE_ALLOWLIST", "")
    monkeypatch.setenv("DLT_APPROVED", "0")
    for k in (
        "COMPLIANCE_PROMO_START",
        "COMPLIANCE_PROMO_END",
        "COMPLIANCE_TXN_START",
        "COMPLIANCE_TXN_END",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def test_transactional_in_hours_allowed():
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.TRANSACTIONAL, now=IN_HOURS))
    assert d.allowed, d.reasons


def test_promotional_blocked_without_dlt():
    """DLT pending (default) => every promotional cold-call is blocked."""
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert not d.allowed
    assert any("dlt_not_approved" in r for r in d.reasons)


def test_promotional_allowed_with_dlt_and_caller_id(monkeypatch):
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert d.allowed, d.reasons


def test_dnd_number_blocked(monkeypatch):
    """With DLT+caller-id set, a DND number is still blocked (isolates DND)."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    g = ComplianceGate(dnd_checker=_FakeDND(True))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert not d.allowed
    assert "on_dnd_registry" in d.reasons


def test_allowlist_bypasses_everything(monkeypatch):
    """An allowlisted (own/consented) number passes even promo+late+DND."""
    monkeypatch.setenv("COMPLIANCE_ALLOWLIST", "+91 98765 43210")
    g = ComplianceGate(dnd_checker=_FakeDND(True))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=LATE))
    assert d.allowed
    assert "allowlisted" in d.reasons


def test_outside_hours_blocked():
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.TRANSACTIONAL, now=LATE))
    assert not d.allowed
    assert any("outside_calling_hours" in r for r in d.reasons)


def test_kill_switch_allows(monkeypatch):
    monkeypatch.setenv("COMPLIANCE_ENABLED", "0")
    g = ComplianceGate(dnd_checker=_FakeDND(True))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=LATE))
    assert d.allowed
    assert "compliance_disabled" in d.reasons


def test_invalid_number_blocked():
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("123", CallType.TRANSACTIONAL, now=IN_HOURS))
    assert not d.allowed
    assert "invalid_number" in d.reasons


def test_gate_never_raises_on_bad_dnd(monkeypatch):
    """A DND backend that explodes must not crash the gate (fail-safe)."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")

    class _BoomDND:
        async def check_single(self, phone):
            raise RuntimeError("dnd backend down")

    g = ComplianceGate(dnd_checker=_BoomDND())
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    # Gate raised nahi (decision return hua) — core intent.
    # TRAI fail-CLOSED: DND unverifiable => promotional call BLOCKED (₹10L-safe),
    # even with DLT + caller-id set. Reason surfaced, not an exception.
    assert not d.allowed
    assert "dnd_lookup_failed" in d.reasons
    assert d.checks.get("dnd") is None
    assert d.checks.get("dnd_note") == "lookup_failed"
