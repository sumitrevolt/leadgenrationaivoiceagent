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
)


@dataclass
class PlatformPitchState:
    phase: str = "await_interest"
    convinced_once: bool = False


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
    """Three-part greet: intro → short pitch → interest yes/no.

    The intro carries the TRAI AI-disclosure ("Main ek AI assistant hoon") for
    parity with every tcbrain-niche opener (which wraps ensure_ai_disclosure).
    Without this the ai_marketing platform pitch was the ONE opener that never
    disclosed it was an AI. Idempotent + never-raise (helper falls back to the
    raw intro on any error)."""
    from app.voice_agent.universal_pitch import (
        INTEREST_ASK,
        PITCH_SHORT,
        UNIVERSAL_AGENT_INTRO,
    )

    s = _script()
    intro = (s.get("opening") or "").strip() or UNIVERSAL_AGENT_INTRO
    try:
        from app.voice_agent.niche_scripts import ensure_ai_disclosure

        intro = ensure_ai_disclosure(intro)
    except Exception:
        pass
    pitch = (s.get("pitch_short") or "").strip() or PITCH_SHORT
    ask = (s.get("interest_ask") or "").strip() or INTEREST_ASK
    return [intro, pitch, ask]


def line_yes_praise() -> str:
    s = _script()
    praise = (s.get("yes_praise") or "").strip()
    if praise:
        return praise
    disc = [str(q).strip() for q in (s.get("discovery") or []) if str(q).strip()]
    if disc:
        return f"Bahut achha sir — {disc[0]}"
    return "Theek sir — marketing abhi khud karte ho, staff se, ya agency?"


def line_no_convince() -> str:
    return (_script().get("no_convince_once") or "").strip() or (
        "Samajh sakti hoon sir — 7 din ka FREE trial hai, pehle result dekho phir decide."
    )


def line_close_cold() -> str:
    return (_script().get("close_cold") or "").strip() or ("Theek hai sir, shukriya — din shubh!")


def line_clarify() -> str:
    return "Ji sir — interested ho to haan, warna seedha nahi bata dijiye?"


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
    if state.phase not in ("await_interest", "await_interest_2"):
        if state.phase == "closed":
            return line_close_cold(), state
        return None, state

    low = re.sub(r"\s+", " ", (user_text or "").lower()).strip()
    if any(w in low for w in ("busy", "meeting", "time nahi")):
        return "Bilkul sir — shaam paanch ya kal subah gyarah, callback kab theek rahega?", state
    if low in ("kya", "kya?", "huh", "what"):
        return (
            "LeadGen AI se Swara — posts, Google profile, festival posters AI se, ₹1,199 se. "
            "Interested hain?",
            state,
        )
    if "samjha nahi" in low:
        return (
            "Simple me — posts, Google listing aur leads automatic, ₹1,199 se. Try karna chahenge?",
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

    verdict = classify_interest(user_text)
    if verdict == "unclear":
        # Substantive reply (not yes/no) = customer bol raha hai — discovery pe le jao.
        if len(low) >= 12 and not low in ("haan", "ji", "ok", "okay", "theek"):
            state.phase = "discovery"
            return None, state
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
