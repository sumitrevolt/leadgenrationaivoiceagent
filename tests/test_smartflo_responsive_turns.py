"""Offline timing/order regressions; all STT, LLM and TTS providers are mocked."""

import asyncio
import base64
from unittest.mock import AsyncMock

import pytest

from app.telephony import smartflo_stream as ss

pytestmark = pytest.mark.skip(
    reason="speculative responsive-turns feature not yet merged into frozen voice pipeline"
)


def audio(ms, speech=True):
    pcm = (b"\x00\x20" if speech else b"\x00\x00") * (8 * ms)
    return base64.b64encode(ss.pcm16_to_mulaw(pcm)).decode()


@pytest.mark.asyncio
async def test_first_sentence_plays_before_remainder_tts_finishes():
    s = ss.SmartfloStreamSession(AsyncMock())
    first_sent = asyncio.Event()
    release_rest = asyncio.Event()
    spoken = []

    async def tts(text):
        if text == "Doosra jawab baad mein.":
            await release_rest.wait()
        return b"\x00\x20" * 320

    async def send(pcm, generation):
        spoken.append(pcm)
        first_sent.set()

    s._tts = tts
    s._send_mulaw_audio = send
    task = asyncio.create_task(
        s._speak_task("Pehla jawab abhi. Doosra jawab baad mein.", s._playback_generation)
    )
    try:
        await asyncio.wait_for(first_sent.wait(), 0.3)
        assert not release_rest.is_set()
        release_rest.set()
        await asyncio.wait_for(task, 0.3)
        assert len(spoken) == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_barge_cancels_prefetched_synthesis():
    s = ss.SmartfloStreamSession(AsyncMock())
    rest_started = asyncio.Event()
    rest_cancelled = asyncio.Event()

    async def tts(text):
        if text == "Doosra jawab baad mein.":
            rest_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                rest_cancelled.set()
        return b"\x00\x20" * 320

    async def send(*args):
        await rest_started.wait()
        await asyncio.Event().wait()

    s._tts = tts
    s._send_mulaw_audio = send
    task = asyncio.create_task(
        s._speak_task("Pehla jawab abhi. Doosra jawab baad mein.", s._playback_generation)
    )
    try:
        await asyncio.wait_for(rest_started.wait(), 0.3)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert rest_cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("packet_ms", [20, 140, 280])
async def test_guard_uses_sustained_audio_duration(monkeypatch, packet_ms):
    monkeypatch.setenv("BARGE_GUARD", "1")
    monkeypatch.setenv("TURN_BARGE_GUARD_MS", "280")
    s = ss.SmartfloStreamSession(AsyncMock())
    s._speaking = True
    s._barge_in = AsyncMock()
    for _ in range(280 // packet_ms):
        await s._on_media(audio(packet_ms))
    s._barge_in.assert_awaited_once()


@pytest.mark.asyncio
async def test_noise_bursts_do_not_accumulate_into_interruption(monkeypatch):
    monkeypatch.setenv("BARGE_GUARD", "1")
    monkeypatch.setenv("TURN_BARGE_GUARD_MS", "280")
    s = ss.SmartfloStreamSession(AsyncMock())
    s._speaking = True
    s._barge_in = AsyncMock()
    for _ in range(4):
        await s._on_media(audio(100))
        await s._on_media(audio(20, False))
    s._barge_in.assert_not_awaited()


@pytest.mark.asyncio
async def test_caller_resuming_while_model_thinks_suppresses_old_reply():
    s = ss.SmartfloStreamSession(AsyncMock())
    model_started = asyncio.Event()
    finish_model = asyncio.Event()
    s._stt = AsyncMock(return_value="Mujhe marketing chahiye")
    s._say = AsyncMock()

    async def reply(_):
        model_started.set()
        await finish_model.wait()
        return "Purana jawab"

    s._llm_reply = reply
    task = asyncio.create_task(s._on_utterance(b"\x00\x20" * 6400))
    await asyncio.wait_for(model_started.wait(), 0.3)
    await s._on_media(audio(400))
    finish_model.set()
    await asyncio.wait_for(task, 0.3)
    s._say.assert_not_awaited()
    assert s.hist == [{"role": "user", "content": "Mujhe marketing chahiye"}]
