"""content_distribute.py — push READY content to legal SEO channels (IndexNow).

Auto-created blog/landing URLs ko IndexNow (Bing/Yandex) pe instant-index ping
karta hai. Meta/FB/IG/GBP = external-approval-blocked (un par auto-post NAHI;
draft hi rehte). Pure wrapper — indexnow.py REUSE, re-implement nahi.

DEFENSIVE: koi function KABHI raise nahi karta — failure = graceful skip.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def submit_indexnow(urls: list[str]) -> dict[str, Any]:
    """Naye blog/landing URLs ko IndexNow (Bing/Yandex) pe ping karo — SEO ke
    liye instant index. Reuse indexnow.submit_urls (same-host gate, dedupe key
    auto-gen). Network/host fail = {"ok": False}. NEVER raises.

    Note: yeh DIRECT submit hai (any-time, koi flag nahi — pure SEO ping, free,
    legal). Scheduled NAYA-only sweep ke liye indexnow.submit_sitemap_if_enabled
    (gated INDEXNOW) blog job me already wired hai.
    """
    if not urls:
        return {"ok": False, "error": "no urls"}
    try:
        from app.marketing import indexnow

        return await indexnow.submit_urls(list(urls))
    except Exception as e:
        logger.warning(f"[content_distribute] submit_indexnow failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


async def submit_new_blog_urls(limit: int = 50) -> dict[str, Any]:
    """Convenience: recent published blog slugs ko /blog/{slug} URLs me badal ke
    IndexNow pe submit karo. Reuse seo_blog.list_articles. NEVER raises."""
    try:
        from app.marketing import seo_blog

        rows = seo_blog.list_articles(limit=limit) or []
        urls = [f"/blog/{r.get('slug')}" for r in rows if r.get("slug")]
        if not urls:
            return {"ok": False, "error": "no blog urls"}
        return await submit_indexnow(urls)
    except Exception as e:
        logger.warning(f"[content_distribute] submit_new_blog_urls failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


__all__ = [
    "submit_indexnow",
    "submit_new_blog_urls",
]
