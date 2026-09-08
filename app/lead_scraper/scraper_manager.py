"""
Unified Lead Scraper Manager
Coordinates multiple scraping sources (Google Maps, IndiaMart, JustDial,
LinkedIn, Web Search, Social Media).
"""

from __future__ import annotations  # Lead-class type hints stay lazy (string annotations)

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.utils.logger import setup_logger
from app.utils.phone_validator import PhoneValidator

if TYPE_CHECKING:
    # Type-only imports — kept out of runtime to preserve the lazy cold-start
    # design (heavy source scrapers stay un-imported until a @property needs them).
    from app.lead_scraper.google_maps import BusinessLead
    from app.lead_scraper.indiamart import IndiaMartLead
    from app.lead_scraper.justdial import JustDialLead
    from app.lead_scraper.social_media import SocialMediaLead
    from app.lead_scraper.web_search import WebSearchLead

# NOTE: the heavy source scrapers (google_maps/indiamart/justdial/linkedin/web_search/
# social_media) are imported LAZILY inside the per-source @property accessors below — so
# importing OR constructing LeadScraperManager never pulls their deps (faster cold-start;
# contract guarded by tests/test_scraper_lazy_import.py). The *Lead dataclasses are used
# only as type annotations (duck-typed at runtime), so __future__ annotations keeps them
# unimported.

logger = setup_logger(__name__)


@dataclass
class UnifiedLead:
    """Unified lead format from all sources"""

    id: str
    company_name: str
    contact_name: str | None
    phone: str | None
    phone_verified: bool
    email: str | None
    address: str
    city: str
    state: str
    country: str
    category: str
    source: str
    source_url: str
    rating: float | None
    verified: bool
    scraped_at: datetime
    raw_data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scraped_at"] = self.scraped_at.isoformat()
        return data


class LeadScraperManager:
    """
    Unified manager for all lead scraping sources

    Provides:
    - Multi-source scraping
    - Deduplication
    - Phone validation
    - Lead scoring
    - Export capabilities
    """

    # Niche to search query mapping
    NICHE_QUERIES = {
        "real_estate": {
            "google_maps": ["real estate developers", "property dealers", "builders"],
            "indiamart": ["real estate developers", "construction company"],
            "justdial": ["real estate agents", "builders", "property dealers"],
        },
        "solar": {
            "google_maps": ["solar panel installers", "solar energy companies"],
            "indiamart": ["solar panels", "solar installation services"],
            "justdial": ["solar panel dealers", "solar companies"],
        },
        "logistics": {
            "google_maps": ["logistics companies", "transport companies", "freight services"],
            "indiamart": ["logistics services", "transport services"],
            "justdial": ["logistics companies", "trucking services"],
        },
        "digital_marketing": {
            "google_maps": ["digital marketing agencies", "SEO companies"],
            "indiamart": ["digital marketing services"],
            "justdial": ["digital marketing", "SEO services"],
        },
        "manufacturing": {
            "google_maps": ["manufacturing companies", "factory"],
            "indiamart": ["manufacturers", "industrial equipment"],
            "justdial": ["manufacturers", "industrial suppliers"],
        },
        "insurance": {
            "google_maps": ["insurance brokers", "insurance agents"],
            "indiamart": ["insurance services", "insurance brokers"],
            "justdial": ["insurance agents", "insurance brokers"],
        },
    }

    # Major Indian cities for scraping
    INDIAN_CITIES = [
        "Mumbai",
        "Delhi",
        "Bangalore",
        "Hyderabad",
        "Chennai",
        "Kolkata",
        "Pune",
        "Ahmedabad",
        "Jaipur",
        "Lucknow",
        "Surat",
        "Kanpur",
        "Nagpur",
        "Indore",
        "Thane",
        "Bhopal",
        "Visakhapatnam",
        "Patna",
        "Vadodara",
        "Ghaziabad",
    ]

    def __init__(self):
        # Lazy source scrapers — constructed (and their modules imported) on first use.
        self._google_maps = None
        self._indiamart = None
        self._justdial = None
        self._linkedin = None
        self._web_search = None
        self._social_media = None
        self.phone_validator = PhoneValidator()
        logger.info("🔍 Lead Scraper Manager initialized")

    @property
    def google_maps(self):
        if self._google_maps is None:
            from app.lead_scraper.google_maps import GoogleMapsScraper

            self._google_maps = GoogleMapsScraper()
        return self._google_maps

    @property
    def indiamart(self):
        if self._indiamart is None:
            from app.lead_scraper.indiamart import IndiaMartScraper

            self._indiamart = IndiaMartScraper()
        return self._indiamart

    @property
    def justdial(self):
        if self._justdial is None:
            from app.lead_scraper.justdial import JustDialScraper

            self._justdial = JustDialScraper()
        return self._justdial

    @property
    def linkedin(self):
        if self._linkedin is None:
            from app.lead_scraper.linkedin import LinkedInScraper

            self._linkedin = LinkedInScraper()
        return self._linkedin

    @property
    def web_search(self):
        if self._web_search is None:
            from app.lead_scraper.web_search import WebSearchScraper

            self._web_search = WebSearchScraper()
        return self._web_search

    @property
    def social_media(self):
        if self._social_media is None:
            from app.lead_scraper.social_media import SocialMediaScraper

            self._social_media = SocialMediaScraper()
        return self._social_media

    async def scrape_leads(
        self,
        niche: str,
        cities: list[str] | None = None,
        sources: list[str] | None = None,
        max_leads: int = 500,
        validate_phones: bool = True,
    ) -> list[UnifiedLead]:
        """
        Scrape leads from multiple sources

        Args:
            niche: Business niche (real_estate, solar, logistics, etc.)
            cities: List of cities to scrape (defaults to major Indian cities)
            sources: List of sources to use (google_maps, indiamart, justdial, linkedin)
            max_leads: Maximum total leads to collect
            validate_phones: Whether to validate phone numbers

        Returns:
            List of unified leads
        """
        cities = cities or self.INDIAN_CITIES[:5]  # Default to top 5 cities
        # Default = google_maps ONLY. indiamart/justdial are ToS-blocked (CLAUDE.md:
        # manual-CSV import only) — must be explicitly opted in by the caller, never
        # auto-fired by a caller that omits sources=.
        sources = sources or ["google_maps"]

        # Hard refuse ToS-blocked auto-scrape unless ALLOW_TOS_SCRAPE=1 (manual
        # research / CSV path only — §5 compliance; comment-only gate was insufficient).
        import os as _os

        _tos_blocked = frozenset(
            {"justdial", "indiamart", "linkedin", "social", "facebook", "instagram"}
        )
        _allow_tos = _os.environ.get("ALLOW_TOS_SCRAPE", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not _allow_tos:
            blocked = [s for s in sources if str(s).strip().lower() in _tos_blocked]
            if blocked:
                logger.warning(
                    "ToS-blocked scrape sources refused (set ALLOW_TOS_SCRAPE=1 only for "
                    "explicit manual research): %s",
                    blocked,
                )
            sources = [s for s in sources if str(s).strip().lower() not in _tos_blocked]
        if not sources:
            sources = ["google_maps"]

        logger.info(
            f"Starting lead scrape - Niche: {niche}, Cities: {len(cities)}, Sources: {sources}"
        )

        all_leads = []
        queries = self.NICHE_QUERIES.get(niche, {})

        # Calculate leads per source/city
        leads_per_source = max_leads // max(1, len(sources))
        leads_per_city = max(1, leads_per_source // max(1, len(cities)))

        tasks = []

        for source in sources:
            if source == "google_maps" and queries.get("google_maps"):
                for query in queries["google_maps"]:
                    tasks.append(self._scrape_google_maps(query, cities, leads_per_city))

            elif source == "indiamart" and queries.get("indiamart"):
                for query in queries["indiamart"]:
                    tasks.append(self._scrape_indiamart(query, cities, leads_per_city))

            elif source == "justdial" and queries.get("justdial"):
                for query in queries["justdial"]:
                    tasks.append(self._scrape_justdial(query, cities, leads_per_city))

            elif source == "web":
                # web search ke liye specific queries na hon to google_maps wali reuse karo
                web_queries = (
                    queries.get("web") or queries.get("google_maps") or [niche.replace("_", " ")]
                )
                for query in web_queries:
                    tasks.append(self._scrape_web(query, cities, leads_per_city))

            elif source == "social":
                social_queries = (
                    queries.get("social") or queries.get("google_maps") or [niche.replace("_", " ")]
                )
                for query in social_queries:
                    tasks.append(self._scrape_social(query, cities, leads_per_city))

        # Run scrapers concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Scraper error: {result}")
            else:
                all_leads.extend(result)

        # Deduplicate leads
        unique_leads = self._deduplicate_leads(all_leads)
        logger.info(f"Deduplicated: {len(all_leads)} → {len(unique_leads)} leads")

        # Validate phone numbers if requested
        if validate_phones:
            unique_leads = await self._validate_phones(unique_leads)

        # Sort by quality (has phone > verified > rating)
        unique_leads.sort(
            key=lambda x: (x.phone is not None, x.verified, x.rating or 0), reverse=True
        )

        logger.info(f"✅ Scraped {len(unique_leads)} unique leads")
        return unique_leads[:max_leads]

    async def _scrape_google_maps(
        self, query: str, cities: list[str], max_per_city: int
    ) -> list[UnifiedLead]:
        """Scrape from Google Maps"""
        leads = []

        for city in cities:
            try:
                raw_leads = await self.google_maps.search_businesses(
                    query=query, location=city, max_results=max_per_city
                )

                for raw in raw_leads:
                    leads.append(self._convert_google_maps_lead(raw))

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Google Maps error for {city}: {e}")

        return leads

    async def _scrape_indiamart(
        self, query: str, cities: list[str], max_per_city: int
    ) -> list[UnifiedLead]:
        """Scrape from IndiaMart"""
        leads = []

        for city in cities:
            try:
                raw_leads = await self.indiamart.search_businesses(
                    query=query, city=city, max_results=max_per_city
                )

                for raw in raw_leads:
                    leads.append(self._convert_indiamart_lead(raw))

                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"IndiaMart error for {city}: {e}")

        return leads

    async def _scrape_justdial(
        self, query: str, cities: list[str], max_per_city: int
    ) -> list[UnifiedLead]:
        """Scrape from JustDial"""
        leads = []

        for city in cities:
            try:
                raw_leads = await self.justdial.search_businesses(
                    category=query, city=city, max_results=max_per_city
                )

                for raw in raw_leads:
                    leads.append(self._convert_justdial_lead(raw))

                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"JustDial error for {city}: {e}")

        return leads

    async def _scrape_web(
        self,
        query: str,
        cities: list[str],
        max_per_city: int,
    ) -> list[UnifiedLead]:
        """Scrape from open web search (DuckDuckGo)."""
        leads = []
        for city in cities:
            try:
                raw_leads = await self.web_search.search_businesses(
                    category=query,
                    city=city,
                    max_results=max_per_city,
                )
                for raw in raw_leads:
                    leads.append(self._convert_web_lead(raw))
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Web search error for {city}: {e}")
        return leads

    async def _scrape_social(
        self,
        query: str,
        cities: list[str],
        max_per_city: int,
    ) -> list[UnifiedLead]:
        """Scrape from public social media pages (Instagram/Facebook)."""
        leads = []
        for city in cities:
            try:
                raw_leads = await self.social_media.search_businesses(
                    category=query,
                    city=city,
                    max_results=max_per_city,
                )
                for raw in raw_leads:
                    leads.append(self._convert_social_lead(raw))
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Social media error for {city}: {e}")
        return leads

    def _convert_web_lead(self, raw: WebSearchLead) -> UnifiedLead:
        """Convert web search lead to unified format."""
        import uuid

        return UnifiedLead(
            id=str(uuid.uuid4()),
            company_name=raw.name,
            contact_name=None,
            phone=raw.phone,
            phone_verified=False,
            email=raw.email,
            address="",
            city=raw.city,
            state="",
            country="India",
            category=raw.category,
            source="web_search",
            source_url=raw.source_url,
            rating=None,
            verified=False,
            scraped_at=datetime.now(),
            raw_data=asdict(raw),
        )

    def _convert_social_lead(self, raw: SocialMediaLead) -> UnifiedLead:
        """Convert social media lead to unified format."""
        import uuid

        return UnifiedLead(
            id=str(uuid.uuid4()),
            company_name=raw.name,
            contact_name=raw.handle,
            phone=raw.phone,
            phone_verified=False,
            email=raw.email,
            address="",
            city=raw.city,
            state="",
            country="India",
            category=raw.category,
            source=f"social_{raw.platform}",
            source_url=raw.profile_url,
            rating=None,
            verified=False,
            scraped_at=datetime.now(),
            raw_data=asdict(raw),
        )

    def _convert_google_maps_lead(self, raw: BusinessLead) -> UnifiedLead:
        """Convert Google Maps lead to unified format"""
        import uuid

        return UnifiedLead(
            id=str(uuid.uuid4()),
            company_name=raw.name,
            contact_name=None,
            phone=raw.phone,
            phone_verified=False,
            email=raw.email,
            address=raw.address,
            city=raw.city,
            state=raw.state,
            country="India",
            category=raw.category,
            source="google_maps",
            source_url=raw.google_maps_url,
            rating=raw.rating,
            verified=raw.reviews_count > 10,
            scraped_at=datetime.now(),
            raw_data=asdict(raw),
        )

    def _convert_indiamart_lead(self, raw: IndiaMartLead) -> UnifiedLead:
        """Convert IndiaMart lead to unified format"""
        import uuid

        return UnifiedLead(
            id=str(uuid.uuid4()),
            company_name=raw.company_name,
            contact_name=raw.contact_person,
            phone=raw.phone or raw.mobile,
            phone_verified=False,
            email=raw.email,
            address=raw.address,
            city=raw.city,
            state=raw.state,
            country="India",
            category=", ".join(raw.products[:3]),
            source="indiamart",
            source_url=raw.indiamart_url,
            rating=None,
            verified=raw.verified or raw.trust_seal,
            scraped_at=datetime.now(),
            raw_data=asdict(raw),
        )

    def _convert_justdial_lead(self, raw: JustDialLead) -> UnifiedLead:
        """Convert JustDial lead to unified format"""
        import uuid

        return UnifiedLead(
            id=str(uuid.uuid4()),
            company_name=raw.name,
            contact_name=None,
            phone=raw.phone,
            phone_verified=False,
            email=None,
            address=raw.address,
            city=raw.city,
            state="",
            country="India",
            category=raw.category,
            source="justdial",
            source_url=raw.justdial_url,
            rating=raw.rating,
            verified=raw.verified,
            scraped_at=datetime.now(),
            raw_data=asdict(raw),
        )

    def _deduplicate_leads(self, leads: list[UnifiedLead]) -> list[UnifiedLead]:
        """Remove duplicate leads based on phone or company name"""
        seen_phones = set()
        seen_companies = set()
        unique = []

        for lead in leads:
            # Normalize phone
            phone_key = None
            if lead.phone:
                phone_key = "".join(filter(str.isdigit, lead.phone))[-10:]

            # Normalize company name
            company_key = lead.company_name.lower().strip()

            # Check for duplicates. Phone is the PRIMARY key: two branches/
            # franchises that share a name but have distinct phones are distinct
            # leads and must both survive. Company-name only dedups phone-LESS
            # leads (so we still drop a phoneless duplicate of a known business).
            is_duplicate = False

            if phone_key and phone_key in seen_phones:
                is_duplicate = True
            elif not phone_key and company_key in seen_companies:
                is_duplicate = True

            if not is_duplicate:
                unique.append(lead)
                if phone_key:
                    seen_phones.add(phone_key)
                seen_companies.add(company_key)

        return unique

    async def _validate_phones(self, leads: list[UnifiedLead]) -> list[UnifiedLead]:
        """Validate and normalize phone numbers"""
        for lead in leads:
            if lead.phone:
                is_valid, normalized = self.phone_validator.validate_indian_number(lead.phone)
                if is_valid:
                    lead.phone = normalized
                    lead.phone_verified = True
                else:
                    lead.phone_verified = False

        return leads

    async def export_leads(
        self, leads: list[UnifiedLead], format: str = "json", filename: str | None = None
    ) -> str:
        """
        Export leads to file

        Args:
            leads: List of leads to export
            format: Export format (json, csv)
            filename: Output filename (auto-generated if not provided)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename or f"leads_{timestamp}.{format}"

        if format == "json":
            data = [lead.to_dict() for lead in leads]
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        elif format == "csv":
            import csv

            with open(filename, "w", newline="", encoding="utf-8") as f:
                if leads:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "company_name",
                            "contact_name",
                            "phone",
                            "email",
                            "city",
                            "state",
                            "category",
                            "source",
                            "rating",
                            "verified",
                        ],
                    )
                    writer.writeheader()
                    for lead in leads:
                        writer.writerow(
                            {
                                "company_name": lead.company_name,
                                "contact_name": lead.contact_name or "",
                                "phone": lead.phone or "",
                                "email": lead.email or "",
                                "city": lead.city,
                                "state": lead.state,
                                "category": lead.category,
                                "source": lead.source,
                                "rating": lead.rating or "",
                                "verified": lead.verified,
                            }
                        )

        logger.info(f"Exported {len(leads)} leads to {filename}")
        return filename
