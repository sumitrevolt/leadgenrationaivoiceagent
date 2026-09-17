"""Cold optional TTS must not hold up a browser voice answer."""

import asyncio

import pytest

from app.api import web_call as wc


class Socket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_cold_filler_does_not_block_answer_or_send_late(monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()
    ws = Socket()

    async def filler():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def reply():
        await started.wait()
        return "answer"

    monkeypatch.setattr(wc, "_filler_b64", filler)
    result = await asyncio.wait_for(
        wc._reply_with_optional_filler(reply(), ws, "question", enabled=True), 1
    )
    assert result == "answer"
    assert cancelled.is_set()
    await asyncio.sleep(0)
    assert ws.messages == []


@pytest.mark.asyncio
async def test_ready_filler_precedes_answer(monkeypatch):
    ws = Socket()

    async def filler():
        return "audio"

    async def reply():
        await asyncio.sleep(0)
        assert ws.messages[0]["audio_b64"] == "audio"
        return "answer"

    monkeypatch.setattr(wc, "_filler_b64", filler)
    assert await wc._reply_with_optional_filler(reply(), ws, "q", enabled=True) == "answer"
    assert len(ws.messages) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_disabled_or_failed_filler_cannot_fail_answer(monkeypatch, enabled):
    calls = []

    async def filler():
        calls.append(True)
        raise RuntimeError("provider unavailable")

    async def reply():
        await asyncio.sleep(0)
        return "answer"

    monkeypatch.setattr(wc, "_filler_b64", filler)
    ws = Socket()
    assert await wc._reply_with_optional_filler(reply(), ws, "q", enabled=enabled) == "answer"
    assert bool(calls) is enabled
    assert ws.messages == []


@pytest.mark.asyncio
async def test_cancelled_answer_drains_filler(monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def filler():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def reply():
        await asyncio.Event().wait()

    monkeypatch.setattr(wc, "_filler_b64", filler)
    task = asyncio.create_task(wc._reply_with_optional_filler(reply(), Socket(), "q", enabled=True))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
