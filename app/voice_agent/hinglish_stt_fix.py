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


def correct_stt(text: str, niche: str = "") -> str:
    """Fix high-confidence Hinglish STT mis-hears so the NLU gates + LLM get the
    real domain word. Gated STT_CORRECT (default ON); fail-open. Word-boundary,
    case-insensitive; only known mis-spellings are touched (clean text is unchanged)."""
    try:
        if not (text or "").strip() or not _enabled():
            return text
        table = _table()
        pat = _pattern(table)
        if pat is None:
            return text
        return pat.sub(lambda m: table.get(m.group(0).lower(), m.group(0)), text)
    except Exception:
        return text


__all__ = ["correct_stt"]
