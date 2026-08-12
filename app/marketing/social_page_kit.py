"""
Social PAGE KIT generator — naye social pages ka complete ready-to-paste setup.
================================================================================

Ek business (apna LeadsGenAI brand YA koi client) ke liye, har platform ka
page-setup content EK call me:
  - Facebook Page: name, username/handle, bio, about, CTA
  - Instagram: handle, 150-char bio (emoji+line-break style), highlights ideas
  - LinkedIn Page: tagline, about/description
  - X (Twitter): handle, 160-char bio
  - Google Business Profile: description (750-char), categories
  - WhatsApp Business: about + greeting message
  + logo URL (ai_image.logo_url), cover-image prompt, pehle 5 din ke posts
    (post_generator) aur 15 hashtags (hashtags.research).

EXISTING engines compose karta hai (rebuild NAHI): post_generator, hashtags,
ai_image, niches. free-LLM se bios — LLM down ho to TEMPLATE fallback se bhi
COMPLETE kit milta hai (kabhi empty/raise nahi).

NOTE: pages khud create nahi hote (Meta/Google account-action hai) — yeh
paste-ready kit hai; client ko 1-click copy deliverable (Growth-tier).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _slug_handle(name: str) -> str:
    h = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return (h or "business")[:24]


def _niche_cfg(niche: str) -> dict:
    try:
        from app.niches import NICHES, refresh_custom_niches

        refresh_custom_niches()
        return NICHES.get((niche or "").strip().lower()) or {}
    except Exception:
        return {}


def _template_bios(biz: str, niche_name: str, city: str, phone: str) -> dict[str, Any]:
    """LLM-free fallback — hamesha complete, decent Hinglish."""
    loc = f" · {city}" if city else ""
    call = f"\n📞 {phone}" if phone else ""
    return {
        "facebook": {
            "page_name": f"{biz}{loc}",
            "username": _slug_handle(biz),
            "bio": f"{niche_name} ke liye bharosemand naam{loc}. Quality kaam, sahi daam.{call}",
            "about": (
                f"{biz} — {city or 'aapke sheher'} me {niche_name} ki trusted service. "
                f"Inquiry ka jawab jaldi, kaam time pe. Message karo ya call karo — aaj hi shuru karein!"
            ),
            "cta_button": "WhatsApp / Call Now",
        },
        "instagram": {
            "handle": _slug_handle(biz),
            "bio": f"✨ {niche_name}{loc}\n✅ Quality + sahi daam\n📩 DM 'INFO' for details{call}",
            "highlights": ["Work / Portfolio", "Offers", "Reviews", "Contact"],
        },
        "linkedin": {
            "tagline": f"{niche_name} services{loc} — quality-first, customer-first.",
            "about": (
                f"{biz} {city or 'India'} me {niche_name} provide karta hai. "
                f"Hum transparent pricing, timely delivery aur after-service pe focus karte hain."
            ),
        },
        "x_twitter": {
            "handle": _slug_handle(biz),
            "bio": f"{niche_name}{loc} | Quality kaam, sahi daam | DM/call for inquiry{call}",
        },
        "gbp": {
            "description": (
                f"{biz} — {city or 'aapke area'} ki bharosemand {niche_name} service. "
                f"Hum quality, transparent pricing aur time pe kaam ke liye jaane jaate hain. "
                f"Free consultation/quote ke liye call ya message karein. Har customer hamare liye khaas hai."
            ),
        },
        "whatsapp_business": {
            "about": f"{biz} | {niche_name}{loc} | Msg karo, turant jawab",
            "greeting": (
                f"Namaste! 🙏 {biz} me aapka swagat hai. Apni requirement bata dijiye — "
                f"hum 10 minute me jawab dete hain."
            ),
        },
    }


async def _llm_bios(
    biz: str, niche_name: str, city: str, phone: str, pitch: str
) -> dict[str, Any] | None:
    """free-LLM se better bios (JSON) — fail => None (template use hoga)."""
    try:
        from app.voice_agent.free_ai import chat

        sys = (
            "Tum Indian local-business social media expert ho. SIRF valid JSON do, "
            "koi markdown/extra text nahi. Hinglish (Roman) me, warm + professional."
        )
        usr = (
            f"Business: {biz} | Niche: {niche_name} | City: {city or 'India'} | "
            f"Phone: {phone or 'n/a'} | USP: {pitch or 'quality + sahi daam'}\n"
            'JSON shape: {"facebook":{"page_name","username","bio","about","cta_button"},'
            '"instagram":{"handle","bio","highlights":[4 strings]},'
            '"linkedin":{"tagline","about"},"x_twitter":{"handle","bio"},'
            '"gbp":{"description"},"whatsapp_business":{"about","greeting"}}\n'
            "Rules: insta bio <=150 chars (emoji + \\n allowed), x bio <=160, "
            "gbp description 400-700 chars, handles lowercase no-space."
        )
        out = await chat(sys, [{"role": "user", "content": usr}])
        txt = (out or "").strip()
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        if not isinstance(data, dict) or "facebook" not in data:
            return None
        return data
    except Exception as e:
        logger.debug(f"[page_kit] llm bios fallback: {e}")
        return None


async def build_page_kit(
    business_name: str,
    niche: str = "general",
    city: str = "",
    phone: str = "",
    posts_count: int = 2,
) -> dict[str, Any]:
    """Complete social-page setup kit. KABHI raise nahi karta, hamesha complete."""
    biz = (business_name or "Aapka Business").strip()
    cfg = _niche_cfg(niche)
    niche_name = str(cfg.get("name") or (niche or "business").replace("_", " ").title())
    pitch = str(cfg.get("pitch_hook") or "")

    bios = await _llm_bios(biz, niche_name, city, phone, pitch) or {}
    base = _template_bios(biz, niche_name, city, phone)
    # LLM jo de gaya use lo, missing platforms template se bharo (merge — kabhi adhura nahi)
    for k, v in base.items():
        if not isinstance(bios.get(k), dict):
            bios[k] = v

    # first posts + hashtags (existing engines, parallel)
    posts_count = max(1, min(int(posts_count or 5), 7))
    occasions = [
        "page launch / welcome",
        "services intro",
        "customer trust / reviews",
        "offer teaser",
        "behind the scenes",
        "FAQ",
        "festival wish",
    ][:posts_count]

    async def _post(occ: str) -> dict:
        try:
            from app.marketing.post_generator import generate_post

            p = await generate_post(biz, niche=niche, occasion=occ)
            return {
                "occasion": occ,
                "caption": p.get("caption", ""),
                "hashtags": p.get("hashtags", []),
                "image_idea": p.get("image_idea", ""),
            }
        except Exception:
            return {
                "occasion": occ,
                "caption": f"{biz} — {niche_name} me aapka apna bharosemand naam. {occ}!",
                "hashtags": [],
                "image_idea": "",
            }

    async def _tags() -> dict:
        try:
            from app.marketing import hashtags as ht

            return await ht.research(niche or niche_name, city=city)
        except Exception:
            return {}

    # 2026-07-19: SEQUENTIAL + per-post 10s timeout — free-tier concurrent LLM calls
    # 429-backoff dete the (bio-page 30s+ hang). posts_count=2 default + sequential
    # + per-call timeout = reliably fast, kabhi hang nahi.
    async def _post_to(occ: str) -> dict:
        try:
            return await asyncio.wait_for(_post(occ), timeout=10)
        except Exception:
            return {
                "occasion": occ,
                "caption": f"{biz} — {niche_name}. {occ}!",
                "hashtags": [],
                "image_idea": "",
            }

    first_posts = []
    for o in occasions:
        first_posts.append(await _post_to(o))
    try:
        tag_research = await asyncio.wait_for(_tags(), timeout=8)
    except Exception:
        tag_research = {}

    logo = ""
    try:
        from app.marketing.ai_image import logo_url

        logo = logo_url(biz, niche=niche_name)
    except Exception:
        pass

    return {
        "business_name": biz,
        "niche": niche,
        "niche_name": niche_name,
        "city": city,
        "pages": bios,
        "logo_url": logo,
        "cover_image_prompt": (
            f"Wide social media cover banner for '{biz}', {niche_name} business in {city or 'India'}, "
            f"modern clean design, brand-friendly colors, large readable business name, no clutter"
        ),
        "first_posts": first_posts,
        "hashtags": tag_research.get("hashtags") or tag_research.get("trending") or [],
        "best_time": tag_research.get("best_time") or tag_research.get("best_times") or "",
        "setup_note": "Pages create karna account-action hai (Meta/Google login) — yeh kit paste-ready content deta hai.",
    }
