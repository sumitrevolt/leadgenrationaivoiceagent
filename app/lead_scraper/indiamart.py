"""
IndiaMart Scraper
Scrapes B2B business leads from IndiaMart.com
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
class IndiaMartLead:
    """IndiaMart business lead"""
    company_name: str
    contact_person: str
    phone: Optional[str]
    mobile: Optional[str]
    email: Optional[str]
    address: str
    city: str
    state: str
    products: List[str]
    gst_number: Optional[str]
    year_established: Optional[int]
    employee_count: Optional[str]
    turnover: Optional[str]
    website: Optional[str]
    indiamart_url: str
    verified: bool
    trust_seal: bool
    source: str = "indiamart"


class IndiaMartScraper:
    """
    Scrapes B2B business listings from IndiaMart
    Great source for manufacturing, trading, and service companies
    """
    
    def __init__(self):
        self.base_url = "https://dir.indiamart.com"
        self.search_url = "https://www.indiamart.com/search.mp"
        self.use_proxy = settings.use_proxy
        self.proxy_url = settings.proxy_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        logger.info("📦 IndiaMart Scraper initialized")
    
    async def search_businesses(
        self,
        query: str,
        city: Optional[str] = None,
        max_results: int = 100
    ) -> List[IndiaMartLead]:
        """
        Search for businesses on IndiaMart
        
        Args:
            query: Product/service to search (e.g., "solar panels", "logistics services")
            city: Optional city filter
            max_results: Maximum results to return
        """
        logger.info(f"IndiaMart search: '{query}' in {city or 'All India'}")
        
        leads = []
        page = 1
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(leads) < max_results:
                try:
                    params = {
                        "ss": query,
                        "pg": page,
                    }
                    if city:
                        params["cq"] = city
                    
                    response = await client.get(
                        self.search_url,
                        params=params,
                        headers=self.headers,
                        follow_redirects=True
                    )
                    response.raise_for_status()
                    
                    page_leads = await self._parse_search_results(response.text)
                    if not page_leads:
                        break
                    
                    leads.extend(page_leads)
                    page += 1
                    
                    # Rate limiting
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error on page {page}: {e}")
                    break
        
        logger.info(f"Found {len(leads)} IndiaMart leads")
        return leads[:max_results]
    
    async def _parse_search_results(self, html: str) -> List[IndiaMartLead]:
        """Parse search results page"""
        leads = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all listing cards
        listings = soup.find_all('div', class_=re.compile(r'lst-li|prd-li'))
        
        for listing in listings:
            try:
                lead = await self._parse_listing(listing)
                if lead:
                    leads.append(lead)
            except Exception as e:
                logger.debug(f"Error parsing listing: {e}")
        
        return leads
    
    async def _parse_listing(self, listing) -> Optional[IndiaMartLead]:
        """Parse individual listing element"""
        try:
            # Company name
            name_elem = listing.find('a', class_=re.compile(r'lcname|company'))
            company_name = name_elem.text.strip() if name_elem else ""
            company_url = name_elem.get('href', '') if name_elem else ""
            
            # Contact person
            contact_elem = listing.find('span', class_='pname')
            contact_person = contact_elem.text.strip() if contact_elem else ""
            
            # Location
            loc_elem = listing.find('span', class_='loc')
            location = loc_elem.text.strip() if loc_elem else ""
            city = location.split(',')[0].strip() if location else ""
            state = location.split(',')[-1].strip() if ',' in location else ""
            
            # Products
            product_elems = listing.find_all('a', class_='prd')
            products = [p.text.strip() for p in product_elems] if product_elems else []
            
            # Verification status
            verified = listing.find('span', class_='verified') is not None
            trust_seal = listing.find('img', alt=re.compile('trust', re.I)) is not None
            
            # Phone (usually masked, need to extract from detail page)
            phone_elem = listing.find('span', class_=re.compile('phn|mobile'))
            phone = self._extract_phone(phone_elem.text) if phone_elem else None
            
            return IndiaMartLead(
                company_name=company_name,
                contact_person=contact_person,
                phone=phone,
                mobile=None,
                email=None,
                address=location,
                city=city,
                state=state,
                products=products,
                gst_number=None,
                year_established=None,
                employee_count=None,
                turnover=None,
                website=None,
                indiamart_url=company_url,
                verified=verified,
                trust_seal=trust_seal
            )
        except Exception as e:
            logger.debug(f"Error parsing listing: {e}")
            return None
    
    def _extract_phone(self, text: str) -> Optional[str]:
        """Extract phone number from text"""
        if not text:
            return None
        
        # Common patterns for Indian phone numbers
        patterns = [
            r'\+91[\s-]?\d{10}',
            r'0\d{10,11}',
            r'\d{10}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.replace(' ', ''))
            if match:
                return match.group()
        
        return None
    
    async def get_company_details(self, company_url: str) -> Dict[str, Any]:
        """Get detailed company information from profile page"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    company_url,
                    headers=self.headers,
                    follow_redirects=True
                )
                response.raise_for_status()
                
                return self._parse_company_page(response.text)
            except Exception as e:
                logger.error(f"Error fetching company details: {e}")
                return {}
    
    def _parse_company_page(self, html: str) -> Dict[str, Any]:
        """Parse company profile page for detailed info"""
        soup = BeautifulSoup(html, 'html.parser')
        details = {}
        
        # GST Number
        gst_elem = soup.find(text=re.compile('GST', re.I))
        if gst_elem:
            gst_match = re.search(r'\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}', gst_elem.parent.text)
            if gst_match:
                details['gst_number'] = gst_match.group()
        
        # Year established
        year_elem = soup.find(text=re.compile('Established|Since', re.I))
        if year_elem:
            year_match = re.search(r'\d{4}', year_elem.parent.text)
            if year_match:
                details['year_established'] = int(year_match.group())
        
        # Employee count
        emp_elem = soup.find(text=re.compile('Employees', re.I))
        if emp_elem:
            details['employee_count'] = emp_elem.parent.text.strip()
        
        # Contact info
        phone_elems = soup.find_all(class_=re.compile('phone|mobile|contact'))
        for elem in phone_elems:
            phone = self._extract_phone(elem.text)
            if phone:
                details['phone'] = phone
                break
        
        # Email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', soup.text)
        if email_match:
            details['email'] = email_match.group()
        
        return details
    
    async def search_by_category(
        self,
        category: str,
        cities: List[str],
        max_per_city: int = 50
    ) -> List[IndiaMartLead]:
        """
        Search for businesses across multiple cities
        """
        all_leads = []
        
        for city in cities:
            try:
                leads = await self.search_businesses(
                    query=category,
                    city=city,
                    max_results=max_per_city
                )
                all_leads.extend(leads)
                await asyncio.sleep(3)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error searching {city}: {e}")
        
        return all_leads
