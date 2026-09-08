"""LeadGen AI platform outbound pitch flow (ai_marketing niche only).

Deterministic opener chain + interest gate before TelecallerBrain discovery.
Import-safe, never raises.
"""

from __future__ import annotations

import math
import os
import re
import struct
from dataclasses import dataclass, field
from typing import Literal

InterestVerdict = Literal["yes", "no", "unclear"]

PLATFORM_NICHE = "ai_marketing"
SAMPLE_RATE = 16000

# Interest-gate patterns (bare haan/ji — generic intent_detector misses these).
_YES_PATTERNS: tuple[str, ...] = (
    r"^ha+a+n?\b",
    r"^ji+\b",
    r"^yes+\s*$",
    r"^yeah+\s*$",
    r"^ok+\s*$",
    r"^okay\s*$",
    r"^theek\s*$",
    r"^thik\s*$",
    r"^bilkul\s*$",
    r"^zaroor\s*$",
    r"^sure\s*$",
    r"interested",
    r"\bbatao\b",
    r"\bsunao\b",
    r"\bbolo\b",
    r"haan\s+bol",
    r"ji\s+bol",
    r"(haan|ji|yes).*(interested|batao|sunao|bolo)",
    r"sounds?\s+good",
    r"tell\s+me\s+more",
    # Devanagari — Groq Whisper (language="hi") outputs native script, so the
    # romanized-only patterns above missed bare "हाँ"/"जी" → endless clarify loop
    # (web transcripts). Clean affirmatives now match; garbled ones fall to discovery.
    r"हाँ|हां|^\s*हा\b|^\s*जी|ठीक|बिल्कुल|बिलकुल|ज़रूर|जरूर|इंटर[ेेिी]स्ट|बता\s*[ओदo]|सुना|चाहत|करना\s*है",
)

_NO_PATTERNS: tuple[str, ...] = (
    r"\bnahi\b",
    r"^no\s*$",
    r"interest\s+nahi",
    r"zaroorat\s+nahi",
    r"mat\s+karo",
    r"band\s+karo",
    r"not\s+interested",
    r"don'?t\s+want",
    r"nahi\s+chahiye",
    r"no\s+thanks",
    r"no\s+need",
    # Devanagari negatives (Whisper hi script).
    r"नहीं|नही|(?:^|\s)ना(?:\s|$)|^\s*नई|मत\s*कर|बंद\s*कर|ज़रूरत\s*नहीं|नहीं\s*चाहि|रहने\s*दो",
)


@dataclass
class PlatformPitchState:
    phase: str = "await_interest"
    convinced_once: bool = False
    clarify_count: int = 0  # repetition guard: clarify line max once, then hand to brain


def is_platform_pitch(niche: str) -> bool:
    return (niche or "").strip().lower() == PLATFORM_NICHE


def initial_state() -> PlatformPitchState:
    return PlatformPitchState(phase="await_interest")


def _script() -> dict:
    try:
        from app.voice_agent.niche_scripts import get_script

        return get_script(PLATFORM_NICHE) or {}
    except Exception:
        return {}


def opening_segments() -> list[str]:
    """ONE short greet only — then WAIT for the caller.

    2026-07-17 live defect: 3-part opener (intro+pitch+ask) spoke ~40s back-to-
    back with barge locked → user_turns=0 → Vobiz "End Of XML Instructions"
    hangup. Owner wants 10–15 conversation turns: so opener = identity +
    permission ask ONLY; price/pitch comes AFTER the caller says haan (see
    line_yes_praise / next_reply). Idempotent + never-raise.
    """
    from app.voice_agent.universal_pitch import UNIVERSAL_AGENT_INTRO

    s = _script()
    intro = (s.get("opening") or "").strip() or UNIVERSAL_AGENT_INTRO
    try:
        from app.voice_agent.niche_scripts import ensure_ai_disclosure

        intro = ensure_ai_disclosure(intro)
    except Exception:
        pass
    return [intro]


def line_yes_praise() -> str:
    """After permission yes: deliver SHORT pitch + one discovery question.

    Pitch moved out of the opener (2026-07-17) so the first breath is short
    enough for the caller to answer — then we give price/trial here."""
    from app.voice_agent.universal_pitch import PITCH_SHORT

    s = _script()
    pitch = (s.get("pitch_short") or "").strip() or PITCH_SHORT
    praise = (s.get("yes_praise") or "").strip()
    if praise:
        return f"{pitch} {praise}"
    disc = [str(q).strip() for q in (s.get("discovery") or []) if str(q).strip()]
    if disc:
        return f"Theek — {pitch} {disc[0]}"
    return f"Theek — {pitch} Marketing abhi khud karte ho, staff se, ya agency?"


def line_no_convince() -> str:
    return (_script().get("no_convince_once") or "").strip() or (
        "Samajh sakti hoon — 7 din ka FREE trial hai, pehle result dekho phir decide."
    )


def line_close_cold() -> str:
    return (_script().get("close_cold") or "").strip() or ("Theek hai, shukriya — din shubh!")


def line_clarify() -> str:
    return "Interested ho to haan, warna seedha nahi bata dijiye?"


# Direct product questions ("kya kya features", "kitne ka", "price", "kaise kaam")
# interest-gate ke yes/no me fit NAHI hote — inhe TelecallerBrain answer kare (uska
# _customer_qa_reply seedha jawab deta). Warna "features BATAO" galti se YES-pattern
# (batao/bolo/sunao) match kar ke discovery-sawaal de deta tha ("marketing khud karte
# ho?") = dodge/noob (real-call 2026-06-28: user "ulta aap mere se puchh rahe ho").
_PRODUCT_Q_WORDS: tuple[str, ...] = (
    "feature",
    "service",
    "kitne",
    "kitna",
    "price",
    "pricing",
    "plan",
    "package",
    "cost",
    "charge",
    "paisa",
    "paise",
    "rupay",
    "rupee",
    "kaise kaam",
    "kya karte",
    "kya karoge",
    "kya hota",
    "kya milta",
    "kya milega",
    "kya provide",
    "kya offer",
    "kya deti",
    "kya dete",
    "matlab kya",
    "demo",
    "samjhao",
    "calling",
    "telecaller",
    "voice agent",
    "ai calling",
    "call karne wala",
    "auto call",
    # English product asks (bilingual / web demo)
    "what do you",
    "what you do",
    "what you guys",
    "guys do",
    "do exactly",
    "how does it work",
    "how it works",
    "tell me about your",
    # Devanagari (Whisper hi script)
    "कॉलिंग",
    "टेलीकॉलर",
    "वॉइस",
    "वायस",
    "फीचर",
    "फ़ीचर",
    "सर्विस",
    "कितने",
    "कितना",
    "कीमत",
    "दाम",
    "प्लान",
    "पैकेज",
    "क्या करते",
    "क्या होता",
    "कैसे काम",
    "क्या मिल",
    "समझा",
)


def is_product_question(text: str) -> bool:
    """User seedha product-sawaal puchh raha (yes/no nahi) — TelecallerBrain answer kare."""
    low = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not low:
        return False
    if "kya kya" in low or "क्या क्या" in low:  # "what all do you do" = feature ask
        return True
    return any(w in low for w in _PRODUCT_Q_WORDS)


def classify_interest(text: str) -> InterestVerdict:
    """Fast yes/no/unclear for the platform interest gate."""
    t = (text or "").strip()
    if len(t) < 2:
        return "unclear"
    low = re.sub(r"\s+", " ", t.lower()).strip()
    if low in ("kya", "kya?", "huh", "what"):
        return "unclear"
    if not re.search(r"[0-9a-zऀ-ॿ]", low):
        return "unclear"
    for pat in _NO_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return "no"
    for pat in _YES_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return "yes"
    return "unclear"


def next_reply(state: PlatformPitchState, user_text: str) -> tuple[str | None, PlatformPitchState]:
    """Deterministic reply for interest-gate phases. None = use TelecallerBrain."""
    from app.voice_agent.universal_pitch import PITCH_SHORT

    if state.phase not in ("await_interest", "await_interest_2"):
        if state.phase == "closed":
            return line_close_cold(), state
        return None, state

    low = re.sub(r"\s+", " ", (user_text or "").lower()).strip()
    if any(w in low for w in ("busy", "meeting", "time nahi")):
        return "Bilkul — shaam paanch ya kal subah gyarah, callback kab theek rahega?", state
    if low in ("kya", "kya?", "huh", "what"):
        return (
            f"LeadGen AI se Swara — {PITCH_SHORT} Interested hain?",
            state,
        )
    if "samjha nahi" in low:
        return (
            f"Simple me — {PITCH_SHORT} Try karna chahenge?",
            state,
        )
    if "kaun ho" in low or "aap kaun" in low:
        state.phase = "discovery"
        return (
            "Main Swara hoon LeadGen AI se — AI se social posts, ads aur Google boost; "
            "marketing abhi aap khud karte ho ya koi aur?",
            state,
        )
    if state.phase == "await_interest_2" and any(
        w in low for w in ("agency", "mehenga", "mahnga", "soch ke", "pehle se", "trial")
    ):
        state.phase = "discovery"
        return None, state

    # DIRECT PRODUCT QUESTION → TelecallerBrain ko do (answer-first). Interest gate ke
    # yes/no classification SE PEHLE — warna "features batao"/"kitne features" galti se
    # YES match kar ke discovery-sawaal de deta tha (dodge). Brain ab seedha jawab dega.
    if is_product_question(user_text):
        state.phase = "discovery"
        return None, state

    verdict = classify_interest(user_text)
    if verdict == "unclear":
        # Substantive reply (not yes/no) = customer bol raha hai — discovery pe le jao.
        if len(low) >= 12 and low not in ("haan", "ji", "ok", "okay", "theek"):
            state.phase = "discovery"
            return None, state
        # Repetition guard: clarify ONCE; a second unclear (garbled/short STT) must
        # NOT loop the same line (web transcripts showed it 3x) — hand to the brain.
        if state.clarify_count >= 1:
            state.phase = "discovery"
            return None, state
        state.clarify_count += 1
        return line_clarify(), state
    if verdict == "yes":
        state.phase = "discovery"
        return line_yes_praise(), state
    # no
    if not state.convinced_once:
        state.convinced_once = True
        state.phase = "await_interest_2"
        return line_no_convince(), state
    state.phase = "closed"
    return line_close_cold(), state


def generate_celebration_pcm(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Short festive ascending chime (~1.4s) — no external file required."""
    freqs = (523.25, 659.25, 783.99, 1046.50)
    pcm = bytearray()
    ms_per = 320
    for f in freqs:
        n = int(sample_rate * ms_per / 1000)
        for i in range(n):
            t = i / sample_rate
            env = 1.0 - (i / max(n, 1)) * 0.35
            val = int(14000 * env * math.sin(2 * math.pi * f * t))
            val = max(-32768, min(32767, val))
            pcm.extend(struct.pack("<h", val))
    return bytes(pcm)


def celebration_audio_path() -> str | None:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for name in ("celebration_sfx.mp3", "celebration_sfx.wav"):
        p = os.path.join(base, "data", "audio", name)
        if os.path.isfile(p):
            return p
    return None


__all__ = [
    "PLATFORM_NICHE",
    "PlatformPitchState",
    "classify_interest",
    "celebration_audio_path",
    "generate_celebration_pcm",
    "initial_state",
    "is_platform_pitch",
    "line_clarify",
    "line_close_cold",
    "line_no_convince",
    "line_yes_praise",
    "next_reply",
    "opening_segments",
]
