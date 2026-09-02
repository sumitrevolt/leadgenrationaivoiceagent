"""
whatsapp_pack.py — WhatsApp marketing pack (broadcast + status + replies).
==========================================================================

Ek call me ready-to-send WhatsApp content: 2 broadcast messages (*bold* +
emojis, <300 chars), 3 status lines, 2 lead-reply templates. LLM-first
(free_ai), TEMPLATE fallback — KABHI empty nahi, KABHI raise nahi.
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
    from app.marketing.post_generator import _niche_name, _niche_pitch  # type: ignore
except Exception:  # pragma: no cover

    def _niche_name(niche: str) -> str:  # type: ignore
        return (niche or "general").replace("_", " ").title()

    def _niche_pitch(niche: str) -> str:  # type: ignore
        return "Quality service, sahi daam, 100% bharosa."


_MAX_BROADCAST_CHARS = 300


def _template_pack(
    business_name: str, niche: str, occasion: str, offer: str
) -> dict[str, list[str]]:
    """Deterministic never-empty pack — LLM bilkul na chale tab bhi."""
    occ_line = f"{occasion} ke shubh avsar par " if occasion else ""
    offer_line = offer or "special offer"
    pitch = _niche_pitch(niche)

    broadcast = [
        (
            f"🎉 Namaste! *{business_name}* laya hai {occ_line}aapke liye *{offer_line}*! "
            f"✨ {pitch} Details ke liye is message ka reply karein *YES* — "
            "team turant call karegi. 📞"
        ),
        (
            f"⏰ *Sirf is hafte!* {occ_line}*{business_name}* par {offer_line} — "
            "pehle aao, pehle pao! 🏃 Abhi reply karein ya call karein, "
            "slots tezi se bhar rahe hain. 🔥"
        ),
    ]
    status_lines = [
        f"✨ {occasion or 'Aaj'} ka special — {business_name} par {offer_line}! DM karein 📲",
        f"💯 {pitch} — {business_name}",
        f"📞 Aaj hi baat karein — {business_name}, aapki seva me hamesha! 🙏",
    ]
    reply_templates = [
        (
            f"Namaste! 🙏 *{business_name}* me aapka swagat hai. Haan ji, {offer_line} abhi "
            "chal raha hai — aap apna naam aur convenient time bata dein, hamari team aapko "
            "call karke poori details de degi. 📞"
        ),
        (
            f"Dhanyawad aapke interest ke liye! 😊 *{business_name}* ki team aapse jald "
            "judegi. Tab tak aap apni requirement 1 line me bhej dein (kya chahiye + area) "
            "taaki hum sahi option ke saath ready rahein. ✅"
        ),
    ]
    # Broadcast <300 chars guarantee
    broadcast = [b[:_MAX_BROADCAST_CHARS] for b in broadcast]
    return {
        "broadcast": broadcast,
        "status_lines": status_lines,
        "reply_templates": reply_templates,
    }


_MARKERS = ("BROADCAST1", "BROADCAST2", "STATUS1", "STATUS2", "STATUS3", "REPLY1", "REPLY2")


def _parse_pack(text: str) -> dict[str, str]:
    """BROADCAST1:/STATUS1:/REPLY1: style markers lenient parse."""
    found: dict[str, str] = {}
    try:
        for marker in _MARKERS:
            m = re.search(
                rf"{marker}\s*:\s*(.+?)(?=\n\s*(?:{'|'.join(_MARKERS)})\s*:|\Z)",
                text,
                re.S | re.I,
            )
            if m:
                val = m.group(1).strip().strip('"').strip()
                if val:
                    found[marker] = val
    except Exception:  # pragma: no cover
        return found
    return found


async def broadcast_pack(
    business_name: str,
    niche: str = "general",
    occasion: str = "",
    offer: str = "",
) -> dict[str, Any]:
    """WhatsApp pack: {"broadcast"[2], "status_lines"[3], "reply_templates"[2], "provider"}.

    LLM-first, template fallback — counts hamesha poore, KABHI empty nahi.
    """
    business_name = (business_name or "").strip() or "Aapka Business"
    niche = (niche or "general").strip().lower() or "general"
    occasion = (occasion or "").strip()
    offer = (offer or "").strip()

    fallback = _template_pack(business_name, niche, occasion, offer)
    parsed: dict[str, str] = {}
    provider = ""

    if free_ai is not None:
        try:
            system = (
                "Tu Indian small-business ka WhatsApp marketing expert hai. Hinglish me "
                "likh, WhatsApp *bold* formatting + emojis use kar. Har broadcast 300 "
                "characters se chhota ho. Output EXACTLY is format me, koi extra text nahi:\n"
                "BROADCAST1: <promotional broadcast msg>\n"
                "BROADCAST2: <urgency/FOMO wala broadcast msg>\n"
                "STATUS1: <chhota status text>\n"
                "STATUS2: <chhota status text>\n"
                "STATUS3: <chhota status text>\n"
                "REPLY1: <lead ke inquiry ka warm jawab>\n"
                "REPLY2: <lead ke inquiry ka jawab, details maangta hua>"
            )
            user = (
                f"Business: {business_name}\n"
                f"Category: {_niche_name(niche)} ({_niche_pitch(niche)})\n"
                f"Occasion: {occasion or 'koi nahi'}\n"
                f"Offer: {offer or 'koi nahi'}"
            )
            text, provider = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=600,
                temperature=0.8,
            )
            if text and text.strip():
                parsed = _parse_pack(text)
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"broadcast_pack LLM step failed, using templates: {e}")

    def _pick(marker: str, pool: list[str], idx: int) -> str:
        val = (parsed.get(marker) or "").strip()
        return (val[:_MAX_BROADCAST_CHARS] if marker.startswith("BROADCAST") else val) or pool[idx]

    broadcast = [
        _pick("BROADCAST1", fallback["broadcast"], 0),
        _pick("BROADCAST2", fallback["broadcast"], 1),
    ]
    status_lines = [
        _pick("STATUS1", fallback["status_lines"], 0),
        _pick("STATUS2", fallback["status_lines"], 1),
        _pick("STATUS3", fallback["status_lines"], 2),
    ]
    reply_templates = [
        _pick("REPLY1", fallback["reply_templates"], 0),
        _pick("REPLY2", fallback["reply_templates"], 1),
    ]

    return {
        "broadcast": broadcast,
        "status_lines": status_lines,
        "reply_templates": reply_templates,
        "provider": (provider if parsed else "template") or "template",
    }
