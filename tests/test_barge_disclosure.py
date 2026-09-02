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


def test_noinput_policy_gate(monkeypatch):
    monkeypatch.delenv("NOINPUT_POLICY", raising=False)
    assert VobizStreamSession._noinput_enabled() is False  # default OFF
    monkeypatch.setenv("NOINPUT_POLICY", "1")
    assert VobizStreamSession._noinput_enabled() is True


def test_noinput_reprompts_then_graceful_close():
    """D-13: reprompt up to MAX, then graceful goodbye + close."""
    import asyncio

    s = _session()
    said = []

    async def _fake_say(text):
        said.append(("say", text))

    async def _fake_wait(text):
        said.append(("wait", text))

    s._say = _fake_say  # type: ignore[assignment]
    s._say_and_wait = _fake_wait  # type: ignore[assignment]

    asyncio.run(s._noinput_handle())
    assert s._noinput_reprompts == 1
    asyncio.run(s._noinput_handle())
    assert s._noinput_reprompts == 2
    # next call exceeds MAX (default 2) -> graceful close
    asyncio.run(s._noinput_handle())
    assert s._closed is True
    assert any(kind == "wait" for kind, _ in said)  # spoke a goodbye before closing


def test_noinput_handle_skips_when_busy():
    """No reprompt if the bot is mid-speech / mid-think / caller talking."""
    import asyncio

    s = _session()
    s._speaking = True
    asyncio.run(s._noinput_handle())
    assert s._noinput_reprompts == 0  # bailed out, no reprompt
