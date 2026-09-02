"""
Post-STT Hinglish correction — Component 1b of the voice smart-fix bundle.
=========================================================================

Groq `whisper-large-v3` (called with ``language="hi"``) mangles English domain
words in code-switched Hinglish business calls (observed: brand names like
"Instagram"/"WhatsApp"/"Facebook" come back as "instagiram"/"vatsapp"/"fesbook").
The downstream NLU is keyword/romanized — one garbled token and the deterministic
"answer the customer" path misses, so the turn falls to the LLM with garbled input
= the "noob/loop" feel.

This module fixes HIGH-CONFIDENCE mis-hears AFTER STT, on the text that feeds BOTH
the gates and the LLM. The companion source-level fix is `niche_scripts.stt_keyterms`
(Component 1a) which biases Whisper toward the right words in the first place.

SAFETY: the map keys are mis-SPELLINGS Whisper emits (NOT real words), matched on
word boundaries — so a correctly-heard word is never rewritten. Gated `STT_CORRECT`
(default ON); fail-open (returns the input unchanged on any error). Extend the map
without code via `data/voice_stt_corrections.jsonl` (`{"wrong": "...", "right": "..."}`
per line) — that's the hook the close-the-loop component (3) writes learned pairs to.
"""

from __future__ import annotations

import os
import re

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Seed map — only OBVIOUS non-word mis-spellings (brand mangling), so replacement
# is safe. "trial"/"plan"/number words are handled at the source by stt_keyterms
# (less false-positive risk than rewriting an ambiguous token like retail<->trial).
_MISHEAR: dict[str, str] = {
    "instagiram": "Instagram",
    "instaagram": "Instagram",
    "instgram": "Instagram",
    "instagram": "Instagram",  # normalise casing
    "vatsapp": "WhatsApp",
    "vatsaap": "WhatsApp",
    "watsap": "WhatsApp",
    "watsapp": "WhatsApp",
    "whatsaap": "WhatsApp",
    "vhatsapp": "WhatsApp",
    "fesbook": "Facebook",
    "facebok": "Facebook",
    "fasebook": "Facebook",
    "gugal": "Google",
    "googal": "Google",
    "gugle": "Google",
    "marketting": "marketing",
}

_EXT_PATH = os.path.join("data", "voice_stt_corrections.jsonl")
_EXT_CACHE: dict[str, str] | None = None
_PAT_CACHE: tuple[int, re.Pattern[str]] | None = None


def _enabled() -> bool:
    return (os.environ.get("STT_CORRECT", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _load_ext() -> dict[str, str]:
    """Learned/manual correction pairs from data/voice_stt_corrections.jsonl. Cached
    (load once); never raises (missing/garbage file => no extensions)."""
    global _EXT_CACHE
    if _EXT_CACHE is not None:
        return _EXT_CACHE
    out: dict[str, str] = {}
    try:
        import json

        if os.path.exists(_EXT_PATH):
            with open(_EXT_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    w = str(d.get("wrong", "")).strip().lower()
                    r = str(d.get("right", "")).strip()
                    if w and r and w != r.lower():
                        out[w] = r
    except Exception:
        out = {}
    _EXT_CACHE = out
    return out


def _table() -> dict[str, str]:
    t = dict(_MISHEAR)
    t.update(_load_ext())
    return t


def _pattern(table: dict[str, str]) -> re.Pattern[str] | None:
    global _PAT_CACHE
    h = len(table)
    if _PAT_CACHE is not None and _PAT_CACHE[0] == h:
        return _PAT_CACHE[1]
    keys = sorted(table.keys(), key=len, reverse=True)
    if not keys:
        return None
    pat = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", re.IGNORECASE)
    _PAT_CACHE = (h, pat)
    return pat


# Spoken English digit-words — in BOTH roman and the Devanagari spellings Whisper
# emits — used to recover phone numbers / long figures STT writes as words
# (POC 2026-06-30: Whisper-hi AND IndicConformer both give "फाइव नाइन जीरो…" for a
# phone number → breaks the post-close number read-back, which needs digits).
_DIGIT_WORD: dict[str, str] = {
    "zero": "0",
    "oh": "0",
    "ohh": "0",
    "nought": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "जीरो": "0",
    "ओह": "0",
    "वन": "1",
    "टू": "2",
    "थ्री": "3",
    "फोर": "4",
    "फाइव": "5",
    "सिक्स": "6",
    "सेवन": "7",
    "एट": "8",
    "नाइन": "9",
    "जीरोनस": "0",
}
_DIGIT_STRIP = ".,!?;:—- "


def _collapse_digit_runs(text: str) -> str:
    """Join a run of >=4 consecutive spoken digit-words into a digit string (recovers
    phone numbers / long figures STT wrote as words). Shorter runs are left untouched
    so a stray 'two'/'do' isn't turned into a digit. Never raises."""
    try:
        out: list[str] = []
        run_d: list[str] = []
        run_w: list[str] = []

        def _flush() -> None:
            if len(run_d) >= 4:
                out.append("".join(run_d))
            else:
                out.extend(run_w)
            run_d.clear()
            run_w.clear()

        for w in text.split():
            core = w.strip(_DIGIT_STRIP)
            d = _DIGIT_WORD.get(core) or _DIGIT_WORD.get(core.lower())
            if d is not None:
                run_d.append(d)
                run_w.append(w)
            else:
                _flush()
                out.append(w)
        _flush()
        return " ".join(out)
    except Exception:
        return text


def correct_stt(text: str, niche: str = "") -> str:
    """Fix high-confidence Hinglish STT mis-hears + recover spoken digit-strings so the
    NLU gates + LLM get the real domain word / a usable phone number. Gated STT_CORRECT
    (default ON); fail-open. Only known mis-spellings + long digit-word runs are touched
    (clean text is unchanged)."""
    try:
        if not (text or "").strip() or not _enabled():
            return text
        t = _collapse_digit_runs(text)
        table = _table()
        pat = _pattern(table)
        if pat is not None:
            t = pat.sub(lambda m: table.get(m.group(0).lower(), m.group(0)), t)
        return t
    except Exception:
        return text


__all__ = ["correct_stt"]
