"""
LinkedIn Scraper
Scrapes business leads from LinkedIn (with proper rate limiting)
"""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency
    BeautifulSoup = None

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class LinkedInLead:
    """LinkedIn business/person lead"""

    name: str
    title: str
    company: str
    company_size: str | None
    industry: str | None
    location: str
    linkedin_url: str
    email: str | None
    phone: str | None
    connection_degree: int | None
    source: str = "linkedin"


class LinkedInScraper:
    """
    LinkedIn Lead Scraper using Sales Navigator API or web scraping

    WARNING: LinkedIn has strict scraping policies.
    Use their official API when possible or ensure compliance.
    """

    SEARCH_URL = "https://html.duckduckgo.com/html/"

    def __init__(self, use_sales_navigator: bool = False):
        self.use_sales_navigator = use_sales_navigator
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        }
        logger.info("💼 LinkedIn Scraper initialized")

    async def search_companies(
        self,
        industry: str,
        location: str,
        company_size: str | None = None,
        max_results: int = 100,
    ) -> list[LinkedInLead]:
        """
        Search for companies on LinkedIn

        Args:
            industry: Industry filter (e.g., "Real Estate", "Solar Energy")
            location: Location filter (e.g., "India", "Mumbai")
            company_size: Size filter (e.g., "11-50", "51-200")
            max_results: Maximum results to return

        Note: This requires LinkedIn API access or browser automation
        """
        logger.info(f"LinkedIn company search: {industry} in {location}")

        # For production, integrate with LinkedIn API
        # This is a placeholder implementation
        leads = []

        if self.use_sales_navigator:
            leads = await self._search_sales_navigator(
                industry=industry,
                location=location,
                company_size=company_size,
                max_results=max_results,
            )
        else:
            # Best-effort, key-less search via DuckDuckGo HTML endpoint.
            # Avoids needing a logged-in LinkedIn session or browser automation.
            leads = await self._search_via_duckduckgo(
                industry=industry, location=location, max_results=max_results
            )

        return leads

    @staticmethod
    def _clean_ddg_link(href: str) -> str:
        """Unwrap DuckDuckGo redirect links (//duckduckgo.com/l/?uddg=<real>)."""
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

    async def _search_via_duckduckgo(
        self, industry: str, location: str, max_results: int
    ) -> list[LinkedInLead]:
        """
        Best-effort LinkedIn company discovery using the free DuckDuckGo HTML
        endpoint. Searches "site:linkedin.com/company <industry> <location>" and
        parses organic results into LinkedInLead records.

        No API key or login required. This will not return private profile data
        (email/phone stay None) — only public company listing metadata.
        """
        if BeautifulSoup is None:
            logger.error("beautifulsoup4 not installed; cannot run LinkedIn search")
            return []

        query = f"site:linkedin.com/company {industry} {location}".strip()
        logger.info(f"LinkedIn DDG search: '{query}'")
        leads: list[LinkedInLead] = []

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=20.0,
                follow_redirects=True,
            ) as client:
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

                    # Only keep genuine LinkedIn company links
                    if "linkedin.com/company" not in link.lower():
                        continue

                    snip_el = r.select_one(".result__snippet")
                    snip_el.get_text(" ", strip=True) if snip_el else ""

                    # LinkedIn titles look like "Acme Solar | LinkedIn" — strip suffix
                    company = re.split(r"\s*[|\-–]\s*LinkedIn", title, flags=re.I)[0].strip()
                    company = company or title

                    leads.append(
                        LinkedInLead(
                            name="",  # contact name not available without profile drill-down
                            title="",
                            company=company,
                            company_size=None,
                            industry=industry,
                            location=location,
                            linkedin_url=link,
                            email=None,
                            phone=None,
                            connection_degree=None,
                        )
                    )

        except httpx.HTTPError as e:
            logger.error(f"LinkedIn DDG search HTTP error: {e}")
        except Exception as e:
            logger.error(f"LinkedIn DDG search failed: {e}")

        logger.info(f"LinkedIn search found {len(leads)} companies for '{industry}' in {location}")
        return leads

    async def _search_sales_navigator(
        self, industry: str, location: str, company_size: str | None, max_results: int
    ) -> list[LinkedInLead]:
        """
        Search using LinkedIn Sales Navigator API
        Requires Sales Navigator subscription and API access
        """
        # Placeholder - implement with actual LinkedIn API
        logger.warning("Sales Navigator API not configured")
        return []

    async def _search_with_browser(
        self, industry: str, location: str, max_results: int
    ) -> list[LinkedInLead]:
        """
        Search using browser automation
        Use with caution - respect LinkedIn's terms of service
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        leads = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Navigate to LinkedIn search
            # Note: This requires being logged in
            search_url = f"https://www.linkedin.com/search/results/companies/?keywords={industry}&origin=SWITCH_SEARCH_VERTICAL"

            await page.goto(search_url, timeout=60000)

            # Check if login is required
            if "login" in page.url:
                logger.warning("LinkedIn login required. Please provide session cookies.")
                await browser.close()
                return []

            # Wait for results
            await page.wait_for_selector(".search-results-container", timeout=30000)

            # Extract company listings
            companies = await page.query_selector_all(".entity-result")

            for company in companies[:max_results]:
                try:
                    name_elem = await company.query_selector(".entity-result__title-text a")
                    name = await name_elem.inner_text() if name_elem else ""
                    url = await name_elem.get_attribute("href") if name_elem else ""

                    subtitle_elem = await company.query_selector(".entity-result__primary-subtitle")
                    industry_text = await subtitle_elem.inner_text() if subtitle_elem else ""

                    location_elem = await company.query_selector(
                        ".entity-result__secondary-subtitle"
                    )
                    location_text = await location_elem.inner_text() if location_elem else ""

                    leads.append(
                        LinkedInLead(
                            name="",  # Contact name (would need to drill down)
                            title="",
                            company=name.strip(),
                            company_size=None,
                            industry=industry_text.strip(),
                            location=location_text.strip(),
                            linkedin_url=url,
                            email=None,
                            phone=None,
                            connection_degree=None,
                        )
                    )

                except Exception as e:
                    logger.debug(f"Error parsing company: {e}")

            await browser.close()

        return leads

    async def search_people(
        self,
        title: str,
        company: str | None = None,
        location: str | None = None,
        max_results: int = 50,
    ) -> list[LinkedInLead]:
        """
        Search for people on LinkedIn

        Args:
            title: Job title to search (e.g., "CEO", "Marketing Director")
            company: Company filter
            location: Location filter
            max_results: Maximum results
        """
        logger.info(f"LinkedIn people search: {title}")

        # Implement similar to _search_with_browser but for people
        # This requires LinkedIn login/API access

        return []

    async def enrich_lead(self, linkedin_url: str) -> dict[str, Any]:
        """
        Enrich a lead with additional information from their LinkedIn profile
        """
        # This would scrape the profile page for additional details
        # Email, phone (if visible), company details, etc.
        return {}


class LinkedInExporter:
    """
    Export LinkedIn search results
    Handles pagination and rate limiting
    """

    def __init__(self, scraper: LinkedInScraper):
        self.scraper = scraper

    async def export_to_csv(self, leads: list[LinkedInLead], filename: str):
        """Export leads to CSV file"""
        import csv

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "name",
                    "title",
                    "company",
                    "company_size",
                    "industry",
                    "location",
                    "linkedin_url",
                    "email",
                    "phone",
                ],
            )
            writer.writeheader()

            for lead in leads:
                writer.writerow(
                    {
                        "name": lead.name,
                        "title": lead.title,
                        "company": lead.company,
                        "company_size": lead.company_size or "",
                        "industry": lead.industry or "",
                        "location": lead.location,
                        "linkedin_url": lead.linkedin_url,
                        "email": lead.email or "",
                        "phone": lead.phone or "",
                    }
                )

        logger.info(f"Exported {len(leads)} leads to {filename}")
