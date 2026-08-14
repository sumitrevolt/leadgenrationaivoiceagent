"""Hinglish STT normalization — Devanagari → roman for the romanized NLU gates.

THE FUNDAMENTAL FIX (council 2026-06-25): Groq Whisper(`language="hi"`) emits
Devanagari ("क्या"/"कितना"/"हाँ"), but the voice agent's deterministic gates
(question-detection, interest yes/no, objections, FAQ keywords) are all written in
*romanized* Hinglish. Patching every gate with Devanagari variants is whack-a-mole.
Instead, normalize the STT text ONCE here so the existing roman gates fire.

Design:
- **Word-level map** of the high-frequency spoken-call vocabulary → the EXACT roman
  form the gates expect ("कितना"→"kitna", not the literal-translit "kitanaa").
  This is the single source of truth — add a word here, every gate benefits.
- Unmapped Devanagari words are left **as-is** (harmless: they matched nothing before
  either, and the ORIGINAL text — not this — is what goes to the LLM, which reads
  Devanagari natively). No lossy char-transliteration that could misfire.
- **Pure passthrough** for already-roman text (zero Devanagari → returns unchanged).
- Import-safe, never raises.

Only gate-MATCHING uses `to_roman(...)`; the LLM + display always get the original.
"""

from __future__ import annotations

import re

# Devanagari → roman, mapped to the exact token the romanized gates look for.
# Grouped by purpose for maintainability. ADD GATE VOCAB HERE (not per-gate).
_WORD_MAP: dict[str, str] = {
    # question words
    "क्या": "kya",
    "कैसे": "kaise",
    "कैसा": "kaisa",
    "कब": "kab",
    "कहाँ": "kahan",
    "कहां": "kahan",
    "क्यों": "kyun",
    "क्यूँ": "kyun",
    "कितना": "kitna",
    "कितने": "kitne",
    "कितनी": "kitni",
    "कौन": "kaun",
    "मतलब": "matlab",
    "समझाओ": "samjhao",
    "समझा": "samjha",
    "समझो": "samjho",
    "बताओ": "batao",
    "बता": "bata",
    "बताते": "batate",
    "बताइए": "bataiye",
    # price / plan
    "चार्ज": "charge",
    "कीमत": "kimat",
    "दाम": "daam",
    "पैसा": "paisa",
    "पैसे": "paise",
    "रुपये": "rupaye",
    "रुपया": "rupaya",
    "प्लान": "plan",
    "पैकेज": "package",
    "महीना": "mahina",
    "महीने": "mahine",
    "साल": "saal",
    "फ्री": "free",
    "ट्रायल": "trial",
    "डेमो": "demo",
    # service / capability
    "सर्विस": "service",
    "सेवा": "seva",
    "करते": "karte",
    "करना": "karna",
    "करोगे": "karoge",
    "काम": "kaam",
    "चाहिए": "chahiye",
    # yes
    "हाँ": "haan",
    "हां": "haan",
    "हा": "haan",
    "जी": "ji",
    "ठीक": "thik",
    "बिल्कुल": "bilkul",
    "बिलकुल": "bilkul",
    "ज़रूर": "zaroor",
    "जरूर": "zaroor",
    "इंटरेस्टेड": "interested",
    "इंटरेस्ट": "interest",
    # no / objection
    "नहीं": "nahi",
    "नही": "nahi",
    "ना": "na",
    "मत": "mat",
    "बंद": "band",
    "करो": "karo",
    "महंगा": "mehenga",
    "मेहंगा": "mehenga",
    "एजेंसी": "agency",
    "सोच": "soch",
    "भरोसा": "bharosa",
    "बाद": "baad",
    # busy / timing
    "बिजी": "busy",
    "मीटिंग": "meeting",
    "टाइम": "time",
    "समय": "samay",
    "अभी": "abhi",
    "रोज": "roz",
    "फाइनल": "final",
    "बुक": "book",
    "कॉल": "call",
    "कॉलबैक": "callback",
    # close / proceed intent (2026-07-03: missing from this map meant a caller
    # saying e.g. "प्री प्लान एक्टिवेट करो" never matched telecaller_brain's
    # roman-only _CLOSE_HARD_RE — the close-signal/WhatsApp-handoff path never
    # fired even though the caller clearly said "activate")
    "एक्टिवेट": "activate",
    "स्टार्ट": "start",
    "शुरू": "shuru",
    "चालू": "chalu",
    "सेटअप": "setup",
    "साइन": "sign",
    "कन्फर्म": "confirm",
    "फिक्स": "fix",
    "एक्टिव": "active",
    "एक्टिवेशन": "activation",
    # identity / channel
    "कौनहो": "kaun ho",
    "रोबोट": "robot",
    "मशीन": "machine",
    "वाट्सएप": "whatsapp",
    "व्हाट्सएप": "whatsapp",
    "भेजो": "bhejo",
    "भेज": "bhej",
    # common glue words (so multi-word gate phrases line up)
    "है": "hai",
    "और": "aur",
    "में": "me",
    "को": "ko",
    "से": "se",
    "पे": "pe",
    "पर": "par",
    "का": "ka",
    "की": "ki",
    "के": "ke",
    "वो": "wo",
    "ये": "ye",
    "यह": "yeh",
    "मुझे": "mujhe",
    "मैं": "main",
    "तुम": "tum",
    "आप": "aap",
    "मिलता": "milta",
    "होता": "hota",
    "गूगल": "google",
    "पोस्ट": "post",
}

_DEV_RE = re.compile(r"[ऀ-ॿ]")
_STRIP = "।?!.,;:—-\"')(॥"


def to_roman(text: str) -> str:
    """Normalize Devanagari spoken-call words → roman gate-forms. Passthrough for
    roman text. Unmapped Devanagari left as-is. Never raises."""
    try:
        if not text or not _DEV_RE.search(text):
            return text or ""
        out: list[str] = []
        for tok in re.split(r"(\s+)", text):
            if not tok or tok.isspace():
                out.append(tok)
                continue
            core = tok.strip(_STRIP)
            repl = _WORD_MAP.get(core)
            if repl:
                i = tok.find(core)
                out.append(tok[:i] + repl + tok[i + len(core) :])
            else:
                out.append(tok)
        return "".join(out)
    except Exception:
        return text or ""


__all__ = ["to_roman"]
