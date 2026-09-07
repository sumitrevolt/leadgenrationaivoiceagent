"""OPS-017 — `DND_CARRIER_SCRUB` must be a VOICE-only allowance.

THE HOLE (found 2026-09-07, cycle 9): `DND_CARRIER_SCRUB=1` makes
`_check_via_registry()` return `is_dnd=False, verified=True` for EVERY number,
with no per-number lookup. It was introduced for voice
(`scripts/vps_deploy_call_learn.py:23` arms it next to VOBIZ_CALL_RECORD and
DLT_APPROVED) but `DNDChecker` is shared: `app/tasks/whatsapp_automation.py::
_scrub_dnd()` — the promotional WhatsApp §5 gate — calls the same checker. One
env var therefore turned the messaging DND gate into "every number is fine",
while the gate's own docstring claimed the opposite ("any number not already in
the cache returns UNVERIFIED and is therefore BLOCKED").

WHY VOICE IS DIFFERENT: TCCCPR 2018 permits a call to a DND number when consent
is documented (this project keeps that in `app/telephony/consent_ledger.py`).
For promotional messaging, NCPR scrubbing is mandatory and — per the research
quoted in docs/DND_NCPR_COMPLIANCE_ADR_2026-09-07.md §3.1 — there is NO consent
mechanism that overrides a DND registration. So a blanket carrier assertion is
defensible for calls and indefensible for messages.

THESE TESTS ARE A COMPLIANCE GATE. If any fail, do NOT "fix" them by loosening
an assertion — a loosened assertion here re-opens a §5 bypass.
"""

import asyncio

import pytest

from app.utils import dnd_checker as dc
from app.utils.dnd_checker import (
    CARRIER_SCRUB_CHANNELS,
    DEFAULT_CHANNEL,
    DNDChecker,
)

VOICE = "voice"
MESSAGING = "messaging"


class FakeAuthority:
    """Nobody has opted out — we are testing the carrier-scrub path only."""

    def is_suppressed(self, phone: str) -> bool:
        return False

    def record_opt_out(self, phone, reason="user_request", channel="voice", call_id=""):
        return {"phone": phone, "suppressed": True}

    def suppression_list(self, limit: int = 500):
        return []

    def opt_back_in(self, phone, **_kw):
        return True


@pytest.fixture
def authority(monkeypatch):
    fake = FakeAuthority()
    monkeypatch.setattr(dc, "_suppression_authority", lambda: fake)
    DNDChecker._cache.clear()
    dc._CARRIER_SCRUB_WARNED = False
    yield fake
    DNDChecker._cache.clear()
    dc._CARRIER_SCRUB_WARNED = False


@pytest.fixture
def armed_vobiz(monkeypatch):
    """DND_CARRIER_SCRUB=1 with Vobiz creds present — the prod shape."""
    monkeypatch.setenv("DND_CARRIER_SCRUB", "1")
    monkeypatch.setenv("TELEPHONY_PROVIDER", "vobiz")
    monkeypatch.setenv("VOBIZ_AUTH_ID", "fake-id")
    monkeypatch.setenv("VOBIZ_AUTH_TOKEN", "fake-token")
    monkeypatch.delenv("DND_API_URL", raising=False)
    monkeypatch.delenv("DND_API_KEY", raising=False)


# ---------------------------------------------------------------- predicate


def test_voice_is_the_only_carrier_scrub_channel():
    assert CARRIER_SCRUB_CHANNELS == {"voice"}


def test_default_channel_is_the_strict_one():
    assert DEFAULT_CHANNEL == "messaging"
    assert dc.carrier_scrub_verifies(DEFAULT_CHANNEL) is False


def test_predicate_channel_cases():
    assert dc.carrier_scrub_verifies("voice") is True
    assert dc.carrier_scrub_verifies("VOICE") is True
    assert dc.carrier_scrub_verifies("messaging") is False
    assert dc.carrier_scrub_verifies("whatsapp") is False
    assert dc.carrier_scrub_verifies("sms") is False
    assert dc.carrier_scrub_verifies("") is False


def test_unknown_or_missing_channel_never_resolves_to_voice():
    # A caller that forgot to declare a channel must get the strict answer.
    assert dc.carrier_scrub_verifies(None) is False
    assert dc.carrier_scrub_verifies("unknown-channel") is False


def test_armed_flag_parsing(monkeypatch):
    for value in ("1", "true", "TRUE", "yes"):
        monkeypatch.setenv("DND_CARRIER_SCRUB", value)
        assert dc.carrier_scrub_armed() is True
    for value in ("0", "", "false", "no"):
        monkeypatch.setenv("DND_CARRIER_SCRUB", value)
        assert dc.carrier_scrub_armed() is False
    monkeypatch.delenv("DND_CARRIER_SCRUB")
    assert dc.carrier_scrub_armed() is False


# ------------------------------------------------------------ the actual fix


def test_carrier_scrub_still_verifies_voice(authority, armed_vobiz):
    res = asyncio.run(DNDChecker().check_single("+919876543210", channel=VOICE))
    assert res.verified is True
    assert res.is_dnd is False
    assert res.source == "vobiz_carrier_scrub"


def test_carrier_scrub_does_not_verify_messaging(authority, armed_vobiz):
    """THE REGRESSION GUARD. This is the §5 bypass that used to exist."""
    res = asyncio.run(DNDChecker().check_single("+919876543210", channel=MESSAGING))
    assert res.verified is False, "carrier scrub must NOT clear the messaging gate"
    assert res.source == "no_provider"


def test_omitted_channel_defaults_to_strict(authority, armed_vobiz):
    res = asyncio.run(DNDChecker().check_single("+919876543210"))
    assert res.verified is False


def test_batch_is_channel_scoped(authority, armed_vobiz):
    phones = ["+919876543210", "+919876543211"]
    voice = asyncio.run(DNDChecker().check_batch(phones, channel=VOICE))
    assert all(r.verified for r in voice.values())

    DNDChecker._cache.clear()
    msg = asyncio.run(DNDChecker().check_batch(phones, channel=MESSAGING))
    assert all(not r.verified for r in msg.values())


def test_filter_dnd_blocks_everything_on_messaging_when_armed(authority, armed_vobiz):
    phones = ["+919876543210", "+919876543211"]
    DNDChecker._cache.clear()
    assert asyncio.run(DNDChecker().filter_dnd(phones, channel=MESSAGING)) == []
    DNDChecker._cache.clear()
    assert asyncio.run(DNDChecker().filter_dnd(phones, channel=VOICE)) == phones


def test_carrier_scrub_verdict_is_never_cached(authority, armed_vobiz):
    """A voice allowance must not be laundered into the messaging path."""
    phone = "+919876543210"
    asyncio.run(DNDChecker().check_single(phone, channel=VOICE))
    assert phone not in DNDChecker._cache, "carrier-scrub verdict must not be cached"
    # ...and therefore the messaging lookup cannot inherit it.
    res = asyncio.run(DNDChecker().check_single(phone, channel=MESSAGING))
    assert res.verified is False


def test_opt_out_still_beats_carrier_scrub_on_voice(authority, armed_vobiz, monkeypatch):
    """Channel scoping must never lift a real STOP."""
    phone = "+919876543210"
    authority.is_suppressed = lambda p: p == phone
    res = asyncio.run(DNDChecker().check_single(phone, channel=VOICE))
    assert res.is_dnd is True
    assert res.verified is True
    assert res.source == "consent_ledger_optout"


# ------------------------------------------------------------------ warning


def test_warning_is_silent_when_flag_off(authority, monkeypatch):
    monkeypatch.delenv("DND_CARRIER_SCRUB", raising=False)
    assert dc.carrier_scrub_warning(MESSAGING) == ""


def test_warning_is_silent_on_voice(authority, armed_vobiz):
    assert dc.carrier_scrub_warning(VOICE) == ""


def test_warning_fires_on_messaging(authority, armed_vobiz):
    msg = dc.carrier_scrub_warning(MESSAGING)
    assert msg, "an armed blanket flag on a messaging channel must be loud"
    assert "OPS-017" in msg
    assert "messaging" in msg
    assert "DND_CARRIER_SCRUB" in msg


def test_warning_never_raises(authority, armed_vobiz):
    for channel in (None, "", "voice", "messaging", "sms"):
        dc.carrier_scrub_warning(channel)
