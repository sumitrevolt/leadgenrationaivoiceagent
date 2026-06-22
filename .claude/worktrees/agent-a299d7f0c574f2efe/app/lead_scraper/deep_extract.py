"""Deep web data extraction for marketing — **Crawl4AI** with a trafilatura fallback.

Crawl4AI is the LLM-friendly crawler: it renders a page and returns clean Markdown
with boilerplate/noise stripped (BM25 filtering) — ideal for competitor analysis and
business enrichment (pull a prospect's real services / about / offers). If Crawl4AI
(or its headless browser) isn't set up, this transparently falls back to a plain
httpx fetch + trafilatura main-text extraction, so callers always get *something*.

Both paths are defensive and never raise. Returns a dict:
  {"ok": bool, "url": str, "markdown": str, "text": str, "emails": [...], "phones": [...], "engine": str}

Crawl4AI is heavier (needs a one-time `crawl4ai-setup` to install Chromium); it is
OPTIONAL and OFF unless installed. The trafilatura fallback covers the common case.

Use:
  from app.lead_scraper.deep_extract import extract_url
  data = await extract_url("https://competitor.example.in")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _empty(url: str) -> dict[str, Any]:
    return {
        "ok": False,
        "url": url,
        "markdown": "",
        "text": "",
        "emails": [],
        "phones": [],
        "engine": "none",
    }


async def _via_crawl4ai(url: str) -> dict[str, Any] | None:
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
        if not getattr(result, "success", True):
            return None
        md = getattr(result, "markdown", "") or ""
        # newer crawl4ai returns a MarkdownGenerationResult object
        md = getattr(md, "raw_markdown", None) or (md if isinstance(md, str) else str(md))
        html = getattr(result, "html", "") or ""
        from app.lead_scraper.web_extract import find_contacts

        c = find_contacts(html or md)
        return {
            "ok": True,
            "url": url,
            "markdown": md.strip(),
            "text": md.strip(),
            "emails": c["emails"],
            "phones": c["phones"],
            "engine": "crawl4ai",
        }
    except Exception as exc:
        logger.info("deep_extract crawl4ai unavailable (%s) — falling back", exc)
        return None


async def _via_trafilatura(url: str) -> dict[str, Any]:
    try:
        import httpx

        from app.lead_scraper.web_extract import clean_text, find_contacts

        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(url, headers={"User-Agent": _UA})
        if resp.status_code != 200:
            return _empty(url)
        html = resp.text
        text = clean_text(html)
        c = find_contacts(html)
        return {
            "ok": bool(text),
            "url": url,
            "markdown": text,
            "text": text,
            "emails": c["emails"],
            "phones": c["phones"],
            "engine": "trafilatura",
        }
    except Exception as exc:
        logger.info("deep_extract trafilatura fallback failed (%s)", exc)
        return _empty(url)


async def extract_url(url: str) -> dict[str, Any]:
    """Deep-extract a page → markdown + contacts. Crawl4AI if present, else trafilatura."""
    if not (url or "").strip():
        return _empty(url)
    via = await _via_crawl4ai(url)
    if via and via.get("ok"):
        return via
    return await _via_trafilatura(url)


__all__ = ["extract_url"]
