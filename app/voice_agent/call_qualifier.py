"""Post-call AI lead qualification + summary — Expedify-style "qualify leads 24/7".

Call ke transcript ko free-LLM se analyze karke STRUCTURED qualification deta:
interest score, qualified?, appointment chahiye?, budget signal, summary, next
action, + ek ready Hinglish follow-up draft.

DESIGN: real-time voice path ke BAHAR (post-call) — koi latency risk nahi.
Free-stack (app.voice_agent.free_ai). Import-safe, kabhi raise nahi karta.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# Bot/IVR gate (USER-MANDATE 2026-07-05): 05-Jul batch me qualifier company
# IVR/answering-bots ko "interested" mark kar raha tha (user ne recordings
# suni). Ab qualified=true tabhi possible jab (a) minimum REAL user turns hon
# aur (b) transcript IVR/bot jaisa na lage. Yeh gate qualify_transcript ke
# ANDAR hai — vobiz_stream / phone_stream / call_manager SAB paths covered.
# --------------------------------------------------------------------------- #
_IVR_PATTERNS = [
    # English IVR/receptionist-bot phrases
    r"press\s*(?:\d|one|two|three|star|hash)",
    r"welcome\s+to\b",
    r"thank\s+you\s+for\s+calling",
    r"(?:all\s+(?:our\s+)?(?:executives|representatives|agents)|our\s+executives?)\s+(?:are|is)\s+busy",
    r"toll\s*free",
    r"customer\s+care",
    r"helpline",
    r"leave\s+a\s+message",
    r"voice\s*mail",
    r"after\s+the\s+(?:beep|tone)",
    r"call\s+(?:is|may\s+be)\s+(?:being\s+)?recorded",
    r"for\s+(?:hindi|english|marathi)\b",
    r"dial\s+(?:\d|extension)",
    # Hinglish / Hindi (roman + devanagari)
    r"daba(?:ye|iye|yen|iyega|o)\b",
    r"दबा(?:एं|इए|ये|यें)",
    r"swagat\s+(?:hai|aahe)",
    r"स्वागत",
    r"aapka\s+call\s+(?:hamare|humare|record)",
    r"आपका\s+कॉल",
    r"pratinidhi",
    r"प्रतिनिधि",
    r"line\s+par\s+bane\s+rah",
    r"लाइन\s+पर\s+बने",
    r"record\s+ki\s+ja\s+rah",
    r"रिकॉर्ड\s+की\s+जा",
    r"karyalay|कार्यालय",
    r"sampark\s+karne\s+ke\s+liye\s+dhanyavad",
    # Marathi IVR
    r"आपले\s+(?:हार्दिक\s+)?स्वागत",
    r"कृपया.{0,20}दाबा",
    # 2026-07-06 (05-Jul transcript audit): phrases the live batch ACTUALLY said
    # that the list above missed — HDFC Ergo / LiveSpace IVRs + voicemail scripts.
    r"connect(?:ing)?\s+your\s+call",
    r"(?:is|are)\s*n[o']?t\s+available",
    r"trying\s+to\s+reach",
    r"you\s+have\s+not\s+entered",
    r"if\s+you\s+are\s+an?\s+existing",
    r"record\s+your\s+message",
    r"finished\s+recording",
    r"forwarded\s+to\s+voice",
    r"(?:quality|training)\s+(?:and\s+\w+\s+)?purposes",
    r"stay\s+on\s+the\s+line",
    r"please\s+wait\s+while",
    # Devanagari STT renders English IVR phonetically ("प्रेस वन", "वेट वाल वी")
    r"प्रेस\s*(?:वन|टू|थ्री|फोर|फाइव|जीरो|स्टार|हैश|\d)",
    r"रिक्वायर्मेंट|कस्टमर\s*केयर|एक्सपीजियंस\s*सेंटर",
    r"क्?नेक्ट\s*योर\s*कोल|प्लीज\s*वेट|होल्ड\s*(?:करें|कीजिए|प्लीज)",
]
_IVR_RE = re.compile("|".join(_IVR_PATTERNS), re.IGNORECASE)


def _user_lines(transcript: str) -> list[str]:
    return [
        ln.split(":", 1)[1].strip()
        for ln in (transcript or "").splitlines()
        if ln.strip().lower().startswith("user:")
    ]


def detect_bot_or_ivr(transcript: str) -> tuple[bool, str]:
    """Heuristic: kya doosri taraf insaan ki jagah IVR/answering-bot tha?

    Returns (suspect, reason). Kabhi raise nahi karta.
    """
    try:
        users = _user_lines(transcript)
        joined = " ".join(users)
        m = _IVR_RE.search(joined)
        if m:
            return True, f"ivr_phrase:{m.group(0)[:40]}"
        # Bot repeat-loop: same utterance baar-baar (>=2 exact repeats among 3+)
        if len(users) >= 3:
            norm = [re.sub(r"\s+", " ", u.lower()).strip() for u in users if u.strip()]
            if norm and len(set(norm)) <= max(1, len(norm) // 2):
                return True, "repeated_identical_turns"
        # Welcome-monologue: pehla hi user turn 220+ chars ka scripted intro
        if users and len(users[0]) >= 220 and _IVR_RE.search(users[0] or ""):
            return True, "long_scripted_intro"
        return False, ""
    except Exception as e:  # pragma: no cover
        logger.debug(f"[call_qualifier] bot detect skip: {e}")
        return False, ""


def _min_user_turns() -> int:
    try:
        return max(1, int(os.environ.get("MIN_QUALIFY_USER_TURNS", "3")))
    except Exception:
        return 3


def _bot_gate_on() -> bool:
    return os.environ.get("QUALIFY_BOT_GATE", "1").strip().lower() not in ("0", "false", "no")


_SYSTEM = (
    "Tum ek sales-QA analyst ho. Ek phone call ka transcript milega. SIRF ek JSON "
    "object lautao (aur kuch nahi):\n"
    '{"interest_score": <1-5 int>, "qualified": <true|false>, '
    '"appointment_requested": <true|false>, "budget_signal": "<low|medium|high|unknown>", '
    '"summary": "<1-2 line Hinglish>", "next_action": "<1 line Hinglish suggestion>", '
    '"followup_draft": "<short Hinglish follow-up message customer ke liye>"}.\n'
    "qualified=true tabhi jab customer ne genuine interest/need dikhaya ho. "
    "Koi explanation mat do, sirf JSON."
)


def _extract_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    t = text.strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        t = t[i : j + 1]
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _coerce(d: dict[str, Any]) -> dict[str, Any]:
    """LLM output ko safe shape me laao (missing/garbage -> defaults)."""
    try:
        score = int(d.get("interest_score", 0))
    except Exception:
        score = 0
    score = max(0, min(5, score))
    bud = str(d.get("budget_signal", "unknown")).lower()
    if bud not in ("low", "medium", "high", "unknown"):
        bud = "unknown"
    return {
        "interest_score": score,
        "qualified": bool(d.get("qualified", False)),
        "appointment_requested": bool(d.get("appointment_requested", False)),
        "budget_signal": bud,
        "summary": str(d.get("summary", "") or "")[:400],
        "next_action": str(d.get("next_action", "") or "")[:200],
        "followup_draft": str(d.get("followup_draft", "") or "")[:600],
    }


async def qualify_transcript(
    transcript: str, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Transcript -> structured qualification + follow-up draft. Kabhi raise nahi.

    Returns dict with keys: interest_score, qualified, appointment_requested,
    budget_signal, summary, next_action, followup_draft, provider, ok.
    """
    ctx = context or {}
    tx = (transcript or "").strip()
    if len(tx) < 10:
        return {
            "ok": False,
            "reason": "transcript too short",
            "interest_score": 0,
            "qualified": False,
            "appointment_requested": False,
            "budget_signal": "unknown",
            "summary": "",
            "next_action": "Call dobara try karo / transcript missing.",
            "followup_draft": "",
            "provider": "",
            "user_turns": 0,
            "bot_suspected": False,
            "bot_reason": "",
        }
    who = ctx.get("business_name") or ctx.get("name") or "customer"
    user_msg = f"Customer: {who}. Niche: {ctx.get('niche', 'general')}.\n\nTranscript:\n{tx[:4000]}"
    try:
        from app.voice_agent import free_ai

        raw, provider = await free_ai.chat(
            _SYSTEM, [{"role": "user", "content": user_msg}], max_tokens=320, temperature=0.2
        )
    except Exception as e:
        logger.warning(f"[call_qualifier] llm failed: {e}")
        raw, provider = "", ""
    parsed = _coerce(_extract_json(raw))
    parsed["provider"] = provider
    parsed["ok"] = bool(provider) and bool(parsed.get("summary"))
    # ---- Bot/IVR + min-turns gate (qualified=true ka DARWAZA) ---- #
    users = _user_lines(tx)
    parsed["user_turns"] = len(users)
    parsed["bot_suspected"] = False
    parsed["bot_reason"] = ""
    if _bot_gate_on():
        suspect, why = detect_bot_or_ivr(tx)
        too_few = len(users) < _min_user_turns()
        if suspect or too_few:
            if not suspect:
                why = f"user_turns={len(users)}<{_min_user_turns()}"
            if parsed.get("qualified") or parsed.get("appointment_requested"):
                logger.info(
                    f"[call_qualifier] qualification GATED ({why}) — "
                    f"LLM ne qualified bola tha, override to false"
                )
            parsed["bot_suspected"] = bool(suspect)
            parsed["bot_reason"] = why
            parsed["qualified"] = False
            parsed["appointment_requested"] = False
            parsed["interest_score"] = min(int(parsed.get("interest_score") or 0), 2)
            if parsed.get("summary"):
                parsed["summary"] = ("[UNVERIFIED — bot/IVR ya kam turns] " + parsed["summary"])[
                    :400
                ]
    if not parsed["followup_draft"]:
        parsed["followup_draft"] = (
            f"Namaste {who}! Call ke liye dhanyawad. Aapki zaroorat ke hisaab se hum aapse jald follow-up karenge."
        )
    return parsed


__all__ = ["qualify_transcript", "detect_bot_or_ivr"]
