"""
JustDial Scraper
Scrapes business leads from JustDial.com
"""
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import re
import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class JustDialLead:
    """JustDial business lead"""
    name: str
    phone: Optional[str]
    address: str
    city: str
    area: str
    category: str
    rating: Optional[float]
    votes: int
    timing: Optional[str]
    justdial_url: str
    verified: bool
    source: str = "justdial"


class JustDialScraper:
    """
    Scrapes business listings from JustDial
    Good source for local businesses across India
    """
    
    def __init__(self):
        self.base_url = "https://www.justdial.com"
        self.use_proxy = settings.use_proxy
        self.proxy_url = settings.proxy_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
        }
        logger.info("📞 JustDial Scraper initialized")
    
    async def search_businesses(
        self,
        category: str,
        city: str,
        area: Optional[str] = None,
        max_results: int = 100
    ) -> List[JustDialLead]:
        """
        Search for businesses on JustDial
        
        Args:
            category: Business category (e.g., "real estate agents", "solar panel dealers")
            city: City name (e.g., "Mumbai", "Delhi")
            area: Optional area within city
            max_results: Maximum results to return
        """
        logger.info(f"JustDial search: '{category}' in {city}")
        
        leads = []
        page = 1
        
        # Build URL
        city_slug = city.lower().replace(' ', '-')
        category_slug = category.lower().replace(' ', '-')
        base_search_url = f"{self.base_url}/{city_slug}/{category_slug}"
        
        if area:
            area_slug = area.lower().replace(' ', '-')
            base_search_url = f"{self.base_url}/{city_slug}/{category_slug}/{area_slug}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(leads) < max_results:
                try:
                    url = f"{base_search_url}/page-{page}" if page > 1 else base_search_url
                    
                    response = await client.get(
                        url,
                        headers=self.headers,
                        follow_redirects=True
                    )
                    
                    if response.status_code == 404:
                        break
                    
                    response.raise_for_status()
                    
                    page_leads = self._parse_search_results(response.text, city, category)
                    if not page_leads:
                        break
                    
                    leads.extend(page_leads)
                    page += 1
                    
                    # Rate limiting
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    logger.error(f"Error on page {page}: {e}")
                    break
        
        logger.info(f"Found {len(leads)} JustDial leads")
        return leads[:max_results]
    
    def _parse_search_results(
        self,
        html: str,
        city: str,
        category: str
    ) -> List[JustDialLead]:
        """Parse search results page"""
        leads = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all listing cards
        listings = soup.find_all('li', class_=re.compile('cntanr'))
        
        for listing in listings:
            try:
                lead = self._parse_listing(listing, city, category)
                if lead:
                    leads.append(lead)
            except Exception as e:
                logger.debug(f"Error parsing listing: {e}")
        
        return leads
    
    def _parse_listing(
        self,
        listing,
        city: str,
        category: str
    ) -> Optional[JustDialLead]:
        """Parse individual listing element"""
        try:
            # Business name
            name_elem = listing.find('span', class_='lng_cont_name')
            name = name_elem.text.strip() if name_elem else ""
            
            if not name:
                name_elem = listing.find('a', class_='lng_cont_name')
                name = name_elem.text.strip() if name_elem else ""
            
            # URL
            url_elem = listing.find('a', href=True)
            listing_url = url_elem['href'] if url_elem else ""
            if not listing_url.startswith('http'):
                listing_url = self.base_url + listing_url
            
            # Address
            addr_elem = listing.find('span', class_='cont_fl_addr')
            address = addr_elem.text.strip() if addr_elem else ""
            
            # Area extraction from address
            area = ""
            if address:
                # Usually format: "Area Name, City"
                parts = address.split(',')
                area = parts[0].strip() if parts else ""
            
            # Rating
            rating = None
            rating_elem = listing.find('span', class_=re.compile('green-box|rating'))
            if rating_elem:
                try:
                    rating = float(rating_elem.text.strip())
                except ValueError:
                    pass
            
            # Votes
            votes = 0
            votes_elem = listing.find('span', class_=re.compile('rt_count|votes'))
            if votes_elem:
                votes_match = re.search(r'\d+', votes_elem.text)
                votes = int(votes_match.group()) if votes_match else 0
            
            # Phone (JustDial encodes phone numbers)
            phone = self._decode_phone(listing)
            
            # Verified status
            verified = listing.find(class_=re.compile('verified|trusted')) is not None
            
            # Timing
            timing = None
            timing_elem = listing.find('span', class_='jdsptimings')
            if timing_elem:
                timing = timing_elem.text.strip()
            
            return JustDialLead(
                name=name,
                phone=phone,
                address=address,
                city=city,
                area=area,
                category=category,
                rating=rating,
                votes=votes,
                timing=timing,
                justdial_url=listing_url,
                verified=verified
            )
            
        except Exception as e:
            logger.debug(f"Error parsing JustDial listing: {e}")
            return None
    
    def _decode_phone(self, listing) -> Optional[str]:
        """
        Decode JustDial's obfuscated phone numbers
        JustDial uses CSS classes to hide actual numbers
        """
        # JustDial uses special fonts/classes to encode numbers
        # This is a simplified version - actual implementation may need browser automation
        phone_elem = listing.find('span', class_='mobilesv')
        
        if phone_elem:
            # The actual decoding requires mapping CSS classes to digits
            # This would need the CSS or JavaScript to properly decode
            # For now, return None and recommend using Playwright for accurate extraction
            pass
        
        return None
    
    async def search_by_category(
        self,
        category: str,
        cities: List[str],
        max_per_city: int = 50
    ) -> List[JustDialLead]:
        """
        Search for businesses across multiple cities
        """
        all_leads = []
        
        for city in cities:
            try:
                leads = await self.search_businesses(
                    category=category,
                    city=city,
                    max_results=max_per_city
                )
                all_leads.extend(leads)
                await asyncio.sleep(5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error searching {city}: {e}")
        
        return all_leads
    
    async def search_with_browser(
        self,
        category: str,
        city: str,
        max_results: int = 50
    ) -> List[JustDialLead]:
        """
        Use Playwright browser automation for accurate phone number extraction
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []
        
        leads = []
        city_slug = city.lower().replace(' ', '-')
        category_slug = category.lower().replace(' ', '-')
        url = f"{self.base_url}/{city_slug}/{category_slug}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.goto(url, timeout=60000)
            await page.wait_for_selector('.cntanr', timeout=30000)
            
            # Scroll to load more results
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
            
            # Extract listings with rendered phone numbers
            listings = await page.query_selector_all('.cntanr')
            
            for listing in listings[:max_results]:
                try:
                    name = await listing.query_selector('.lng_cont_name')
                    name_text = await name.inner_text() if name else ""
                    
                    # Phone number should be visible after JS rendering
                    phone_elem = await listing.query_selector('.mobilesv')
                    phone = await phone_elem.inner_text() if phone_elem else None
                    
                    address_elem = await listing.query_selector('.cont_fl_addr')
                    address = await address_elem.inner_text() if address_elem else ""
                    
                    leads.append(JustDialLead(
                        name=name_text,
                        phone=phone,
                        address=address,
                        city=city,
                        area="",
                        category=category,
                        rating=None,
                        votes=0,
                        timing=None,
                        justdial_url="",
                        verified=False
                    ))
                except Exception as e:
                    logger.debug(f"Error: {e}")
            
            await browser.close()
        
        return leads
