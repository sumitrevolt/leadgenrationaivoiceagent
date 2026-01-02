"""
Unified Lead Scraper Manager
Coordinates multiple scraping sources
"""
import asyncio
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import json

from app.lead_scraper.google_maps import GoogleMapsScraper, BusinessLead
from app.lead_scraper.indiamart import IndiaMartScraper, IndiaMartLead
from app.lead_scraper.justdial import JustDialScraper, JustDialLead
from app.lead_scraper.linkedin import LinkedInScraper, LinkedInLead
from app.utils.logger import setup_logger
from app.utils.phone_validator import PhoneValidator

logger = setup_logger(__name__)


@dataclass
class UnifiedLead:
    """Unified lead format from all sources"""
    id: str
    company_name: str
    contact_name: Optional[str]
    phone: Optional[str]
    phone_verified: bool
    email: Optional[str]
    address: str
    city: str
    state: str
    country: str
    category: str
    source: str
    source_url: str
    rating: Optional[float]
    verified: bool
    scraped_at: datetime
    raw_data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['scraped_at'] = self.scraped_at.isoformat()
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
            "justdial": ["real estate agents", "builders", "property dealers"]
        },
        "solar": {
            "google_maps": ["solar panel installers", "solar energy companies"],
            "indiamart": ["solar panels", "solar installation services"],
            "justdial": ["solar panel dealers", "solar companies"]
        },
        "logistics": {
            "google_maps": ["logistics companies", "transport companies", "freight services"],
            "indiamart": ["logistics services", "transport services"],
            "justdial": ["logistics companies", "trucking services"]
        },
        "digital_marketing": {
            "google_maps": ["digital marketing agencies", "SEO companies"],
            "indiamart": ["digital marketing services"],
            "justdial": ["digital marketing", "SEO services"]
        },
        "manufacturing": {
            "google_maps": ["manufacturing companies", "factory"],
            "indiamart": ["manufacturers", "industrial equipment"],
            "justdial": ["manufacturers", "industrial suppliers"]
        },
        "insurance": {
            "google_maps": ["insurance brokers", "insurance agents"],
            "indiamart": ["insurance services", "insurance brokers"],
            "justdial": ["insurance agents", "insurance brokers"]
        }
    }
    
    # Major Indian cities for scraping
    INDIAN_CITIES = [
        "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
        "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
        "Surat", "Kanpur", "Nagpur", "Indore", "Thane",
        "Bhopal", "Visakhapatnam", "Patna", "Vadodara", "Ghaziabad"
    ]
    
    def __init__(self):
        self.google_maps = GoogleMapsScraper()
        self.indiamart = IndiaMartScraper()
        self.justdial = JustDialScraper()
        self.linkedin = LinkedInScraper()
        self.phone_validator = PhoneValidator()
        logger.info("🔍 Lead Scraper Manager initialized")
    
    async def scrape_leads(
        self,
        niche: str,
        cities: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        max_leads: int = 500,
        validate_phones: bool = True
    ) -> List[UnifiedLead]:
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
        sources = sources or ["google_maps", "indiamart", "justdial"]
        
        logger.info(f"Starting lead scrape - Niche: {niche}, Cities: {len(cities)}, Sources: {sources}")
        
        all_leads = []
        queries = self.NICHE_QUERIES.get(niche, {})
        
        # Calculate leads per source/city
        leads_per_source = max_leads // len(sources)
        leads_per_city = leads_per_source // len(cities)
        
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
        unique_leads.sort(key=lambda x: (
            x.phone is not None,
            x.verified,
            x.rating or 0
        ), reverse=True)
        
        logger.info(f"✅ Scraped {len(unique_leads)} unique leads")
        return unique_leads[:max_leads]
    
    async def _scrape_google_maps(
        self,
        query: str,
        cities: List[str],
        max_per_city: int
    ) -> List[UnifiedLead]:
        """Scrape from Google Maps"""
        leads = []
        
        for city in cities:
            try:
                raw_leads = await self.google_maps.search_businesses(
                    query=query,
                    location=city,
                    max_results=max_per_city
                )
                
                for raw in raw_leads:
                    leads.append(self._convert_google_maps_lead(raw))
                    
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Google Maps error for {city}: {e}")
        
        return leads
    
    async def _scrape_indiamart(
        self,
        query: str,
        cities: List[str],
        max_per_city: int
    ) -> List[UnifiedLead]:
        """Scrape from IndiaMart"""
        leads = []
        
        for city in cities:
            try:
                raw_leads = await self.indiamart.search_businesses(
                    query=query,
                    city=city,
                    max_results=max_per_city
                )
                
                for raw in raw_leads:
                    leads.append(self._convert_indiamart_lead(raw))
                    
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"IndiaMart error for {city}: {e}")
        
        return leads
    
    async def _scrape_justdial(
        self,
        query: str,
        cities: List[str],
        max_per_city: int
    ) -> List[UnifiedLead]:
        """Scrape from JustDial"""
        leads = []
        
        for city in cities:
            try:
                raw_leads = await self.justdial.search_businesses(
                    category=query,
                    city=city,
                    max_results=max_per_city
                )
                
                for raw in raw_leads:
                    leads.append(self._convert_justdial_lead(raw))
                    
                await asyncio.sleep(3)
                
            except Exception as e:
                logger.error(f"JustDial error for {city}: {e}")
        
        return leads
    
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
            raw_data=asdict(raw)
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
            raw_data=asdict(raw)
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
            raw_data=asdict(raw)
        )
    
    def _deduplicate_leads(self, leads: List[UnifiedLead]) -> List[UnifiedLead]:
        """Remove duplicate leads based on phone or company name"""
        seen_phones = set()
        seen_companies = set()
        unique = []
        
        for lead in leads:
            # Normalize phone
            phone_key = None
            if lead.phone:
                phone_key = ''.join(filter(str.isdigit, lead.phone))[-10:]
            
            # Normalize company name
            company_key = lead.company_name.lower().strip()
            
            # Check for duplicates
            is_duplicate = False
            
            if phone_key and phone_key in seen_phones:
                is_duplicate = True
            elif company_key in seen_companies:
                is_duplicate = True
            
            if not is_duplicate:
                unique.append(lead)
                if phone_key:
                    seen_phones.add(phone_key)
                seen_companies.add(company_key)
        
        return unique
    
    async def _validate_phones(self, leads: List[UnifiedLead]) -> List[UnifiedLead]:
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
        self,
        leads: List[UnifiedLead],
        format: str = "json",
        filename: Optional[str] = None
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
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        elif format == "csv":
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                if leads:
                    writer = csv.DictWriter(f, fieldnames=[
                        'company_name', 'contact_name', 'phone', 'email',
                        'city', 'state', 'category', 'source', 'rating', 'verified'
                    ])
                    writer.writeheader()
                    for lead in leads:
                        writer.writerow({
                            'company_name': lead.company_name,
                            'contact_name': lead.contact_name or '',
                            'phone': lead.phone or '',
                            'email': lead.email or '',
                            'city': lead.city,
                            'state': lead.state,
                            'category': lead.category,
                            'source': lead.source,
                            'rating': lead.rating or '',
                            'verified': lead.verified
                        })
        
        logger.info(f"Exported {len(leads)} leads to {filename}")
        return filename
