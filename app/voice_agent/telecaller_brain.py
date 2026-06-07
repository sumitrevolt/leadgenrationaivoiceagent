"""
TelecallerBrain — lean, phone-optimized Hinglish sales brain (NO ML overhead).
==============================================================================

WHY THIS EXISTS (vs llm_brain.LLMBrain)
---------------------------------------
LLMBrain carries ML/RAG/feedback machinery — great for web, too heavy and too
verbose for a live PSTN turn where every token = latency = dead air. This brain
is ONE system prompt + direct google.generativeai call (same _init_gemini
pattern as llm_brain), tuned with telecaller research (2025-26):

  * Gong (300M+ calls): permission-based openers hit ~11% success vs 2.3% avg.
  * Voice-AI prompting guides (Vapi/Smith.ai/Retell): 1-2 short sentences per
    turn, EXACTLY one question per turn, acknowledge-confirm-prompt structure.
  * LARA objection handling (Listen-Acknowledge-Respond-Ask); "busy" → offer
    two specific callback slots (alternative close); "not interested" → one
    respectful value-line, then thank + end (respect the no).
  * BANT sequencing: need/pain first, money later — questions woven into
    conversation, never an interrogation checklist.

Usage:
    brain = TelecallerBrain(niche="real_estate", client_name="Sharma Realty")
    text  = await brain.reply(history, user_text)   # "" on any failure
    opener = brain.opening_line()                    # permission-based greet
"""
from __future__ import annotations

import asyncio
import re
from typing import Dict, List

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Default qualification flow when the niche is unknown/missing.
_GENERIC_QUESTIONS = [
    "Aap apne business ke liye naye customers abhi kahan se laate hain?",
    "Ek mahine me approx kitni nayi inquiries aati hain aapke paas?",
    "Agar ready qualified leads milne lagein, toh kab se shuru karna chahenge?",
]

_MAX_HISTORY_TURNS = 8          # last ~8 turns to keep prompt (and latency) small
_GEN_CONFIG = {"temperature": 0.6, "max_output_tokens": 80}
_REPLY_TIMEOUT_S = 6.0          # Gemini se itne me jawab nahi => "" (fallback chain)


def _short_hook(hook: str, max_len: int = 90) -> str:
    """pitch_hook ka pehla, chhota hissa — opener me poora English hook lamba
    lagta hai. Split on em-dash/hyphen clause, cap length."""
    h = (hook or "").strip()
    for sep in ("—", " - ", ";"):
        if sep in h:
            h = h.split(sep)[0].strip()
            break
    return h[:max_len].rstrip(" ,.-")


class TelecallerBrain:
    """Phone-call brain: one researched system prompt, direct Gemini call,
    no ML pipeline. Raises on init if Gemini unusable (caller falls back)."""

    def __init__(self, niche: str = "general", client_name: str = "Demo Co") -> None:
        self.niche = (niche or "general").strip() or "general"
        self.client_name = (client_name or "Demo Co").strip() or "Demo Co"

        if not settings.gemini_api_key:
            raise ValueError("TelecallerBrain needs settings.gemini_api_key")

        # Same pattern as llm_brain._init_gemini — direct google.generativeai.
        import google.generativeai as genai  # ImportError → caller falls back

        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai

        model = (settings.default_llm or "").strip()
        if "gemini" not in model.lower() or "vertex" in model.lower():
            model = "gemini-2.5-flash-lite"  # highest free-tier quota
        self.model = model

        self._load_niche()
        self.system_prompt = self._build_system_prompt()
        logger.info(f"[telecaller-brain] ready niche={self.niche} model={self.model}")

    # ------------------------------------------------------------------ #
    # Niche data (pitch_hook + qualification_questions from app.niches)
    # ------------------------------------------------------------------ #
    def _load_niche(self) -> None:
        data: Dict = {}
        try:
            from app.niches import NICHES

            data = NICHES.get(self.niche) or {}
        except Exception as e:  # niches module broken should not kill calls
            logger.warning(f"[telecaller-brain] niches load failed: {e}")
        self.niche_name = data.get("name") or self.niche.replace("_", " ").title()
        self.pitch_hook = (data.get("pitch_hook") or "").strip()
        qs = data.get("qualification_questions") or []
        self.questions: List[str] = [str(q).strip() for q in qs if str(q).strip()] or list(_GENERIC_QUESTIONS)
        # Numbers the agent is ALLOWED to say — only what niche data provides.
        nums = []
        if data.get("avg_ticket_inr"):
            nums.append(f"typical deal/ticket size: {data['avg_ticket_inr']}")
        if data.get("avg_deal_value"):
            nums.append(f"average deal value: {data['avg_deal_value']}")
        self.allowed_numbers = "; ".join(nums)

    # ------------------------------------------------------------------ #
    # System prompt — research-distilled rules + 3 few-shot exchanges
    # ------------------------------------------------------------------ #
    def _build_system_prompt(self) -> str:
        q_block = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(self.questions))
        hook = self.pitch_hook or "businesses ko ready qualified leads dilana"
        hook_short = _short_hook(hook) or "qualified leads"
        numbers_line = self.allowed_numbers or "(koi nahi — matlab tum KOI number/price quote nahi kar sakti)"

        return f"""Tum "Swara" ho — {self.client_name} ki professional Indian female telecaller. Tum ek LIVE PHONE CALL par ho (text chat nahi). Awaaz warm, confident, bilkul insaan jaisi; bhasha natural Hinglish (Hindi-English mix).

CLIENT: {self.client_name} | NICHE: {self.niche_name}
VALUE LINE (pitch hook): {hook}
QUALIFICATION QUESTIONS (ISI ORDER me, ek turn me sirf EK, baat-cheet me naturally piro ke — survey/interrogation jaisa nahi):
{q_block}
ALLOWED NUMBERS/PRICES (sirf yehi bol sakti ho): {numbers_line}

STRICT PHONE RULES (har turn par follow karo):
1. Har reply MAX 2 chhote sentences (~25 shabd total). Phone par lambi speech koi nahi sunta — chhota bolo, ruk jao.
2. Har turn me EXACTLY EK sawaal. Do sawaal ek saath kabhi nahi; sawaal reply ke END me aaye.
3. User ke pichhle jawab ka koi SPECIFIC shabd/detail pakad ke acknowledge karo, phir aage badho. Khali "haan bilkul" / "achha ok" jaisa generic acknowledgment AKELE bolna BANNED.
4. Qualification questions diye order me, ek-ek karke. Jo baat user PEHLE bata chuka hai (history padho), woh sawaal DOBARA kabhi mat poochho.
5. User "busy hoon" bole → ek line me samajh dikhao + DO specific callback time options do (jaise "aaj shaam paanch baje ya kal subah gyarah baje?").
6. User "interest nahi" bole → sirf EK respectful value-line (pitch hook se), phir shukriya bol ke politely call khatam. Pushy hona, baar-baar manana BANNED.
7. User ki baat unclear/adhuri lage → chhota sa bolo "maaf kijiye, awaaz thodi kat gayi — dobara bata denge?" Samajhne ka NATAK kabhi mat karo, guess karke aage mat badho.
8. Numbers, prices, percentages SIRF upar ALLOWED list se. Apne se koi figure, discount ya promise kabhi mat banao.
9. User ki bhasha mirror karo: Hindi me Hindi, English me English, Hinglish me Hinglish. Agar seedha poochhe "AI/bot ho kya?" — sach bolo (haan, AI assistant hoon) aur ek line me value par wapas aao.
10. Output me SIRF bola jaane wala text — koi "Swara:" prefix, emoji, markdown, bullet, ya stage-direction nahi.

EXAMPLES (bilkul aise hi style me bolna hai):

User: Haan leads toh aati hain par conversion bahut kam hai.
Swara: Achha, leads aa rahi hain par conversion nahi — yahi gap hum bharte hain. {self.questions[0]}

User: Abhi main meeting me hoon, busy hoon.
Swara: Oh sorry, main zyada time nahi lungi. Aaj shaam paanch baje ya kal subah gyarah baje — kab call karna theek rahega?

User: Nahi yaar, humein interest nahi hai.
Swara: Koi baat nahi, zabardasti bilkul nahi — bas itna ki hamare clients ko "{hook_short}" se seedha fayda hua hai. Aapke time ke liye shukriya, din shubh rahe!"""

    # ------------------------------------------------------------------ #
    # Permission-based opener (Gong: ~11% vs 2.3% generic) — 2 sentences,
    # ends with a yes/no question. Used by vobiz_stream._opening_line().
    # ------------------------------------------------------------------ #
    def opening_line(self) -> str:
        hook = _short_hook(self.pitch_hook)
        if hook:
            return (f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                    f"Aapke kaam ki ek choti si baat hai — {hook} — kya main tees second me bata doon?")
        return (f"Namaste, main Swara bol rahi hoon {self.client_name} ki taraf se. "
                "Kya main do minute le sakti hoon?")

    # ------------------------------------------------------------------ #
    # Reply — system prompt + last ~8 turns → ONE short spoken line.
    # ------------------------------------------------------------------ #
    async def reply(self, history: List[Dict[str, str]], user_text: str) -> str:
        """Returns stripped reply text, or "" on ANY failure (caller falls back)."""
        try:
            turns = list(history or [])[-_MAX_HISTORY_TURNS:]
            lines = [self.system_prompt, "", "CALL ABHI TAK:"]
            for m in turns:
                role = "User" if (m.get("role") == "user") else "Swara"
                content = str(m.get("content") or "").strip()
                if content:
                    lines.append(f"{role}: {content}")
            # history me aakhri user msg already ho sakta hai (vobiz_stream
            # appends before _think) — duplicate mat karo.
            ut = (user_text or "").strip()
            if ut and not (turns and turns[-1].get("role") == "user"
                           and str(turns[-1].get("content", "")).strip() == ut):
                lines.append(f"User: {ut}")
            lines.append("Swara:")

            model = self._genai.GenerativeModel(self.model)
            # Hard latency cap: phone par 6s+ ka silence = dead call. Timeout
            # => TimeoutError => except => "" => caller fallback chain.
            response = await asyncio.wait_for(
                model.generate_content_async(
                    "\n".join(lines), generation_config=dict(_GEN_CONFIG)
                ),
                timeout=_REPLY_TIMEOUT_S,
            )
            text = (getattr(response, "text", "") or "").strip()
            return self._clean(text)
        except Exception as e:
            logger.warning(f"[telecaller-brain] reply failed: {e}")
            return ""

    @staticmethod
    def _clean(text: str) -> str:
        """TTS-safe: strip role prefixes, markdown junk, collapse whitespace."""
        t = (text or "").strip()
        t = re.sub(r"^(swara|agent|assistant)\s*:\s*", "", t, flags=re.IGNORECASE)
        t = t.replace("*", "").replace("`", "").replace("#", "")
        t = re.sub(r"\s+", " ", t).strip()
        return t


__all__ = ["TelecallerBrain"]
