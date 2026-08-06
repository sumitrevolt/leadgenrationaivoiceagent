"""LLM token stream → sentence chunks for early TTS (voice hot path).

Gated ``USE_LLM_STREAM_TTS=1`` (default OFF). Works with free_ai.chat_stream;
never raises.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator

# Sentence terminators — Latin (. ! ?), Arabic question mark (؟), AND the Hindi
# danda (। ॥). Without the danda a Hinglish/Hindi reply ("namaste ji।") never
# chunks mid-stream, so the FIRST audio waits for the whole reply -> higher
# time-to-first-audio (the #1 voice-latency metric). The trailing-\s+ requirement
# stays so decimals like "3.5" don't split.
_SENT_END = re.compile(r"(?<=[.!?؟।॥])\s+|\n+")

# Clause separators for the optional early FIRST-chunk flush (TTFA boost): comma,
# semicolon, colon, Hindi/Arabic comma, and spaced dashes — natural micro-pauses
# a TTS can speak. Used only when STREAM_TTS_CLAUSE_FLUSH=1 (default OFF).
_CLAUSE_END = re.compile(r"(?<=[,;:।،])\s+|\s[—–-]\s")


def _env_flag(name: str, default_on: bool = False) -> bool:
    """Read a boolean env flag. When ``default_on`` is True the flag is enabled
    unless explicitly set to a false value (0/false/no/off) — used for latency
    features that should be ON for the shipped voice path but stay disable-able
    per deploy without a redeploy."""
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default_on
    return raw in ("1", "true", "yes", "on")


def _clause_min_chars(default: int = 45) -> int:
    """First-chunk clause flush only fires once the buffer reaches this many chars
    (avoids choppy 2-word fragments). Env: STREAM_TTS_CLAUSE_MIN."""
    try:
        raw = os.getenv("STREAM_TTS_CLAUSE_MIN", "")
        return int(float(raw)) if raw.strip() else default
    except Exception:
        return default


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


def pop_clause(buf: str) -> tuple[str, str]:
    """Like pop_sentence but breaks at the first CLAUSE boundary (comma/dash/danda).
    Used only to flush the FIRST chunk early so audio starts sooner."""
    b = buf or ""
    if not b.strip():
        return "", b
    m = _CLAUSE_END.search(b)
    if m:
        # Drop the trailing clause separator itself (comma/dash) — the chunk reads
        # cleaner for TTS; the pause is implied by the chunk boundary.
        head = b[: m.start()].strip(" ,;:।،—–-")
        rest = b[m.end() :]
        if head:
            return head, rest
    return "", b


async def iter_sentences_from_tokens(
    token_stream: AsyncIterator[str],
) -> AsyncIterator[str]:
    """Buffer token deltas; yield on sentence boundaries.

    With STREAM_TTS_CLAUSE_FLUSH=1 (default ON since 2026-08-06) the FIRST chunk
    may also flush early at a clause boundary once it reaches STREAM_TTS_CLAUSE_MIN
    chars — this cuts time-to-first-audio on a long opening sentence without making
    the rest of the reply choppy (only the first chunk is eligible). Set
    STREAM_TTS_CLAUSE_FLUSH=0 to restore wait-for-full-sentence (default OFF legacy).
    """
    buf = ""
    first_done = False
    clause_flush = _env_flag("STREAM_TTS_CLAUSE_FLUSH", default_on=True)
    clause_min = _clause_min_chars()
    async for tok in token_stream:
        if not tok:
            continue
        buf += tok
        while True:
            sent, buf = pop_sentence(buf)
            if sent:
                first_done = True
                yield sent
                continue
            if clause_flush and not first_done and len(buf) >= clause_min:
                head, buf = pop_clause(buf)
                if head:
                    first_done = True
                    yield head
                    continue
            break
    tail = (buf or "").strip()
    if tail:
        yield tail


__all__ = [
    "stream_tts_enabled",
    "pop_sentence",
    "pop_clause",
    "iter_sentences_from_tokens",
]
