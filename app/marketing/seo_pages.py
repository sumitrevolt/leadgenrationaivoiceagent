"""Programmatic SEO page generator — niche×city landing pages for organic INBOUND.

Inbound = customer khud aata hai (sabse sasta long-term channel). 42 niches × top
cities = sencrypted hundreds of indexable pages. Har page genuinely useful content
(thin spam = Google penalty) + H1 keyword + FAQ schema + CTA → /audit.

Reuse: NICHES (keywords/pain) + free_ai. Pages JSONL me store hote (`data/seo_pages.jsonl`)
— existing `/blog` ya sitemap inhe serve/index kar sakta. Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "seo_pages.jsonl")
DEFAULT_CITIES = ["Pune", "Mumbai", "Nagpur", "Nashik", "Thane", "Nagpur"]


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in (s or "").lower()).strip("-")[:80]


def _niche_cfg(niche: str) -> dict[str, Any]:
    try:
        from app.niches import NICHES

        return NICHES.get((niche or "").strip().lower(), {}) or {}
    except Exception:
        return {}


def _schema(title: str, city: str, faqs: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "name": title,
        "areaServed": city,
        "mainEntity": [
            {
                "@type": "Question",
                "name": q["q"],
                "acceptedAnswer": {"@type": "Answer", "text": q["a"]},
            }
            for q in faqs
        ],
    }


def _track(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[seo_pages] track skip: {e}")


def list_pages(limit: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows[-limit:]


async def generate_page(niche: str, city: str) -> dict[str, Any]:
    """Ek niche×city SEO landing page (title/H1/body/FAQ/schema/CTA). Kabhi raise nahi."""
    cfg = _niche_cfg(niche)
    label = str(cfg.get("name") or niche.replace("_", " ").title())
    city = (city or "India").strip()
    kw = f"{label} marketing & lead generation in {city}"
    title = f"AI Marketing & Lead Generation for {label} in {city} | LeadGenAI"
    h1 = f"{label} ke liye AI Marketing + Lead Generation — {city}"

    body = ""
    faqs = [
        {
            "q": f"{label} ko {city} me naye leads kaise milein?",
            "a": "AI voice agent har inquiry ko 2-min me call karke qualify karta hai + social posts, "
            "Google ranking, aur WhatsApp follow-up automate hote hain. Free audit: leadsgenai.in/audit",
        },
        {
            "q": "Kitna kharcha aata hai?",
            "a": "₹1,999/mo AI Marketing Automation se shuru, ₹0 me 7-din trial. Advanced tier me AI calling (500 min/mo). Alag AI voice agent flat ₹5,999/mo se (unlimited calls).",
        },
        {
            "q": "Result kitne din me?",
            "a": "Pehle hafte me naye leads + content live. Cancel anytime.",
        },
    ]
    try:
        from app.voice_agent import free_ai

        sys = (
            f"Tum ek local-SEO copywriter ho. {city} me '{label}' businesses ke liye ek 150-200 "
            "word Hinglish landing-page intro likho — keyword '" + kw + "' natural use karo, pain "
            "+ AI-solution + free-audit CTA. Genuinely useful, no spam. Sirf paragraph text."
        )
        txt, _ = await free_ai.chat(
            sys, [{"role": "user", "content": kw}], max_tokens=320, temperature=0.6
        )
        body = (txt or "").strip()
    except Exception as e:
        logger.debug(f"[seo_pages] llm skip: {e}")
    if not body:
        body = (
            f"{city} ke {label} businesses ke liye naye customers tak pahunchna mehenga aur slow ho "
            f"gaya hai. LeadGenAI AI se aapki marketing, Google ranking, aur inquiry-calling automate "
            f"karta hai — har lead ko 2 minute me call karke qualified banata hai. Aaj hi free Google "
            f"audit lijiye aur dekhiye aap kahan leads kho rahe hain."
        )

    page = {
        "niche": niche,
        "city": city,
        "slug": _slug(f"{label}-{city}"),
        "title": title,
        "h1": h1,
        "keyword": kw,
        "body": body,
        "faqs": faqs,
        "schema": _schema(title, city, faqs),
        "cta": {"text": "Free Google Audit lein", "url": "/audit"},
    }
    _track({k: page[k] for k in ("niche", "city", "slug", "title")})
    return {"ok": True, "page": page}


async def generate_batch(
    tier: str | None = None, cities: list[str] | None = None, limit: int = 8
) -> dict[str, Any]:
    """Multiple niche×city pages (LLM-heavy → default limit 8)."""
    try:
        from app.niches import NICHES
    except Exception:
        return {"ok": False, "reason": "NICHES unavailable", "pages": []}
    cities = cities or DEFAULT_CITIES[:3]
    keys = [
        k
        for k, c in NICHES.items()
        if isinstance(c, dict) and (not tier or str(c.get("tier", "")).upper() == tier.upper())
    ]
    pages, n = [], 0
    for k in keys:
        for city in cities:
            if n >= limit:
                break
            r = await generate_page(k, city)
            if r.get("ok"):
                pages.append(
                    {
                        "niche": k,
                        "city": city,
                        "slug": r["page"]["slug"],
                        "title": r["page"]["title"],
                    }
                )
                n += 1
        if n >= limit:
            break
    return {"ok": True, "count": len(pages), "pages": pages}


__all__ = ["generate_page", "generate_batch", "list_pages"]
