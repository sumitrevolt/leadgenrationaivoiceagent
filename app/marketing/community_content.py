"""Community / Q&A content drafter — inbound via communities (telephony-free).

Quora/Reddit answers, WhatsApp/FB-group value posts, LinkedIn articles,
Medium syndication — sab VALUE-first (spam nahi), soft CTA → /audit. AI platform-
appropriate draft deta (insaan khud post kare — ban-safe). free-LLM, template fallback.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

PLATFORMS = {
    "quora": "Quora answer — detailed, helpful, 1 soft mention at end",
    "reddit": "Reddit comment — genuine, no salesy tone, value-first (r/india business)",
    "whatsapp_group": "WhatsApp business-group post — short, useful tip + free-audit offer",
    "linkedin_article": "LinkedIn article — 150-200 word professional, thought-leadership",
    "medium": "Medium blog intro — SEO-friendly, useful, CTA at end",
}


def list_platforms() -> list[dict[str, str]]:
    return [{"key": k, "desc": v} for k, v in PLATFORMS.items()]


def _fallback(platform: str, topic: str, niche: str) -> str:
    nm = (niche or "local business").replace("_", " ")
    return (
        f"[{platform}] {nm} ke liye {topic or 'naye customers laana'}: sabse bada gap hai inquiry ka "
        f"5-min me follow-up na hona — 80% leads yahi khote hain. Ek AI voice agent har inquiry ko "
        f"turant call karke qualify kar sakta hai. Free Google audit se shuru karo: leadsgenai.in/audit"
    )


async def draft_content(platform: str, topic: str = "", niche: str = "general") -> dict[str, Any]:
    """Ek platform ke liye value-first content draft. free-LLM, fallback template."""
    plat = (platform or "quora").strip().lower()
    style = PLATFORMS.get(plat, PLATFORMS["quora"])
    topic = (topic or "local business ke leads kaise badhayein").strip()
    text = _fallback(plat, topic, niche)
    try:
        from app.voice_agent import free_ai

        sys = (
            f"Tum ek helpful content writer ho. Style: {style}. Hinglish. Genuinely USEFUL "
            "(spam nahi), end me 1 soft mention LeadGen AI / free Google audit (leadsgenai.in/audit). "
            "Sirf content text, koi meta."
        )
        prompt = f"Platform: {plat}. Topic: {topic}. Niche: {niche}."
        txt, _ = await free_ai.chat(
            sys, [{"role": "user", "content": prompt}], max_tokens=320, temperature=0.7
        )
        if txt and txt.strip():
            text = txt.strip()
    except Exception as e:
        logger.debug(f"[community_content] llm skip: {e}")
    return {
        "ok": True,
        "platform": plat,
        "topic": topic,
        "niche": niche,
        "content": text,
        "cta": "leadsgenai.in/audit",
        "auto_posted": False,
    }


async def draft_batch(
    topic: str = "", niche: str = "general", platforms: list[str] | None = None
) -> dict[str, Any]:
    """Multiple platforms ke liye content pack (ek topic → har jagah)."""
    plats = platforms or ["quora", "reddit", "whatsapp_group", "linkedin_article"]
    out = []
    for p in plats[:6]:
        out.append(await draft_content(p, topic, niche))
    return {"ok": True, "count": len(out), "content": out}


__all__ = ["PLATFORMS", "list_platforms", "draft_content", "draft_batch"]
