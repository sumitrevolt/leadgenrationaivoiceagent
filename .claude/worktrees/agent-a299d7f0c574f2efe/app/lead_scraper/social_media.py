"""
Social Media Scraper
Public business pages se leads — Instagram / Facebook (best-effort, key-less).

REALITY CHECK (important):
- Instagram aur Facebook login-wall ke peeche hain. Bina official API ya
  paid service (Apify / Bright Data) ke 100% reliable scraping mushkil hai.
- Yeh module "best-effort" hai: web search se public IG/FB business pages
  dhoondhta hai, phir un public pages se bio/contact (phone/email) nikalta hai.
- Reliable, scale-ready data ke liye:
    * Instagram/Facebook -> Meta Graph API (business pages, free with app review)
    * Ya Apify Instagram Scraper (paid, ~$0.x per 1k)
  Iska interface same rakha gaya hai taaki baad me swap aasaan ho.
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

PHONE_RE = re.compile(r"(?:(?:\+?91[\-\s]?)|0)?([6-9]\d{4}[\-\s]?\d{5})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


@dataclass
class SocialMediaLead:
    """A business lead discovered from a public social media page."""

    name: str
    handle: str | None
    platform: str  # "instagram" | "facebook"
    profile_url: str
    phone: str | None
    email: str | None
    bio: str
    city: str
    category: str
    source: str = "social_media"
    raw_data: dict[str, Any] = field(default_factory=dict)


class SocialMediaScraper:
    """
    Finds public Instagram / Facebook business pages for a niche + city
    and extracts whatever contact info is publicly visible.
    """

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    PLATFORM_DOMAINS = {
        "instagram": "instagram.com",
        "facebook": "facebook.com",
    }

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
        logger.info("📱 Social Media Scraper initialized")

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

    async def search_businesses(
        self,
        category: str,
        city: str,
        platforms: list[str] | None = None,
        max_results: int = 20,
        enrich: bool = True,
    ) -> list[SocialMediaLead]:
        """
        Find public social pages for a category + city.

        Args:
            category: e.g. "interior designer", "dental clinic"
            city: e.g. "Pune"
            platforms: subset of ["instagram", "facebook"] (default both)
            max_results: results per platform
            enrich: fetch each profile page for phone/email in bio
        """
        platforms = platforms or ["instagram", "facebook"]
        leads: list[SocialMediaLead] = []

        for platform in platforms:
            domain = self.PLATFORM_DOMAINS.get(platform)
            if not domain:
                continue
            query = f"site:{domain} {category} {city}"
            logger.info(f"Social search: '{query}'")
            try:
                async with self._client() as client:
                    resp = await client.post(
                        self.SEARCH_URL,
                        data={"q": query, "kl": "in-en"},
                    )
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for r in soup.select(".result")[:max_results]:
                        a = r.select_one(".result__a")
                        if not a:
                            continue
                        link = self._clean_ddg_link(a.get("href", ""))
                        if domain not in link:
                            continue
                        title = a.get_text(strip=True)
                        snip_el = r.select_one(".result__snippet")
                        snippet = snip_el.get_text(" ", strip=True) if snip_el else ""
                        handle = self._extract_handle(link, platform)

                        leads.append(
                            SocialMediaLead(
                                name=self._clean_name(title, platform),
                                handle=handle,
                                platform=platform,
                                profile_url=link,
                                phone=self._first_phone(f"{title} {snippet}"),
                                email=self._first_email(snippet),
                                bio=snippet,
                                city=city,
                                category=category,
                                raw_data={"query": query},
                            )
                        )
            except httpx.HTTPError as e:
                logger.error(f"Social search HTTP error ({platform}): {e}")
            except Exception as e:
                logger.error(f"Social search failed ({platform}): {e}")

        if enrich:
            await self._enrich_leads(leads)

        logger.info(f"Social media found {len(leads)} leads for '{category}' in {city}")
        return leads

    async def _enrich_leads(self, leads: list[SocialMediaLead]) -> None:
        sem = asyncio.Semaphore(4)

        async def fetch(lead: SocialMediaLead):
            if lead.phone and lead.email:
                return
            async with sem:
                try:
                    async with self._client() as client:
                        resp = await client.get(lead.profile_url)
                        if resp.status_code != 200:
                            return
                        # public pages me bio aksar og:description / meta me hota hai
                        soup = BeautifulSoup(resp.text, "html.parser")
                        meta = soup.find("meta", property="og:description")
                        text = (meta.get("content", "") if meta else "") + " " + soup.get_text(" ")
                        if not lead.phone:
                            lead.phone = self._first_phone(text)
                        if not lead.email:
                            lead.email = self._first_email(text)
                except Exception as e:
                    logger.debug(f"Social enrich failed for {lead.profile_url}: {e}")

        await asyncio.gather(*(fetch(l) for l in leads), return_exceptions=True)

    @staticmethod
    def _extract_handle(url: str, platform: str) -> str | None:
        try:
            path = urlparse(url).path.strip("/")
            if not path:
                return None
            handle = path.split("/")[0]
            return f"@{handle}" if platform == "instagram" else handle
        except Exception:
            return None

    @staticmethod
    def _clean_name(title: str, platform: str) -> str:
        # "Name (@handle) • Instagram photos..." -> "Name"
        title = re.split(r"[(•|]", title)[0]
        title = title.replace("Instagram", "").replace("Facebook", "")
        return title.strip(" -–·") or title.strip()

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
        if any(x in email.lower() for x in ("example.com", ".png", ".jpg", "sentry")):
            return None
        return email


__all__ = ["SocialMediaScraper", "SocialMediaLead"]
