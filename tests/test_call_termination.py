"""Tests for call termination observability + conversation limits."""

from __future__ import annotations

import asyncio

import pytest

from app.telephony import vobiz_stream as vs
from app.voice_agent import call_termination as ct
from app.voice_agent.platform_pitch import initial_state, next_reply


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self) -> None:
        self.closed = True


def test_opening_segments_single_only():
    segs = __import__(
        "app.voice_agent.platform_pitch", fromlist=["opening_segments"]
    ).opening_segments()
    assert len(segs) == 1
    assert "₹" not in segs[0] or "1999" not in segs[0].replace(",", "")


def test_turn_count_not_audio_chunks():
    hist = [
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "haan"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "price?"},
    ]
    assert ct.count_user_turns(hist) == 2
    assert ct.count_completed_exchanges(hist) == 2


def test_rejection_ends_early_platform_pitch():
    st = initial_state()
    _, st = next_reply(st, "nahi interested")
    assert st.convinced_once is True
    reply, st = next_reply(st, "nahi chahiye")
    assert st.phase == "closed"
    assert reply


def test_supported_max_turns_default():
    assert ct.supported_max_turns() >= 15


@pytest.mark.asyncio
async def test_greet_does_not_terminate_session(monkeypatch):
    monkeypatch.setattr(vs, "TTS_AVAILABLE", False)
    sess = vs.VobizStreamSession(_FakeWS(), niche="ai_marketing", client_name="LeadGen AI")
    await sess._greet()
    assert sess._closed is False
    assert sess._termination_reason is None
    assert len([m for m in sess.hist if m["role"] == "assistant"]) == 1


@pytest.mark.asyncio
async def test_stop_event_sets_provider_disconnect(monkeypatch):
    sess = vs.VobizStreamSession(_FakeWS(), niche="ai_marketing")
    await sess._on_event('{"event":"stop"}')
    assert sess._termination_reason == ct.PROVIDER_DISCONNECT
    assert sess._closed is True


@pytest.mark.asyncio
async def test_opt_out_terminates_with_reason(monkeypatch):
    monkeypatch.setattr(vs, "TTS_AVAILABLE", False)

    async def _noop_say(_t):
        return None

    sess = vs.VobizStreamSession(_FakeWS(), niche="general")
    sess._lead_phone = "+918459012607"
    monkeypatch.setattr(sess, "_say_and_wait", _noop_say)
    monkeypatch.setattr(
        sess,
        "_stt",
        lambda _p: asyncio.sleep(0, result="do not call again"),
    )
    await sess._on_utterance(b"\x00" * 32000)
    assert sess._termination_reason == ct.RECIPIENT_OPTED_OUT


@pytest.mark.asyncio
async def test_max_turns_hard_cap(monkeypatch):
    monkeypatch.setenv("VOICE_SUPPORTED_MAX_TURNS", "2")
    monkeypatch.setenv("VOICE_MAX_CALL_DURATION_SECONDS", "600")
    sess = vs.VobizStreamSession(_FakeWS(), niche="general")
    sess.hist = [
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "d"},
    ]
    await sess._maybe_end_on_limits()
    assert sess._termination_reason == ct.MAX_TURNS_REACHED


@pytest.mark.asyncio
async def test_classify_unknown_not_success():
    reason = ct.classify_unknown(user_turns=0, duration_s=45, media_events=0)
    assert reason in (ct.PROVIDER_DISCONNECT, ct.UNKNOWN_TERMINATION)
    assert reason != "completed"
