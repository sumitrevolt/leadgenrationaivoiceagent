"""Free-stack DETERMINISTIC eval metrics (no LLM judge, no network, no cost).

eval_gate.py gives us the regression-gating mechanism, but its scores came from
DeepEval (an LLM judge → network + cost → can't run in offline CI). These pure
functions produce 0..1 scores from text alone so the guardrail
(`scripts/eval_guardrail.py`) can run on every build for free and feed
`eval_gate.score_and_gate`.

Two metrics:
  * voice_turn_score  — encodes the telecaller rule "≤2 sentences / ≤1 question,
    no empty/echo, no consecutive repeats" (mirrors scripts/agent_tester.py flags).
  * grounding_score   — lexical RAG-faithfulness proxy: how much of the answer's
    content vocabulary actually appears in the retrieved context.

All pure + side-effect-free + never-raise → trivially unit-testable.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["voice_turn_score", "grounding_score", "transcript_quality"]

_BOT_ROLES = {"assistant", "bot", "agent", "ai"}
_EMPTY_MARKERS = ("", "[echo", "(no response)", "...", "…")
_SENTENCE_END = re.compile(r"[.!?।]+")
_WORD = re.compile(r"[a-z0-9ऀ-ॿ]{3,}")  # latin + devanagari, len>=3


def _is_empty(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    return any(t == m or t.startswith(m) for m in _EMPTY_MARKERS if m)


def _sentence_count(text: str) -> int:
    parts = [p for p in _SENTENCE_END.split(text or "") if p.strip()]
    return max(1, len(parts)) if (text or "").strip() else 0


def voice_turn_score(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Score a conversation's BOT turns against the telecaller quality rules.

    Returns {"score": 0..1, "bot_turns": n, "flags": {...counts...}}.
    score = 1 - (total_issues / bot_turns), clamped to [0,1]. Empty convo → 1.0
    (nothing wrong) so an empty fixture never reports a false regression.
    """
    flags = {"empty": 0, "too_long": 0, "double_question": 0, "repeat": 0}
    bot_turns = 0
    prev_reply: str | None = None
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("role", "")).strip().lower() not in _BOT_ROLES:
            continue
        bot_turns += 1
        content = str(m.get("content", "") or "")
        if _is_empty(content):
            flags["empty"] += 1
            prev_reply = content.strip().lower()
            continue
        if _sentence_count(content) > 2:
            flags["too_long"] += 1
        if content.count("?") + content.count("？") > 1:
            flags["double_question"] += 1
        norm = content.strip().lower()
        if prev_reply is not None and norm == prev_reply:
            flags["repeat"] += 1
        prev_reply = norm

    if bot_turns == 0:
        return {"score": 1.0, "bot_turns": 0, "flags": flags}
    issues = sum(flags.values())
    score = max(0.0, min(1.0, 1.0 - issues / float(bot_turns)))
    return {"score": round(score, 4), "bot_turns": bot_turns, "flags": flags}


def grounding_score(answer: str, context: str) -> float:
    """Lexical RAG-faithfulness proxy in [0,1]: fraction of the answer's content
    tokens that also appear in the retrieved context. Empty answer or empty
    context → 0.0. Cheap, deterministic, language-agnostic (latin + devanagari)."""
    a = set(_WORD.findall((answer or "").lower()))
    c = set(_WORD.findall((context or "").lower()))
    if not a or not c:
        return 0.0
    return round(len(a & c) / float(len(a)), 4)


def transcript_quality(messages: list[dict[str, Any]]) -> float:
    """Convenience scalar (just the voice_turn_score) for the guardrail/eval_gate."""
    return float(voice_turn_score(messages).get("score", 1.0))
