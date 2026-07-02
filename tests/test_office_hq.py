"""Tests for app.platform.office_hq — offline_reason classification (Task 1)."""
from __future__ import annotations

from app.platform import office_hq


def test_offline_reason_flag_off(monkeypatch):
    monkeypatch.delenv("SOCIAL_ENGINE", raising=False)  # unset = off
    reason = office_hq.classify_offline_reason("zara")
    assert reason == "flag_off:SOCIAL_ENGINE"


def test_offline_reason_flag_on_no_data(monkeypatch):
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    reason = office_hq.classify_offline_reason("anika")
    assert reason == "no_data_today"


def test_offline_reason_unknown_member():
    reason = office_hq.classify_offline_reason("not_a_real_key")
    assert reason == "unknown"


def test_offline_reason_never_raises(monkeypatch):
    # Simulate a broken env read — must still return a string, never raise.
    import os
    original_environ = os.environ
    try:
        monkeypatch.setattr(office_hq.os, "environ", None)
        reason = office_hq.classify_offline_reason("zara")
        assert isinstance(reason, str)
    finally:
        monkeypatch.setattr(office_hq.os, "environ", original_environ)


def test_build_rooms_and_agents_includes_offline_reason_only_when_offline():
    rooms, agents = office_hq.build_rooms_and_agents()
    for a in agents:
        if a["status"] == "offline":
            assert a["offline_reason"] is not None
            assert isinstance(a["offline_reason"], str)
        else:
            assert a["offline_reason"] is None
