"""
Provider-routing TRUTH tests (Tata Tele SmartFlo parity).

Guards the defect where:
  1. `CallManager` only ever built a `VobizClient` (so `tata_smartflo` silently
     dialled Vobiz and *reported* vobiz).
  2. `admin_ops.system_summary()` reported `PROVIDER_CREDS` from Vobiz env vars
     even when the active provider was `tata_smartflo`.
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
from app.telephony.vobiz_handler import VobizClient


# ── Enum ──────────────────────────────────────────────────────────────────────
def test_enum_has_both_providers():
    """VOBIZ must stay (live default) and TATA_SMARTFLO must be present."""
    assert TelephonyProvider.VOBIZ.value == "vobiz"
    assert TelephonyProvider.TATA_SMARTFLO.value == "tata_smartflo"


# ── _build_handler routing ────────────────────────────────────────────────────
def test_build_handler_vobiz():
    assert isinstance(_build_handler("vobiz"), VobizClient)


def test_build_handler_tata_smartflo():
    assert isinstance(_build_handler("tata_smartflo"), TataSmartfloClient)


@pytest.mark.parametrize("bad", ["exotel", "twilio", "", "not-a-provider", "VOBIZ_X"])
def test_build_handler_unknown_falls_back_to_vobiz(bad, caplog):
    with caplog.at_level(logging.WARNING, logger="app.telephony.call_manager"):
        handler = _build_handler(bad)
    assert isinstance(handler, VobizClient)
    assert "falling back to vobiz" in caplog.text


# ── _provider_creds_ok truth table ────────────────────────────────────────────
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


def test_creds_vobiz(clean_env):
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


def test_creds_cross_provider_isolation(clean_env):
    """Tata creds must NOT make vobiz 'ok' (and vice-versa) — no more lying."""
    clean_env.setenv("TATA_SMARTFLO_API_TOKEN", "tok")
    clean_env.setenv("TATA_SMARTFLO_API_KEY", "key")
    assert _provider_creds_ok("tata_smartflo") is True
    assert _provider_creds_ok("vobiz") is False

    clean_env.setenv("VOBIZ_AUTH_ID", "id")
    clean_env.setenv("VOBIZ_AUTH_TOKEN", "tok")
    assert _provider_creds_ok("vobiz") is True
    assert _provider_creds_ok("tata_smartflo") is True  # still genuine


def test_creds_unknown_provider_is_false(clean_env):
    clean_env.setenv("VOBIZ_AUTH_ID", "id")
    clean_env.setenv("VOBIZ_AUTH_TOKEN", "tok")
    clean_env.setenv("TATA_SMARTFLO_API_TOKEN", "tok")
    clean_env.setenv("TATA_SMARTFLO_API_KEY", "key")
    assert _provider_creds_ok("exotel") is False
    assert _provider_creds_ok("") is False


# ── CallManager regression ────────────────────────────────────────────────────
def test_call_manager_defaults_to_vobiz_when_setting_unset(monkeypatch):
    """No DEFAULT_TELEPHONY (or blank) ⇒ vobiz. Zero behaviour change."""
    from app.config import settings

    monkeypatch.setattr(settings, "default_telephony", "", raising=False)
    cm = CallManager()
    assert cm.provider is TelephonyProvider.VOBIZ
    assert isinstance(cm.handler, VobizClient)


def test_call_manager_with_default_telephony_none(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "default_telephony", None, raising=False)
    cm = CallManager()
    assert cm.provider is TelephonyProvider.VOBIZ
    assert isinstance(cm.handler, VobizClient)


def test_call_manager_tata_smartflo_selected(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "default_telephony", "tata_smartflo", raising=False)
    cm = CallManager()
    assert cm.provider is TelephonyProvider.TATA_SMARTFLO
    assert isinstance(cm.handler, TataSmartfloClient)


def test_call_manager_legacy_provider_still_falls_back(monkeypatch, caplog):
    """Legacy 'exotel' in .env must NOT crash startup — vobiz + warning."""
    from app.config import settings

    monkeypatch.setattr(settings, "default_telephony", "exotel", raising=False)
    with caplog.at_level(logging.WARNING, logger="app.telephony.call_manager"):
        cm = CallManager()
    assert cm.provider is TelephonyProvider.VOBIZ
    assert isinstance(cm.handler, VobizClient)
    assert "falling back to vobiz" in caplog.text
