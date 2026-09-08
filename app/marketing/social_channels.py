"""Naye customer-approach channels (2026) — sab BAN-SAFE drafts, human 1-click post.

community_content.py (quora/reddit/wa-group/li-article/medium) ke UPAR
8 NAYE methods — koi auto-post/auto-send NAHI (Insta/YT/Meta ToS + WA ban-safety):
  instagram_comment  — local pages pe value-comment + DM follow-up draft
  youtube_shorts     — 30-sec Hinglish Shorts script (hook/value/CTA)
  gbp_qna            — apne Google Business profile pe Q&A seed pairs (allowed)
  whatsapp_status    — daily WhatsApp Status content (apna status = ban-safe)
  micro_influencer   — local micro-influencer (1k-20k) collab pitch draft
  local_pr           — local newspaper/portal ke liye press-pitch draft
  event_outreach     — exhibition/trade-event/society-event outreach drafts
  listing_optimizer  — JustDial/Sulekha/IndiaMART listing text optimize draft

free-LLM (free_ai chain) + static Hinglish fallback — LLM down ho to bhi draft
milta. Import-safe, kabhi raise nahi. channel_experiments bandit me wired.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

CHANNELS: dict[str, str] = {
    "instagram_comment": "Instagram comment-first — local page/reel pe genuine value-comment, fir DM follow-up (manual)",
    "youtube_shorts": "YouTube Shorts 30-sec Hinglish script — hook (3s) → value → CTA",
    "gbp_qna": "Google Business Q&A seeding — apne profile pe common-question + answer pairs",
    "whatsapp_status": "WhatsApp Status daily content — tip/offer/social-proof (apna status, ban-safe)",
    "micro_influencer": "Local micro-influencer (1k-20k followers) barter/paid collab pitch",
    "local_pr": "Local newspaper/news-portal press pitch — story angle + quote",
    "event_outreach": "Exhibition/trade-event/society-event stall ya sponsorship outreach",
    "listing_optimizer": "JustDial/Sulekha/IndiaMART listing title+description optimize",
}


def list_channels() -> list[dict[str, str]]:
    return [{"key": k, "desc": v} for k, v in CHANNELS.items()]


def _fallback(channel: str, niche: str, city: str, business: str) -> str:
    nm = (niche or "local business").replace("_", " ")
    biz = business or f"{city or 'aapke sheher'} ka {nm}"
    f = {
        "instagram_comment": (
            f"Comment (local {nm} page pe): 'Bhai kaam ekdum solid hai 🔥 {city} me aap jaise "
            f"businesses ko roz naye customer chahiye — humne ek FREE Google-profile audit tool banaya hai, "
            f"DM karu link?' | DM follow-up: 'Hi! Comment wala audit link — leadsgenai.in/audit. "
            f"2 min me score milega, koi charge nahi.'"
        ),
        "youtube_shorts": (
            f"HOOK (0-3s): '{city} ke {nm} owners — roz ke 5 customer miss kar rahe ho!'\n"
            f"VALUE (3-20s): 'Jab aap busy ho, calls miss hoti hain. Har missed call = gaya hua customer. "
            f"AI assistant 2 minute me callback karta hai, inquiry pakad leta hai.'\n"
            f"CTA (20-30s): 'FREE audit ke liye bio link — leadsgenai.in/audit. Comment me apna business type likho!'"
        ),
        "gbp_qna": (
            f"Q1: Kya {biz} same-day service deta hai? → A: Haan, {city} me same-day available — call/WhatsApp karein.\n"
            f"Q2: Pricing kya hai? → A: Free estimate milta hai, kaam ke hisaab se transparent rate.\n"
            f"Q3: Kya advance booking ho sakti hai? → A: Haan, online/WhatsApp booking available hai."
        ),
        "whatsapp_status": (
            f"Status 1 (tip): '{nm} customers ke liye pro-tip 💡 — Google pe review zaroor karein, "
            f"local business ko bahut madad milti hai!'\n"
            f"Status 2 (offer): 'Is hafte special — pehli service pe 10% off. Reply karke slot book karein ✅'\n"
            f"Status 3 (proof): 'Aaj ka kaam ✅ Ek aur khush customer {city} me 🙏'"
        ),
        "micro_influencer": (
            f"Hi! Main {biz} se hu. Aapka {city} content genuine lagta hai 👌 Hum local logo tak "
            f"pahunchna chahte hain — ek chhota collab socha: aap humari service try karo (free), "
            f"pasand aaye to ek honest reel/post. Barter ya paid, jo comfortable ho. Interested?"
        ),
        "local_pr": (
            f"Story pitch: '{city} ke chhote businesses ab AI se inquiry handle kar rahe hain' — "
            f"local {nm} ne missed-calls se hone wala nuksan AI callback se rok diya. "
            f"Quote ready hai, photos de sakte hain. Aapke readers (local business owners) ke liye useful angle."
        ),
        "event_outreach": (
            f"Namaste! {city} ke aane wale trade-event/exhibition me hum {biz} ke liye ek chhota "
            f"demo stall/sponsorship explore kar rahe hain — live AI inquiry-callback demo rakhenge. "
            f"Stall/slot availability aur charges share karenge? Society events ke liye bhi open hain."
        ),
        "listing_optimizer": (
            f"Title: {biz} — {city} me trusted {nm} | Same-day service, free estimate\n"
            f"Description: {city} aur aas-paas ke liye {nm} services. ✅ Verified reviews ✅ Transparent pricing "
            f"✅ WhatsApp booking. Abhi call karein ya enquiry chhodein — 2 minute me callback milega.\n"
            f"Keywords: {nm} {city}, best {nm} near me, {nm} price, {nm} booking"
        ),
    }
    return f.get(channel, f"{biz} ke liye {CHANNELS.get(channel, channel)} draft.")


async def draft(
    channel: str, niche: str = "general", city: str = "", business_name: str = ""
) -> dict[str, Any]:
    """Ek channel ka ready-to-use Hinglish draft. free-LLM, static fallback.
    Kabhi raise nahi."""
    ch = (channel or "").strip().lower()
    if ch not in CHANNELS:
        return {"ok": False, "error": f"unknown channel (valid: {list(CHANNELS)})"}
    text = _fallback(ch, niche, city, business_name)
    try:
        from app.voice_agent import free_ai

        sys = (
            "Tu Indian local-business marketing expert hai. Hinglish (Roman script) me likho. "
            f"Channel: {CHANNELS[ch]}. Ban-safe manual posting ke liye draft — koi spammy tone nahi, "
            "value-first, max 120 words. Sirf draft do, koi explanation nahi."
        )
        user = (
            f"Business: {business_name or 'local ' + (niche or 'business').replace('_', ' ')}"
            f" | Niche: {niche} | City: {city or 'Maharashtra'}. Is channel ke liye draft banao."
        )
        out, _ = await asyncio.wait_for(
            free_ai.chat(sys, [{"role": "user", "content": user}], max_tokens=260, temperature=0.7),
            timeout=40,
        )
        if out and len(out.strip()) > 30:
            text = out.strip()
    except Exception as e:
        logger.debug(f"[social] LLM skip ({ch}): {e}")
    return {
        "ok": True,
        "channel": ch,
        "niche": niche,
        "city": city,
        "draft": text,
        "note": "ban-safe: manual 1-click post",
    }


async def draft_batch(
    niche: str = "general",
    city: str = "",
    business_name: str = "",
    channels: list[str] | None = None,
    limit: int = 4,
) -> dict[str, Any]:
    """Multiple naye channels ka pack (rotation se variety). Kabhi raise nahi."""
    try:
        keys = [c for c in (channels or list(CHANNELS.keys())) if c in CHANNELS][: max(1, limit)]
        out = []
        for ch in keys:
            out.append(await draft(ch, niche, city, business_name))
        return {"ok": True, "count": len(out), "drafts": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = ["CHANNELS", "list_channels", "draft", "draft_batch"]
