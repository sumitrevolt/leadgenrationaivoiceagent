"""
Google Maps Scraper
Scrapes business leads from Google Maps
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class PlacesQuotaExhausted(Exception):
    """Places API quota throttle hua; fallback paths run nahi karne hain."""


@dataclass
class BusinessLead:
    """Scraped business lead data"""

    name: str
    phone: str | None
    email: str | None
    address: str
    city: str
    state: str
    category: str
    rating: float | None
    reviews_count: int
    website: str | None
    google_maps_url: str
    place_id: str
    latitude: float
    longitude: float
    source: str = "google_maps"
    # Optional Places quality signals; legacy/browser constructors stay valid.
    primary_type: str = ""
    types: tuple[str, ...] = ()
    business_status: str = ""


class GoogleMapsScraper:
    """
    Scrapes business listings from Google Maps
    Uses both official API and web scraping as fallback
    """

    def __init__(self):
        self.api_key = settings.google_maps_api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place"
        self.use_proxy = settings.use_proxy
        self.proxy_url = settings.proxy_url
        logger.info("🗺️ Google Maps Scraper initialized")

    async def search_businesses(
        self, query: str, location: str, radius_km: int = 50, max_results: int = 100
    ) -> list[BusinessLead]:
        """
        Search for businesses on Google Maps

        Args:
            query: Search query (e.g., "real estate developers", "solar installers")
            location: City/area name (e.g., "Mumbai", "Delhi NCR")
            radius_km: Search radius in kilometers
            max_results: Maximum number of results to return
        """
        logger.info(f"Searching: '{query}' in '{location}'")

        if self.api_key:
            try:
                from app.platform.integration_health import places_quota_cooldown_remaining

                remaining = places_quota_cooldown_remaining()
            except Exception:
                remaining = 0
            if remaining:
                logger.warning("Places quota cooldown active (%ss); search skipped", remaining)
                return []
            # Places API (New) pehle — legacy textsearch ab REQUEST_DENIED deta hai
            # (Google ne naye projects pe legacy band kar di). New fail ho to
            # legacy try, phir scraping.
            try:
                leads = await self._search_with_places_new(query, location, max_results)
            except PlacesQuotaExhausted:
                return []
            if leads:
                return leads
            try:
                return await self._search_with_api(query, location, radius_km, max_results)
            except Exception as e:
                logger.warning(f"legacy Places API failed ({e}); scraping fallback")
                return await self._search_with_scraping(query, location, max_results)
        else:
            return await self._search_with_scraping(query, location, max_results)

    async def _search_with_places_new(
        self, query: str, location: str, max_results: int
    ) -> list[BusinessLead]:
        """Google Places API (New) — POST places:searchText. Returns phone +
        rating + reviews + website + address in ONE call (no separate details).
        Never raises — [] on any failure (caller falls back)."""
        url = "https://places.googleapis.com/v1/places:searchText"
        field_mask = (
            "places.displayName,places.nationalPhoneNumber,"
            "places.internationalPhoneNumber,places.rating,places.userRatingCount,"
            "places.formattedAddress,places.websiteUri,places.id,"
            "places.primaryType,places.types,places.businessStatus,"
            "nextPageToken"  # MUST be in mask or Places API (New) omits it → pagination dead (capped at 20/query)
        )
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }
        leads: list[BusinessLead] = []
        had_successful_response = False
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                page_token = None
                while len(leads) < max_results:
                    body: dict[str, Any] = {
                        "textQuery": f"{query} in {location}",
                        "maxResultCount": min(20, max_results - len(leads)),
                        "regionCode": "IN",
                    }
                    if page_token:
                        body["pageToken"] = page_token
                    resp = await client.post(url, headers=headers, json=body, timeout=30.0)
                    if resp.status_code != 200:
                        logger.warning(f"Places(New) HTTP {resp.status_code}: {resp.text[:160]}")
                        # "places" is in integration_health.KNOWN but was never
                        # instrumented — a dead/expired key was invisible on the
                        # integrations dashboard (audit 2026-07-04).
                        try:
                            from app.platform.integration_health import record_failure

                            record_failure("places", f"http_{resp.status_code}")
                        except Exception:
                            pass
                        if resp.status_code == 429:
                            try:
                                from app.platform.integration_health import (
                                    start_places_quota_cooldown,
                                )

                                start_places_quota_cooldown()
                            except Exception:
                                pass
                            raise PlacesQuotaExhausted("Places API quota exhausted")
                        break
                    had_successful_response = True
                    data = resp.json()
                    places = data.get("places", []) or []
                    for p in places:
                        try:
                            name = (p.get("displayName") or {}).get("text", "").strip()
                            if not name:
                                continue
                            leads.append(
                                BusinessLead(
                                    name=name,
                                    phone=p.get("nationalPhoneNumber")
                                    or p.get("internationalPhoneNumber"),
                                    email=None,
                                    address=p.get("formattedAddress", ""),
                                    city=location,
                                    state="",
                                    category=query,
                                    rating=p.get("rating"),
                                    reviews_count=p.get("userRatingCount") or 0,
                                    website=p.get("websiteUri"),
                                    google_maps_url=f"https://www.google.com/maps/place/?q=place_id:{p.get('id', '')}",
                                    place_id=p.get("id", ""),
                                    latitude=0.0,
                                    longitude=0.0,
                                    primary_type=str(p.get("primaryType") or ""),
                                    types=tuple(str(t) for t in (p.get("types") or [])),
                                    business_status=str(p.get("businessStatus") or ""),
                                )
                            )
                        except Exception:
                            continue
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
                    await asyncio.sleep(2)  # token activation delay
        except PlacesQuotaExhausted:
            raise
        except Exception as e:
            logger.warning(f"Places(New) search failed: {e}")
            try:
                from app.platform.integration_health import record_failure

                record_failure("places", str(e)[:80])
            except Exception:
                pass
            return []
        if had_successful_response:
            try:
                from app.platform.integration_health import record_success

                record_success("places")
            except Exception:
                pass
        logger.info(f"Found {len(leads)} businesses via Places API (New)")
        return leads[:max_results]

    async def _search_with_api(
        self, query: str, location: str, radius_km: int, max_results: int
    ) -> list[BusinessLead]:
        """Search using official Google Places API"""

        # First, geocode the location
        coords = await self._geocode_location(location)
        if not coords:
            logger.error(f"Could not geocode location: {location}")
            return []

        leads = []
        next_page_token = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(leads) < max_results:
                params = {
                    "query": f"{query} in {location}",
                    "location": f"{coords['lat']},{coords['lng']}",
                    "radius": radius_km * 1000,  # Convert to meters
                    "key": self.api_key,
                }

                if next_page_token:
                    params["pagetoken"] = next_page_token

                response = await client.get(
                    f"{self.base_url}/textsearch/json", params=params, timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "OK":
                    logger.warning(f"API returned status: {data.get('status')}")
                    break

                for place in data.get("results", []):
                    lead = await self._place_to_lead(place)
                    if lead:
                        leads.append(lead)

                next_page_token = data.get("next_page_token")
                if not next_page_token:
                    break

                # API requires delay before using next_page_token
                await asyncio.sleep(2)

        logger.info(f"Found {len(leads)} businesses via Google API")
        return leads[:max_results]

    async def _place_to_lead(self, place: dict[str, Any]) -> BusinessLead | None:
        """Convert Google Places result to BusinessLead"""
        try:
            place_id = place.get("place_id", "")

            # Get detailed info including phone number
            details = await self._get_place_details(place_id)

            address_parts = place.get("formatted_address", "").split(", ")
            city = address_parts[-3] if len(address_parts) >= 3 else ""
            state = address_parts[-2] if len(address_parts) >= 2 else ""

            # Clean state (remove postal code)
            state = re.sub(r"\d+", "", state).strip()

            # Rating/reviews: textsearch `place` usually has them; fall back to
            # Place Details if missing.
            rating = place.get("rating")
            if rating is None:
                rating = details.get("rating")
            reviews_count = place.get("user_ratings_total")
            if reviews_count is None:
                reviews_count = details.get("user_ratings_total", 0)

            return BusinessLead(
                name=place.get("name", ""),
                phone=details.get("formatted_phone_number")
                or details.get("international_phone_number"),
                email=await self._extract_email_from_website(details.get("website")),
                address=place.get("formatted_address", ""),
                city=city,
                state=state,
                category=", ".join(place.get("types", [])[:3]),
                rating=rating,
                reviews_count=reviews_count or 0,
                website=details.get("website"),
                google_maps_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}",
                place_id=place_id,
                latitude=place.get("geometry", {}).get("location", {}).get("lat", 0),
                longitude=place.get("geometry", {}).get("location", {}).get("lng", 0),
                primary_type=str(place.get("types", [""])[0] if place.get("types") else ""),
                types=tuple(str(t) for t in (place.get("types") or [])),
                business_status=str(place.get("business_status") or ""),
            )
        except Exception as e:
            logger.error(f"Error parsing place: {e}")
            return None

    async def _get_place_details(self, place_id: str) -> dict[str, Any]:
        """Get detailed place information including phone number"""
        if not self.api_key:
            return {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/details/json",
                params={
                    "place_id": place_id,
                    "fields": (
                        "formatted_phone_number,international_phone_number,"
                        "website,email,rating,user_ratings_total"
                    ),
                    "key": self.api_key,
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result", {})

    async def _geocode_location(self, location: str) -> dict[str, float] | None:
        """Convert location name to coordinates.

        Bare city names ("Thane", "Aurangabad") ambiguous/ZERO_RESULTS de sakte
        (live 2026-07-06 — poori city ke prospects silently skip) → miss pe
        ", India" bias ke saath ek retry.
        """
        coords = await self._geocode_once(location)
        if coords is None and location and "india" not in location.lower():
            coords = await self._geocode_once(f"{location}, India")
        return coords

    async def _geocode_once(self, location: str) -> dict[str, float] | None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": location, "key": self.api_key},
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK":
                # status log = triage-able (ZERO_RESULTS vs OVER_QUERY_LIMIT vs
                # REQUEST_DENIED alag-alag fix maangte)
                logger.warning(f"Geocode non-OK for {location!r}: {data.get('status')}")
            if data.get("status") == "OK" and data.get("results"):
                geometry = data["results"][0].get("geometry", {})
                location_data = geometry.get("location", {})
                lat, lng = location_data.get("lat"), location_data.get("lng")
                # Only return real coords — otherwise the caller would build a
                # "None,None" location string and waste a Google API call.
                if lat is not None and lng is not None:
                    return {"lat": lat, "lng": lng}
            return None

    # Regex for harvesting email addresses from page HTML
    _EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    _EMAIL_JUNK = ("example.com", "sentry", ".png", ".jpg", ".jpeg", ".gif", "wix.com")

    async def _extract_email_from_website(self, website: str | None) -> str | None:
        """
        Fetch a business website and extract the first non-junk email address.

        Prefers the centralized extractor (app.lead_scraper.web_extract —
        trafilatura-backed, de-duplicated + validated); falls back to the inline
        regex. Filters out placeholder/asset-embedded addresses. Returns None if
        the site is unreachable or no usable email is found.
        """
        if not website:
            return None

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                response = await client.get(
                    website,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                        )
                    },
                )
                if response.status_code != 200:
                    return None

                html = response.text

                # Preferred: centralized extractor (dedup + validation, never raises).
                try:
                    from app.lead_scraper.web_extract import find_contacts

                    for candidate in find_contacts(html).get("emails", []):
                        if not any(junk in candidate for junk in self._EMAIL_JUNK):
                            return candidate
                except Exception:
                    pass

                # Fallback: inline regex.
                for match in self._EMAIL_RE.findall(html):
                    candidate = match.lower()
                    if any(junk in candidate for junk in self._EMAIL_JUNK):
                        continue
                    return match
        except Exception as e:
            logger.debug(f"Email extraction failed for {website}: {e}")

        return None

    async def _search_with_scraping(
        self, query: str, location: str, max_results: int
    ) -> list[BusinessLead]:
        """
        Fallback: Scrape Google Maps using browser automation
        Note: This is rate-limited and should be used carefully
        """
        logger.warning("Using web scraping fallback (no API key)")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run: pip install playwright && playwright install"
            )
            return []

        leads = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Navigate to Google Maps
            search_url = f"https://www.google.com/maps/search/{query}+in+{location}"
            await page.goto(search_url, timeout=60000)

            # Wait for results to load
            await page.wait_for_selector('div[role="feed"]', timeout=30000)

            # Scroll to load more results
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                for _ in range(min(5, max_results // 20)):  # Scroll a few times
                    await feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                    await asyncio.sleep(2)

            # Extract business listings
            listings = await page.query_selector_all('div[role="feed"] > div > div > a')

            for listing in listings[:max_results]:
                try:
                    href = await listing.get_attribute("href")
                    aria_label = await listing.get_attribute("aria-label")

                    if aria_label:
                        # Parse basic info from aria-label
                        lead = BusinessLead(
                            name=(
                                aria_label.split("·")[0].strip()
                                if "·" in aria_label
                                else aria_label
                            ),
                            phone=None,  # Would need to click through to get
                            email=None,
                            address="",
                            city=location,
                            state="",
                            category=query,
                            rating=None,
                            reviews_count=0,
                            website=None,
                            google_maps_url=href or "",
                            place_id="",
                            latitude=0,
                            longitude=0,
                        )
                        leads.append(lead)
                except Exception as e:
                    logger.debug(f"Error extracting listing: {e}")

            await browser.close()

        logger.info(f"Scraped {len(leads)} businesses from Google Maps")
        return leads

    async def search_by_category(
        self, category: str, cities: list[str], max_per_city: int = 50
    ) -> list[BusinessLead]:
        """
        Search for businesses in multiple cities

        Args:
            category: Business category to search
            cities: List of cities to search in
            max_per_city: Maximum results per city
        """
        all_leads = []

        for city in cities:
            try:
                leads = await self.search_businesses(
                    query=category, location=city, max_results=max_per_city
                )
                all_leads.extend(leads)

                # Rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error searching in {city}: {e}")

        logger.info(f"Total leads collected: {len(all_leads)}")
        return all_leads


# Legacy / pipeline alias — udyam_pipeline imports GoogleMapsClient.
# Without this, UDYAM Maps enrich ImportError'd forever and silently fell through to OSM.
GoogleMapsClient = GoogleMapsScraper
