"""Contract tests — voice launch posture contradiction (2026-09-11).

Prod finding under test: ``VOICE_LAUNCH_KILL`` was a TRUE token in production
(``admin_kill_status() -> engaged=True source=ENV reason=ENV_ENGAGED``) while
``PLATFORM_DIAL_DAILY`` was ON. Every dial path refused — yet nothing reported it,
so a HALTED dialer looked exactly like a live one.

These tests pin the reporting contract:
  * no conflict when the kill switch is disengaged
  * no conflict when no live-posture flag is asserted
  * conflict when the kill switch is engaged while a live flag is ON
  * the readiness monitor surfaces it and does not score "ready"
"""

from __future__ import annotations

from app.telephony import telephony_readiness as tr
from app.telephony import voice_launch as vl

# The kill switch falls back to a data file that is absent in a clean checkout
# (which fail-closes to ENGAGED). Every test here therefore sets it explicitly
# so the outcome never depends on ambient on-disk state.
_KILL = "VOICE_LAUNCH_KILL"


def test_no_conflict_when_kill_disengaged(monkeypatch):
    monkeypatch.setenv(_KILL, "0")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
    assert vl.launch_state_conflict() is None


def test_no_conflict_when_no_live_flag_asserted(monkeypatch):
    monkeypatch.setenv(_KILL, "1")
    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    monkeypatch.delenv("VOICE_LAUNCH_CAMPAIGN", raising=False)
    assert vl.launch_state_conflict() is None


def test_conflict_when_kill_engaged_and_platform_dial_on(monkeypatch):
    monkeypatch.setenv(_KILL, "1")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
    monkeypatch.delenv("VOICE_LAUNCH_CAMPAIGN", raising=False)

    conflict = vl.launch_state_conflict()

    assert conflict is not None
    assert conflict["asserted_live_flags"] == ["PLATFORM_DIAL_DAILY"]
    assert conflict["kill_reason"] == "ENV_ENGAGED"
    assert "NOT live" in conflict["detail"]


def test_conflict_lists_every_asserting_flag(monkeypatch):
    monkeypatch.setenv(_KILL, "1")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "1")

    conflict = vl.launch_state_conflict()

    assert conflict is not None
    assert conflict["asserted_live_flags"] == ["VOICE_LAUNCH_CAMPAIGN", "PLATFORM_DIAL_DAILY"]


def test_false_valued_flags_do_not_assert_a_live_posture(monkeypatch):
    monkeypatch.setenv(_KILL, "1")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "0")
    monkeypatch.setenv("VOICE_LAUNCH_CAMPAIGN", "false")
    assert vl.launch_state_conflict() is None


def test_readiness_flags_the_conflict_and_it_lands_in_missing(monkeypatch):
    monkeypatch.setenv(_KILL, "1")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")

    res = tr.run_checks()
    check = res["checks"]["voice_launch_posture"]

    assert check["ok"] is False
    assert check["weight"] == 15
    assert "voice_launch_posture" in res["missing"]
    assert any("kill switch" in a.lower() for a in res["actions"])


def test_readiness_posture_passes_when_kill_disengaged(monkeypatch):
    monkeypatch.setenv(_KILL, "0")

    res = tr.run_checks()
    check = res["checks"]["voice_launch_posture"]

    assert check["ok"] is True
    assert "voice_launch_posture" not in res["missing"]
