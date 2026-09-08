"""LinkedIn comment-first outreach — DRAFT generator (ban-safe).

2026 reality: LinkedIn **automation = ToS violation** (23% accounts 90 din me
restricted). Auto-send NAHI karte. Par **comment-first outreach** kaam karta hai —
cold DM ka accept-rate 20% vs comment-pehle 45-60% (2.5x). Isliye yeh module per
B2B target ke liye DRAFTS deta hai (insaan khud post/send kare — safe + effective):

  1. COMMENT — unke recent post pe ek thoughtful comment (relationship pehle)
  2. CONNECT NOTE — connection request ka 1-line note (300 char limit)
  3. DM — accept hone ke baad ka first message (value-first, pushy nahi)

Free-LLM (template fallback). Import-safe, kabhi raise nahi. Safe limits reminder:
20-30 connection/din, 14-din warmup, quality > volume.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_NICHE_HOOK = {
    "real_estate": "portal leads ko 5 min me call karna",
    "real_estate_luxury": "HNI database ko AI se re-engage karna",
    "coaching": "admission inquiries ka instant follow-up",
    "ai_marketing": "clients ke liye AI-driven lead-gen",
    "solar_residential": "solar inquiries ko qualified leads me badalna",
}


def _tpl(name: str, company: str, niche: str) -> dict[str, str]:
    hook = _NICHE_HOOK.get(niche, "naye customers tak tezi se pahunchna")
    return {
        "comment": f"Bahut accha point, {name}. {company} jaise businesses ke liye {hook} aaj sabse bada lever hai — well said! 👏",
        "connect_note": f"Hi {name}, {company} ka kaam follow kar raha hoon. Main AI se local businesses ki marketing+lead-gen automate karta hoon — connect karna chahunga 🙏",
        "dm": (
            f"Thanks for connecting, {name}! Main LeadGen AI chalata hoon — AI voice agent jo "
            f"inquiries ko 2-min me call karke qualified leads laata hai. {company} ke liye ek "
            f"free Google audit bhej dun? Koi pressure nahi — bas value. (leadsgenai.in/audit)"
        ),
    }


async def draft_outreach(
    target_name: str, company: str = "", niche: str = "general"
) -> dict[str, Any]:
    """Ek LinkedIn target ke liye comment + connect-note + DM draft. free-LLM, fallback template."""
    name = (target_name or "there").strip()
    company = (company or "aapki company").strip()
    niche = (niche or "general").strip().lower()
    base = _tpl(name, company, niche)
    try:
        from app.voice_agent import free_ai

        sys = (
            "Tum ek polite B2B LinkedIn outreach expert ho (India). Ek JSON object lautao: "
            '{"comment":"<unke post pe 1-line thoughtful comment>",'
            '"connect_note":"<connection request note, <300 char, warm>",'
            '"dm":"<accept ke baad first DM, value-first, free Google audit offer, pushy nahi>"}. '
            "Hinglish, short. LeadGen AI = AI voice agent jo inquiries ko call karke qualified "
            "leads laata. Sirf JSON."
        )
        prompt = f"Target: {name}, Company: {company}, Niche: {niche}."
        raw, _ = await free_ai.chat(
            sys, [{"role": "user", "content": prompt}], max_tokens=300, temperature=0.6
        )
        import json

        i, j = raw.find("{"), raw.rfind("}")
        if i != -1 and j != -1:
            d = json.loads(raw[i : j + 1])
            for k in ("comment", "connect_note", "dm"):
                if isinstance(d.get(k), str) and d[k].strip():
                    base[k] = d[k].strip()
    except Exception as e:
        logger.debug(f"[linkedin_assist] llm skip: {e}")
    return {
        "ok": True,
        "target": name,
        "company": company,
        **base,
        "tip": "Pehle COMMENT karo (relationship), 1-2 din baad CONNECT, accept hone par DM. 20-30 connect/din max.",
        "auto_sent": False,  # ban-safe: manual send
    }


__all__ = ["draft_outreach"]
