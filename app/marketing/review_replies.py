"""
review_replies.py — Google/JustDial review ke liye 3 ready Hinglish replies.
============================================================================

LLM-first (free_ai chain), sentiment-based TEMPLATE fallback — KABHI empty
nahi, KABHI raise nahi. Output: short / medium / detailed teen variants.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore


# --------------------------------------------------------------------------- #
# Sentiment templates — {business_name} fill hota hai
# --------------------------------------------------------------------------- #

_POSITIVE = [
    (
        "short",
        "Dhanyawad! 🙏 Aapka pyaar hi {business_name} ki asli kamai hai. Phir se zaroor aaiye!",
    ),
    (
        "medium",
        "Bahut bahut shukriya aapke kind words ke liye! 🙏 {business_name} ki team ke liye "
        "aapki ye review kisi award se kam nahi. Agli baar bhi isi quality ki guarantee — "
        "zaroor padhariye!",
    ),
    (
        "detailed",
        "Dil se dhanyawad! 🙏 Aap jaise customers ki wajah se hi {business_name} aaj is "
        "mukaam par hai. Aapka feedback humari poori team ke saath share kiya gaya hai — "
        "sabke chehre par muskaan aa gayi. Aapke doston/family ko bhi humari services "
        "chahiye hon to bas ek call door hain. Phir se swagat hai! ✨",
    ),
]

_NEGATIVE = [
    (
        "short",
        "Maafi chahte hain aapke experience ke liye. 🙏 {business_name} isse seriously le raha "
        "hai — please humein direct call/DM karein, turant solve karenge.",
    ),
    (
        "medium",
        "Aapke experience ke liye dil se maafi. Ye humare standard se bilkul neeche hai aur "
        "{business_name} ki team ne ise turant flag kiya hai. Please apna contact DM karein "
        "ya humein call karein — 24 ghante me aapki problem ka solution denge. 🙏",
    ),
    (
        "detailed",
        "Sabse pehle — sincere apology. 🙏 Jo hua wo {business_name} ke values ke khilaaf "
        "hai aur hum ise personally fix karna chahte hain. Humne internally review shuru "
        "kar diya hai taaki ye kisi aur ke saath na ho. Please humein call ya DM karke "
        "apni details dein — owner khud aapse baat karenge aur jo bhi sahi hoga (replacement/"
        "re-service/refund) turant karenge. Aapka bharosa wapas jeetna hi humara goal hai.",
    ),
]

_NEUTRAL = [
    (
        "short",
        "Feedback ke liye shukriya! 🙏 {business_name} hamesha behtar hone ki koshish me hai.",
    ),
    (
        "medium",
        "Aapke honest feedback ke liye dhanyawad! {business_name} aapke points ko seriously "
        "le raha hai — agli visit par aapko farak zaroor dikhega. Koi bhi baat ho to humein "
        "direct bata sakte hain. 🙏",
    ),
    (
        "detailed",
        "Thank you for taking the time to review us! 🙏 {business_name} me hum har feedback "
        "se seekhte hain — aapke points team ke saath discuss kiye gaye hain aur jahan "
        "improvement chahiye wahan kaam shuru ho gaya hai. Agli baar aapko 5-star experience "
        "dene ka waada hai. Koi suggestion ho to humein call/DM karein, hum sun rahe hain!",
    ),
]

_NEG_WORDS = (
    "kharab",
    "bekar",
    "worst",
    "bad ",
    "ganda",
    "fraud",
    "cheat",
    "rude",
    "slow",
    "late",
    "refund",
    "complaint",
    "dhokha",
    "waste",
    "poor",
)
_POS_WORDS = (
    "accha",
    "achha",
    "best",
    "great",
    "amazing",
    "excellent",
    "awesome",
    "badhiya",
    "mast",
    "love",
    "perfect",
    "wonderful",
    "shandar",
)


def _sentiment(review_text: str, rating: float | None) -> str:
    """rating-first sentiment; rating na ho to halka keyword guess; warna neutral."""
    try:
        if rating is not None:
            r = float(rating)
            if r >= 4:
                return "positive"
            if r <= 2:
                return "negative"
            return "neutral"
    except (TypeError, ValueError):
        pass
    low = (review_text or "").lower()
    if any(w in low for w in _NEG_WORDS):
        return "negative"
    if any(w in low for w in _POS_WORDS):
        return "positive"
    return "neutral"


def _template_replies(business_name: str, sentiment: str) -> list[dict[str, str]]:
    pool = {"positive": _POSITIVE, "negative": _NEGATIVE}.get(sentiment, _NEUTRAL)
    return [
        {"label": label, "text": text.format(business_name=business_name)} for label, text in pool
    ]


def _parse_llm_replies(text: str) -> list[dict[str, str]]:
    """SHORT:/MEDIUM:/DETAILED: markers parse karo — teeno mile tabhi valid."""
    out: list[dict[str, str]] = []
    try:
        for label in ("short", "medium", "detailed"):
            m = re.search(
                rf"{label}\s*:\s*(.+?)(?=\n\s*(?:SHORT|MEDIUM|DETAILED)\s*:|\Z)",
                text,
                re.S | re.I,
            )
            if m:
                reply = m.group(1).strip().strip('"').strip()
                if reply:
                    out.append({"label": label, "text": reply})
    except Exception:  # pragma: no cover
        return []
    return out if len(out) == 3 else []


async def generate_replies(
    review_text: str,
    rating: float | None = None,
    business_name: str = "",
    tone: str = "professional",
) -> dict[str, Any]:
    """Ek review ke liye 3 Hinglish replies (short/medium/detailed). KABHI empty nahi.

    Returns: {"replies": [{"label","text"} x3], "sentiment", "provider"}.
    """
    review_text = (review_text or "").strip()
    business_name = (business_name or "").strip() or "Hamari team"
    tone = (tone or "professional").strip().lower() or "professional"
    sentiment = _sentiment(review_text, rating)

    replies: list[dict[str, str]] = []
    provider = ""

    if free_ai is not None and review_text:
        try:
            system = (
                "Tu ek Indian business ka review-reply expert hai. Customer ke Google "
                f"review ka {tone} tone me Hinglish (Roman script) jawab likh. "
                "Output EXACTLY is format me, koi extra commentary nahi:\n"
                "SHORT: <1-2 line reply>\n"
                "MEDIUM: <3-4 line reply>\n"
                "DETAILED: <5-6 line reply>\n"
                "Rules: customer ko thank/apologize sahi sentiment ke hisab se, "
                "business ka naam naturally use kar, negative par defensive mat ban — "
                "maafi + fix + direct contact invite kar."
            )
            user = (
                f"Business: {business_name}\n"
                f"Rating: {rating if rating is not None else 'pata nahi'}\n"
                f"Review: {review_text[:800]}"
            )
            text, provider = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=450,
                temperature=0.7,
            )
            if text and text.strip():
                replies = _parse_llm_replies(text)
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"generate_replies LLM step failed, using templates: {e}")

    if not replies:
        replies = _template_replies(business_name, sentiment)
        provider = "template"

    return {
        "replies": replies,
        "sentiment": sentiment,
        "provider": provider or "llm",
    }
