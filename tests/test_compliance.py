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
    """Stand-in for DNDChecker — returns a fixed, VERIFIED is_dnd verdict.

    `channel` is accepted because ComplianceGate._is_dnd() calls
    `check_single(phone, channel="voice")` (OPS-017 voice-only allowance). A fake
    without it raises TypeError, which the gate's `except` swallows into a
    fail-closed `dnd_lookup_failed` — silently turning these "allowed" tests into
    block tests. Keep the signature in sync with the real DNDChecker.
    """

    def __init__(self, is_dnd: bool = False):
        self._v = is_dnd

    async def check_single(self, phone: str, channel: str = "voice"):
        return SimpleNamespace(is_dnd=self._v, verified=True)


IN_HOURS = datetime(2026, 6, 7, 12, 0, tzinfo=IST)  # noon IST — inside both windows
LATE = datetime(2026, 6, 7, 22, 0, tzinfo=IST)  # 22:00 IST — outside both windows
EARLY_0930 = datetime(2026, 6, 7, 9, 30, tzinfo=IST)  # 09:30 IST — inside new promo window
EVENING_2030 = datetime(2026, 6, 7, 20, 30, tzinfo=IST)  # 20:30 IST — past promo window end


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


def test_promo_window_default_is_9_to_20(monkeypatch):
    """D-0 (LEGAL-GATE): promo window default starts 09:00 (not 10:00) and ends
    20:00 — the owner operating window within TRAI's 09:00–21:00 ceiling. The 09:30 slot, which the
    old 10:00 default blocked, is now allowed (with DLT + caller-id set)."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=EARLY_0930))
    assert d.allowed, d.reasons
    assert d.checks.get("window") == "09:00-20:00"
    assert d.checks.get("within_hours") is True


def test_promo_after_2000_blocked(monkeypatch):
    """20:30 is past the promo window end → blocked even with DLT + caller-id."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=EVENING_2030))
    assert not d.allowed
    assert any("outside_calling_hours" in r for r in d.reasons)
    assert d.checks.get("window") == "09:00-20:00"


def test_promo_window_env_override(monkeypatch):
    """Env still overrides the default (10:00 start blocks the 09:30 slot)."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    monkeypatch.setenv("COMPLIANCE_PROMO_START", "10:00")
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=EARLY_0930))
    assert not d.allowed
    assert any("outside_calling_hours" in r for r in d.reasons)
    assert d.checks.get("window") == "10:00-20:00"


def test_kill_switch_allows(monkeypatch):
    monkeypatch.setenv("COMPLIANCE_ENABLED", "0")
    g = ComplianceGate(dnd_checker=_FakeDND(True))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=LATE))
    assert d.allowed
    assert "compliance_disabled" in d.reasons


def test_kill_switch_alerts_without_raising(monkeypatch):
    """D-1: with the gate disabled AND ops-alerts on, the call still returns
    allowed and the alert path never raises (loud log + best-effort ntfy)."""
    monkeypatch.setenv("COMPLIANCE_ENABLED", "0")
    monkeypatch.setenv("OPS_ALERTS", "1")
    g = ComplianceGate(dnd_checker=_FakeDND(True))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=LATE))
    assert d.allowed
    assert "compliance_disabled" in d.reasons


def test_alert_compliance_disabled_gated(monkeypatch):
    """The ops-alert helper is OPS_ALERTS-gated and never raises."""
    from app.platform.ops_alerts import alert_compliance_disabled

    monkeypatch.delenv("OPS_ALERTS", raising=False)
    assert alert_compliance_disabled("x")["alerted"] is False  # gated off → inert


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


# --------------------------------------------------------------------------- #
# TRAI legal-ceiling clamp on promotional window override (2026-07 audit fix)  #
# --------------------------------------------------------------------------- #
class _UnverifiedDND:
    """DND backend that answers but cannot verify — exercises the fail-open path."""

    async def check_single(self, phone: str, channel: str = "voice"):
        return SimpleNamespace(is_dnd=False, verified=False)


def test_promo_window_override_clamped_to_2100(monkeypatch):
    """A promo-END override past 21:00 is clamped to the TRAI 21:00 ceiling."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    monkeypatch.setenv("COMPLIANCE_PROMO_END", "23:00")  # breaches 21:00 ceiling
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert d.checks.get("window") == "09:00-21:00"  # clamped, not 09:00-23:00
    assert d.allowed, d.reasons


def test_promo_window_start_override_floored_to_0900(monkeypatch):
    """A promo-START override before 09:00 is floored to 09:00."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    monkeypatch.setenv("COMPLIANCE_PROMO_START", "06:00")  # before 09:00 floor
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert d.checks.get("window") == "09:00-20:00"  # floored to 09:00


def test_promo_window_garbage_env_falls_back_to_default(monkeypatch):
    """Un-parseable overrides fall back to the safe default 09:00-20:00."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    monkeypatch.setenv("COMPLIANCE_PROMO_START", "banana")
    monkeypatch.setenv("COMPLIANCE_PROMO_END", "99:99")
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert d.checks.get("window") == "09:00-20:00"


def test_promo_window_degenerate_override_falls_back(monkeypatch):
    """Both overrides above the ceiling (start>=end after clamp) -> safe default."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    monkeypatch.setenv("COMPLIANCE_PROMO_START", "22:00")
    monkeypatch.setenv("COMPLIANCE_PROMO_END", "23:00")
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert d.checks.get("window") == "09:00-20:00"


def test_effective_promo_window_helper_clamps(monkeypatch):
    """effective_promo_window() is the single source of truth (clamped)."""
    from app.telephony.compliance import effective_promo_window

    monkeypatch.setenv("COMPLIANCE_PROMO_END", "23:00")
    assert effective_promo_window() == ("09:00", "21:00")
    monkeypatch.setenv("COMPLIANCE_PROMO_START", "banana")
    monkeypatch.delenv("COMPLIANCE_PROMO_END", raising=False)
    assert effective_promo_window() == ("09:00", "20:00")


def test_dnd_fail_open_ignored_in_production(monkeypatch):
    """DND_FAIL_OPEN=1 in production is REFUSED -> gate stays fail-CLOSED, so an
    unverifiable DND lookup still BLOCKS the promotional call (TRAI-safe)."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    monkeypatch.setenv("DND_FAIL_OPEN", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    g = ComplianceGate(dnd_checker=_UnverifiedDND())
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert not d.allowed
    assert "dnd_lookup_failed" in d.reasons  # fail-CLOSED despite DND_FAIL_OPEN=1


def test_dnd_fail_open_honoured_outside_production(monkeypatch):
    """Outside production, DND_FAIL_OPEN=1 is honoured (unverified -> not on DND),
    so with DLT + caller-id the promotional call is allowed."""
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911140000000")
    monkeypatch.setenv("DND_FAIL_OPEN", "1")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    g = ComplianceGate(dnd_checker=_UnverifiedDND())
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert d.allowed, d.reasons
    assert d.checks.get("dnd") is False


# ---------------------------------------------------------------------------
# caller-id source (finding B-5: SmartFlo-only must not depend on VOBIZ_*)
# ---------------------------------------------------------------------------
_TATA_DID = "+911140000001"
_LEGACY_DID = "+911140000000"


def _pin_settings(monkeypatch, **attrs):
    """Force the settings path to be deterministic (pydantic Settings reads .env)."""
    try:
        from app.config import settings
    except Exception:  # pragma: no cover - settings import is required in practice
        return
    for name, value in attrs.items():
        if hasattr(settings, name):
            monkeypatch.setattr(settings, name, value, raising=False)


def _clear_caller_id_sources(monkeypatch):
    for k in ("TATA_SMARTFLO_DID", "SMARTFLO_DID", "VOBIZ_CALLER_ID"):
        monkeypatch.delenv(k, raising=False)
    _pin_settings(monkeypatch, tata_smartflo_did="", vobiz_caller_id="")


def test_promotional_allowed_with_smartflo_did_only(monkeypatch):
    """THE B-5 acceptance test: with the retired VOBIZ_* variable GONE, a
    promotional call must still dial. Before the fix the resolver returned ''
    and the gate blocked 100% of promo calls as `no_caller_id`."""
    _clear_caller_id_sources(monkeypatch)
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("TATA_SMARTFLO_DID", _TATA_DID)

    assert ComplianceGate._caller_id() == _TATA_DID
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert d.allowed, d.reasons
    assert not any("no_caller_id" in r for r in d.reasons)


def test_caller_id_prefers_canonical_smartflo_over_legacy_vobiz(monkeypatch):
    """Both variables present -> the live provider's DID wins. The gate asserts
    that a registered CLI exists for the provider that actually places the call."""
    _clear_caller_id_sources(monkeypatch)
    monkeypatch.setenv("TATA_SMARTFLO_DID", _TATA_DID)
    monkeypatch.setenv("VOBIZ_CALLER_ID", _LEGACY_DID)
    assert ComplianceGate._caller_id() == _TATA_DID


def test_caller_id_legacy_fallback_still_dials_and_is_announced(monkeypatch):
    """A prod env that still carries only VOBIZ_* keeps dialing (no silent
    outage during the removal window), but the fallback is LOGGED once so the
    legacy dependency is visible instead of silent."""
    from app.telephony import compliance as comp

    _clear_caller_id_sources(monkeypatch)
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", _LEGACY_DID)

    warnings: list[tuple] = []

    class _Recorder:
        def warning(self, *a, **kw):
            warnings.append(a)

        def __getattr__(self, _name):  # debug/info/error -> no-op
            return lambda *a, **kw: None

    monkeypatch.setattr(comp, "logger", _Recorder())
    monkeypatch.setattr(comp, "_LEGACY_CALLER_ID_WARNED", False, raising=False)

    assert ComplianceGate._caller_id() == _LEGACY_DID
    assert warnings, "the legacy caller-id fallback must be announced once"
    # Never log the credential-like value in full — only the last 4 digits.
    assert _LEGACY_DID not in str(warnings[0])
    assert warnings[0][-1] == _LEGACY_DID[-4:]

    # ...and only once per process (no per-dial log spam).
    assert ComplianceGate._caller_id() == _LEGACY_DID
    assert len(warnings) == 1


def test_caller_id_empty_when_nothing_configured(monkeypatch):
    """Absent config stays fail-CLOSED: '' -> promo blocked with the canonical
    variable named in the reason, so the operator fixes the right variable."""
    _clear_caller_id_sources(monkeypatch)
    monkeypatch.setenv("DLT_APPROVED", "1")
    monkeypatch.setenv("COMPLIANCE_DND_WAIVED", "1")
    assert ComplianceGate._caller_id() == ""
    g = ComplianceGate(dnd_checker=_FakeDND(False))
    d = _run(g.check("+919876543210", CallType.PROMOTIONAL, now=IN_HOURS))
    assert not d.allowed
    assert any("TATA_SMARTFLO_DID" in r for r in d.reasons)
