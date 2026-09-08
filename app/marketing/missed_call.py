"""
missed_call.py — Missed call WhatsApp auto-reply generator.
=============================================================

Generates follow-up messages for clients when they miss a call from a customer.
Uses free LLM chain with strict Hinglish rules and instant template fallbacks.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover
    free_ai = None  # type: ignore

try:
    from app.niches import NICHES  # type: ignore
except Exception:  # pragma: no cover
    NICHES = {}  # type: ignore

_TEMPLATE = (
    "Namaste! 🙏 {biz} se. Abhi hum aapka call nahi utha paye, iske liye sorry! "
    "Kya aap {niche_name} ke baare me inquiry karna chahte hain? "
    "Aap directly niche link par click karke callback schedule kar sakte hain: {url}"
)


def _niche_display(niche: str) -> str:
    n = (niche or "").strip().lower()
    try:
        cfg = NICHES.get(n, {}) or {}
        return str(cfg.get("name") or n.replace("_", " ").title()) or "hamari services"
    except Exception:
        return "hamari services"


async def generate_missed_call_reply(
    business_name: str,
    niche: str = "general",
    callback_url: str = "",
) -> dict[str, Any]:
    """Generates missed call auto-response message. KABHI raise nahi karta."""
    biz = (business_name or "").strip() or "Hamari team"
    n = (niche or "general").strip().lower() or "general"
    url = (callback_url or "").strip() or "leadsgenai.in"
    niche_name = _niche_display(n)

    fallback = _TEMPLATE.format(biz=biz, niche_name=niche_name, url=url)
    message = fallback
    provider = "template"

    if free_ai is not None:
        try:
            system = (
                "Tu ek Indian business ka helper AI hai. Client ne ek customer ka call miss kiya hai. "
                "Ek warm, polite, aur helpful WhatsApp message likh (Hinglish/Roman script, 1-2 emoji). "
                "Apologize kar ki call receive nahi kar paye, aur poonch ki kya {niche_name} ke baare me "
                "inquiry karni hai. Message me niche diya gaya callback link zaroor add kar:\n"
                "{url}\n"
                "Sirf message de, koi extra text nahi, direct copy-paste format."
            )
            prompt = f"Business Name: {biz}. Niche: {niche_name}. Link: {url}."
            text, p = await free_ai.chat(
                system.format(niche_name=niche_name, url=url),
                [{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.7,
            )
            if text and text.strip():
                message = text.strip()
                provider = p or "llm"
        except Exception as e:
            logger.warning(f"missed_call LLM failed, using template: {e}")

    return {
        "business_name": biz,
        "niche": n,
        "callback_url": url,
        "message": message,
        "provider": provider,
    }
