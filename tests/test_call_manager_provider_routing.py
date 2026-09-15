"""Provider-routing TRUTH tests (Tata SmartFlo sole provider, Vobiz removed 2026-09-15).

Guards the current contract:
  1. `TelephonyProvider` has ONLY `TATA_SMARTFLO` — no VOBIZ member.
  2. `_build_handler("tata_smartflo")` → `TataSmartfloClient`.
  3. `_build_handler(<anything-else>)` → `ValueError` (no silent fallback).
  4. `CallManager()` with no default → provider=TATA_SMARTFLO.
  5. `CallManager()` with legacy "exotel"/"vobiz" → raises ValueError.
  6. `admin_ops._provider_creds_ok` still checks both vobiz + tata creds
     (env vars may linger in .env even after code removal).
"""

import logging
import os

import pytest

from app.telephony.call_manager import (
    CallManager,
    TelephonyProvider,
    _build_handler,
)
from app.telephony.tata_smartflo_handler import TataSmartfloClient


# ── Enum (single-provider) ────────────────────────────────────────────────────
def test_enum_has_smartflo_sole():
    """Vobiz was REMOVED 2026-09-15 — only TATA_SMARTFLO remains."""
    assert TelephonyProvider.TATA_SMARTFLO.value == "tata_smartflo"
    member_values = [m.value for m in TelephonyProvider]
    assert "vobiz" not in member_values
    assert len(member_values) == 1


# ── _build_handler routing ────────────────────────────────────────────────────
def test_build_handler_tata_smartflo():
    assert isinstance(_build_handler("tata_smartflo"), TataSmartfloClient)


def test_build_handler_uppercase_normalises():
    assert isinstance(_build_handler("TATA_SMARTFLO"), TataSmartfloClient)


@pytest.mark.parametrize("bad", ["exotel", "twilio", "", "not-a-provider", "VOBIZ_X", "vobiz"])
def test_build_handler_unknown_raises(bad):
    """Vobiz removed — unknown/legacy provider strings RAISE, not silently fall back."""
    with pytest.raises(ValueError, match="Vobiz was REMOVED"):
        _build_handler(bad)


# ── admin_ops._provider_creds_ok truth table ──────────────────────────────────
# NOTE: admin_ops still checks both provider env vars for diagnostics display
# even though the code path for vobiz was removed. The creds check is
# informational (admin dashboard) and does NOT route calls.

def _provider_creds_ok(provider: str) -> bool:
    """Import lazily: app.api.admin_ops pulls in the admin router stack."""
    from app.api.admin_ops import _provider_creds_ok as _impl
    return _impl(provider)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove every provider credential so each case sets only what it needs."""
    for var in (
        "VOBIZ_AUTH_ID",
        "VOBIZ_AUTH_TOKEN",
        "TATA_SMARTFLO_API_TOKEN",
        "TATA_SMARTFLO_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_creds_vobiz_diag(clean_env):
    """admin_ops still reports vobiz creds state (diagnostic only, not routing)."""
    assert _provider_creds_ok("vobiz") is False  # both missing
    clean_env.setenv("VOBIZ_AUTH_ID", "id")
    assert _provider_creds_ok("vobiz") is False  # one missing
    clean_env.setenv("VOBIZ_AUTH_TOKEN", "tok")
    assert _provider_creds_ok("vobiz") is True  # both set


def test_creds_tata_smartflo(clean_env):
    assert _provider_creds_ok("tata_smartflo") is False  # both missing
    clean_env.setenv("TATA_SMARTFLO_API_TOKEN", "tok")
    assert _provider_creds_ok("tata_smartflo") is False  # one missing
    clean_env.setenv("TATA_SMARTFLO_API_KEY", "key")
    assert _provider_creds_ok("tata_smartflo") is True  # both set


def test_creds_unknown_provider_is_false(clean_env):
    assert _provider_creds_ok("exotel") is False
    assert _provider_creds_ok("") is False


# ── CallManager regression ────────────────────────────────────────────────────
def test_call_manager_defaults_to_smartflo_when_setting_unset(monkeypatch):
    """No default_telephony (or blank) ⇒ TATA_SMARTFLO (sole provider)."""
    from app.config import settings
    monkeypatch.setattr(settings, "default_telephony", "", raising=False)
    cm = CallManager()
    assert cm.provider is TelephonyProvider.TATA_SMARTFLO
    assert isinstance(cm.handler, TataSmartfloClient)


def test_call_manager_with_default_telephony_none(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "default_telephony", None, raising=False)
    cm = CallManager()
    assert cm.provider is TelephonyProvider.TATA_SMARTFLO
    assert isinstance(cm.handler, TataSmartfloClient)


def test_call_manager_tata_smartflo_selected(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "default_telephony", "tata_smartflo", raising=False)
    cm = CallManager()
    assert cm.provider is TelephonyProvider.TATA_SMARTFLO
    assert isinstance(cm.handler, TataSmartfloClient)


def test_call_manager_legacy_provider_raises(monkeypatch):
    """Legacy 'vobiz'/'exotel' in .env now raises ValueError (not silent fallback)."""
    from app.config import settings
    monkeypatch.setattr(settings, "default_telephony", "vobiz", raising=False)
    with pytest.raises(ValueError, match="Vobiz was REMOVED"):
        CallManager()
    monkeypatch.setattr(settings, "default_telephony", "exotel", raising=False)
    with pytest.raises(ValueError, match="Vobiz was REMOVED"):
        CallManager()
