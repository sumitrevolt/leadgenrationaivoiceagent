"""Carousel post generator (Predis-style) — ek topic → 3-5 branded SVG slides.

Instagram/LinkedIn carousel = 2026 ka highest-engagement format. Har slide:
hook → value points → CTA. SVG self-contained (poster pipeline jaisa reliable,
koi image-API dependency nahi). free-LLM se slide texts, template fallback.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import html
import json
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_COLORS = [("#6d28d9", "#ede9fe"), ("#0e7490", "#cffafe"), ("#b45309", "#fef3c7"), ("#be123c", "#ffe4e6"), ("#166534", "#dcfce7")]


def _slide_svg(idx: int, total: int, title: str, body: str, brand: str) -> str:
    """Ek slide ka self-contained square SVG (1080-style 540 viewBox)."""
    fg, bg = _COLORS[idx % len(_COLORS)]
    t = html.escape((title or "")[:60])
    lines = [html.escape(body[i : i + 38]) for i in range(0, min(len(body), 152), 38)]
    tspans = "".join(
        f'<tspan x="40" dy="{0 if i == 0 else 30}">{ln}</tspan>' for i, ln in enumerate(lines)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 540">'
        f'<rect width="540" height="540" fill="{bg}"/>'
        f'<rect width="540" height="10" fill="{fg}"/>'
        f'<text x="40" y="60" font-family="Arial" font-size="16" fill="{fg}" font-weight="bold">{html.escape(brand[:40])}</text>'
        f'<text x="500" y="60" text-anchor="end" font-family="Arial" font-size="16" fill="{fg}">{idx + 1}/{total}</text>'
        f'<text x="40" y="160" font-family="Arial" font-size="34" fill="#111827" font-weight="bold">{t}</text>'
        f'<text x="40" y="240" font-family="Arial" font-size="20" fill="#374151">{tspans}</text>'
        f'<rect x="40" y="460" width="220" height="40" rx="20" fill="{fg}"/>'
        f'<text x="150" y="486" text-anchor="middle" font-family="Arial" font-size="16" fill="#ffffff">leadsgenai.in/audit</text>'
        f"</svg>"
    )


def _fallback_slides(business: str, niche: str, topic: str, n: int) -> list[dict[str, str]]:
    nm = (niche or "business").replace("_", " ")
    base = [
        {"title": topic or f"{nm} growth ka raaz", "body": f"{business} — yeh carousel aapke kaam ka hai. Swipe karo →"},
        {"title": "80% leads kyu khoti hain?", "body": "Inquiry ke 5 minute me jawab na mile to customer agle ko call kar leta hai."},
        {"title": "Fix: 2-minute auto-callback", "body": "AI har inquiry ko turant call/WhatsApp karta hai — aap sirf garam leads se baat karo."},
        {"title": "Roz ka content autopilot", "body": "Festival posts, offers, reviews — sab AI banata hai, aap 1-click post karte ho."},
        {"title": "Shuru karo FREE me", "body": "Apna Google profile audit 2 minute me — link bio me ya leadsgenai.in/audit"},
    ]
    return base[: max(3, min(n, 5))]


async def generate_carousel(business_name: str, niche: str = "general", topic: str = "", slides: int = 4) -> dict[str, Any]:
    """Carousel pack: slide texts (free-LLM, fallback) + per-slide SVG. Kabhi raise nahi."""
    business = (business_name or "Aapka Business").strip()[:80]
    n = max(3, min(int(slides or 4), 5))
    texts: list[dict[str, str]] = []
    try:
        from app.voice_agent.free_ai import chat

        raw, _ = await chat(
            (
                "Tu Indian local-business social media expert hai. Carousel slides bana — "
                'JSON list: [{"title": "<6 words>", "body": "<25 words Hinglish>"}]. '
                "Slide 1 = hook, last = CTA (free audit). Salesy nahi, value-first."
            ),
            [{"role": "user", "content": f"Business: {business} | Niche: {niche} | Topic: {topic or 'naye customer kaise laaye'} | {n} slides"}],
            max_tokens=420,
        )
        s, e = raw.find("["), raw.rfind("]")
        if s >= 0 and e > s:
            parsed = json.loads(raw[s : e + 1])
            texts = [
                {"title": str(x.get("title", ""))[:80], "body": str(x.get("body", ""))[:200]}
                for x in parsed
                if isinstance(x, dict) and x.get("title")
            ][:n]
    except Exception as e:
        logger.debug(f"[carousel] llm fallback: {e}")
    if len(texts) < 3:
        texts = _fallback_slides(business, niche, topic, n)
    total = len(texts)
    out_slides = [
        {**t, "svg": _slide_svg(i, total, t["title"], t["body"], business)} for i, t in enumerate(texts)
    ]
    return {
        "business_name": business,
        "niche": niche,
        "topic": topic,
        "slides": out_slides,
        "caption": f"{topic or 'Growth tips'} — swipe karo 👉 | {business}",
        "note": "Har slide ka SVG download karke carousel post banao (IG/LinkedIn).",
    }
