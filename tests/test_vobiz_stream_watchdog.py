"""
Regression tests for the 2026-06-22 "agent goes deaf after 2-3 turns" fix.

Root cause was an UNBOUNDED await inside VobizStreamSession._on_utterance:
  * free_ai.chat_stream iterated tokens with no per-token timeout, so a free
    provider that stalled mid-stream hung the generator forever; and
  * vobiz_stream._whisper_transcribe ran the local-STT executor with no timeout.
Either hang left self._thinking == True permanently, and _on_media then dropped
ALL subsequent caller audio -> the call went permanently silent.

These tests lock in the fix:
  1. _on_utterance ALWAYS clears self._thinking and ALWAYS speaks something, even
     if the streaming reply path hangs forever (THINK watchdog).
  2. The same holds when both the stream AND non-stream reply come back empty
     (never dead air).
  3. free_ai.chat_stream is bounded: a stalling stream yields what it got and
     terminates instead of hanging.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from app.telephony import vobiz_stream as vs


class _FakeWS:
    """Minimal async websocket double — never touches the network."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def accept(self) -> None:  # pragma: no cover - unused here
        pass

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self) -> None:  # pragma: no cover
        pass

    async def receive(self) -> dict:  # pragma: no cover
        return {"type": "websocket.disconnect"}


def _session() -> vs.VobizStreamSession:
    return vs.VobizStreamSession(_FakeWS(), niche="general", client_name="Test Co")


async def test_thinking_clears_when_stream_reply_hangs(monkeypatch):
    """The exact production bug: the streaming reply path hangs. The watchdog must
    still clear _thinking AND deliver a (non-stream) spoken reply — never deaf."""
    monkeypatch.setattr(vs, "THINK_MAX_S", 0.3)
    monkeypatch.setattr(vs, "TTS_AVAILABLE", True)
    monkeypatch.setenv("USE_THINKING_FILLER", "0")
    sess = _session()

    said: list[str] = []

    async def _stt(_pcm):
        return "mujhe naye customers chahiye"

    async def _hang(_text):
        await asyncio.sleep(30)  # simulate a stuck token stream
        return "never reached"

    async def _think(_text):
        return "Ji sir, kis area me business hai?"

    async def _say(text):
        said.append(text)

    monkeypatch.setattr(sess, "_stt", _stt)
    monkeypatch.setattr(sess, "_think_and_say_stream", _hang)
    monkeypatch.setattr(sess, "_think", _think)
    monkeypatch.setattr(sess, "_say", _say)

    # Must return well under the simulated 30s hang (watchdog = 0.3s).
    await asyncio.wait_for(sess._on_utterance(b"\x00" * 16000), timeout=5)

    assert sess._thinking is False, "watchdog must clear _thinking (the deaf-call bug)"
    roles = [m["role"] for m in sess.hist]
    assert "user" in roles and "assistant" in roles, "turn must record user + reply"
    assert said and said[-1], "agent must speak a reply — never dead air"


async def test_never_dead_air_when_both_paths_empty(monkeypatch):
    """Worst case: stream AND non-stream both return nothing. The agent must still
    speak a safe bridge line and clear _thinking — silence is the failure mode."""
    monkeypatch.setattr(vs, "THINK_MAX_S", 0.3)
    monkeypatch.setattr(vs, "TTS_AVAILABLE", True)
    monkeypatch.setenv("USE_THINKING_FILLER", "0")
    sess = _session()

    said: list[str] = []

    async def _stt(_pcm):
        return "haan bilkul, batao"

    async def _empty_stream(_text):
        return ""

    async def _empty_think(_text):
        return ""

    async def _say(text):
        said.append(text)

    monkeypatch.setattr(sess, "_stt", _stt)
    monkeypatch.setattr(sess, "_think_and_say_stream", _empty_stream)
    monkeypatch.setattr(sess, "_think", _empty_think)
    monkeypatch.setattr(sess, "_say", _say)

    await asyncio.wait_for(sess._on_utterance(b"\x00" * 16000), timeout=5)

    assert sess._thinking is False
    assert said and said[-1], "must speak a bridge line, never go silent"
    assert sess.hist[-1]["role"] == "assistant"


class _Delta:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]


class _StallStream:
    """Yields one token, then stalls forever (mid-stream provider hang)."""

    def __init__(self) -> None:
        self._n = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        self._n += 1
        if self._n == 1:
            return _Chunk("Hello")
        await asyncio.sleep(30)  # stall — must NOT hang the caller
        raise StopAsyncIteration

    async def aclose(self):
        pass


async def test_chat_stream_is_bounded_on_midstream_stall(monkeypatch):
    """chat_stream must not hang when a provider stalls after the first token —
    it yields what it got and terminates (idle deadline)."""
    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "_STREAM_FIRST_TOKEN_S", 0.2)
    monkeypatch.setattr(free_ai, "_STREAM_IDLE_S", 0.2)
    monkeypatch.setattr(free_ai, "_STREAM_TOTAL_S", 1.0)
    monkeypatch.setattr(free_ai, "_build_llm_chain", lambda prof: [("fake", "m")])
    monkeypatch.setattr(free_ai, "_provider_down", lambda p: False)

    async def _create(**_kw):
        return _StallStream()

    fake_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))
    )
    monkeypatch.setattr(free_ai, "_client", lambda p: fake_client)

    # Budget guard must not interfere.
    try:
        from app.llm import budget_guard

        monkeypatch.setattr(budget_guard, "active", lambda: False)
    except Exception:
        pass

    out: list[str] = []

    async def _drain():
        async for tok in free_ai.chat_stream(
            system="", messages=[{"role": "user", "content": "hi"}]
        ):
            out.append(tok)

    # The whole drain must complete fast (idle deadline ~0.2s), not hang on the stall.
    await asyncio.wait_for(_drain(), timeout=5)
    assert out == ["Hello"], "should yield the first token then stop on idle timeout"


async def test_send_is_bounded_when_ws_write_hangs(monkeypatch):
    """2026-07-03: _send() used to `await self.ws.send_text(...)` with no timeout.
    _play_frames() calls _send() for every 20ms playAudio frame while
    self._speaking=True; a single hung send would leave _speaking stuck True
    forever, permanently blocking the ONLY code path that finalizes an
    utterance (lives entirely under "not speaking") — the exact failure shape
    seen on a real 2026-07-03 test call (clean decoded audio the whole call,
    zero user_turns). Lock in that a hung ws.send_text() no longer hangs the
    session forever: it times out and closes the session instead."""
    monkeypatch.setattr(vs, "_SEND_TIMEOUT_S", 0.05)
    sess = _session()

    async def _hangs_forever(_text):
        await asyncio.sleep(999)

    monkeypatch.setattr(sess.ws, "send_text", _hangs_forever)

    await asyncio.wait_for(sess._send({"event": "playAudio"}), timeout=1)

    assert sess._closed is True


async def test_processing_ack_does_not_cancel_live_stream(monkeypatch):
    """Ack bridge must stop stale playback only — never kill in-flight LLM stream."""
    monkeypatch.setenv("VOICE_PROCESSING_ACK", "1")
    monkeypatch.setenv("VOICE_PROCESSING_ACK_DELAY_S", "0.05")
    monkeypatch.setattr(vs, "TTS_AVAILABLE", True)
    monkeypatch.setattr(vs, "_PROCESSING_ACK_PCM", b"\x00" * 640)
    sess = _session()
    sess._thinking = True
    sess._active_generation_id = "gen-test-01"
    stream_cancelled = False

    async def _live_stream():
        nonlocal stream_cancelled
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            stream_cancelled = True
            raise

    sess._stream_task = asyncio.create_task(_live_stream())

    async def _quick_play(_pcm):
        return None

    monkeypatch.setattr(sess, "_run_play", _quick_play)

    await sess._processing_ack_watch()

    assert stream_cancelled is False
    assert sess._stream_task is not None
    assert not sess._stream_task.done()
    assert sess._active_generation_id == "gen-test-01"
    sess._stream_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sess._stream_task
