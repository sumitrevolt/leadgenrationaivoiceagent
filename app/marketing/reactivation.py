"""
reactivation.py — Database Reactivation campaign (GHL-style, manual-send).
===========================================================================

Purane/inactive customers ki list do → har ek ke liye personalized Hinglish
win-back WhatsApp message + ready wa.me link milta hai. Bulk auto-send NAHI
(WhatsApp ban risk) — user one-click karke khud bhejta hai (outreach pattern).

LLM se 1 batch call me 3 message STYLES bante hain ({name}/{offer} slots),
phir per-customer template-fill hota hai (50 cap). LLM fail → built-in styles.
KABHI empty, KABHI raise nahi.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

_MAX_CUSTOMERS = 50


def _digits10(raw: str | None) -> str:
    """Sirf digits; +91/0 prefix normalize karke 10-digit lautao ('' = unusable)."""
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


# --- 3 built-in win-back styles ({name}/{biz}/{offer_line} slots) --- #
_STYLES = [
    (
        "warm",
        "Namaste {name} ji! 🙏 {biz} se. Aapko humse seva liye kaafi time ho "
        "gaya — aapki yaad aayi! {offer_line} Is hafte aaiye, special dhyan "
        "rakhenge. Bas is message ka reply kar dijiye 😊",
    ),
    (
        "offer",
        "Hello {name} ji! {biz} ki taraf se sirf purane customers ke liye "
        "khaas: {offer_line} Limited time hai — reply karein ya isi number "
        "par call karein, turant book kar denge 🎁",
    ),
    (
        "feedback",
        "Namaste {name} ji, {biz} se. Aap kaafi time se nahi aaye — kya "
        "hum kuch behtar kar sakte the? Aapka 1 reply hamare liye bahut "
        "keemti hai. {offer_line} Wapas aane par special welcome pakka 🙏",
    ),
]


def _offer_line(offer: str) -> str:
    offer = (offer or "").strip()
    return (
        f"Aapke liye khaas offer: {offer}."
        if offer
        else "Aapke liye ek khaas welcome-back offer rakha hai."
    )


def _parse_llm_styles(text: str) -> list[str]:
    """STYLE1:/STYLE2:/STYLE3: parse — sirf {name} slot wale valid maane jaate."""
    out: list[str] = []
    try:
        for i in (1, 2, 3):
            m = re.search(rf"STYLE\s*{i}\s*:\s*(.+?)(?=\n\s*STYLE\s*\d\s*:|\Z)", text, re.S | re.I)
            if m:
                style = m.group(1).strip().strip('"').strip()
                if style and "{name}" in style:
                    out.append(style[:500])
    except Exception:  # pragma: no cover
        return []
    return out


async def reactivation_campaign(
    business_name: str,
    niche: str = "general",
    customers: list[dict[str, Any]] | None = None,
    offer: str = "",
) -> dict[str, Any]:
    """Per-customer win-back message + wa.me link (cap 50). KABHI empty nahi.

    customers: [{"name","phone","last_visit"?,"note"?}, ...]
    Returns: {"messages":[{name,phone,text,wa_link}], "tips":[2], "provider", ...}
    """
    biz = (business_name or "").strip() or "Hamara business"
    niche = (niche or "general").strip().lower() or "general"
    rows = [r for r in (customers or []) if isinstance(r, dict)][:_MAX_CUSTOMERS]
    oline = _offer_line(offer)

    # --- 1 batch LLM call -> 3 styles; fail par built-in --- #
    styles = [tpl for _label, tpl in _STYLES]
    provider = "template"
    if free_ai is not None and rows:
        try:
            system = (
                "Tu ek Indian business ka WhatsApp win-back copywriter hai. Purane "
                "customers ko wapas bulane ke 3 ALAG style ke Hinglish (Roman "
                "script) messages likh. Har message me {name} placeholder ZAROOR "
                "ho (customer ke naam ke liye) aur 2-3 line se lamba na ho. "
                "Output EXACTLY is format me, koi extra commentary nahi:\n"
                "STYLE1: <warm-personal message>\n"
                "STYLE2: <offer-led message>\n"
                "STYLE3: <feedback-ask message>"
            )
            user = f"Business: {biz} (category: {niche}). Offer line jo include karni hai: {oline}"
            text, p = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=400,
                temperature=0.8,
            )
            if text and text.strip():
                parsed = _parse_llm_styles(text)
                if len(parsed) == 3:
                    styles = parsed
                    provider = p or "llm"
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"reactivation LLM styles failed, using templates: {e}")

    # --- per-customer template-fill (round-robin styles) --- #
    messages: list[dict[str, str]] = []
    for i, row in enumerate(rows):
        name = str(row.get("name") or "").strip()[:60] or "ji"
        text = (
            styles[i % 3]
            .replace("{name}", name)
            .replace("{biz}", biz)
            .replace("{offer_line}", oline)
        )
        d10 = _digits10(row.get("phone"))
        wa_link = f"https://wa.me/91{d10}?text={quote(text)}" if d10 else ""
        messages.append(
            {
                "name": name,
                "phone": d10 or str(row.get("phone") or "").strip()[:20],
                "text": text,
                "wa_link": wa_link,
            }
        )

    tips = [
        "Roz 15-20 se zyada mat bhejo aur har message personalized rakho — "
        "bulk-identical messages par WhatsApp number ban kar deta hai.",
        "Jo reply kare use 5 minute ke andar jawab do (ya AI agent se callback "
        "karwao) — win-back leads sabse garam tabhi hoti hain.",
    ]
    return {
        "business_name": biz,
        "niche": niche,
        "offer": (offer or "").strip(),
        "messages": messages,
        "count": len(messages),
        "tips": tips,
        "provider": provider,
    }
