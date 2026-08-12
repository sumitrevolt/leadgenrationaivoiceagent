"""Carousel post generator (Predis-style) — ek topic → 3-5 branded SVG slides.

Instagram/LinkedIn carousel = 2026 ka highest-engagement format. Har slide:
hook → value points → CTA. SVG self-contained (poster pipeline jaisa reliable,
koi image-API dependency nahi). free-LLM se slide texts, template fallback.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_COLORS = [
    ("#6d28d9", "#ede9fe"),
    ("#0e7490", "#cffafe"),
    ("#b45309", "#fef3c7"),
    ("#be123c", "#ffe4e6"),
    ("#166534", "#dcfce7"),
]

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Default CTA (agency/admin carousel — LeadGen ka apna audit lead-magnet).
# CUSTOMER carousels apni mini-site URL / phone pass karti hain (client_cta()).
_DEFAULT_CTA = "leadsgenai.in/audit"


def _valid_hex(value: str) -> str | None:
    v = (value or "").strip()
    return v if _HEX_RE.match(v) else None


def client_cta(slug: str = "", phone: str = "") -> str:
    """CUSTOMER carousel CTA — apni mini-site URL (/b/<slug>) ya phone.

    slug diya = "leadsgenai.in/b/<slug>" (client ki apni booking page); warna
    phone; dono khali = "" (caller default use kare). CTA slot chhota hai to
    "https://" strip karke sirf host+path dikhate hain (readable, brand-clean).
    """
    s = (slug or "").strip().strip("/")
    if s:
        return f"leadsgenai.in/b/{s}"
    p = "".join(ch for ch in str(phone or "") if ch.isdigit() or ch == "+")
    if p:
        return f"\U0001f4de {p}"
    return ""


def _slide_svg(
    idx: int, total: int, title: str, body: str, brand: str, cta: str = "", fg_override: str = ""
) -> str:
    """Ek slide ka self-contained square SVG (1080-style 540 viewBox).

    cta = footer button ka text (customer = apni mini-site URL/phone; khali =
    default leadsgenai.in/audit lead-magnet). fg_override (#RRGGBB) = client
    brand-primary color (accent-rotation ki jagah), invalid/khali = palette.
    """
    fg, bg = _COLORS[idx % len(_COLORS)]
    fg = _valid_hex(fg_override) or fg
    t = html.escape((title or "")[:60])
    cta_text = html.escape((cta or "").strip()[:40] or _DEFAULT_CTA)
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
        f'<rect x="40" y="460" width="260" height="40" rx="20" fill="{fg}"/>'
        f'<text x="170" y="486" text-anchor="middle" font-family="Arial" font-size="15" fill="#ffffff">{cta_text}</text>'
        f"</svg>"
    )


def _fallback_slides(
    business: str, niche: str, topic: str, n: int, cta: str = ""
) -> list[dict[str, str]]:
    nm = (niche or "business").replace("_", " ")
    # Last-slide CTA line — customer ho to apni mini-site/phone; warna default audit.
    last_cta = (cta or "").strip() or _DEFAULT_CTA
    base = [
        {
            "title": topic or f"{nm} growth ka raaz",
            "body": f"{business} — yeh carousel aapke kaam ka hai. Swipe karo →",
        },
        {
            "title": "80% leads kyu khoti hain?",
            "body": "Inquiry ke 5 minute me jawab na mile to customer agle ko call kar leta hai.",
        },
        {
            "title": "Fix: 2-minute auto-callback",
            "body": "AI har inquiry ko turant call/WhatsApp karta hai — aap sirf garam leads se baat karo.",
        },
        {
            "title": "Roz ka content autopilot",
            "body": "Festival posts, offers, reviews — sab AI banata hai, aap 1-click post karte ho.",
        },
        {
            "title": "Aaj hi shuru karo",
            "body": f"Abhi book karo ya poocho — {last_cta}",
        },
    ]
    return base[: max(3, min(n, 5))]


async def generate_carousel(
    business_name: str,
    niche: str = "general",
    topic: str = "",
    slides: int = 4,
    slug: str = "",
    phone: str = "",
    brand_primary: str = "",
    cta: str = "",
) -> dict[str, Any]:
    """Carousel pack: slide texts (free-LLM, fallback) + per-slide SVG. Kabhi raise nahi.

    slug/phone = CUSTOMER carousel ke liye — slide-footer CTA client ki apni
    mini-site (/b/<slug>) ya phone banti hai (default leadsgenai.in/audit sirf
    tab jab dono khali = agency/admin use). `cta` = explicit override.
    brand_primary (#RRGGBB) = client brand color accent-rotation ki jagah.
    Sab optional — na do to purana byte-identical behavior (backward-compat).
    """
    business = (business_name or "Aapka Business").strip()[:80]
    n = max(3, min(int(slides or 4), 5))
    # CTA precedence: explicit cta > client mini-site/phone > default audit.
    slide_cta = (cta or "").strip() or client_cta(slug=slug, phone=phone)
    texts: list[dict[str, str]] = []
    try:
        from app.voice_agent.free_ai import chat

        raw, _ = await chat(
            (
                "Tu Indian local-business social media expert hai. Carousel slides bana — "
                'JSON list: [{"title": "<6 words>", "body": "<25 words Hinglish>"}]. '
                "Slide 1 = hook, last = CTA (is business ko book/contact karne ko bolo — "
                "koi external website/audit link mat likho). Salesy nahi, value-first."
            ),
            [
                {
                    "role": "user",
                    "content": f"Business: {business} | Niche: {niche} | Topic: {topic or 'naye customer kaise laaye'} | {n} slides",
                }
            ],
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
        texts = _fallback_slides(business, niche, topic, n, cta=slide_cta)
    total = len(texts)
    out_slides = [
        {
            **t,
            "svg": _slide_svg(
                i, total, t["title"], t["body"], business, cta=slide_cta, fg_override=brand_primary
            ),
        }
        for i, t in enumerate(texts)
    ]
    return {
        "business_name": business,
        "niche": niche,
        "topic": topic,
        "slides": out_slides,
        "caption": f"{topic or 'Growth tips'} — swipe karo 👉 | {business}",
        "note": "Har slide ka SVG download karke carousel post banao (IG/LinkedIn).",
    }
