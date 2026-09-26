"""DID-pool tests for the Tata SmartFlo outbound path (2026-09-24).

Context
-------
The owner goal requires **five distinct provider-active Tata SmartFlo DIDs**.
Code-side, this was impossible to satisfy: ``app/telephony/tata_tele_config.py``
listed five channels, but nothing in the dial path read them — only
``scripts/smartflo_channel_verify.py`` did. ``app/telephony/trunks.py`` built
exactly ONE trunk from the single ``TATA_SMARTFLO_DID`` env value, and the five
built-in numbers are documented placeholders (``+9180698797{01..05}``).

These tests lock down the contract that replaces that:

1. real DIDs come from env only (``TATA_SMARTFLO_DID``,
   ``TATA_SMARTFLO_DID_2..5``, comma-separated ``TATA_SMARTFLO_DIDS``);
2. ``configured_dids()`` is ordered, de-duplicated, and drops placeholders and
   malformed values — so a placeholder can never become a caller-ID;
3. ``list_active_trunks()`` emits one trunk per real DID and ``pick_trunk()``
   spreads across all of them (the 5-DID provisioning is actually usable);
4. a creds-present-but-no-DID trunk stays visible to readiness yet is never
   selected (fail-closed: no call without a caller-ID);
5. ``is_outbound_allowed()`` uses the single compliance window authority and the
   IST clock, not the host-local clock.

Hermetic: env-only, no network, no secrets, no DB. Nothing here weakens a
compliance gate (DND / TRAI window / consent / AI-disclosure).
"""

from __future__ import annotations

from datetime import datetime as _dt
from datetime import time, timedelta, timezone

import pytest

from app.telephony import tata_tele_config as ttc

_ALL_DID_ENV = (
    ttc.DID_ENV_SINGLE,
    "TATA_SMARTFLO_DID_2",
    "TATA_SMARTFLO_DID_3",
    "TATA_SMARTFLO_DID_4",
    "TATA_SMARTFLO_DID_5",
    ttc.DID_ENV_LIST,
)

_REAL_DIDS = (
    "+918069879757",
    "+918069879758",
    "+918069879759",
    "+918069879760",
    "+918069879761",
)


def _clear_did_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ALL_DID_ENV:
        monkeypatch.delenv(name, raising=False)


def _arm_trunk(monkeypatch: pytest.MonkeyPatch, **dids: str) -> None:
    """Set smartflo creds/enabled plus the given DID env slots."""
    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "tok_test")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "key_test")
    monkeypatch.setenv("TATA_SMARTFLO_ENABLED", "1")
    for name, value in dids.items():
        monkeypatch.setenv(name, value)


# --------------------------------------------------------------------------
# configured_dids() — the pool itself
# --------------------------------------------------------------------------


def test_no_env_means_empty_pool_and_scaffold_numbers_are_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_did_env(monkeypatch)

    assert ttc.configured_dids() == []
    for i in range(1, 6):
        assert ttc.is_placeholder_did(f"+9180698797{i:02d}") is True
    # A real DID that merely shares the prefix is NOT a placeholder.
    assert ttc.is_placeholder_did("+918069879757") is False


def test_single_env_slot_is_returned_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backward compatibility: the legacy single slot still wins, unmodified."""
    _clear_did_env(monkeypatch)
    monkeypatch.setenv(ttc.DID_ENV_SINGLE, _REAL_DIDS[0])

    assert ttc.configured_dids() == [_REAL_DIDS[0]]


def test_five_slots_keep_order_and_drop_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_did_env(monkeypatch)
    for slot, did in enumerate(_REAL_DIDS, start=1):
        name = ttc.DID_ENV_SINGLE if slot == 1 else ttc.DID_ENV_SLOT_FMT.format(n=slot)
        monkeypatch.setenv(name, did)
    # Same DID again in the list form + a second spelling of the first DID.
    monkeypatch.setenv(ttc.DID_ENV_LIST, f"918069879757,{_REAL_DIDS[2]}, {_REAL_DIDS[4]}")

    pool = ttc.configured_dids()

    assert pool == list(_REAL_DIDS), pool


def test_placeholders_and_malformed_values_are_never_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: a placeholder pasted into env must not become a caller-ID."""
    _clear_did_env(monkeypatch)
    monkeypatch.setenv(ttc.DID_ENV_SINGLE, "+918069879701")  # placeholder
    monkeypatch.setenv("TATA_SMARTFLO_DID_2", "not-a-number")
    monkeypatch.setenv("TATA_SMARTFLO_DID_3", "12345")  # too short
    monkeypatch.setenv("TATA_SMARTFLO_DID_4", _REAL_DIDS[3])

    assert ttc.configured_dids() == [_REAL_DIDS[3]]


def test_pool_is_capped_at_five_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_did_env(monkeypatch)
    monkeypatch.setenv(ttc.DID_ENV_LIST, ",".join(f"+91981234567{i}" for i in range(1, 9)))

    assert len(ttc.configured_dids()) == ttc.MAX_DIDS


def test_normalize_did_accepts_common_indian_spellings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ttc.normalize_did("+918069879757") == "8069879757"
    assert ttc.normalize_did("918069879757") == "8069879757"
    assert ttc.normalize_did("08069879757") == "8069879757"
    assert ttc.normalize_did("8069879757") == "8069879757"
    assert ttc.normalize_did("") == ""
    assert ttc.normalize_did("+91 80698-79757") == "8069879757"


# --------------------------------------------------------------------------
# trunks.py — the pool is actually used by the dial path
# --------------------------------------------------------------------------


def test_one_trunk_per_real_did_and_pick_spreads_across_all_five(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.telephony.trunks import list_active_trunks, pick_trunk

    _clear_did_env(monkeypatch)
    _arm_trunk(
        monkeypatch,
        **{ttc.DID_ENV_SINGLE: _REAL_DIDS[0]},
        **{ttc.DID_ENV_SLOT_FMT.format(n=i): _REAL_DIDS[i - 1] for i in range(2, 6)},
    )

    trunks = list_active_trunks()
    assert len(trunks) == 5, "a 5-DID provisioning must yield 5 usable trunks"
    assert {t.name for t in trunks} == {"tata_smartflo"}
    assert {t.caller_id for t in trunks} == set(_REAL_DIDS)

    chosen = {pick_trunk(lead=None)[1] for _ in range(400)}
    assert chosen == set(_REAL_DIDS), f"rotation skipped DIDs: {set(_REAL_DIDS) - chosen}"


def test_single_did_keeps_legacy_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.telephony.trunks import list_active_trunks, pick_trunk

    _clear_did_env(monkeypatch)
    _arm_trunk(monkeypatch, **{ttc.DID_ENV_SINGLE: _REAL_DIDS[0]})

    trunks = list_active_trunks()
    assert len(trunks) == 1
    provider, caller_id = pick_trunk(lead=None)
    assert provider == "tata_smartflo"
    assert caller_id == _REAL_DIDS[0]


def test_placeholder_only_env_yields_no_selectable_trunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.telephony.trunks import list_active_trunks, pick_trunk

    _clear_did_env(monkeypatch)
    _arm_trunk(monkeypatch, **{ttc.DID_ENV_SINGLE: "+918069879701"})

    for trunk in list_active_trunks():
        assert trunk.caller_id.strip() == ""
    assert pick_trunk(lead=None) == ("none", "")


def test_creds_without_did_stays_visible_but_unselectable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness must still see the trunk; the dialer must not use it."""
    from app.telephony.trunks import list_active_trunks, pick_trunk

    _clear_did_env(monkeypatch)
    _arm_trunk(monkeypatch)

    trunks = list_active_trunks()
    assert len(trunks) == 1 and trunks[0].caller_id == ""
    assert pick_trunk(lead=None) == ("none", "")


def test_import_failure_falls_back_to_the_legacy_single_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken channel-config import must not silently drop the trunk."""
    import builtins

    from app.telephony.trunks import _smartflo_dids

    _clear_did_env(monkeypatch)
    monkeypatch.setenv(ttc.DID_ENV_SINGLE, _REAL_DIDS[0])
    real_import = builtins.__import__

    def _boom(name: str, *args: object, **kwargs: object) -> object:
        if name.endswith("tata_tele_config"):
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)
    try:
        assert _smartflo_dids() == [_REAL_DIDS[0]]
    finally:
        monkeypatch.setattr(builtins, "__import__", real_import)


# --------------------------------------------------------------------------
# channel scaffold — status reflects a bound DID, not a hard-coded "active"
# --------------------------------------------------------------------------


def test_channel_status_tracks_real_dids_and_never_exposes_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_did_env(monkeypatch)
    monkeypatch.setenv(ttc.DID_ENV_SINGLE, _REAL_DIDS[0])
    monkeypatch.setenv("TATA_SMARTFLO_DID_2", _REAL_DIDS[1])

    cfg = ttc.TataTeleConfig()

    assert len(cfg.channels) == 5
    assert {c["id"] for c in cfg.get_active_channels()} == {"tata_channel_1", "tata_channel_2"}
    assert [c["number"] for c in cfg.channels[:2]] == [_REAL_DIDS[0], _REAL_DIDS[1]]
    for channel in cfg.channels[2:]:
        assert channel["is_placeholder"] is True
        assert channel["status"] == "pending"
        assert ttc.is_placeholder_did(channel["number"]) is True
    # Capacity/revenue must only count channels with a REAL DID.
    assert cfg.get_total_capacity() == 2 * 240


def test_no_real_did_means_zero_active_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    """The old hard-coded 'channel 1 = active' was scaffolding, not activation."""
    _clear_did_env(monkeypatch)

    cfg = ttc.TataTeleConfig()

    assert cfg.get_active_channels() == []
    assert len(cfg.get_pending_channels()) == 5
    assert cfg.get_total_capacity() == 0
    assert cfg.get_revenue_potential()["daily_calls"] == 0


# --------------------------------------------------------------------------
# outbound window — IST + single compliance authority
# --------------------------------------------------------------------------


def test_outbound_window_follows_the_compliance_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_did_env(monkeypatch)
    monkeypatch.setattr(
        "app.telephony.compliance.effective_promo_window", lambda: ("09:00", "20:00")
    )

    cfg = ttc.TataTeleConfig()

    assert cfg.outbound_start == time(9, 0)
    assert cfg.outbound_end == time(20, 0)
    assert cfg.is_outbound_allowed(time(8, 59)) is False
    assert cfg.is_outbound_allowed(time(9, 0)) is True
    assert cfg.is_outbound_allowed(time(19, 59)) is True
    assert cfg.is_outbound_allowed(time(20, 1)) is False


def test_default_window_is_the_conservative_compliance_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner's 09:00–20:00 request is armed via env, not silently defaulted."""
    _clear_did_env(monkeypatch)
    for name in ("COMPLIANCE_PROMO_START", "COMPLIANCE_PROMO_END"):
        monkeypatch.delenv(name, raising=False)

    cfg = ttc.TataTeleConfig()

    assert (cfg.outbound_start, cfg.outbound_end) == (time(9, 0), time(19, 0))


def test_window_clock_is_ist_not_host_local() -> None:
    expected = (_dt.now(timezone.utc) + timedelta(hours=5, minutes=30)).time()
    got = ttc._ist_now_time()

    delta = abs((got.hour * 60 + got.minute) - (expected.hour * 60 + expected.minute))
    assert delta <= 1, f"window clock is not IST: got {got}, expected ~{expected}"
