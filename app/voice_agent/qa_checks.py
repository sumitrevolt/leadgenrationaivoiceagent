"""
Conversation QA checks (India-telecalling discipline) — reusable, pure, testable.
==============================================================================

D-13 (P4): the eval-harness's "judge" half. Pure functions over a transcript
(``[{"role": "user"|"assistant", "content": str}, ...]``) that flag the
behaviours an Indian telecaller MUST get right — so both ``scripts/agent_tester.py``
(live web-call QA) and ``eval_suite.py`` (persona sim) score the same way.

Checks (each returns a finding string, or None / [] when clean):
  * check_pushy_after_softno   — bot kept pitching after the caller's 2nd soft-no
  * check_talk_listen_ratio    — bot talked more than its share (listen ≥ talk)
  * check_missing_permission   — opener never asked "do minute baat kar sakti hoon?"
  * check_literal_translation  — robotic Sanskritised translationese (not natural Hinglish)

Design: no LLM, no network, import-safe, never raises. Heuristic by nature —
tuned for recall on the India failure-modes, documented where fuzzy.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- #
# Pattern banks (lowercased, ASCII-folded Hinglish + Devanagari friendly)
# --------------------------------------------------------------------------- #
# Soft "no" — the polite Indian refusal that a pushy bot mis-reads as "maybe".
_SOFT_NO_PATTERNS = [
    r"dekh\s*te?\s+ha?i?n",          # dekhte hain
    r"soch\s*ke?\s+bata",            # soch ke bata(ta/ti) hoon
    r"baad\s+m[ei]\b",               # baad me (baat)
    r"abhi\s+nah[ie]",               # abhi nahi
    r"time\s+nah[ie]",               # time nahi
    r"zarur\s*at?\s+nah[ie]",        # zarurat nahi
    r"(?:interest|intrest)\s+nah[ie]",
    r"nah[ie]\s+chahiy?e",           # nahi chahiye
    r"theek\s+hai\s+theek\s+hai",    # rushed brush-off
    r"whats?\s*app\s*(?:p[ae]?\s*)?bhej",  # "whatsapp pe bhej do"
    r"रुचि\s*नहीं|नहीं\s*चाहिए|बाद\s*में",
]
_SOFT_NO_RE = [re.compile(p) for p in _SOFT_NO_PATTERNS]

# Permission / timing ask — Gong: permission-opener converts ~5–10x better.
_PERMISSION_PATTERNS = [
    r"(?:do|ek|2)\s*minute",
    r"baat\s+kar\s+sak",             # baat kar sakti/sakte hoon
    r"busy\s+(?:to|ho|hain)",
    r"abhi\s+(?:sahi\s+)?(?:samay|time)",
    r"theek\s+(?:samay|time)\s+hai",
    r"convenient",
    r"baat\s+karne?\s+ka\s+(?:samay|time)",
]
_PERMISSION_RE = [re.compile(p) for p in _PERMISSION_PATTERNS]

# Pitch / push markers — a reply that asks for more or pushes value.
_PITCH_PATTERNS = [
    r"\?",                           # any question
    r"demo", r"book", r"slot", r"meeting", r"call\s+kar",
    r"sirf\s+\d", r"₹\s*\d", r"offer", r"discount",
    r"ek\s+baar\s+(?:dekh|try|sun)",
]
_PITCH_RE = [re.compile(p) for p in _PITCH_PATTERNS]

# Graceful close markers — a polite goodbye is NOT pushy.
_GOODBYE_PATTERNS = [
    r"shukriya", r"dhanyaw?ad", r"thank", r"din\s+ach?ha", r"aabhar",
    r"samajh\s+(?:gay|gai)", r"bilkul\s+ji", r"koi\s+baat\s+nah[ie]",
    r"pareshan\s+nah[ie]", r"aapka\s+din",
]
_GOODBYE_RE = [re.compile(p) for p in _GOODBYE_PATTERNS]

# Robotic translationese — over-Sanskritised tokens a natural Hinglish caller
# would NEVER use; strong signal of literal machine-translation, not real speech.
_TRANSLATIONESE_TOKENS = [
    "sahayata", "uplabdh", "pradan kar", "samadhan", "abhivadan",
    "sewa pradan", "kृपया", "nivedan hai", "sampark karein", "uttam seva",
    "aapki kaise sahayata", "main aapki kis prakar", "kis prakar sahayata",
]


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def is_soft_no(text: str) -> bool:
    """True if the caller utterance is a polite/soft refusal."""
    t = _norm(text)
    return any(rx.search(t) for rx in _SOFT_NO_RE)


def has_permission_ask(text: str) -> bool:
    """True if the bot line asks for permission/timing (do-minute opener)."""
    t = _norm(text)
    return any(rx.search(t) for rx in _PERMISSION_RE)


def _is_pitch(text: str) -> bool:
    t = _norm(text)
    if any(rx.search(t) for rx in _GOODBYE_RE):
        return False  # a polite goodbye is never "pushy"
    return any(rx.search(t) for rx in _PITCH_RE)


def _turns(transcript: list[dict]) -> list[dict]:
    return [t for t in (transcript or []) if isinstance(t, dict) and t.get("content")]


def check_pushy_after_softno(transcript: list[dict]) -> list[str]:
    """Flag every bot turn that keeps pitching AFTER the caller's 2nd soft-no.
    India-critical: 2 polite refusals => pushing further is rude + trust-breaking.
    Returns a list of finding strings ([] when clean)."""
    findings: list[str] = []
    soft_no_count = 0
    for turn in _turns(transcript):
        role = turn.get("role")
        content = turn.get("content", "")
        if role == "user":
            if is_soft_no(content):
                soft_no_count += 1
        elif role == "assistant":
            if soft_no_count >= 2 and _is_pitch(content):
                findings.append(
                    f"PUSHY_AFTER_SOFTNO (refusal #{soft_no_count}): bot still pitched: "
                    f"{content[:90]!r}"
                )
    return findings


def check_talk_listen_ratio(transcript: list[dict], max_ratio: float = 0.6) -> str | None:
    """Bot ka word-share check — listen ≥ talk (agent never >~60% of words).
    Returns a finding if the bot over-talked, else None. Needs ≥2 bot turns to
    be meaningful (a single long answer is not a ratio)."""
    bot_words = 0
    user_words = 0
    bot_turns = 0
    for turn in _turns(transcript):
        n = len(str(turn.get("content", "")).split())
        if turn.get("role") == "assistant":
            bot_words += n
            bot_turns += 1
        elif turn.get("role") == "user":
            user_words += n
    total = bot_words + user_words
    if total == 0 or bot_turns < 2:
        return None
    ratio = bot_words / total
    if ratio > max_ratio:
        return f"TALK_LISTEN_RATIO: bot spoke {ratio:.0%} of words (>{max_ratio:.0%} cap)"
    return None


def check_missing_permission(transcript: list[dict], within_bot_turns: int = 2) -> str | None:
    """The opener must ask permission/timing within the first ``within_bot_turns``
    bot turns ("do minute baat kar sakti hoon ya busy?"). Returns a finding if
    none of the early bot turns ask, else None."""
    bot_turns = [t.get("content", "") for t in _turns(transcript) if t.get("role") == "assistant"]
    if not bot_turns:
        return None
    early = bot_turns[:within_bot_turns]
    if any(has_permission_ask(b) for b in early):
        return None
    return (
        f"MISSING_PERMISSION: first {len(early)} bot turn(s) never asked "
        "permission/timing (do-minute opener)"
    )


def check_literal_translation(text: str) -> str | None:
    """Flag robotic Sanskritised translationese in a single bot line — a natural
    Hinglish telecaller would not say 'sahayata/uplabdh/pradan'. Heuristic
    (recall-tuned); returns a finding string or None."""
    t = _norm(text)
    hits = [tok for tok in _TRANSLATIONESE_TOKENS if tok in t]
    if hits:
        return f"LITERAL_TRANSLATION: robotic translationese {hits} in: {text[:80]!r}"
    return None


def run_all(transcript: list[dict], *, max_talk_ratio: float = 0.6) -> list[str]:
    """Run every transcript-level check + the per-line literal-translation check.
    Returns a flat list of finding strings ([] when the conversation is clean)."""
    findings: list[str] = []
    try:
        findings.extend(check_pushy_after_softno(transcript))
        r = check_talk_listen_ratio(transcript, max_ratio=max_talk_ratio)
        if r:
            findings.append(r)
        p = check_missing_permission(transcript)
        if p:
            findings.append(p)
        for turn in _turns(transcript):
            if turn.get("role") == "assistant":
                lt = check_literal_translation(turn.get("content", ""))
                if lt:
                    findings.append(lt)
    except Exception:  # pragma: no cover - defensive, never break a QA run
        pass
    return findings


__all__: list[Any] = [
    "is_soft_no",
    "has_permission_ask",
    "check_pushy_after_softno",
    "check_talk_listen_ratio",
    "check_missing_permission",
    "check_literal_translation",
    "run_all",
]
