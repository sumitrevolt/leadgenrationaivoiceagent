"""
Tests for D-6 barge-in gate + disclosure-leg lock (vobiz_stream).
Constructs a session with a stub websocket and exercises the pure gate logic.
"""

import pytest

from app.telephony.vobiz_stream import VobizStreamSession


class _StubWS:
    async def send_text(self, *_a, **_k):
        return None

    async def close(self, *_a, **_k):
        return None


def _session():
    return VobizStreamSession(_StubWS(), niche="solar", client_name="Acme")


def test_barge_allowed_by_default(monkeypatch):
    monkeypatch.delenv("BARGE_IN_ENABLED", raising=False)
    s = _session()
    assert s._barge_allowed() is True
    assert s._disclosure_locked() is False


def test_disclosure_lock_blocks_barge(monkeypatch):
    monkeypatch.setenv("DISCLOSURE_LOCK", "1")
    s = _session()
    s._begin_disclosure()
    assert s._disclosure_locked() is True
    assert s._barge_allowed() is False  # barge suppressed during disclosure


def test_disclosure_lock_clears_after_deadline(monkeypatch):
    monkeypatch.setenv("DISCLOSURE_LOCK", "1")
    s = _session()
    s._begin_disclosure()
    s._disclosure_deadline_ms = 0.0  # force the safety deadline into the past
    assert s._disclosure_locked() is False  # auto-cleared, never sticks
    assert s._disclosure_active is False
    assert s._barge_allowed() is True


def test_disclosure_lock_gated_off(monkeypatch):
    monkeypatch.setenv("DISCLOSURE_LOCK", "0")
    s = _session()
    s._begin_disclosure()
    assert s._disclosure_locked() is False  # lock disabled -> barge allowed
    assert s._barge_allowed() is True


def test_barge_master_switch_off(monkeypatch):
    monkeypatch.setenv("BARGE_IN_ENABLED", "0")
    s = _session()
    assert s._barge_allowed() is False  # bot cannot be interrupted at all
