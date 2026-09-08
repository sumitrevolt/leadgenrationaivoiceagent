"""Trending hashtag research + best-time-to-post (niche + city). free_ai + template.

Hashtag discovery + posting-time tips are standard social-marketing features. free_ai
generates a relevant mix (popular + niche + local); template fallback never-empty.

research(niche, city, count) -> {hashtags[], best_times[], niche, city}
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# India local-business posting windows (engagement-backed general guidance)
_BEST_TIMES = [
    "12:00-13:00 (lunch scroll)",
    "19:00-21:00 (evening peak)",
    "Sun 11:00-13:00 (weekend)",
]


def _template_tags(niche: str, city: str) -> list[str]:
    base = niche.replace("_", "")
    tags = [
        f"#{base}",
        "#India",
        "#smallbusiness",
        "#supportlocal",
        "#localbusiness",
        "#offer",
        "#sale",
        "#trending",
        "#instagood",
        "#explore",
        "#shoplocal",
    ]
    if city:
        c = city.replace(" ", "")
        tags += [f"#{c}", f"#{c}{base}", f"#{c}business"]
    return tags


async def research(niche: str, city: str = "", count: int = 15) -> dict:
    niche = (niche or "general").strip()
    city = (city or "").strip()
    tags: list[str] = []
    try:
        from app.voice_agent import free_ai

        reply, _ = await free_ai.chat(
            system="Generate relevant trending Instagram hashtags (space-separated, each starting with #) "
            "for the given Indian local-business niche + city. Mix popular + niche + local. ONLY hashtags.",
            messages=[
                {
                    "role": "user",
                    "content": f"Niche: {niche}\nCity: {city or 'India'}\nHow many: {count}",
                }
            ],
            max_tokens=120,
            temperature=0.6,
        )
        tags = [w.strip() for w in (reply or "").split() if w.strip().startswith("#")][
            : max(1, count)
        ]
    except Exception as e:
        logger.info("hashtags err: %s", e)

    if not tags:
        tags = _template_tags(niche, city)[: max(1, count)]
    return {"hashtags": tags, "best_times": _BEST_TIMES, "niche": niche, "city": city}


__all__ = ["research"]
