"""
Web Search Scraper
Free, key-less business lead discovery via web search (DuckDuckGo HTML endpoint).

Niche + city query daalo -> web par jo businesses milte hain unke
name / website / phone / email extract karta hai. Koi API key nahi chahiye.

Note: DuckDuckGo ka HTML endpoint (https://html.duckduckgo.com/html/) free hai
aur rate-limit lenient hai. Agar zyada volume chahiye to Google Custom Search
API (100 free/day) ya SerpAPI plug kar sakte ho — interface same rahega.
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Indian phone numbers: +91 / 0 prefix optional, 10 digits starting 6-9
PHONE_RE = re.compile(r"(?:(?:\+?91[\-\s]?)|0)?([6-9]\d{4}[\-\s]?\d{5})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


@dataclass
class WebSearchLead:
    """A business lead discovered via web search."""

    name: str
    website: str | None
    phone: str | None
    email: str | None
    snippet: str
    city: str
    category: str
    source_url: str
    source: str = "web_search"
    raw_data: dict[str, Any] = field(default_factory=dict)


class WebSearchScraper:
    """
    Discovers business leads from open web search results.

    Pipeline:
      1. Query DuckDuckGo HTML for "<category> <city> contact"
      2. Collect organic result links + titles + snippets
      3. Optionally fetch each business website and extract phone/email
    """

    SEARCH_URL = "https://html.duckduckgo.com/html/"

    def __init__(self):
        self.use_proxy = getattr(settings, "use_proxy", False)
        self.proxy_url = getattr(settings, "proxy_url", None)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        }
        # domains jo business websites nahi hote — skip
        self.skip_domains = {
            "facebook.com",
            "instagram.com",
            "linkedin.com",
            "twitter.com",
            "youtube.com",
            "wikipedia.org",
            "justdial.com",
            "indiamart.com",
            "duckduckgo.com",
            "google.com",
            "amazon.in",
            "flipkart.com",
            "quora.com",
            "reddit.com",
            "tripadvisor.com",
        }
        logger.info("🌐 Web Search Scraper initialized")

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "headers": self.headers,
            "timeout": 20.0,
            "follow_redirects": True,
        }
        if self.use_proxy and self.proxy_url:
            kwargs["proxies"] = self.proxy_url
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def _clean_ddg_link(href: str) -> str:
        """DuckDuckGo wraps links like //duckduckgo.com/l/?uddg=<real>. Unwrap it."""
        if not href:
            return ""
        if "uddg=" in href:
            try:
                q = parse_qs(urlparse(href).query)
                if "uddg" in q:
                    return unquote(q["uddg"][0])
            except Exception:
                pass
        if href.startswith("//"):
            return "https:" + href
        return href

    def _domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            return ""

    async def search_businesses(
        self,
        category: str,
        city: str,
        max_results: int = 30,
        enrich: bool = True,
    ) -> list[WebSearchLead]:
        """
        Search the web for businesses in a category + city.

        Args:
            category: e.g. "solar panel installers", "dental implant clinic"
            city: e.g. "Mumbai"
            max_results: how many search results to process
            enrich: if True, fetch each website to pull phone/email
        """
        query = f"{category} in {city} contact phone number"
        logger.info(f"Web search: '{query}'")
        leads: list[WebSearchLead] = []

        try:
            async with self._client() as client:
                resp = await client.post(
                    self.SEARCH_URL,
                    data={"q": query, "kl": "in-en"},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                results = soup.select(".result")[:max_results]

                for r in results:
                    a = r.select_one(".result__a")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    link = self._clean_ddg_link(a.get("href", ""))
                    if not link or self._domain(link) in self.skip_domains:
                        continue
                    snip_el = r.select_one(".result__snippet")
                    snippet = snip_el.get_text(" ", strip=True) if snip_el else ""

                    phone = self._first_phone(f"{title} {snippet}")
                    email = self._first_email(snippet)

                    leads.append(
                        WebSearchLead(
                            name=title,
                            website=link,
                            phone=phone,
                            email=email,
                            snippet=snippet,
                            city=city,
                            category=category,
                            source_url=link,
                            raw_data={"query": query},
                        )
                    )

            if enrich:
                await self._enrich_leads(leads)

        except httpx.HTTPError as e:
            logger.error(f"Web search HTTP error: {e}")
        except Exception as e:
            logger.error(f"Web search failed: {e}")

        logger.info(f"Web search found {len(leads)} leads for '{category}' in {city}")
        return leads

    async def _enrich_leads(self, leads: list[WebSearchLead]) -> None:
        """Fetch each business website to fill in missing phone/email."""
        sem = asyncio.Semaphore(5)

        async def fetch(lead: WebSearchLead):
            if lead.phone and lead.email:
                return
            async with sem:
                try:
                    async with self._client() as client:
                        resp = await client.get(lead.website)
                        if resp.status_code != 200:
                            return
                        text = BeautifulSoup(resp.text, "html.parser").get_text(" ")
                        if not lead.phone:
                            lead.phone = self._first_phone(text)
                        if not lead.email:
                            lead.email = self._first_email(text)
                except Exception as e:
                    logger.debug(f"Enrich failed for {lead.website}: {e}")

        await asyncio.gather(*(fetch(l) for l in leads), return_exceptions=True)

    @staticmethod
    def _first_phone(text: str) -> str | None:
        m = PHONE_RE.search(text or "")
        if not m:
            return None
        digits = re.sub(r"\D", "", m.group(1))
        return digits[-10:] if len(digits) >= 10 else None

    @staticmethod
    def _first_email(text: str) -> str | None:
        m = EMAIL_RE.search(text or "")
        if not m:
            return None
        email = m.group(0)
        # generic / junk emails skip
        if any(x in email.lower() for x in ("example.com", "sentry", "wix.com", ".png", ".jpg")):
            return None
        return email


__all__ = ["WebSearchScraper", "WebSearchLead"]
