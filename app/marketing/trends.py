"""Trend ingestion — Google Trends RSS (free, no-key, India works) → content angles.

weather_angle.py jaisa hi pattern: defensive, 1hr cache, never-raise, static fallback.
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RSS_URL = "https://trends.google.com/trending/rss?geo={geo}"
_CACHE: dict[str, tuple[float, list[str]]] = {}
_TTL = 3600

_FALLBACK_ANGLES = [
    "Seasonal offer — abhi ka mausam/tyohar pakdo",
    "Customer success story — real result dikhao",
    "Quick tip — niche ka ek kaam-ka gyaan",
]


def trending(geo: str = "IN", limit: int = 10) -> list[str]:
    """Aaj ke trending search topics (cached 1hr). Fail = empty list."""
    geo = (geo or "IN").upper()
    now = time.time()
    hit = _CACHE.get(geo)
    if hit and now - hit[0] < _TTL:
        return hit[1][: max(1, limit)]
    titles: list[str] = []
    try:
        import httpx

        r = httpx.get(_RSS_URL.format(geo=geo), timeout=6, follow_redirects=True)
        if r.status_code == 200:
            titles = parse_rss_titles(r.text)
    except Exception as e:
        logger.debug(f"trends fetch failed: {e}")
    if titles:
        _CACHE[geo] = (now, titles)
    return titles[: max(1, limit)]


def parse_rss_titles(xml: str) -> list[str]:
    """RSS <item><title> nikaalo — koi xml dep nahi, regex enough."""
    items = re.findall(r"<item>(.*?)</item>", xml or "", re.S)
    out = []
    for it in items:
        m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if m and m.group(1).strip():
            out.append(m.group(1).strip()[:100])
    return out


async def trend_angles(niche: str, business_name: str = "", n: int = 3) -> dict[str, Any]:
    """Trending topics → niche-relevant Hinglish marketing angles (free-LLM, fallback static)."""
    topics = trending("IN", 10)
    angles: list[str] = []
    provider = "fallback"
    if topics:
        try:
            from app.voice_agent import free_ai

            text, provider = await free_ai.chat(
                "Tu ek Indian local-business marketing expert hai. Hinglish me reply.",
                [
                    {
                        "role": "user",
                        "content": (
                            f"Aaj India me trending: {', '.join(topics[:8])}. "
                            f"'{niche}' business ({business_name or 'local'}) ke liye {n} short "
                            "social-post angles do jo kisi trend se connect ho. Ek line each, numbered."
                        ),
                    }
                ],
                max_tokens=200,
            )
            angles = [
                re.sub(r"^\s*\d+[\).\-]?\s*", "", ln).strip()
                for ln in (text or "").splitlines()
                if ln.strip() and any(c.isalpha() for c in ln)
            ][:n]
        except Exception as e:
            logger.debug(f"trend_angles llm skip: {e}")
    if not angles:
        angles = _FALLBACK_ANGLES[:n]
        provider = "fallback"
    return {"niche": niche, "trending": topics, "angles": angles, "provider": provider}
