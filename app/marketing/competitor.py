"""
competitor.py — competitor notes se actionable Hinglish comparison tips.
========================================================================

User apne competitor ki jaankari paste karta hai (reviews zyada, website
acchi, mehenga, slow reply...) → LLM analysis (free_ai) → strengths-to-copy,
gaps-to-exploit, 3-step action plan. Rule-based keyword fallback — KABHI
empty nahi, KABHI raise nahi.
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
    from app.marketing.post_generator import _niche_name  # type: ignore
except Exception:  # pragma: no cover

    def _niche_name(niche: str) -> str:  # type: ignore
        return (niche or "general").replace("_", " ").title()


# --------------------------------------------------------------------------- #
# Rule-based fallback — notes ke keywords se strengths/gaps nikalo
# --------------------------------------------------------------------------- #

# (keywords) -> strength-to-copy line
_STRENGTH_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("review", "rating", "star", "5-star"),
        "Unke paas reviews/ratings zyada hain — har khush customer se Google review maango "
        "(counter par QR-code rakho), 90 din me gap band ho sakta hai.",
    ),
    (
        ("photo", "instagram", "insta", "reel", "social", "follower"),
        "Unki social/photo presence strong hai — hafte me 3 post + 2 reels ka simple routine "
        "shuru karo, content calendar humara module bana dega.",
    ),
    (
        ("website", "site", "online", "seo"),
        "Unki website/online presence behtar hai — apna GBP 100% complete karo aur ek "
        "simple landing page lagao (free me bhi ho jaata hai).",
    ),
    (
        ("sasta", "cheap", "price", "discount", "offer", "deal"),
        "Wo aggressive offers/pricing chalate hain — price-war mat karo, value-bundle banao "
        "(service + guarantee + freebie) jo compare hi na ho.",
    ),
    (
        ("ads", "advertis", "promotion", "hoarding", "pamphlet"),
        "Wo paid promotion karte hain — tum free channels (GBP posts, WhatsApp status, "
        "referral) se wahi reach nikaalo, phir chhota ad-budget test karo.",
    ),
    (
        ("fast", "jaldi", "quick", "same day", "turant"),
        "Unki delivery/response speed acchi hai — apna response-time SLA banao aur use "
        "marketing me bolo ('30-min me callback guarantee').",
    ),
]

# (keywords) -> gap-to-exploit line
_GAP_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("slow", "late", "der", "delay", "time lagta"),
        "Wo slow hain — tum speed becho: 'same-day visit / 30-min callback' promise har "
        "post me daalo.",
    ),
    (
        ("rude", "behaviour", "behavior", "badtameez", "staff kharab"),
        "Unke service-behaviour ki complaints hain — tum har review ka namr reply do aur "
        "'customer-first' stories post karo.",
    ),
    (
        ("mehenga", "expensive", "costly", "overpriced", "mehnga"),
        "Wo mehenge hain — transparent pricing dikhao (price-range GBP services me daalo), "
        "'no hidden charges' bolo.",
    ),
    (
        ("purana", "old", "outdated", "design"),
        "Unka look/process purana hai — apne fresh photos, naye equipment/process ko "
        "highlight karo.",
    ),
    (
        ("reply nahi", "no reply", "response nahi", "ignore", "phone nahi uthate"),
        "Wo enquiries ignore karte hain — tum WhatsApp auto-reply + AI agent se har lead "
        "ka 5-minute me jawab do (yahi sabse bada switch-reason hai).",
    ),
    (
        ("review kam", "kam review", "negative review", "1 star", "complaint"),
        "Unke negative/kam reviews hain — apne happy customers ke reviews tezi se badhao "
        "aur unke naraz customers ko target karo ('second opinion' angle).",
    ),
]

_GENERIC_STRENGTHS = [
    "Unka jo bhi channel sabse active hai (GBP/Instagram/WhatsApp), wahi tum consistently "
    "chalao — consistency hi unka asli edge hota hai.",
    "Unke best-selling offer ka structure copy karo (offer mat copy karo) — bundle/guarantee "
    "format apne service par lagao.",
]
_GENERIC_GAPS = [
    "Zyada-tar local competitors reviews ka reply nahi karte — tum 24-ghante reply rule se "
    "turant alag dikhoge.",
    "Festival-marketing koi seriously nahi karta — agle tyohar par poster + WhatsApp pack "
    "ready rakho, walk-ins badhenge.",
]


def _rule_based(business_name: str, niche: str, notes: str) -> dict[str, list[str]]:
    """Keyword-match fallback — notes khali ho to bhi generic par useful output."""
    low = (notes or "").lower()
    strengths = [line for keys, line in _STRENGTH_RULES if any(k in low for k in keys)]
    gaps = [line for keys, line in _GAP_RULES if any(k in low for k in keys)]

    for g in _GENERIC_STRENGTHS:
        if len(strengths) >= 2:
            break
        strengths.append(g)
    for g in _GENERIC_GAPS:
        if len(gaps) >= 2:
            break
        gaps.append(g)
    strengths, gaps = strengths[:3], gaps[:3]

    action_plan = [
        f"Is hafte: {business_name} ka GBP 100% complete karo (photos+services+Q&A) aur "
        "competitor ke profile se categories compare karo.",
        "Agle 15 din: upar wale sabse bade gap par ek loud promise banao (speed/price/"
        "transparency) aur har post + WhatsApp status me wahi repeat karo.",
        f"Roz: har naye lead ko 5-minute me jawab + har customer se review request — "
        f"{_niche_name(niche)} me 90 din me yahi sabse bada farak banata hai.",
    ]
    return {"strengths_to_copy": strengths, "gaps_to_exploit": gaps, "action_plan": action_plan}


# --------------------------------------------------------------------------- #
# LLM parse — COPY:/GAP:/ACTION: prefixed lines
# --------------------------------------------------------------------------- #


def _parse_llm(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"strengths_to_copy": [], "gaps_to_exploit": [], "action_plan": []}
    key_map = {"COPY": "strengths_to_copy", "GAP": "gaps_to_exploit", "ACTION": "action_plan"}
    try:
        for line in (text or "").splitlines():
            m = re.match(
                r"^\s*[\-\*\d\.\)\s]*(COPY|GAP|ACTION)\s*[:\-]\s*(.+)$", line.strip(), re.I
            )
            if m:
                val = m.group(2).strip()
                if val:
                    out[key_map[m.group(1).upper()]].append(val)
    except Exception:  # pragma: no cover
        pass
    return out


async def compare_tips(
    business_name: str,
    niche: str = "general",
    competitor_notes: str = "",
) -> dict[str, Any]:
    """Competitor notes → {"strengths_to_copy"[2-3], "gaps_to_exploit"[2-3],
    "action_plan"[3], "provider"}. KABHI empty nahi, KABHI raise nahi.
    """
    business_name = (business_name or "").strip() or "Aapka Business"
    niche = (niche or "general").strip().lower() or "general"
    competitor_notes = (competitor_notes or "").strip()

    fallback = _rule_based(business_name, niche, competitor_notes)
    provider = ""
    parsed: dict[str, list[str]] = {}

    if free_ai is not None and competitor_notes:
        try:
            system = (
                "Tu Indian local-business ka marketing strategist hai. User apne competitor "
                "ki observations dega — practical Hinglish analysis de. Output EXACTLY in "
                "lines me, har line ek prefix se shuru (koi extra commentary nahi):\n"
                "COPY: <competitor ki strength jo copy karni chahiye> (2-3 lines)\n"
                "GAP: <unki kamzori jise exploit karna chahiye> (2-3 lines)\n"
                "ACTION: <concrete step> (EXACTLY 3 lines)\n"
                "Har point chhota, specific aur turant karne layak ho."
            )
            user = (
                f"Mera business: {business_name} (category: {_niche_name(niche)})\n"
                f"Competitor ke baare me notes:\n{competitor_notes[:1500]}"
            )
            text, provider = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=500,
                temperature=0.7,
            )
            if text and text.strip():
                parsed = _parse_llm(text)
        except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
            logger.warning(f"compare_tips LLM step failed, using rules: {e}")

    def _take(key: str, lo: int, hi: int) -> list[str]:
        vals = [v for v in (parsed.get(key) or []) if v.strip()][:hi]
        return vals if len(vals) >= lo else fallback[key][:hi]

    strengths = _take("strengths_to_copy", 2, 3)
    gaps = _take("gaps_to_exploit", 2, 3)
    actions = _take("action_plan", 3, 3)
    llm_used = bool(parsed.get("strengths_to_copy") or parsed.get("gaps_to_exploit"))

    return {
        "business_name": business_name,
        "niche": niche,
        "strengths_to_copy": strengths,
        "gaps_to_exploit": gaps,
        "action_plan": actions,
        "provider": (provider if llm_used else "template") or "template",
    }
