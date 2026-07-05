"""
LinkedIn Scraper — TOMBSTONED BY POLICY (ToS-blocked, KABHI implement NAHI karna)
=================================================================================

STATUS: permanently INERT. LinkedIn auto-scraping (web/DDG/browser/Sales
Navigator/API) is a hard project invariant violation — see CLAUDE.md
"Ban-safety" (ToS-blocked auto-scrape justdial/indiamart/sulekha/linkedin/fb/
insta REFUSED). Manual CSV import hi eklauta legal path hai.

WHY THIS FILE STILL EXISTS (API-surface compat):
`app/lead_scraper/scraper_manager.py` isko lazily instantiate karta hai
(`.linkedin` property) aur ye class-shape (`LinkedInScraper`, `LinkedInLead`,
`LinkedInExporter`) legacy imports expose karta hai. Isliye class/method surface
bilkul waisa hi rakha hai — bas har scraping method turant EMPTY return karta
hai, koi network/browser call NAHI hoti.

DO NOT re-implement search/enrich. Koi bhi "for production integrate LinkedIn
API" wala kaam yahan add karna FORBIDDEN hai. Ref: docs/GAP_REGISTER_2026_07_05.md
R-26, CLAUDE.md §5 ban-safety.
"""

from dataclasses import dataclass
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class LinkedInLead:
    """LinkedIn business/person lead (shape kept for import compat only)."""

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
    LinkedIn Lead Scraper — TOMBSTONE (ToS-blocked, permanently inert).

    Every search/enrich method returns empty immediately. LinkedIn scraping is a
    hard invariant violation (CLAUDE.md ban-safety) — kabhi implement NAHI karna;
    manual CSV import hi legal path hai. Class surface sirf backward-compat imports
    (scraper_manager) ke liye rakha hai.
    """

    def __init__(self, use_sales_navigator: bool = False):
        # Signature preserved for API compat; the flag is inert (no scraping path).
        self.use_sales_navigator = use_sales_navigator
        logger.info(
            "LinkedIn source is TOMBSTONED-by-policy (ToS-blocked auto-scrape "
            "refused; manual CSV import only) — returns no leads."
        )

    async def search_companies(
        self,
        industry: str,
        location: str,
        company_size: str | None = None,
        max_results: int = 100,
    ) -> list[LinkedInLead]:
        """
        TOMBSTONE — always returns []. LinkedIn company scraping is ToS-blocked
        (CLAUDE.md ban-safety invariant); kabhi implement NAHI karna, manual CSV
        import hi legal path hai. Ref: GAP_REGISTER R-26.
        """
        return []

    async def search_people(
        self,
        title: str,
        company: str | None = None,
        location: str | None = None,
        max_results: int = 50,
    ) -> list[LinkedInLead]:
        """
        TOMBSTONE — always returns []. LinkedIn people scraping is ToS-blocked
        (CLAUDE.md ban-safety invariant); kabhi implement NAHI karna, manual CSV
        import hi legal path hai. Ref: GAP_REGISTER R-26.
        """
        return []

    async def enrich_lead(self, linkedin_url: str) -> dict[str, Any]:
        """
        TOMBSTONE — always returns {}. LinkedIn profile enrichment/scraping is
        ToS-blocked (CLAUDE.md ban-safety invariant); kabhi implement NAHI karna,
        manual CSV import hi legal path hai. Ref: GAP_REGISTER R-26.
        """
        return {}


class LinkedInExporter:
    """
    Export helper for LinkedIn search results (API-surface compat).

    Note: the scraper is tombstoned (always empty), so in practice there is
    nothing to export. This is a plain local-CSV writer with no LinkedIn/network
    access — kept only so legacy imports don't break.
    """

    def __init__(self, scraper: LinkedInScraper):
        self.scraper = scraper

    async def export_to_csv(self, leads: list[LinkedInLead], filename: str):
        """Export the given leads to a local CSV file (no network access)."""
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
