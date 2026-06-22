"""LLM stream → sentence TTS helpers + TelecallerBrain stream path."""

from __future__ import annotations

import pytest

from app.voice_agent.llm_stream_tts import (
    iter_sentences_from_tokens,
    pop_clause,
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


@pytest.mark.asyncio
async def test_phone_stream_think_and_say_stream_mock(monkeypatch):
    """phone_stream stream path speaks sentences when flag ON."""
    from app.voice_agent import phone_stream as ps

    monkeypatch.setenv("USE_LLM_STREAM_TTS", "1")
    monkeypatch.setattr(ps, "TTS_AVAILABLE", True)

    spoken: list[str] = []

    class _FakeTC:
        async def reply_stream_sentences(self, history, user_text):
            yield "Pehla sentence."
            yield "Doosra sentence."

    sess = ps.PhoneCallSession(
        websocket=None,  # type: ignore[arg-type]
        niche="general",
        client_name="Demo",
    )
    sess._running = True
    sess._telecaller = _FakeTC()
    sess._telecaller_tried = True

    async def _fake_gen(_gen):
        async for s in _gen:
            spoken.append(s)

    monkeypatch.setattr(sess, "_speak_from_sentence_gen", _fake_gen)

    reply = await sess._think_and_say_stream("hello")
    assert "Pehla" in reply
    assert spoken == ["Pehla sentence.", "Doosra sentence."]


# --------------------------------------------------------------------------- #
# Hindi danda + early clause-flush (time-to-first-audio improvements).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_iter_sentences_splits_on_hindi_danda():
    """A Hindi/Hinglish reply ending in danda (।) chunks per sentence so the
    first audio doesn't wait for the whole reply."""

    async def _tok():
        for part in ("Namaste ji। ", "Aap kaise hain?"):
            yield part

    out = [s async for s in iter_sentences_from_tokens(_tok())]
    assert out == ["Namaste ji।", "Aap kaise hain?"]


def test_pop_clause_breaks_on_comma():
    head, rest = pop_clause("dekhiye sir, aapka business kaisa hai")
    assert head == "dekhiye sir"
    assert rest == "aapka business kaisa hai"


def test_pop_clause_no_break_without_separator():
    head, rest = pop_clause("ek lambi line bina comma ke")
    assert head == ""
    assert rest == "ek lambi line bina comma ke"


@pytest.mark.asyncio
async def test_clause_flush_first_chunk_only(monkeypatch):
    monkeypatch.setenv("STREAM_TTS_CLAUSE_FLUSH", "1")
    monkeypatch.setenv("STREAM_TTS_CLAUSE_MIN", "20")

    async def _tok():
        yield "dekhiye sir yeh ek lambi shuruaat hai, "
        yield "phir baaki baat poori hoti hai."

    out = [s async for s in iter_sentences_from_tokens(_tok())]
    assert out[0] == "dekhiye sir yeh ek lambi shuruaat hai"
    assert out[-1].endswith("hoti hai.")


@pytest.mark.asyncio
async def test_clause_flush_off_by_default(monkeypatch):
    monkeypatch.delenv("STREAM_TTS_CLAUSE_FLUSH", raising=False)

    async def _tok():
        yield "dekhiye sir yeh ek lambi shuruaat hai, phir baaki baat poori hoti hai."

    out = [s async for s in iter_sentences_from_tokens(_tok())]
    assert out == [
        "dekhiye sir yeh ek lambi shuruaat hai, phir baaki baat poori hoti hai."
    ]
