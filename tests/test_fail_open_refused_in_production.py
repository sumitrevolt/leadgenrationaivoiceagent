"""OPS-019 — fail-OPEN escape hatches must be REFUSED in production.

Cycle 9 (OPS-017) found that one env var (`DND_CARRIER_SCRUB`) could silently
open the §5 messaging gate. The obvious follow-up question was: **how many other
escape hatches can do that, and do they get refused in production?**

Answer found by sweep:
  * `DND_FAIL_OPEN` — already refused in prod with a one-time CRITICAL log. ✅
  * `WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN` — **NOT refused**. Default 0
    (fail-closed), but setting it to 1 on the VPS turned the only guard on the
    WAHA send path back into fail-OPEN, with nothing objecting. ❌ **FIXED HERE.**
  * `REQUEST_GUARD_SKIP` — replaces the ENTIRE default skip list rather than
    extending it, so adding one path silently removes `/ws`, `/health`,
    `/api/voiceai` from the skip list. Availability foot-gun, not a compliance
    gate. Reported, not changed.

Also found: **four** independent `is_production` implementations
(`telephony/compliance`, `platform/runtime_data`, `integrations/openclaw/
policies`, `config`). Four answers to "are we in production?" is how a safety
flag ends up honoured in prod. This cycle adds ONE authority —
`app/utils/env_probe.py` — and points the compliance gate at it.

THESE TESTS ARE A COMPLIANCE GATE. If any fail, do NOT "fix" them by loosening
an assertion.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.utils import env_probe

_SETTINGS_CLS = type(settings)


@pytest.fixture
def prod(monkeypatch):
    """Production, and with the env fallback unable to contradict it."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setattr(_SETTINGS_CLS, "is_production", True)
    yield


@pytest.fixture
def nonprod(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setattr(_SETTINGS_CLS, "is_production", False)
    yield


# ------------------------------------------------- the single authority


def test_settings_is_production_wins(prod):
    assert env_probe.is_production() is True


def test_env_environment_fallback(monkeypatch, nonprod):
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert env_probe.is_production() is True


def test_env_app_env_fallback(monkeypatch, nonprod):
    monkeypatch.setenv("APP_ENV", "production")
    assert env_probe.is_production() is True


def test_unset_environment_is_not_production(nonprod):
    """Unknown must never be answered as production — but see the DND test below:
    a caller that needs safety must treat 'unknown' as the safe side itself."""
    assert env_probe.is_production() is False


def test_settings_raising_falls_back_to_env(monkeypatch, nonprod):
    def _boom(_self):
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(_SETTINGS_CLS, "is_production", property(_boom))
    monkeypatch.setenv("APP_ENV", "production")
    assert env_probe.is_production() is True  # probe never crashes


# ------------------------------------------------- shared refusal helper


def test_fail_open_refused_when_flag_off(prod, monkeypatch):
    monkeypatch.delenv("SOME_FAIL_OPEN", raising=False)
    assert env_probe.fail_open_refused("SOME_FAIL_OPEN", "x") is False


def test_fail_open_not_refused_outside_production(nonprod, monkeypatch):
    monkeypatch.setenv("SOME_FAIL_OPEN", "1")
    assert env_probe.fail_open_refused("SOME_FAIL_OPEN", "x") is False


def test_fail_open_refused_in_production(prod, monkeypatch):
    monkeypatch.setenv("SOME_FAIL_OPEN", "1")
    assert env_probe.fail_open_refused("SOME_FAIL_OPEN", "x") is True


def test_refusal_message_names_flag_and_consequence():
    msg = env_probe.refusal_message("MY_FLAG", "the gate stays fail-CLOSED")
    assert "MY_FLAG" in msg
    assert "IGNORED in production" in msg
    assert "the gate stays fail-CLOSED" in msg


# ------------------------------------------------- the actual fix


def test_recipient_check_fail_open_defaults_closed(nonprod, monkeypatch):
    from app.integrations.whatsapp_selfhost import _recipient_check_fail_open

    monkeypatch.delenv("WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN", raising=False)
    assert _recipient_check_fail_open() is False


def test_recipient_check_fail_open_honoured_outside_production(nonprod, monkeypatch):
    from app.integrations.whatsapp_selfhost import _recipient_check_fail_open

    monkeypatch.setenv("WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN", "1")
    assert _recipient_check_fail_open() is True


def test_recipient_check_fail_open_refused_in_production(prod, monkeypatch):
    """THE REGRESSION GUARD — before OPS-019 this returned True."""
    from app.integrations.whatsapp_selfhost import _recipient_check_fail_open

    monkeypatch.setenv("WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN", "1")
    assert _recipient_check_fail_open() is False


def test_recipient_check_fail_open_refused_when_probe_breaks(monkeypatch, nonprod):
    """A broken production probe must CLOSE the gate, never open it."""
    import app.integrations.whatsapp_selfhost as wsh

    def _boom():
        raise RuntimeError("probe down")

    monkeypatch.setattr(env_probe, "is_production", _boom)
    monkeypatch.setenv("WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN", "1")
    assert wsh._recipient_check_fail_open() is False


# ------------------------------------------------- existing gate unchanged


def test_dnd_fail_open_still_refused_in_production(prod, monkeypatch):
    from app.telephony.compliance import _dnd_fail_open

    monkeypatch.setenv("DND_FAIL_OPEN", "1")
    assert _dnd_fail_open() is False


def test_dnd_fail_open_still_honoured_outside_production(nonprod, monkeypatch):
    from app.telephony.compliance import _dnd_fail_open

    monkeypatch.setenv("DND_FAIL_OPEN", "1")
    assert _dnd_fail_open() is True


def test_dnd_fail_open_defaults_closed(nonprod, monkeypatch):
    from app.telephony.compliance import _dnd_fail_open

    monkeypatch.delenv("DND_FAIL_OPEN", raising=False)
    assert _dnd_fail_open() is False


def test_compliance_delegates_to_the_single_authority(prod, monkeypatch):
    """The gate and the probe must never disagree."""
    from app.telephony.compliance import _is_production

    assert _is_production() is True
    assert _is_production() == env_probe.is_production()
