"""
drip.py — WhatsApp nurture (drip) sequences: Day 0/2/5/9 follow-up plan.
=========================================================================

Lead type ke hisab se 4-step Hinglish WhatsApp sequence:
  - new_inquiry   : nayi inquiry ko bharosa → proof → doubt-clear → soft close
  - no_reply      : thandi lead ko dobara jagana (value-first, pushy nahi)
  - post_purchase : thank-you → review ask → referral → repeat offer

LLM-first (1 free_ai call, "Day X | goal | message" lines), per-lead-type
TEMPLATE fallback — KABHI empty, KABHI raise nahi. Send manual hota hai
(wa.me / copy-paste) — bulk auto-send WhatsApp ban risk hai.
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

try:
    from app.niches import NICHES  # type: ignore
except Exception:  # pragma: no cover
    NICHES = {}  # type: ignore

_DAYS = (0, 2, 5, 9)
LEAD_TYPES = ("new_inquiry", "no_reply", "post_purchase")

# --- per-lead-type fallback sequences ({biz} slot) --- #
_FALLBACK: dict[str, list[dict[str, Any]]] = {
    "new_inquiry": [
        {
            "day": 0,
            "goal": "Turant bharosa banao",
            "message": "Namaste! 🙏 {biz} se — aapki inquiry mil gayi, dhanyawad! "
            "Aapke sawalon ke jawab ready hain. Bataiye, baat karne ka "
            "sahi time kya rahega — aaj shaam ya kal subah?",
            "suggested_buttons": ["💬 Yes, talk now", "📞 Call me later", "❌ Not now"],
        },
        {
            "day": 2,
            "goal": "Proof / value dikhao",
            "message": "Hello! {biz} se. Socha aapko hamare recent kaam ki jhalak "
            "bhej dein — customers ka feedback dekh kar aapko sahi "
            "andaaza milega ⭐ Koi sawal ho to bas reply karein.",
            "suggested_buttons": ["⭐ Read reviews", "💬 Talk to team"],
        },
        {
            "day": 5,
            "goal": "Doubt / objection clear karo",
            "message": "Namaste! Aksar log price aur process ko lekar sochte hain — "
            "bilkul natural hai. {biz} me dono transparent hain, 5-min "
            "call me sab clear ho jayega. Kab call karein? 😊",
            "suggested_buttons": ["📞 5-min call", "❌ Not interested"],
        },
        {
            "day": 9,
            "goal": "Soft close / last nudge",
            "message": "Hi! {biz} se aakhri reminder 🙏 Aapki inquiry abhi bhi "
            "hamare paas saved hai. Is hafte book karne par special "
            "attention milega. Interest ho to bas 'YES' reply karein — "
            "warna hum aapko disturb nahi karenge.",
            "suggested_buttons": ["🙋 Yes, interested", "❌ Unsubscribe"],
        },
    ],
    "no_reply": [
        {
            "day": 0,
            "goal": "Naram re-open (guilt nahi)",
            "message": "Namaste! 🙏 {biz} se. Kaafi din pehle aapne interest dikhaya "
            "tha — busy schedule samajh sakte hain! Bas batana chaha ki "
            "hum abhi bhi aapki madad ke liye ready hain. 1 reply kaafi hai 😊",
            "suggested_buttons": ["💬 Yes, let's talk", "❌ Not now"],
        },
        {
            "day": 2,
            "goal": "Nayi value / update do",
            "message": "Hello! {biz} se ek chhota update — is mahine humne kuch naya "
            "shuru kiya hai jo aapke kaam aa sakta hai. 30-second me "
            "padh lijiye, details bhej dein kya?",
            "suggested_buttons": ["ℹ️ Details please", "📞 Call me"],
        },
        {
            "day": 5,
            "goal": "Social proof se jagao",
            "message": "Namaste! Pichhle hafte 3 logon ne (aap jaise hi sawal ke "
            "saath) {biz} ki service li — unka experience bahut accha "
            "raha ⭐ Aapke sawal ka jawab bhi 5 minute me de sakte hain.",
            "suggested_buttons": ["⭐ Read feedback", "💬 Chat with team"],
        },
        {
            "day": 9,
            "goal": "Polite break-up (door khula)",
            "message": "Hi! {biz} se. Lagta hai abhi sahi time nahi hai — koi baat "
            "nahi 🙏 Hum follow-up band kar rahe hain, par jag bhi zaroorat "
            "ho ye number saved rakhiye. Bas 'HI' likhiye, hum hazir!",
            "suggested_buttons": ["👋 Keep in touch", "❌ Delete number"],
        },
    ],
    "post_purchase": [
        {
            "day": 0,
            "goal": "Thank you + support",
            "message": "Dhanyawad! 🙏 {biz} ko chunne ke liye dil se shukriya. Koi "
            "bhi dikkat ya sawal ho to seedha is number par message "
            "karein — hum turant help karenge 😊",
            "suggested_buttons": ["🙋 Ask a question", "👍 All good"],
        },
        {
            "day": 2,
            "goal": "Review ask",
            "message": "Namaste! Umeed hai {biz} ki service se aap khush hain ⭐ "
            "Agar 30 second hon to Google par chhota review de dijiye — "
            "aapke 2 shabd hamare liye bahut keemti hain. Link bhej dein?",
            "suggested_buttons": ["⭐ Give review link", "❌ Later"],
        },
        {
            "day": 5,
            "goal": "Referral maango",
            "message": "Hello! {biz} se 🙏 Agar hamara kaam pasand aaya ho to apne "
            "kisi dost/family ko hamara number share kar dein — unke "
            "liye special first-time benefit rakha hai 🎁",
            "suggested_buttons": ["🎁 Referral info", "❌ Skip"],
        },
        {
            "day": 9,
            "goal": "Repeat / upsell offer",
            "message": "Namaste! {biz} ki taraf se sirf existing customers ke liye: "
            "agli service par khaas discount 🎉 Valid limited time ke "
            "liye hai — book karne ke liye bas reply karein.",
            "suggested_buttons": ["🎉 View discounts", "❌ Not now"],
        },
    ],
}


def _niche_hook(niche: str) -> str:
    try:
        cfg = NICHES.get((niche or "").strip().lower(), {}) or {}
        return str(cfg.get("pitch_hook") or "").strip() or "quality service, sahi daam"
    except Exception:
        return "quality service, sahi daam"


def _parse_llm_steps(text: str, biz: str, lt: str) -> list[dict[str, Any]]:
    """'Day X | goal | message' lines parse — EXACT 4 valid steps chahiye."""
    steps: list[dict[str, Any]] = []
    try:
        for line in (text or "").splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3 and parts[-2] and parts[-1]:
                m = re.search(r"(\d+)", parts[0])
                day = _DAYS[len(steps)] if not m else int(m.group(1))
                steps.append(
                    {
                        "day": day,
                        "goal": parts[-2][:120],
                        "message": parts[-1][:500].replace("{biz}", biz),
                        "suggested_buttons": _FALLBACK[lt][len(steps)]["suggested_buttons"],
                    }
                )
            if len(steps) >= 4:
                break
    except Exception:  # pragma: no cover
        return []
    if len(steps) != 4:
        return []
    # Day numbers standard schedule par lock karo (0/2/5/9)
    for i, s in enumerate(steps):
        s["day"] = _DAYS[i]
    return steps


async def drip_sequence(
    business_name: str,
    niche: str = "general",
    lead_type: str = "new_inquiry",
) -> dict[str, Any]:
    """4-step WhatsApp drip sequence [{day,goal,message,suggested_buttons} x4]. KABHI empty nahi.

    Returns: {"business_name","niche","lead_type","steps","tips","provider"}.
    """
    biz = (business_name or "").strip() or "Hamara business"
    niche = (niche or "general").strip().lower() or "general"
    lt = (lead_type or "new_inquiry").strip().lower()
    if lt not in LEAD_TYPES:
        lt = "new_inquiry"

    steps: list[dict[str, Any]] = []
    provider = "template"
    if free_ai is not None:
        try:
            goals = " -> ".join(s["goal"] for s in _FALLBACK[lt])
            system = (
                "Tu ek Indian business ka WhatsApp follow-up copywriter hai. "
                "4-step nurture sequence likh — har step EXACTLY is format me, "
                "EXACTLY 4 lines, koi extra text nahi:\n"
                "Day <n> | <goal 3-5 shabd> | <2-3 line Hinglish (Roman) message, 1 emoji>\n"
                "Days: 0, 2, 5, 9. Pushy mat ban, har message me 1 clear "
                "next-step ho."
            )
            user = (
                f"Business: {biz} (category: {niche}, USP: {_niche_hook(niche)}). "
                f"Lead type: {lt}. Step goals roughly: {goals}."
            )
            text, p = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=500,
                temperature=0.7,
            )
            if text and text.strip():
                parsed = _parse_llm_steps(text, biz, lt)
                if parsed:
                    steps = parsed
                    provider = p or "llm"
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"drip_sequence LLM failed, using template: {e}")

    if not steps:
        steps = [
            {
                "day": s["day"],
                "goal": s["goal"],
                "message": s["message"].replace("{biz}", biz),
                "suggested_buttons": s.get("suggested_buttons", []),
            }
            for s in _FALLBACK[lt]
        ]
        provider = "template"

    return {
        "business_name": biz,
        "niche": niche,
        "lead_type": lt,
        "steps": steps,
        "tips": [
            "Har step apne CRM/reminder me daal lo — Day 0 turant, baaki "
            "schedule par. Reply aate hi sequence band karo.",
            "Same text sabko mat bhejo — naam/detail badal kar bhejo, warna "
            "WhatsApp spam-flag kar sakta hai.",
        ],
        "provider": provider,
    }
