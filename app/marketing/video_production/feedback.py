"""Natural-language customer video feedback → structured revision tasks.

Never silently treats ambiguous replies as approval.
"""

from __future__ import annotations

import re
from typing import Any

# Explicit intent tokens (English + Hinglish)
_APPROVE_RE = re.compile(
    r"^\s*(approve|approved|ok\s*post|post\s*kar\s*do|publish|haa?\s*theek|haan?\s*post|"
    r"video\s*theek\s*hai.*post|final\s*ok|go\s*ahead)\s*[.!]*\s*$",
    re.I,
)
_REJECT_RE = re.compile(
    r"^\s*(reject|rejected|mat\s*post|cancel|nahi\s*chahiye|don't\s*post)\s*[.!]*\s*$",
    re.I,
)
_CHANGES_RE = re.compile(
    r"^\s*(changes?|change\s*chahiye|revise|edit|update)\b",
    re.I,
)

# Ambiguous — must NOT approve
_AMBIGUOUS_RE = re.compile(
    r"^\s*(theek|thik|ok|okay|haan|han|hmm+|dekh(ta|te)?\s*(hoon|hun)?|"
    r"dekhta\s*hu|looks?\s*okay|looks?\s*fine|👍|👌|🙂|😊|\.+)\s*$",
    re.I,
)

_CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("pricing", re.compile(r"\b(price|pricing|₹|rs\.?|rupaye|rate)\b", re.I)),
    ("offer", re.compile(r"\b(offer|discount|sale|deal|expiry|valid)\b", re.I)),
    ("branding", re.compile(r"\b(logo|brand|colour|color|theme)\b", re.I)),
    ("voice", re.compile(r"\b(voice|awaz|female|male|tts)\b", re.I)),
    ("music", re.compile(r"\b(music|bgm|song|gaana)\b", re.I)),
    ("subtitle", re.compile(r"\b(subtitle|caption\s*timing|subtitles)\b", re.I)),
    ("duration", re.compile(r"\b(slow|fast|duration|length|lamb[ai]|chhota|lamba)\b", re.I)),
    ("cta", re.compile(r"\b(cta|call\s*to\s*action|whatsapp|call\s*karo)\b", re.I)),
    ("text_overlay", re.compile(r"\b(text|overlay|font|size|bada|chhota)\b", re.I)),
    ("script", re.compile(r"\b(script|dialogue|bolna|line)\b", re.I)),
    ("asset", re.compile(r"\b(image|photo|video\s*clip|asset|picture)\b", re.I)),
    ("platform", re.compile(r"\b(instagram|reels?|shorts?|youtube|facebook|linkedin)\b", re.I)),
]


def classify_feedback(raw: str) -> dict[str, Any]:
    """Return {intent, categories, tasks, ambiguous, clarification}.

    intent ∈ {approve, changes, reject, ambiguous, unrelated}
    """
    text = (raw or "").strip()
    if not text:
        return {
            "intent": "ambiguous",
            "categories": [],
            "tasks": [],
            "ambiguous": True,
            "clarification": ("Reply APPROVE to post, CHANGES + what to fix, or REJECT to cancel."),
            "raw": text,
        }

    if _AMBIGUOUS_RE.match(text) and not _APPROVE_RE.match(text):
        return {
            "intent": "ambiguous",
            "categories": [],
            "tasks": [],
            "ambiguous": True,
            "clarification": (
                "Samajh nahi aaya. APPROVE likho post ke liye, CHANGES + detail, ya REJECT."
            ),
            "raw": text,
        }

    if _APPROVE_RE.match(text) or (
        re.search(r"video\s*(theek|thik)\s*hai", text, re.I)
        and re.search(r"post\s*kar", text, re.I)
    ):
        return {
            "intent": "approve",
            "categories": [],
            "tasks": [],
            "ambiguous": False,
            "clarification": "",
            "raw": text,
        }

    if _REJECT_RE.match(text):
        return {
            "intent": "reject",
            "categories": [],
            "tasks": [],
            "ambiguous": False,
            "clarification": "",
            "raw": text,
        }

    cats: list[str] = []
    for name, pat in _CATEGORY_RULES:
        if pat.search(text):
            cats.append(name)
    if not cats and (_CHANGES_RE.match(text) or len(text) > 8):
        cats = ["other"]

    if cats or _CHANGES_RE.match(text):
        tasks = [
            {
                "category": c,
                "instruction": text[:400],
                "priority": "normal",
            }
            for c in (cats or ["other"])
        ]
        return {
            "intent": "changes",
            "categories": cats or ["other"],
            "tasks": tasks,
            "ambiguous": False,
            "clarification": "",
            "raw": text,
        }

    return {
        "intent": "ambiguous",
        "categories": [],
        "tasks": [],
        "ambiguous": True,
        "clarification": (
            "Is reply se clear nahi. APPROVE / CHANGES <detail> / REJECT mein se ek bhejo."
        ),
        "raw": text,
    }


__all__ = ["classify_feedback"]
