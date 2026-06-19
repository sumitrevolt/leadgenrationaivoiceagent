"""LLM token stream → sentence chunks for early TTS (voice hot path).

Gated ``USE_LLM_STREAM_TTS=1`` (default OFF). Works with free_ai.chat_stream;
never raises.
"""
from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator

_SENT_END = re.compile(r"(?<=[.!?؟])\s+|\n+")


def stream_tts_enabled() -> bool:
    return (os.getenv("USE_LLM_STREAM_TTS", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def pop_sentence(buf: str) -> tuple[str, str]:
    """Return (complete_sentence_or_empty, remainder)."""
    b = buf or ""
    if not b.strip():
        return "", b
    m = _SENT_END.search(b)
    if m:
        sent = b[: m.start()].strip()
        rest = b[m.end() :]
        if sent:
            return sent, rest
    return "", b


async def iter_sentences_from_tokens(
    token_stream: AsyncIterator[str],
) -> AsyncIterator[str]:
    """Buffer token deltas; yield on sentence boundaries."""
    buf = ""
    async for tok in token_stream:
        if not tok:
            continue
        buf += tok
        while True:
            sent, buf = pop_sentence(buf)
            if sent:
                yield sent
            else:
                break
    tail = (buf or "").strip()
    if tail:
        yield tail


__all__ = ["stream_tts_enabled", "pop_sentence", "iter_sentences_from_tokens"]
