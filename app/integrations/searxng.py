"""Self-hosted SearXNG meta-search client (FREE unlimited web search).

Paid search APIs (Brave $5/mo ≈ 1k queries) ki jagah apna SearXNG container —
70+ engines aggregate, JSON API, zero per-query cost. `deploy/compose/docker-compose.tools.yml`
me `searxng` service (app ke SAME docker network pe).

GATED: `SEARXNG_URL` env (e.g. http://searxng:8080). Unset = inert (callers
gracefully fallback — lead_harvester Brave key pe, baaki skip). NEVER raises.

Use:
    from app.integrations import searxng
    results = await searxng.search("solar installer pune contact")  # [{title,url,content}]
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT = 12.0


def base_url() -> str:
    """Configured SearXNG base URL ('' = disabled)."""
    return os.environ.get("SEARXNG_URL", "").strip().rstrip("/")


def enabled() -> bool:
    return bool(base_url())


async def search(
    query: str,
    count: int = 10,
    categories: str = "general",
    language: str = "en-IN",
) -> list[dict[str, Any]]:
    """Search via self-hosted SearXNG. Returns [{title, url, content, engine}].

    Empty list on any failure / when disabled — caller decides fallback.
    """
    url = base_url()
    q = (query or "").strip()
    if not url or not q:
        return []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(
                f"{url}/search",
                params={
                    "q": q,
                    "format": "json",
                    "categories": categories,
                    "language": language,
                    "safesearch": 1,
                },
            )
            if r.status_code != 200:
                logger.info("searxng %s for %r", r.status_code, q[:60])
                return []
            results = r.json().get("results") or []
            out: list[dict[str, Any]] = []
            for item in results[: max(1, min(int(count), 30))]:
                out.append(
                    {
                        "title": str(item.get("title") or "")[:200],
                        "url": str(item.get("url") or ""),
                        "content": str(item.get("content") or "")[:400],
                        "engine": str(item.get("engine") or ""),
                    }
                )
            return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("searxng search failed: %s", exc)
        return []


async def healthy() -> bool:
    """Quick liveness probe (infra monitors ke liye)."""
    url = base_url()
    if not url:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{url}/healthz")
            return r.status_code == 200
    except Exception:
        return False


__all__ = ["search", "enabled", "base_url", "healthy"]
