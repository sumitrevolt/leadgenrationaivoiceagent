"""AI image generation — real marketing images from a text prompt (Pollinations, FREE).

The #1 feature of competitor marketing-AI apps (Predis.ai, AdBanao) is turning a phrase
into an actual image/creative. We only had SVG templates. Pollinations.ai gives free,
**no-API-key**, unlimited Flux text-to-image — a perfect free-stack fit.

URL-based by design: we return an image URL that renders on load (no server-side fetch or
storage = light + fast; the frontend <img>/download just uses the URL). A free_ai step
crafts a vivid prompt from the business + occasion + offer (template fallback). Never raises.

Use:
  from app.marketing.ai_image import image_url, marketing_image
  url = image_url("Diwali sale poster for a jewellery store, golden diyas, festive, text space")
  data = await marketing_image("Sharma Jewellers", "jewellery_store", occasion="Diwali", offer="20% off")
  # -> {"url": "...", "prompt": "...", "provider": "pollinations-flux", "width":1024, "height":1024}
"""

from __future__ import annotations

import logging
import urllib.parse

logger = logging.getLogger(__name__)

_BASE = "https://image.pollinations.ai/prompt/"


def image_url(prompt: str, width: int = 1024, height: int = 1024, seed: int | None = None, model: str = "flux") -> str:
    """Build a Pollinations image URL (renders a real AI image on load). Never raises."""
    try:
        p = urllib.parse.quote((prompt or "marketing poster").strip()[:480], safe="")
        q = f"width={int(width)}&height={int(height)}&nologo=true&model={model}"
        if seed is not None:
            q += f"&seed={int(seed)}"
        return f"{_BASE}{p}?{q}"
    except Exception:
        return f"{_BASE}marketing%20poster?width=1024&height=1024&nologo=true&model=flux"


def _template_prompt(business: str, niche: str, occasion: str, offer: str, style: str) -> str:
    bits = [f"{style} social-media marketing poster"]
    if occasion:
        bits.append(f"for {occasion}")
    bits.append(f"for a {niche.replace('_', ' ')} business '{business}' in India")
    if offer:
        bits.append(f"highlighting the offer: {offer}")
    bits.append("vibrant colors, professional, high quality, clean space for text, Indian festive aesthetic")
    return ", ".join(bits)


async def _craft_prompt(business: str, niche: str, occasion: str, offer: str, style: str) -> str:
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            system="Tu ek pro graphic designer hai. Diye gaye business ke liye ek vivid ENGLISH "
            "image-generation prompt likh (max 40 words) jo ek attractive marketing poster banaye. "
            "Sirf prompt de, aur kuch nahi (no quotes).",
            messages=[{"role": "user", "content": f"Business: {business}\nNiche: {niche}\nOccasion: {occasion or 'general'}\nOffer: {offer or 'none'}\nStyle: {style}"}],
            max_tokens=70,
            temperature=0.7,
        )
        r = (reply or "").strip().strip('"')
        if len(r) > 15:
            return r
    except Exception:
        pass
    return _template_prompt(business, niche, occasion, offer, style)


async def marketing_image(
    business_name: str,
    niche: str = "general",
    occasion: str = "",
    offer: str = "",
    style: str = "vibrant professional",
    width: int = 1024,
    height: int = 1024,
) -> dict:
    """Craft a prompt + return a ready AI-image URL. Never raises."""
    business_name = (business_name or "Aapka Business").strip()
    niche = (niche or "general").strip()
    prompt = await _craft_prompt(business_name, niche, (occasion or "").strip(), (offer or "").strip(), style)
    return {
        "url": image_url(prompt, width, height),
        "prompt": prompt,
        "provider": "pollinations-flux",
        "width": width,
        "height": height,
    }


def logo_url(business_name: str, niche: str = "general", style: str = "modern minimalist") -> str:
    """AI logo image URL (Pollinations free) for a business. Never raises."""
    prompt = (
        f"{style} vector logo for '{(business_name or 'Business').strip()}', a "
        f"{(niche or 'general').replace('_', ' ')} business, clean flat iconic memorable brand mark, "
        "white background, professional, centered, no text"
    )
    return image_url(prompt, width=512, height=512)


__all__ = ["image_url", "marketing_image", "logo_url"]
