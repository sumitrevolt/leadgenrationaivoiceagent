"""Synthetic audio regression coverage; no customer traffic or provider calls."""

import asyncio
import base64
import threading
from unittest.mock import AsyncMock

import pytest

from app.telephony import smartflo_stream as ss


@pytest.fixture
def session(monkeypatch):
    s = ss.SmartfloStreamSession(AsyncMock(), niche="ai_marketing")
    s._say = AsyncMock()
    s._persist_transcript = AsyncMock()
    from app.telephony import post_call_hooks

    monkeypatch.setattr(post_call_hooks, "finalize_stream_session", AsyncMock())
    return s


def payload(speech=True, ms=20):
    pcm = (b"\x00\x20" if speech else b"\x00\x00") * (8 * ms)
    return base64.b64encode(ss.pcm16_to_mulaw(pcm)).decode()


@pytest.mark.asyncio
async def test_receive_and_stop_remain_responsive_during_stt(session):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def stalled(_pcm):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    session._stt = stalled
    for _ in range(20):
        await session._on_media(payload())
    for _ in range(40):
        await asyncio.wait_for(session._on_media(payload(False)), 0.1)
    await asyncio.wait_for(started.wait(), 0.2)
    await asyncio.wait_for(session._cleanup(), 0.2)
    assert cancelled.is_set()
    assert session._closed
    session._say.assert_not_awaited()


@pytest.mark.asyncio
async def test_packet_duration_and_internal_pauses_preserved(session):
    session._stt = AsyncMock(return_value="Namaste")
    session._llm_reply = AsyncMock(return_value="Namaste ji")
    # Smartflo may coalesce frames; duration is bytes/rate, not packet count.
    await session._on_media(payload(True, 200))
    await session._on_media(payload(False, 200))
    await session._on_media(payload(True, 200))
    await session._on_media(payload(False, 800))
    for _ in range(10):
        await asyncio.sleep(0)
    session._stt.assert_awaited_once()
    pcm = session._stt.await_args.args[0]
    assert len(pcm) == 16000 * 2 * 1400 // 1000
    assert pcm[6400:12800] == b"\x00" * 6400


@pytest.mark.asyncio
async def test_empty_primary_stt_uses_fallback(session, monkeypatch):
    monkeypatch.setattr(ss, "STT_AVAILABLE", True)
    monkeypatch.setattr(ss, "_OPENAI_SDK_OK", True)
    monkeypatch.setattr(ss, "_groq_key", lambda: "test-only")
    monkeypatch.setattr(ss, "_GENAI_OK", True)
    session._groq_stt = AsyncMock(return_value="")
    session._gemini_stt = AsyncMock(return_value="Namaste")
    assert await session._stt(b"\x00" * 16000) == "Namaste"


@pytest.mark.asyncio
async def test_fallbacks_use_existing_vobiz_engines(session, monkeypatch):
    from app.telephony import vobiz_stream as vs

    gemini = AsyncMock(return_value="Gemini transcript")
    local = AsyncMock(return_value="Local transcript")
    monkeypatch.setattr(vs.VobizStreamSession, "_gemini_transcribe", gemini)
    monkeypatch.setattr(vs.VobizStreamSession, "_whisper_transcribe", local)
    pcm = b"\x00" * 16000
    assert await session._gemini_stt(pcm) == "Gemini transcript"
    assert await session._local_stt(pcm) == "Local transcript"


@pytest.mark.asyncio
async def test_reply_timeout_recovers_and_releases_turn(session, monkeypatch):
    monkeypatch.setattr(ss, "_REPLY_DEADLINE_S", 0.01)
    session._speech_buf = [b"\x00\x20" * 6400]
    session._stt = AsyncMock(return_value="Price kya hai?")

    async def stalled(_text):
        await asyncio.Event().wait()

    session._llm_reply = stalled
    await asyncio.wait_for(session._on_utterance(), 0.2)
    session._say.assert_awaited_once()
    assert session.hist[-1]["role"] == "assistant"


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["inbound", "outbound"])
async def test_three_audio_turns_keep_order(session, direction):
    session.direction = direction
    words = ["Namaste", "Marketing ka price kya hai?", "Website bhi milegi?"]
    session._stt = AsyncMock(side_effect=words)
    session._llm_reply = AsyncMock(side_effect=["Namaste ji", "Plan ki jaankari deti hoon", "Haan ji"])
    for _ in words:
        await session._on_media(payload(True, 400))
        await session._on_media(payload(False, 800))
        await asyncio.wait_for(session._turn_task, 0.2)
    assert [m["content"] for m in session.hist if m["role"] == "user"] == words
    assert session._say.await_count == 3
    assert session._turns == 3


@pytest.mark.asyncio
async def test_brain_constructor_runs_off_event_loop(session, monkeypatch):
    from app.voice_agent import telecaller_brain

    event_loop_thread = threading.get_ident()
    constructed = []

    class Brain:
        def __init__(self, **kwargs):
            constructed.append(threading.get_ident())

        async def reply(self, history, text):
            return "Haan ji"

    monkeypatch.setattr(telecaller_brain, "TelecallerBrain", Brain)
    assert await session._llm_reply("Namaste") == "Haan ji"
    assert constructed and constructed[0] != event_loop_thread


@pytest.mark.asyncio
async def test_stt_timeout_advances_to_next_provider(session, monkeypatch):
    monkeypatch.setattr(ss, "STT_AVAILABLE", True)
    monkeypatch.setattr(ss, "_STT_PROVIDER_DEADLINE_S", 0.01)
    monkeypatch.setattr(ss, "_OPENAI_SDK_OK", True)
    monkeypatch.setattr(ss, "_groq_key", lambda: "test-only")
    monkeypatch.setattr(ss, "_GENAI_OK", True)

    async def stalled(_pcm):
        await asyncio.Event().wait()

    session._groq_stt = stalled
    session._gemini_stt = AsyncMock(return_value="Namaste")
    assert await asyncio.wait_for(session._stt(b"\x00" * 16000), 0.2) == "Namaste"


@pytest.mark.asyncio
async def test_initial_disclosure_is_not_cancelled_by_caller_audio(monkeypatch):
    monkeypatch.setattr(ss, "TTS_AVAILABLE", True)
    s = ss.SmartfloStreamSession(AsyncMock())
    s.stream_sid = "synthetic-stream"
    started = asyncio.Event()
    release = asyncio.Event()

    async def tts(_text):
        started.set()
        await release.wait()
        return b"\x00\x00" * 320

    s._tts = tts
    await s._maybe_greet()
    await started.wait()
    first = s._play_task
    for _ in range(4):
        await s._on_media(payload())
    assert s._play_task is first and not first.done()
    release.set()
    await s.wait_playback()
    assert not s._greeting_active
    assert "AI assistant" in s.hist[0]["content"]


@pytest.mark.asyncio
async def test_continuous_noise_buffer_has_a_bound(session):
    session._stt = AsyncMock(return_value="")
    for _ in range(600):
        await session._on_media(payload())
    assert session._turn_task is not None
    await session._turn_task
    assert len(session._stt.await_args.args[0]) <= 16000 * 2 * 12
    assert not session._speech_buf


@pytest.mark.asyncio
async def test_cold_brain_survives_first_turn_deadline(session, monkeypatch):
    from app.voice_agent import telecaller_brain

    release = threading.Event()
    calls = []

    class Brain:
        def __init__(self, **kwargs):
            calls.append(1)
            release.wait(1.0)

        async def reply(self, history, text):
            return "Haan ji"

    monkeypatch.setattr(telecaller_brain, "TelecallerBrain", Brain)
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(session._llm_reply("Namaste"), 0.02)
    finally:
        release.set()
    assert await asyncio.wait_for(session._llm_reply("Sun rahe hain?"), 0.5) == "Haan ji"
    assert calls == [1]


@pytest.mark.asyncio
async def test_next_utterance_retained_while_reply_is_pending(session):
    entered = asyncio.Event()
    release = asyncio.Event()
    session._stt = AsyncMock(side_effect=["Namaste", "Price kya hai?"])

    async def reply(text):
        if text == "Namaste":
            entered.set()
            await release.wait()
        return "Haan ji"

    session._llm_reply = reply
    await session._on_media(payload(True, 400))
    await session._on_media(payload(False, 800))
    await entered.wait()
    await session._on_media(payload(True, 400))
    await session._on_media(payload(False, 800))
    release.set()
    await asyncio.wait_for(session._turn_task, 0.3)
    assert session._stt.await_count == 2
    assert [m["content"] for m in session.hist if m["role"] == "user"] == [
        "Namaste", "Price kya hai?"
    ]


@pytest.mark.asyncio
async def test_real_fallback_adapter_uses_fake_engine(session, monkeypatch):
    from app.telephony import vobiz_stream as vs
    from app.voice_agent import gemini_keys

    monkeypatch.setattr(gemini_keys, "active_key", lambda: "test-only")
    monkeypatch.setattr(vs, "_get_genai_client", lambda key: object())
    monkeypatch.setattr(vs, "_gemini_stt_sync", lambda *args: "Namaste")
    monkeypatch.setattr(vs, "_get_stt", lambda: ("fake", object()))
    monkeypatch.setattr(vs, "_stt_sync", lambda *args: "Local namaste")
    session._stt_bias = "marketing"
    assert await session._gemini_stt(b"\x00" * 16000) == "Namaste"
    assert await session._local_stt(b"\x00" * 16000) == "Local namaste"
