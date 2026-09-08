"""PLATFORM_DIAL_DAILY parsing — the switch that silently disabled the campaign.

Found in prod on 2026-08-03: `.env` had VOICE_LAUNCH_KILL=0, DIAL_TEST_MODE=0,
DLT_APPROVED=1 and PLATFORM_DIAL_DAILY=100, so the campaign looked fully armed —
yet automation_health reported the daily dial job as `mandate_paused` because
`enabled()` was False.

Cause: PLATFORM_DIAL_DAILY is the on/off SWITCH (the per-run count is
PLATFORM_DIAL_LIMIT). "100" matched neither the true nor the false token, and the
old code SILENTLY fell through to the data-file, which said disabled. The
operator's intent and the system's behaviour disagreed with nothing to show it.

These tests pin the parse so a count can never again read as "off", and so 0
keeps working as the hard kill-switch.
"""

from __future__ import annotations

import pytest

from app.platform import platform_dial as PD


@pytest.fixture(autouse=True)
def _no_file_cfg(monkeypatch):
    """File config says DISABLED, so any True below comes from the env alone."""
    monkeypatch.setattr(PD, "_file_cfg", lambda: {"enabled": False})


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_boolean_true_tokens_enable(monkeypatch, val):
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", val)
    assert PD.enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF"])
def test_boolean_false_tokens_are_the_hard_kill_switch(monkeypatch, val):
    monkeypatch.setattr(PD, "_file_cfg", lambda: {"enabled": True})  # file says ON
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", val)
    assert PD.enabled() is False, "env 0 must override the data-file (kill-switch)"


@pytest.mark.parametrize("val", ["100", "5", "1000"])
def test_a_positive_count_means_ON_not_silently_off(monkeypatch, val):
    """THE REGRESSION. `PLATFORM_DIAL_DAILY=100` used to resolve to False."""
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", val)
    assert PD.enabled() is True


def test_zero_count_is_still_off(monkeypatch):
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "0")
    assert PD.enabled() is False


def test_unset_falls_back_to_the_data_file(monkeypatch):
    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    monkeypatch.setattr(PD, "_file_cfg", lambda: {"enabled": True})
    assert PD.enabled() is True
    monkeypatch.setattr(PD, "_file_cfg", lambda: {"enabled": False})
    assert PD.enabled() is False


def test_garbage_falls_back_to_file_and_warns(monkeypatch, caplog):
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "banana")
    monkeypatch.setattr(PD, "_file_cfg", lambda: {"enabled": False})
    with caplog.at_level("WARNING"):
        assert PD.enabled() is False
    assert any("PLATFORM_DIAL_DAILY" in r.message for r in caplog.records)


def test_count_and_cap_are_separate_knobs(monkeypatch):
    """The two names read alike; prove they are not the same control."""
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "37")
    assert PD.enabled() is True
    assert PD.dial_limit() == 37


def test_dial_limit_stays_bounded(monkeypatch):
    """Cap is clamped 1..200 — an operator typo cannot dial unbounded."""
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "99999")
    assert PD.dial_limit() == 200
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "-5")
    assert PD.dial_limit() == 1
