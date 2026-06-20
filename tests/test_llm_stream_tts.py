"""LLM stream → sentence TTS helpers + TelecallerBrain stream path."""

from __future__ import annotations

import pytest

from app.voice_agent.llm_stream_tts import (
    iter_sentences_from_tokens,
    pop_sentence,
    stream_tts_enabled,
)


@pytest.mark.asyncio
async def test_iter_sentences_from_tokens_multipart():
    async def _tok():
        for part in ("Namaste sir. ", "Aapka ", "budget kya hai?"):
            yield part

    out = [s async for s in iter_sentences_from_tokens(_tok())]
    assert out == ["Namaste sir.", "Aapka budget kya hai?"]


@pytest.mark.asyncio
async def test_iter_sentences_flushes_tail_without_punct():
    async def _tok():
        yield "Ji sun rahi hoon"

    out = [s async for s in iter_sentences_from_tokens(_tok())]
    assert out == ["Ji sun rahi hoon"]


def test_pop_sentence_no_split_mid_buffer():
    s, rest = pop_sentence("Hello there")
    assert s == ""
    assert rest == "Hello there"


@pytest.mark.asyncio
async def test_reply_stream_sentences_uses_chat_stream(monkeypatch):
    from app.voice_agent.telecaller_brain import TelecallerBrain

    async def _fake_stream(**kwargs):
        for t in ("Achha sir. ", "Budget kitna hai?"):
            yield t

    async def _fake_kb(_text: str):
        return ""

    monkeypatch.setattr(
        "app.voice_agent.free_ai.chat_stream",
        lambda **kw: _fake_stream(**kw),
    )
    brain = TelecallerBrain(niche="general", client_name="Demo")
    monkeypatch.setattr(brain, "_kb_facts", _fake_kb)

    parts = [s async for s in brain.reply_stream_sentences([], "hello")]
    assert len(parts) >= 1
    joined = " ".join(parts)
    assert "budget" in joined.lower() or "achha" in joined.lower()


@pytest.mark.asyncio
async def test_reply_stream_sentences_fallback_on_empty_stream(monkeypatch):
    from app.voice_agent.telecaller_brain import TelecallerBrain

    async def _empty(**kwargs):
        if False:
            yield ""  # pragma: no cover

    async def _fake_kb(_text: str):
        return ""

    async def _one_shot(_history, _text):
        return "Fallback line."

    monkeypatch.setattr("app.voice_agent.free_ai.chat_stream", _empty)
    brain = TelecallerBrain(niche="general", client_name="Demo")
    monkeypatch.setattr(brain, "_kb_facts", _fake_kb)
    monkeypatch.setattr(brain, "reply", _one_shot)

    parts = [s async for s in brain.reply_stream_sentences([], "hello")]
    assert parts == ["Fallback line."]


def test_stream_tts_flag_on(monkeypatch):
    monkeypatch.setenv("USE_LLM_STREAM_TTS", "1")
    assert stream_tts_enabled() is True
