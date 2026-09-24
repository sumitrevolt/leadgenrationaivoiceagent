"""
Multi-Source Lead Generation Integrations

This module implements:
1. JustDial lead scraper via Apify API (primary) + local fallback
2. IndiaMART CRM API integration for lead extraction
3. WhatsApp Business API (WAHA) lead capture automation
4. GitHub automation for open-source project leads
5. Multi-source deduplication logic for phone numbers

All integrations follow the existing project patterns:
- FastAPI endpoints in app/api/
- Celery tasks in app/tasks/
- Async processing with httpx
- Phone validation with phonenumbers
- Deduplication by normalized phone
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# ============================================================================
# 1. JUSTDIAL LEAD SCRAPER (Apify API + Local Fallback)
# ============================================================================

@dataclass
class JustDialLead:
    """JustDial business lead"""
    company_name: str
    contact_person: str | None
    phone: str | None
    phone_raw: str | None
    address: str
    city: str
    area: str
    category: str
    rating: float | None
    reviews: int
    justdial_url: str
    website: str | None
    verified: bool
    source: str = "justdial"
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scraped_at"] = self.scraped_at.isoformat()
        return data


class JustDialApifyClient:
    """
    JustDial scraper using Apify API (recommended for production).

    Apify provides reliable JustDial scraping with:
    - tugelbay/justdial-leads-extractor actor
    - thirdwatch/justdial-business-scraper actor

    Environment variables:
    - APIFY_API_TOKEN: Your Apify API token (https://console.apify.com/account#/integrations)
    """

    def __init__(self):
        self.api_token = os.environ.get("APIFY_API_TOKEN", "").strip()
        self.base_url = "https://api.apify.com/v2"
        # Recommended Apify actors for JustDial
        self.actor_ids = {
            "justdial_leads": "tugelbay/justdial-leads-extractor",
            "justdial_search": "thirdwatch/justdial-business-scraper",
        }
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client

    async def search_by_category(
        self,
        category: str,
        city: str,
        max_results: int = 100,
        actor_id: str = "justdial_leads",
    ) -> list[JustDialLead]:
        """
        Search JustDial by category and city using Apify.

        Args:
            category: Business category (e.g., "real estate agents")
            city: City name (e.g., "Mumbai")
            max_results: Maximum leads to return
            actor_id: Apify actor to use

        Returns:
            List of JustDialLead objects
        """
        if not self.is_configured:
            logger.warning("Apify not configured - skipping JustDial search")
            return []

        client = await self._get_client()
        actor = self.actor_ids.get(actor_id, actor_id)

        # Prepare input for Apify actor
        input_data = {
            "startUrls": [
                f"https://www.justdial.com/{self._slugify(city)}/{self._slugify(category)}"
            ],
            "maxResults": min(max_results, 500),  # Apify actors typically cap at 500
            "additionalData": {
                "extractPhones": True,
                "extractAddresses": True,
                "extractRatings": True,
            },
        }

        try:
            # Run the actor
            run_response = await client.post(
                f"/actions/{actor}/runs",
                json={"input": input_data},
            )
            run_response.raise_for_status()
            run_data = run_response.json()
            run_id = run_data.get("data", {}).get("id")

            if not run_id:
                logger.error(f"Failed to start Apify run: {run_data}")
                return []

            # Wait for completion (poll)
            logger.info(f"Apify run started: {run_id}")
            result_data = await self._wait_for_run(client, run_id)

            # Parse results
            leads = self._parse_apify_results(result_data, category, city)
            logger.info(f"Extracted {len(leads)} leads from JustDial via Apify")
            return leads

        except Exception as e:
            logger.error(f"JustDial Apify search failed: {e}")
            return []

    async def _wait_for_run(self, client: httpx.AsyncClient, run_id: str) -> list[dict]:
        """Wait for Apify run to complete and fetch results."""
        for attempt in range(30):  # Max 30 minutes
            await asyncio.sleep(10)

            status_response = await client.get(f"/acts/{run_id.split('/')[0]}/runs/{run_id}")
            status_response.raise_for_status()
            status_data = status_response.json()

            status = status_data.get("status", "")
            if status in ["SUCCEEDED", "FAILED", "TIMED-OUT"]:
                break

        if status != "SUCCEEDED":
            logger.error(f"Apify run failed: {status}")
            return []

        # Fetch dataset items
        dataset_response = await client.get(f"/datasets/{run_data.get('defaultDatasetId')}/items")
        dataset_response.raise_for_status()
        return dataset_response.json() or []

    def _parse_apify_results(self, items: list[dict], category: str, city: str) -> list[JustDialLead]:
        """Parse Apify dataset items into JustDialLead objects."""
        leads = []

        for item in items:
            try:
                # Apify actor typically returns these fields
                lead = JustDialLead(
                    company_name=item.get("name") or item.get("businessName") or "Unknown",
                    contact_person=item.get("contactPerson"),
                    phone=item.get("phone") or item.get("phoneNumber"),
                    phone_raw=item.get("phoneRaw"),
                    address=item.get("address") or item.get("fullAddress") or "",
                    city=city,
                    area=item.get("area") or item.get("locality") or "",
                    category=category,
                    rating=item.get("rating"),
                    reviews=item.get("reviews") or item.get("voteCount") or 0,
                    justdial_url=item.get("url") or item.get("listingUrl") or "",
                    website=item.get("website"),
                    verified=item.get("verified") or item.get("isTrusted"),
                    raw_data=item,
                )
                leads.append(lead)
            except Exception as e:
                logger.debug(f"Error parsing Apify result: {e}")
                continue

        return leads

    def _slugify(self, text: str) -> str:
        """Convert text to URL slug."""
        return re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


class JustDialLocalScraper:
    """
    Local JustDial scraper using Playwright (fallback when Apify not available).

    Uses browser automation to extract business listings.
    """

    def __init__(self):
        self.base_url = "https://www.justdial.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def search_by_category(
        self,
        category: str,
        city: str,
        max_results: int = 50,
    ) -> list[JustDialLead]:
        """Search JustDial using browser automation."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Install with: pip install playwright")
            return []

        leads = []
        city_slug = self._slugify(city)
        category_slug = self._slugify(category)
        url = f"{self.base_url}/{city_slug}/{category_slug}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(url, timeout=60000, wait_until="networkidle")

                # Wait for listings to load
                await page.wait_for_selector('[class*="cntanr"]', timeout=30000)

                # Scroll to load more results
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)

                # Extract listings
                listings = await page.query_selector_all('[class*="cntanr"], [class*="listing"]')

                for listing in listings[:max_results]:
                    try:
                        lead = await self._extract_listing(listing, city, category, page)
                        if lead:
                            leads.append(lead)
                    except Exception as e:
                        logger.debug(f"Error extracting listing: {e}")

            finally:
                await browser.close()

        logger.info(f"Extracted {len(leads)} leads from JustDial (local)")
        return leads

    async def _extract_listing(self, listing, city: str, category: str, page) -> JustDialLead | None:
        """Extract lead data from a listing element."""
        try:
            name_elem = await listing.query_selector('[class*="name"], [class*="company"], span')
            name = await name_elem.inner_text() if name_elem else ""

            url_elem = await listing.query_selector('a[href*="justdial.com"]')
            url = await url_elem.get_attribute("href") if url_elem else ""
            if url and not url.startswith("http"):
                url = f"{self.base_url}{url}"

            phone_elem = await listing.query_selector('[class*="phone"], [class*="mobile"], [class*="number"]')
            phone = await phone_elem.inner_text() if phone_elem else None

            address_elem = await listing.query_selector('[class*="address"], [class*="location"]')
            address = await address_elem.inner_text() if address_elem else ""

            rating_elem = await listing.query_selector('[class*="rating"], [class*="stars"]')
            rating = None
            if rating_elem:
                try:
                    rating = float(await rating_elem.inner_text() or 0)
                except ValueError:
                    pass

            return JustDialLead(
                company_name=name.strip() if name else "Unknown",
                contact_person=None,
                phone=phone,
                phone_raw=phone,
                address=address.strip() if address else "",
                city=city,
                area="",
                category=category,
                rating=rating,
                reviews=0,
                justdial_url=url,
                website=None,
                verified=False,
            )
        except Exception as e:
            logger.debug(f"Error in _extract_listing: {e}")
            return None

    def _slugify(self, text: str) -> str:
        return re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')


# ============================================================================
# 2. INDIAMART CRM API INTEGRATION
# ============================================================================

@dataclass
class IndiaMartLead:
    """IndiaMART lead from CRM API"""
    company_name: str
    contact_person: str
    phone: str | None
    email: str | None
    query: str
    product_interest: str
    city: str
    state: str
    indiamart_url: str
    verified: bool
    source: str = "indiamart_api"
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scraped_at"] = self.scraped_at.isoformat()
        return data


class IndiaMartCRMClient:
    """
    IndiaMART Lead Manager CRM API integration.

    Uses IndiaMART's official CRM Pull API to fetch seller's own leads.
    NOT for scraping IndiaMART listings (ToS-blocked).

    Environment variables:
    - INDIAMART_CRM_KEY: IndiaMART Lead Manager API key
    """

    _PULL_URL = "https://mapi.indiamart.com/wservce/crm/crmListing/v2/"

    def __init__(self):
        self.api_key = os.environ.get("INDIAMART_CRM_KEY", "").strip()
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def fetch_leads(
        self,
        days: int = 7,
        niche: str = "general",
    ) -> list[IndiaMartLead]:
        """
        Fetch leads from IndiaMART Lead Manager CRM API.

        Args:
            days: Number of days to look back
            niche: Business niche to filter by

        Returns:
            List of IndiaMartLead objects
        """
        if not self.is_configured:
            logger.warning("IndiaMART CRM key not configured - skipping")
            return []

        client = await self._get_client()
        end = datetime.now()
        start = end - __import__('datetime').timedelta(days=max(1, int(days)))

        fmt = "%d-%b-%Y %H:%M:%S"

        try:
            response = await client.get(
                self._PULL_URL,
                params={
                    "glusr_crm_key": self.api_key,
                    "start_time": start.strftime(fmt),
                    "end_time": end.strftime(fmt),
                },
            )
            response.raise_for_status()
            body = response.json()

            leads = self._parse_response(body, niche)
            logger.info(f"Extracted {len(leads)} leads from IndiaMART CRM")
            return leads

        except Exception as e:
            logger.error(f"IndiaMART CRM fetch failed: {e}")
            return []

    def _parse_response(self, body: dict, niche: str) -> list[IndiaMartLead]:
        """Parse IndiaMART API response."""
        leads = []
        rows = body.get("RESPONSE") or []

        if not isinstance(rows, list):
            logger.error(f"Invalid IndiaMART response format: {type(rows)}")
            return []

        for row in rows:
            try:
                sender_name = str(row.get("SENDER_NAME") or row.get("SENDER_COMPANY") or "").strip()
                sender_mobile = str(row.get("SENDER_MOBILE") or "").strip()
                sender_email = str(row.get("SENDER_EMAIL") or "").strip() or None
                sender_city = str(row.get("SENDER_CITY") or "").strip()
                query_message = str(row.get("QUERY_MESSAGE") or row.get("QUERY_PRODUCT_NAME") or "").strip()

                # Basic validation
                if not sender_name and not sender_mobile:
                    continue

                lead = IndiaMartLead(
                    company_name=sender_name or "IndiaMART Buyer",
                    contact_person="",
                    phone=sender_mobile if len(sender_mobile) >= 10 else None,
                    email=sender_email if sender_email and '@' in sender_email else None,
                    query=query_message[:500],
                    product_interest=query_message[:200],
                    city=sender_city,
                    state="",
                    indiamart_url="",
                    verified=False,
                    raw_data=row,
                )
                leads.append(lead)

            except Exception as e:
                logger.debug(f"Error parsing IndiaMART row: {e}")
                continue

        return leads

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


# ============================================================================
# 3. WHATSAPP LEAD CAPTURE AUTOMATION (WAHA)
# ============================================================================

@dataclass
class WhatsAppLeadCapture:
    """Lead captured from WhatsApp conversation"""
    phone: str
    message: str
    contact_name: str | None
    city: str | None
    intent: str | None
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["captured_at"] = self.captured_at.isoformat()
        return data


class WhatsAppLeadCaptureHandler:
    """
    Handles lead capture from WhatsApp Business API (WAHA).

    Processes incoming WhatsApp messages to extract lead information.
    Integrates with the existing WAHA stack (app/integrations/whatsapp_selfhost.py).
    """

    def __init__(self):
        from app.integrations.whatsapp_selfhost import is_active_provider, is_configured

        self.waha_configured = is_configured() and is_active_provider()
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def process_incoming_message(
        self,
        from_number: str,
        message_body: str,
        contact_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Process an incoming WhatsApp message to capture lead.

        Args:
            from_number: Sender's phone number
            message_body: Message text
            contact_name: Optional contact name

        Returns:
            Dict with capture result and extracted lead data
        """
        result = {
            "captured": False,
            "phone": from_number,
            "message": message_body[:500],
            "intent": None,
            "lead_id": None,
        }

        # Extract intent from message
        intent = self._classify_intent(message_body)
        result["intent"] = intent

        # Extract potential lead data
        city = self._extract_city(message_body)
        result["city"] = city

        # Create lead record
        lead = WhatsAppLeadCapture(
            phone=from_number,
            message=message_body,
            contact_name=contact_name,
            city=city,
            intent=intent,
            raw_data=result,
        )
        result["lead"] = lead.to_dict()

        # Save to database (async)
        try:
            import uuid

            from app.platform import lead_harvester

            rec = {
                "id": str(uuid.uuid4()),
                "found_at": lead.captured_at.isoformat(),
                "business_name": (contact_name or "WhatsApp Lead")[:200],
                "phone": self._normalize_phone(from_number),
                "email": None,
                "website": "",
                "address": "",
                "city": city or "",
                "niche": "whatsapp_inbound",
                "query": message_body[:300],
                "source": "whatsapp_waha",
                "status": "new",
                "lead_score": self._score_lead(intent),
            }

            new_id = lead_harvester._append(rec)
            result["lead_id"] = new_id
            result["captured"] = True

        except Exception as e:
            logger.error(f"Failed to save WhatsApp lead: {e}")

        return result

    def _classify_intent(self, message: str) -> str | None:
        """Classify lead intent from message."""
        msg_lower = message.lower()

        # High intent indicators
        if any(kw in msg_lower for kw in ["pricing", "price", "quote", "cost", "how much", "charges", "plan", "package"]):
            return "pricing_inquiry"

        if any(kw in msg_lower for kw in ["demo", "trial", "test", "sample", "show me", "want to try"]):
            return "demo_requested"

        if any(kw in msg_lower for kw in ["buy", "purchase", "order", "hire", "book", "schedule", "appointment", "meeting"]):
            return "purchase_intent"

        # Medium intent indicators
        if any(kw in msg_lower for kw in ["interested", "need", "looking for", "searching", "want"]):
            return "interested"

        if any(kw in msg_lower for kw in ["more info", "details", "learn more", "tell me", "explain"]):
            return "info_request"

        # Low intent indicators
        if any(kw in msg_lower for kw in ["hello", "hi", "hey", "good morning", "good evening"]):
            return "greeting"

        return "unknown"

    def _extract_city(self, message: str) -> str | None:
        """Extract city from message if mentioned."""
        # Common Indian cities
        cities = [
            "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
            "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
            "Surat", "Kanpur", "Nagpur", "Indore", "Thane",
            "Bhopal", "Visakhapatnam", "Patna", "Vadodara", "Ghaziabad"
        ]

        msg_lower = message.lower()
        for city in cities:
            if city.lower() in msg_lower:
                return city

        return None

    def _score_lead(self, intent: str | None) -> int:
        """Score lead based on intent."""
        scores = {
            "purchase_intent": 90,
            "demo_requested": 85,
            "pricing_inquiry": 80,
            "interested": 60,
            "info_request": 50,
            "greeting": 30,
            "unknown": 20,
        }
        return scores.get(intent, 20)

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to E.164 format for India."""
        digits = "".join(c for c in str(phone or "") if c.isdigit())

        if len(digits) == 10:
            return f"91{digits}"
        elif digits.startswith("0") and len(digits) == 11:
            return f"91{digits[1:]}"
        elif digits.startswith("91") and len(digits) == 12:
            return digits
        return digits

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


# ============================================================================
# 4. GITHUB AUTOMATION FOR OPEN-SOURCE PROJECT LEADS
# ============================================================================

@dataclass
class GitHubProjectLead:
    """Lead from GitHub open-source project"""
    repo_name: str
    owner: str
    description: str
    language: str
    stars: int
    forks: int
    url: str
    last_updated: datetime
    contact_email: str | None
    website: str | None
    location: str | None
    source: str = "github"
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scraped_at"] = self.scraped_at.isoformat()
        if self.last_updated:
            data["last_updated"] = self.last_updated.isoformat()
        return data


class GitHubLeadHunter:
    """
    GitHub automation for finding open-source project leads.

    Searches for projects with specific tech stacks, recent activity,
    and potential customer signals.
    """

    GITHUB_API = "https://api.github.com"

    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "").strip()
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "LeadGenAI-Scraper",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self._client = None

    @property
    def is_configured(self) -> bool:
        return True  # GitHub API works without token (rate limited)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.GITHUB_API,
                headers=self.headers,
                timeout=30.0,
            )
        return self._client

    async def search_projects(
        self,
        query: str,
        sort: str = "stars",
        per_page: int = 30,
        max_pages: int = 3,
    ) -> list[GitHubProjectLead]:
        """
        Search GitHub for projects matching criteria.

        Args:
            query: Search query (e.g., "solar panel management system")
            sort: Sort by (stars, forks, updated)
            per_page: Results per page (max 100)
            max_pages: Maximum pages to fetch

        Returns:
            List of GitHubProjectLead objects
        """
        client = await self._get_client()
        leads = []

        # Build search query
        search_query = f"{query} in:name,description"

        for page in range(1, max_pages + 1):
            try:
                response = await client.get(
                    "/search/repositories",
                    params={
                        "q": search_query,
                        "sort": sort,
                        "order": "desc",
                        "page": page,
                        "per_page": min(per_page, 100),
                    },
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                if not items:
                    break

                for repo in items:
                    try:
                        lead = self._parse_repo(repo)
                        if lead:
                            leads.append(lead)
                    except Exception as e:
                        logger.debug(f"Error parsing repo: {e}")

                # Check if there are more pages
                total_count = data.get("total_count", 0)
                if page * per_page >= total_count:
                    break

                # Rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"GitHub search failed: {e}")
                break

        logger.info(f"Extracted {len(leads)} leads from GitHub")
        return leads

    async def search_by_tech_stack(
        self,
        language: str,
        min_stars: int = 100,
        sort: str = "stars",
        limit: int = 50,
    ) -> list[GitHubProjectLead]:
        """
        Search for projects by programming language and star count.

        Args:
            language: Programming language (e.g., "python", "javascript")
            min_stars: Minimum stars
            sort: Sort criteria
            limit: Maximum results

        Returns:
            List of GitHubProjectLead objects
        """
        client = await self._get_client()
        leads = []

        query = f"language:{language} stars:>{min_stars}"

        try:
            response = await client.get(
                "/search/repositories",
                params={
                    "q": query,
                    "sort": sort,
                    "order": "desc",
                    "per_page": min(limit, 100),
                },
            )
            response.raise_for_status()
            data = response.json()

            for repo in data.get("items", []):
                try:
                    lead = self._parse_repo(repo)
                    if lead:
                        leads.append(lead)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"GitHub tech stack search failed: {e}")

        logger.info(f"Extracted {len(leads)} leads from GitHub (tech stack: {language})")
        return leads

    async def get_contributor_leads(
        self,
        org: str,
        limit: int = 20,
    ) -> list[GitHubProjectLead]:
        """
        Get leads from contributors of a specific organization.

        Args:
            org: Organization name
            limit: Maximum contributors to fetch

        Returns:
            List of GitHubProjectLead objects
        """
        client = await self._get_client()
        leads = []

        try:
            response = await client.get(
                f"/orgs/{org}/members",
                params={"per_page": limit},
            )
            response.raise_for_status()

            for member in response.json():
                try:
                    # Get user details
                    user_resp = await client.get(f"/users/{member['login']}")
                    user_resp.raise_for_status()
                    user_data = user_resp.json()

                    lead = GitHubProjectLead(
                        repo_name="",
                        owner=member['login'],
                        description="",
                        language="",
                        stars=0,
                        forks=0,
                        url=member['html_url'],
                        last_updated=datetime.now(timezone.utc),
                        contact_email=user_data.get("email"),
                        website=user_data.get("blog"),
                        location=user_data.get("location"),
                        raw_data=user_data,
                    )
                    leads.append(lead)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"GitHub contributor fetch failed: {e}")

        logger.info(f"Extracted {len(leads)} contributor leads from {org}")
        return leads

    def _parse_repo(self, repo: dict) -> GitHubProjectLead | None:
        """Parse GitHub repository data into a lead."""
        try:
            pushed_at = repo.get("pushed_at")
            updated_at = repo.get("updated_at")
            last_updated = None

            if pushed_at:
                last_updated = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
            elif updated_at:
                last_updated = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))

            # Try to find contact info from repo
            contact_email = None
            website = None
            location = None

            # Check README for contact info
            readme_url = repo.get("readme_url")
            if readme_url:
                # Could fetch README, but skip for now to avoid extra API calls
                pass

            return GitHubProjectLead(
                repo_name=repo.get("full_name", ""),
                owner=repo.get("owner", {}).get("login", ""),
                description=repo.get("description", "")[:500],
                language=repo.get("language", ""),
                stars=repo.get("stargazers_count", 0),
                forks=repo.get("forks_count", 0),
                url=repo.get("html_url", ""),
                last_updated=last_updated,
                contact_email=contact_email,
                website=website,
                location=location,
                raw_data=repo,
            )
        except Exception as e:
            logger.debug(f"Error parsing repo: {e}")
            return None

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


# ============================================================================
# 5. MULTI-SOURCE DEDUPLICATION LOGIC
# ============================================================================

class MultiSourceDeduplicator:
    """
    Multi-source deduplication for phone numbers.

    Normalizes and deduplicates leads from multiple sources (JustDial, IndiaMART,
    WhatsApp, GitHub, Google Maps) based on phone number.
    """

    # Common Indian phone formats
    PHONE_PATTERNS = [
        r'\+91[\s-]?(\d{10})',  # +91 9876543210
        r'91[\s-]?(\d{10})',    # 91 9876543210
        r'0(\d{10})',           # 09876543210
        r'(\d{10})',            # 9876543210
    ]

    def __init__(self):
        self._seen_phones: set[str] = set()
        self._seen_emails: set[str] = set()
        self._dedup_stats: dict[str, int] = {
            "total_processed": 0,
            "duplicates_removed": 0,
            "unique_leads": 0,
        }

    def normalize_phone(self, phone: str | None) -> str | None:
        """
        Normalize phone number to consistent format.

        Args:
            phone: Raw phone number string

        Returns:
            Normalized 10-digit phone or None
        """
        if not phone:
            return None

        # Extract digits
        digits = re.sub(r'\D', '', str(phone))

        # Handle common Indian formats
        if len(digits) == 10:
            # Already 10 digits, validate first digit
            if digits[0] in '6789':
                return digits
        elif len(digits) == 11 and digits.startswith('0'):
            # 0XXXXXXXXXX -> XXXXXXXXXX
            return digits[1:]
        elif len(digits) == 12 and digits.startswith('91'):
            # +91XXXXXXXXXX -> XXXXXXXXXX
            return digits[2:]

        return None

    def normalize_email(self, email: str | None) -> str | None:
        """Normalize email for deduplication."""
        if not email:
            return None
        return email.strip().lower()

    def is_duplicate(
        self,
        phone: str | None,
        email: str | None,
        company_name: str | None = None,
    ) -> bool:
        """
        Check if lead is duplicate based on phone or email.

        Args:
            phone: Lead's phone number
            email: Lead's email
            company_name: Optional company name for logging

        Returns:
            True if duplicate, False otherwise
        """
        self._dedup_stats["total_processed"] += 1

        # Check phone first (most reliable)
        norm_phone = self.normalize_phone(phone)
        if norm_phone:
            if norm_phone in self._seen_phones:
                self._dedup_stats["duplicates_removed"] += 1
                logger.debug(f"Duplicate by phone: {norm_phone} ({company_name or ''})")
                return True
            self._seen_phones.add(norm_phone)

        # Check email (secondary)
        norm_email = self.normalize_email(email)
        if norm_email:
            if norm_email in self._seen_emails:
                self._dedup_stats["duplicates_removed"] += 1
                logger.debug(f"Duplicate by email: {norm_email} ({company_name or ''})")
                return True
            self._seen_emails.add(norm_email)

        self._dedup_stats["unique_leads"] += 1
        return False

    def deduplicate_leads(self, leads: list[dict]) -> list[dict]:
        """
        Deduplicate a list of leads.

        Args:
            leads: List of lead dictionaries

        Returns:
            Deduplicated list of leads
        """
        unique = []

        for lead in leads:
            phone = lead.get("phone")
            email = lead.get("email")
            company = lead.get("company_name", lead.get("name", ""))

            if not self.is_duplicate(phone, email, company):
                unique.append(lead)

        logger.info(
            f"Deduplication complete: {self._dedup_stats['total_processed']} processed, "
            f"{self._dedup_stats['duplicates_removed']} duplicates, "
            f"{len(unique)} unique leads"
        )
        return unique

    def get_stats(self) -> dict[str, int]:
        """Get deduplication statistics."""
        return dict(self._dedup_stats)

    def reset(self):
        """Reset deduplication state."""
        self._seen_phones.clear()
        self._seen_emails.clear()
        self._dedup_stats = {
            "total_processed": 0,
            "duplicates_removed": 0,
            "unique_leads": 0,
        }


# ============================================================================
# FastAPI Router
# ============================================================================

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/lead-integrations", tags=["lead-integrations"])


# Request/Response Models
class JustDialSearchRequest(BaseModel):
    category: str = Field(..., description="Business category (e.g., 'real estate agents')")
    city: str = Field(..., description="City name (e.g., 'Mumbai')")
    max_results: int = Field(100, ge=1, le=500, description="Maximum results")
    use_apify: bool = Field(True, description="Use Apify API if configured")


class IndiaMartRequest(BaseModel):
    days: int = Field(7, ge=1, le=30, description="Days to look back")
    niche: str = Field("general", description="Business niche")


class GitHubSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    sort: str = Field("stars", pattern="^(stars|forks|updated)$")
    per_page: int = Field(30, ge=1, le=100)
    max_pages: int = Field(3, ge=1, le=10)


class GitHubTechRequest(BaseModel):
    language: str = Field(..., description="Programming language")
    min_stars: int = Field(100, ge=0)
    limit: int = Field(50, ge=1, le=100)


class DedupRequest(BaseModel):
    leads: list[dict] = Field(..., description="List of leads to deduplicate")


class DedupResponse(BaseModel):
    unique_count: int
    duplicate_count: int
    leads: list[dict]
    stats: dict[str, int]


class IntegrationStatus(BaseModel):
    justdial_apify: bool
    justdial_local: bool
    indiamart: bool
    whatsapp: bool
    github: bool


# In-memory task tracking
_scrape_tasks: dict[str, dict] = {}


@router.get("/status", response_model=IntegrationStatus)
async def get_integration_status():
    """Check which integrations are configured and available."""
    # Check JustDial Apify
    justdial_apify = os.environ.get("APIFY_API_TOKEN", "").strip() != ""

    # Check JustDial Local (Playwright)
    justdial_local = True  # Assume available if not using Apify

    # Check IndiaMART
    indiamart = os.environ.get("INDIAMART_CRM_KEY", "").strip() != ""

    # Check WhatsApp
    try:
        from app.integrations.whatsapp_selfhost import is_active_provider, is_configured
        whatsapp = is_configured() and is_active_provider()
    except ImportError:
        whatsapp = False

    # Check GitHub
    github = True  # Always available (rate limited without token)

    return IntegrationStatus(
        justdial_apify=justdial_apify,
        justdial_local=justdial_local,
        indiamart=indiamart,
        whatsapp=whatsapp,
        github=github,
    )


@router.post("/justdial/search", response_model=list[dict])
async def search_justdial(
    request: JustDialSearchRequest,
    background_tasks: BackgroundTasks,
):
    """
    Search JustDial for business leads.

    Uses Apify API if configured, otherwise falls back to local scraper.
    """
    task_id = str(uuid.uuid4())
    _scrape_tasks[task_id] = {"status": "running", "started_at": datetime.now().isoformat()}

    async def run_scrape():
        try:
            if request.use_apify:
                client = JustDialApifyClient()
                leads = await client.search_by_category(
                    category=request.category,
                    city=request.city,
                    max_results=request.max_results,
                )
                await client.close()
            else:
                scraper = JustDialLocalScraper()
                leads = await scraper.search_by_category(
                    category=request.category,
                    city=request.city,
                    max_results=request.max_results,
                )

            _scrape_tasks[task_id] = {
                "status": "completed",
                "leads_found": len(leads),
                "completed_at": datetime.now().isoformat(),
            }
            return [lead.to_dict() for lead in leads]

        except Exception as e:
            logger.error(f"JustDial search failed: {e}")
            _scrape_tasks[task_id] = {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now().isoformat(),
            }
            return []

    background_tasks.add_task(run_scrape)

    return [{"task_id": task_id, "status": "running", "message": "Search started"}]


@router.get("/justdial/search/{task_id}")
async def get_justdial_status(task_id: str):
    """Get JustDial search task status."""
    task = _scrape_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/indiamart/fetch", response_model=list[dict])
async def fetch_indiamart_leads(
    request: IndiaMartRequest,
    background_tasks: BackgroundTasks,
):
    """
    Fetch leads from IndiaMART CRM API.

    Requires INDIAMART_CRM_KEY environment variable.
    """
    task_id = str(uuid.uuid4())
    _scrape_tasks[task_id] = {"status": "running", "started_at": datetime.now().isoformat()}

    async def run_fetch():
        try:
            client = IndiaMartCRMClient()
            leads = await client.fetch_leads(
                days=request.days,
                niche=request.niche,
            )
            await client.close()

            _scrape_tasks[task_id] = {
                "status": "completed",
                "leads_found": len(leads),
                "completed_at": datetime.now().isoformat(),
            }
            return [lead.to_dict() for lead in leads]

        except Exception as e:
            logger.error(f"IndiaMART fetch failed: {e}")
            _scrape_tasks[task_id] = {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now().isoformat(),
            }
            return []

    background_tasks.add_task(run_fetch)

    return [{"task_id": task_id, "status": "running", "message": "Fetch started"}]


@router.post("/whatsapp/capture", response_model=dict)
async def capture_whatsapp_lead(
    phone: str = Query(..., description="Sender's phone number"),
    message: str = Query(..., description="Message text"),
    contact_name: str | None = Query(None, description="Contact name"),
):
    """
    Capture lead from incoming WhatsApp message.

    Processes the message, extracts intent, and saves to lead database.
    """
    try:
        handler = WhatsAppLeadCaptureHandler()
        result = await handler.process_incoming_message(
            from_number=phone,
            message_body=message,
            contact_name=contact_name,
        )
        await handler.close()
        return result
    except Exception as e:
        logger.error(f"WhatsApp lead capture failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/github/search", response_model=list[dict])
async def search_github_projects(
    request: GitHubSearchRequest,
):
    """
    Search GitHub for open-source project leads.

    Useful for finding tech companies, SaaS projects, and potential customers.
    """
    try:
        hunter = GitHubLeadHunter()
        leads = await hunter.search_projects(
            query=request.query,
            sort=request.sort,
            per_page=request.per_page,
            max_pages=request.max_pages,
        )
        await hunter.close()
        return [lead.to_dict() for lead in leads]
    except Exception as e:
        logger.error(f"GitHub search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/github/tech-stack", response_model=list[dict])
async def search_by_tech_stack(
    request: GitHubTechRequest,
):
    """
    Search GitHub by programming language and star count.

    Finds active projects in a specific tech stack.
    """
    try:
        hunter = GitHubLeadHunter()
        leads = await hunter.search_by_tech_stack(
            language=request.language,
            min_stars=request.min_stars,
            sort="stars",
            limit=request.limit,
        )
        await hunter.close()
        return [lead.to_dict() for lead in leads]
    except Exception as e:
        logger.error(f"GitHub tech stack search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deduplicate", response_model=DedupResponse)
async def deduplicate_leads(request: DedupRequest):
    """
    Deduplicate leads from multiple sources.

    Normalizes phone numbers and emails, removes duplicates.
    """
    try:
        dedup = MultiSourceDeduplicator()
        unique_leads = dedup.deduplicate_leads(request.leads)
        stats = dedup.get_stats()

        return DedupResponse(
            unique_count=len(unique_leads),
            duplicate_count=request.leads.__len__() - len(unique_leads),
            leads=unique_leads,
            stats=stats,
        )
    except Exception as e:
        logger.error(f"Deduplication failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deduplicate/batch", response_model=DedupResponse)
async def deduplicate_batch(
    leads: list[dict] = Body(..., description="List of leads to deduplicate"),
):
    """Batch deduplication endpoint."""
    return await deduplicate_leads(DedupRequest(leads=leads))


# ============================================================================
# Celery Tasks
# ============================================================================

from celery import shared_task

from app.platform.celery_async import run as run_async


@shared_task(bind=True, max_retries=3)
def scrape_justdial_task(
    self,
    category: str,
    city: str,
    max_results: int = 100,
    use_apify: bool = True,
) -> dict:
    """
    Celery task for JustDial lead scraping.

    Uses Apify API if configured, otherwise local Playwright scraper.
    """
    try:
        if use_apify:
            client = JustDialApifyClient()
            leads = run_async(client.search_by_category(
                category=category,
                city=city,
                max_results=max_results,
            ))
            run_async(client.close())
        else:
            scraper = JustDialLocalScraper()
            leads = run_async(scraper.search_by_category(
                category=category,
                city=city,
                max_results=max_results,
            ))

        return {
            "status": "completed",
            "leads_found": len(leads),
            "niche": category,
            "city": city,
        }
    except Exception as e:
        logger.error(f"JustDial task failed: {e}")
        raise self.retry(exc=e, countdown=300)


@shared_task(bind=True, max_retries=2)
def fetch_indiamart_task(self, days: int = 7, niche: str = "general") -> dict:
    """Celery task for IndiaMART CRM lead fetching."""
    try:
        client = IndiaMartCRMClient()
        leads = run_async(client.fetch_leads(days=days, niche=niche))
        run_async(client.close())

        return {
            "status": "completed",
            "leads_found": len(leads),
            "days": days,
            "niche": niche,
        }
    except Exception as e:
        logger.error(f"IndiaMART task failed: {e}")
        raise self.retry(exc=e, countdown=600)


@shared_task
def search_github_task(query: str, sort: str = "stars", max_pages: int = 3) -> dict:
    """Celery task for GitHub project search."""
    try:
        hunter = GitHubLeadHunter()
        leads = run_async(hunter.search_projects(
            query=query,
            sort=sort,
            max_pages=max_pages,
        ))
        run_async(hunter.close())

        return {
            "status": "completed",
            "leads_found": len(leads),
            "query": query,
            "sort": sort,
        }
    except Exception as e:
        logger.error(f"GitHub task failed: {e}")
        return {"status": "failed", "error": str(e)}


@shared_task
def deduplicate_leads_task(leads: list[dict]) -> dict:
    """Celery task for lead deduplication."""
    try:
        dedup = MultiSourceDeduplicator()
        unique = dedup.deduplicate_leads(leads)
        stats = dedup.get_stats()

        return {
            "status": "completed",
            "unique_count": len(unique),
            "duplicate_count": stats["duplicates_removed"],
            "total_processed": stats["total_processed"],
        }
    except Exception as e:
        logger.error(f"Deduplication task failed: {e}")
        return {"status": "failed", "error": str(e)}


__all__ = [
    # Classes
    "JustDialApifyClient",
    "JustDialLocalScraper",
    "IndiaMartCRMClient",
    "WhatsAppLeadCaptureHandler",
    "GitHubLeadHunter",
    "MultiSourceDeduplicator",
    # Dataclasses
    "JustDialLead",
    "IndiaMartLead",
    "WhatsAppLeadCapture",
    "GitHubProjectLead",
    # Router
    "router",
    # Celery tasks
    "scrape_justdial_task",
    "fetch_indiamart_task",
    "search_github_task",
    "deduplicate_leads_task",
]
