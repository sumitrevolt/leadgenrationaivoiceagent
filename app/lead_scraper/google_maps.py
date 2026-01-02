"""
Google Maps Scraper
Scrapes business leads from Google Maps
"""
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import re
import json
import httpx

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class BusinessLead:
    """Scraped business lead data"""
    name: str
    phone: Optional[str]
    email: Optional[str]
    address: str
    city: str
    state: str
    category: str
    rating: Optional[float]
    reviews_count: int
    website: Optional[str]
    google_maps_url: str
    place_id: str
    latitude: float
    longitude: float
    source: str = "google_maps"


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
        self,
        query: str,
        location: str,
        radius_km: int = 50,
        max_results: int = 100
    ) -> List[BusinessLead]:
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
            return await self._search_with_api(query, location, radius_km, max_results)
        else:
            return await self._search_with_scraping(query, location, max_results)
    
    async def _search_with_api(
        self,
        query: str,
        location: str,
        radius_km: int,
        max_results: int
    ) -> List[BusinessLead]:
        """Search using official Google Places API"""
        
        # First, geocode the location
        coords = await self._geocode_location(location)
        if not coords:
            logger.error(f"Could not geocode location: {location}")
            return []
        
        leads = []
        next_page_token = None
        
        async with httpx.AsyncClient() as client:
            while len(leads) < max_results:
                params = {
                    "query": f"{query} in {location}",
                    "location": f"{coords['lat']},{coords['lng']}",
                    "radius": radius_km * 1000,  # Convert to meters
                    "key": self.api_key
                }
                
                if next_page_token:
                    params["pagetoken"] = next_page_token
                
                response = await client.get(
                    f"{self.base_url}/textsearch/json",
                    params=params,
                    timeout=30.0
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
    
    async def _place_to_lead(self, place: Dict[str, Any]) -> Optional[BusinessLead]:
        """Convert Google Places result to BusinessLead"""
        try:
            place_id = place.get("place_id", "")
            
            # Get detailed info including phone number
            details = await self._get_place_details(place_id)
            
            address_parts = place.get("formatted_address", "").split(", ")
            city = address_parts[-3] if len(address_parts) >= 3 else ""
            state = address_parts[-2] if len(address_parts) >= 2 else ""
            
            # Clean state (remove postal code)
            state = re.sub(r'\d+', '', state).strip()
            
            return BusinessLead(
                name=place.get("name", ""),
                phone=details.get("formatted_phone_number") or details.get("international_phone_number"),
                email=self._extract_email_from_website(details.get("website")),
                address=place.get("formatted_address", ""),
                city=city,
                state=state,
                category=", ".join(place.get("types", [])[:3]),
                rating=place.get("rating"),
                reviews_count=place.get("user_ratings_total", 0),
                website=details.get("website"),
                google_maps_url=f"https://www.google.com/maps/place/?q=place_id:{place_id}",
                place_id=place_id,
                latitude=place.get("geometry", {}).get("location", {}).get("lat", 0),
                longitude=place.get("geometry", {}).get("location", {}).get("lng", 0)
            )
        except Exception as e:
            logger.error(f"Error parsing place: {e}")
            return None
    
    async def _get_place_details(self, place_id: str) -> Dict[str, Any]:
        """Get detailed place information including phone number"""
        if not self.api_key:
            return {}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/details/json",
                params={
                    "place_id": place_id,
                    "fields": "formatted_phone_number,international_phone_number,website,email",
                    "key": self.api_key
                },
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result", {})
    
    async def _geocode_location(self, location: str) -> Optional[Dict[str, float]]:
        """Convert location name to coordinates"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": location,
                    "key": self.api_key
                },
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                geometry = data["results"][0].get("geometry", {})
                location_data = geometry.get("location", {})
                return {
                    "lat": location_data.get("lat"),
                    "lng": location_data.get("lng")
                }
            return None
    
    def _extract_email_from_website(self, website: Optional[str]) -> Optional[str]:
        """Try to extract email from website (placeholder for actual implementation)"""
        # This would require actually scraping the website
        # For now, return None
        return None
    
    async def _search_with_scraping(
        self,
        query: str,
        location: str,
        max_results: int
    ) -> List[BusinessLead]:
        """
        Fallback: Scrape Google Maps using browser automation
        Note: This is rate-limited and should be used carefully
        """
        logger.warning("Using web scraping fallback (no API key)")
        
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
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
                            name=aria_label.split("·")[0].strip() if "·" in aria_label else aria_label,
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
                            longitude=0
                        )
                        leads.append(lead)
                except Exception as e:
                    logger.debug(f"Error extracting listing: {e}")
            
            await browser.close()
        
        logger.info(f"Scraped {len(leads)} businesses from Google Maps")
        return leads
    
    async def search_by_category(
        self,
        category: str,
        cities: List[str],
        max_per_city: int = 50
    ) -> List[BusinessLead]:
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
                    query=category,
                    location=city,
                    max_results=max_per_city
                )
                all_leads.extend(leads)
                
                # Rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error searching in {city}: {e}")
        
        logger.info(f"Total leads collected: {len(all_leads)}")
        return all_leads
