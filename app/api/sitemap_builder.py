"""
sitemap_builder.py — Enriched XML sitemap generator (SEO: lastmod + changefreq + priority).

Usage (drop-in replacement for the inline block in main.py sitemap_xml()):

    from app.api.sitemap_builder import build_sitemap_xml
    xml = await build_sitemap_xml(base)
    return Response(content=xml, media_type="application/xml")

Priority / changefreq table (Google best-practices):
  Homepage          1.0  daily
  Lead magnets      0.9  weekly   (/audit /site-audit /demo /compare /geo-check)
  Revenue pages     0.8  weekly   (/pricing /start /voice-agent)
  Blog index        0.7  daily    (new articles added daily)
  Blog articles     0.6  monthly
  Mini-sites        0.5  monthly
  Niche×city pages  0.5  monthly
  Legal             0.3  yearly

lastmod = today's date (ISO 8601) — used as a proxy; dynamic content pages like
blog articles ideally carry their real publish date but that requires per-slug
lookup which would slow sitemap generation. Today-date is widely accepted.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from xml.sax.saxutils import escape as _xesc

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# Priority / changefreq config
# --------------------------------------------------------------------------- #
_TODAY = ""  # refreshed per-request via _today()


def _today() -> str:
    return date.today().isoformat()


_STATIC_URLS: list[tuple[str, str, str]] = [
    # (path, changefreq, priority)
    ("/", "daily", "1.0"),
    ("/audit", "weekly", "0.9"),
    ("/site-audit", "weekly", "0.9"),
    ("/demo", "weekly", "0.9"),
    ("/compare", "weekly", "0.9"),
    ("/geo-check", "weekly", "0.8"),
    ("/pricing", "weekly", "0.8"),
    # /start deliberately excluded — it's a pure alias serving the same file as
    # /pricing (its own canonical points to /pricing), sitemaps should only
    # list canonical/self-referencing URLs.
    ("/voice-agent", "weekly", "0.8"),
    ("/blog", "daily", "0.7"),
    ("/app/test-call", "monthly", "0.6"),
    ("/privacy", "yearly", "0.3"),
    ("/terms", "yearly", "0.3"),
    ("/refund", "yearly", "0.3"),
]


def _url_block(base: str, path: str, changefreq: str, priority: str, lastmod: str) -> str:
    """Single <url> block with all SEO signals."""
    loc = _xesc(base + path)
    return (
        "  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
    )


async def build_sitemap_xml(base: str) -> str:
    """Build full sitemap XML string with enriched SEO metadata.

    base: scheme+host, e.g. "https://leadsgenai.in" (no trailing slash).
    Returns complete <?xml ...> ... </urlset> string.
    """
    today = _today()
    blocks: list[str] = []

    # 1) Static pages with priority/changefreq
    for path, freq, pri in _STATIC_URLS:
        blocks.append(_url_block(base, path, freq, pri, today))

    # 2) Blog articles — real publish date if available, else today
    try:
        from app.marketing import seo_blog

        for slug in seo_blog.all_slugs():
            if not slug:
                continue
            # Try to get article publish date for accurate lastmod
            pub_date = today
            try:
                art = seo_blog.get_article(slug)
                raw_date = (art or {}).get("published_at") or (art or {}).get("created_at") or ""
                if raw_date:
                    # Accept ISO string; strip time portion
                    pub_date = str(raw_date)[:10]
            except Exception:
                pass
            blocks.append(_url_block(base, f"/blog/{slug}", "monthly", "0.6", pub_date))
    except Exception as e:
        logger.debug(f"[sitemap_builder] blog slugs skipped: {e}")

    # 3) Per-client mini-sites (active only)
    try:
        from app.marketing.clients_store import list_clients

        for c in list_clients(status="active"):
            slug = str(c.get("slug") or "").strip()
            if slug:
                blocks.append(_url_block(base, f"/b/{slug}", "monthly", "0.5", today))
    except Exception as e:
        logger.debug(f"[sitemap_builder] mini-site slugs skipped: {e}")

    # 4) Niche × city SEO landing pages
    _SITEMAP_NICHES = [
        "real-estate",
        "solar",
        "coaching",
        "dental",
        "insurance",
        "home-loans",
        "interior-design",
        "restaurant",
    ]
    _SITEMAP_CITIES = ["india", "mumbai", "delhi", "bangalore"]
    for niche in _SITEMAP_NICHES:
        for city in _SITEMAP_CITIES:
            blocks.append(_url_block(base, f"/for/{niche}-in-{city}", "monthly", "0.5", today))

    items = "\n".join(blocks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '        xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9'
        ' http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">\n'
        f"{items}\n"
        "</urlset>\n"
    )


__all__ = ["build_sitemap_xml"]
