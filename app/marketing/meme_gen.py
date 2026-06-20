"""Meme generator (Predis-style) — niche/topic → desi business meme (SVG + caption).

Memes = sabse shareable format, zero cost. Top-text/bottom-text classic format,
free-LLM se relatable Hinglish meme text, template fallback. SVG self-contained.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import html
import json
import random
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FALLBACKS = [
    ("Customer: 'kal pakka aaunga'", "Kal: *kabhi nahi aata*"),
    ("Inquiry aayi raat 11 baje", "AI: 2 minute me callback ho gaya 😎"),
    ("Competitor: roz post nahi karta", "Tum: AI se roz fresh post 🚀"),
    ("5 missed calls = 5 khoye customer", "Auto-callback = 5 naye dhande 💰"),
]
_BG = ["#1f2937", "#312e81", "#7c2d12", "#14532d"]


def _meme_svg(top: str, bottom: str, brand: str) -> str:
    bg = random.choice(_BG)
    t = html.escape(top[:70])
    b = html.escape(bottom[:70])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 540">'
        f'<rect width="540" height="540" fill="{bg}"/>'
        f'<text x="270" y="90" text-anchor="middle" font-family="Impact, Arial" font-size="28" fill="#ffffff" font-weight="bold">{t}</text>'
        f'<text x="270" y="300" text-anchor="middle" font-family="Arial" font-size="80">😅</text>'
        f'<text x="270" y="470" text-anchor="middle" font-family="Impact, Arial" font-size="28" fill="#fbbf24" font-weight="bold">{b}</text>'
        f'<text x="270" y="520" text-anchor="middle" font-family="Arial" font-size="14" fill="#9ca3af">{html.escape(brand[:50])}</text>'
        f"</svg>"
    )


async def generate_meme(
    business_name: str = "", niche: str = "general", topic: str = ""
) -> dict[str, Any]:
    """Ek meme: top/bottom text (free-LLM, fallback) + SVG + caption. Kabhi raise nahi."""
    business = (business_name or "leadsgenai.in").strip()[:60]
    top = bottom = ""
    try:
        from app.voice_agent.free_ai import chat

        raw, _ = await chat(
            (
                "Tu Indian small-business meme writer hai. Relatable, funny, clean. "
                'JSON de: {"top": "<setup <10 words>", "bottom": "<punchline <10 words>"} Hinglish.'
            ),
            [
                {
                    "role": "user",
                    "content": f"Niche: {niche} | Topic: {topic or 'customer/leads ka struggle'}",
                }
            ],
            max_tokens=120,
        )
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            d = json.loads(raw[s : e + 1])
            top, bottom = str(d.get("top", ""))[:80], str(d.get("bottom", ""))[:80]
    except Exception as e:
        logger.debug(f"[meme] llm fallback: {e}")
    if not top or not bottom:
        top, bottom = random.choice(_FALLBACKS)
    return {
        "top": top,
        "bottom": bottom,
        "svg": _meme_svg(top, bottom, business),
        "caption": f"{top} {bottom} 😂 | Tag karo us dost ko jiska dhandha aisa hi hai | {business}",
        "hashtags": [
            "#SmallBusinessMemes",
            "#DhandaMemes",
            "#LocalBusiness",
            "#" + (niche or "business").replace("_", ""),
        ],
    }
