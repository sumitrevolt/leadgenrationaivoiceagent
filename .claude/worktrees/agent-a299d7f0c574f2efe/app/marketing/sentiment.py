"""Sentiment analysis — reviews/feedback ka mood + themes + action (free_ai + rule baseline).

2026 marketing must-have: real-time sentiment on reviews/social mentions. Given a batch of
review/feedback texts → per-text sentiment (rule baseline) + an LLM summary (themes + action).
Never raises.

analyze(texts) -> {count, breakdown{positive/negative/neutral}, score, summary}
"""

from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger(__name__)

_POS = {
    "good",
    "great",
    "best",
    "love",
    "excellent",
    "amazing",
    "accha",
    "badhiya",
    "mast",
    "behtreen",
    "👍",
    "🙏",
    "❤",
}
_NEG = {
    "bad",
    "worst",
    "poor",
    "terrible",
    "ganda",
    "bekaar",
    "slow",
    "rude",
    "kharab",
    "late",
    "👎",
}


def _rule(text: str) -> str:
    t = (text or "").lower()
    p = sum(w in t for w in _POS)
    n = sum(w in t for w in _NEG)
    return "positive" if p > n else "negative" if n > p else "neutral"


async def analyze(texts: list[str]) -> dict:
    items = [str(t).strip() for t in (texts or []) if str(t).strip()][:50]
    if not items:
        return {"count": 0, "breakdown": {}, "score": 0.0, "summary": ""}

    labels = [_rule(t) for t in items]
    bd = dict(Counter(labels))
    score = round((bd.get("positive", 0) - bd.get("negative", 0)) / len(items), 2)

    summary = ""
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            system="Tu reviews analyse karta hai. Diye reviews ka overall sentiment, top 2-3 themes "
            "(kya acha, kya improve), aur ek concrete action — sab 3-4 line Hinglish me.",
            messages=[{"role": "user", "content": "\n".join(f"- {t[:160]}" for t in items[:20])}],
            max_tokens=150,
            temperature=0.3,
        )
        summary = (reply or "").strip()
    except Exception as e:
        logger.info("sentiment summary err: %s", e)

    return {"count": len(items), "breakdown": bd, "score": score, "summary": summary}


__all__ = ["analyze"]
