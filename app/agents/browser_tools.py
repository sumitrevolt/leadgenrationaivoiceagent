"""Browser tools — headless render/extract for deeper lead enrichment (Hermes parity).

Playwright OPTIONAL dependency. Flag `BROWSER_TOOLS=1` default OFF (INERT) — bina
flag ke fetch_rendered/extract seedha {"ok":False,"error":"disabled"} return karte.
Flag ON par bhi agar playwright installed nahi → graceful
{"ok":False,"error":"playwright_not_installed"} (kabhi raise nahi).

USE-CASE: JS-rendered business pages se enrichment (title/visible text) jab plain
HTTP fetch khaali aata. Reviews/phone/owner-name jaisa public-page data hi target.

ToS / LEGAL NOTE: sirf enrichment ke liye — robots.txt + site ToS RESPECT karo.
ToS-blocked directories (justdial/indiamart/linkedin/fb/insta) yahan se KABHI scrape
mat karo (manual CSV import hi unka path — CLAUDE.md policy). No bulk crawling.

Import-safe (playwright import lazy), kabhi raise nahi. Flag: BROWSER_TOOLS=1
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_TEXT_CAP = 8000  # rendered text truncate (response/token safety)
_MAX_TIMEOUT_S = 60


def enabled() -> bool:
    """Default OFF — bina iske browser tools inert (kuch launch nahi hota)."""
    return (os.getenv("BROWSER_TOOLS") or "").strip().lower() in ("1", "true", "yes")


def _timeout_ms(timeout_s: int) -> int:
    try:
        return max(1, min(int(timeout_s or 20), _MAX_TIMEOUT_S)) * 1000
    except Exception:
        return 20000


def _url_is_safe(url: str) -> bool:
    """SSRF guard — block a headless nav to internal/private/metadata hosts before
    launching the browser (defense-in-depth; these tools are super-admin +
    BROWSER_TOOLS-gated, but a compromised admin could otherwise pivot to
    127.0.0.1:6333 Qdrant / 169.254.169.254 metadata / the Docker net). http(s)
    only; hostname MUST resolve to a PUBLIC IP. Fail-CLOSED (unresolvable/unknown
    => unsafe). NOTE: a headless browser can still follow a REDIRECT to a private
    IP — full coverage needs route interception; this closes the direct case."""
    try:
        import ipaddress
        import socket
        from urllib.parse import urlparse

        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        port = p.port or (443 if p.scheme == "https" else 80)
        infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False  # fail-closed: unresolvable / parse error => treat as unsafe


async def fetch_rendered(url: str, timeout_s: int = 20) -> dict[str, Any]:
    """JS-rendered page fetch → {ok, url, title, text}.

    GATED: enabled() False → {"ok":False,"error":"disabled"}. playwright missing →
    {"ok":False,"error":"playwright_not_installed","hint":"pip install playwright"}.
    Browser hamesha finally me close. Never-raise.
    """
    url = (url or "").strip()
    if not enabled():
        return {"ok": False, "error": "disabled"}
    if not url:
        return {"ok": False, "error": "empty_url"}
    if not _url_is_safe(url):
        return {"ok": False, "error": "blocked_unsafe_url"}
    try:
        from playwright.async_api import async_playwright  # lazy optional dep
    except ImportError:
        return {
            "ok": False,
            "error": "playwright_not_installed",
            "hint": "pip install playwright",
        }

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=_timeout_ms(timeout_s))
                title = await page.title()
                text = await page.inner_text("body")
                return {
                    "ok": True,
                    "url": url,
                    "title": (title or "")[:300],
                    "text": (text or "")[:_TEXT_CAP],
                }
            finally:
                if browser is not None:
                    await browser.close()
    except Exception as e:  # never-raise (timeout / nav error / launch fail)
        logger.debug(f"browser_tools.fetch_rendered failed for {url}: {e}")
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:200], "url": url}


async def extract(url: str, selector: str, timeout_s: int = 20) -> dict[str, Any]:
    """Ek CSS `selector` ka rendered text nikaalo → {ok, url, selector, text, count}.

    GATED + playwright-optional (same as fetch_rendered). Selector miss → ok with
    empty text (count 0), not an error. Never-raise.
    """
    url = (url or "").strip()
    selector = (selector or "").strip()
    if not enabled():
        return {"ok": False, "error": "disabled"}
    if not url or not selector:
        return {"ok": False, "error": "empty_url_or_selector"}
    if not _url_is_safe(url):
        return {"ok": False, "error": "blocked_unsafe_url"}
    try:
        from playwright.async_api import async_playwright  # lazy optional dep
    except ImportError:
        return {
            "ok": False,
            "error": "playwright_not_installed",
            "hint": "pip install playwright",
        }

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=_timeout_ms(timeout_s))
                nodes = await page.query_selector_all(selector)
                parts: list[str] = []
                for n in nodes:
                    try:
                        t = await n.inner_text()
                        if t and t.strip():
                            parts.append(t.strip())
                    except Exception:
                        continue
                joined = "\n".join(parts)[:_TEXT_CAP]
                return {
                    "ok": True,
                    "url": url,
                    "selector": selector,
                    "text": joined,
                    "count": len(parts),
                }
            finally:
                if browser is not None:
                    await browser.close()
    except Exception as e:  # never-raise
        logger.debug(f"browser_tools.extract failed for {url} [{selector}]: {e}")
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:200], "url": url, "selector": selector}


__all__ = ["enabled", "fetch_rendered", "extract"]
