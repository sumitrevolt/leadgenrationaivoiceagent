"""
DND Checker
Check if phone numbers are on Do Not Disturb list
"""
import aiohttp
from typing import Optional, Dict, List, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio
import json

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class DNDCheckResult:
    """DND check result"""
    phone: str
    is_dnd: bool
    checked_at: datetime
    source: str
    category: Optional[str] = None  # Full DND, Partial DND category


class DNDChecker:
    """
    Check phone numbers against DND (Do Not Disturb) registry
    
    India has NDNC (National Do Not Call) registry managed by TRAI.
    Calling DND numbers for marketing can result in penalties.
    
    This implementation:
    1. Uses Exotel's DND check API (primary)
    2. Falls back to local cache
    3. Supports batch checking
    """
    
    # Cache DND results to reduce API calls
    _cache: Dict[str, DNDCheckResult] = {}
    _cache_expiry: timedelta = timedelta(days=7)
    
    # Known DND prefixes (for quick filtering)
    KNOWN_DND_PREFIXES: Set[str] = set()
    
    def __init__(self):
        self.api_key = settings.exotel_api_key
        self.api_token = settings.exotel_api_token
        self.sid = settings.exotel_sid
        self.base_url = f"https://api.exotel.com/v1/Accounts/{self.sid}"
    
    async def check_single(self, phone: str) -> DNDCheckResult:
        """
        Check if a single phone number is on DND
        
        Args:
            phone: Phone number to check
        
        Returns:
            DNDCheckResult with DND status
        """
        # Check cache first
        cached = self._get_from_cache(phone)
        if cached:
            return cached
        
        # Check via API
        result = await self._check_via_exotel(phone)
        
        # Cache the result
        self._cache[phone] = result
        
        return result
    
    async def check_batch(
        self,
        phones: List[str],
        remove_dnd: bool = True
    ) -> Dict[str, DNDCheckResult]:
        """
        Check multiple phone numbers
        
        Args:
            phones: List of phone numbers
            remove_dnd: If True, filter out DND numbers
        
        Returns:
            Dict mapping phone to DNDCheckResult
        """
        results = {}
        uncached = []
        
        # Check cache first
        for phone in phones:
            cached = self._get_from_cache(phone)
            if cached:
                results[phone] = cached
            else:
                uncached.append(phone)
        
        # Check uncached numbers via API
        if uncached:
            # Batch check (5 concurrent)
            semaphore = asyncio.Semaphore(5)
            
            async def check_with_semaphore(p):
                async with semaphore:
                    return await self.check_single(p)
            
            tasks = [check_with_semaphore(p) for p in uncached]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for phone, result in zip(uncached, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"DND check failed for {phone}: {result}")
                    # Assume not DND on error (fail open for business continuity)
                    result = DNDCheckResult(
                        phone=phone,
                        is_dnd=False,
                        checked_at=datetime.now(),
                        source="error_fallback"
                    )
                results[phone] = result
        
        return results
    
    async def filter_dnd(self, phones: List[str]) -> List[str]:
        """
        Filter out DND numbers from a list
        
        Args:
            phones: List of phone numbers
        
        Returns:
            List of non-DND phone numbers
        """
        results = await self.check_batch(phones)
        return [phone for phone, result in results.items() if not result.is_dnd]
    
    async def _check_via_exotel(self, phone: str) -> DNDCheckResult:
        """Check DND status via Exotel API"""
        try:
            # Clean phone number
            clean_phone = phone.replace('+', '').replace(' ', '').replace('-', '')
            if not clean_phone.startswith('91'):
                clean_phone = '91' + clean_phone[-10:]
            
            url = f"{self.base_url}/Numbers/{clean_phone}"
            
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(self.api_key, self.api_token)
                
                async with session.get(url, auth=auth) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Parse Exotel response
                        number_info = data.get('Number', {})
                        dnd_status = number_info.get('DND', 'No')
                        
                        is_dnd = dnd_status.lower() in ['yes', 'true', 'full']
                        
                        return DNDCheckResult(
                            phone=phone,
                            is_dnd=is_dnd,
                            checked_at=datetime.now(),
                            source="exotel",
                            category=dnd_status if is_dnd else None
                        )
                    else:
                        logger.warning(f"Exotel DND check returned {response.status} for {phone}")
                        
        except Exception as e:
            logger.error(f"Exotel DND check error for {phone}: {e}")
        
        # Fallback: Assume not DND
        return DNDCheckResult(
            phone=phone,
            is_dnd=False,
            checked_at=datetime.now(),
            source="fallback"
        )
    
    def _get_from_cache(self, phone: str) -> Optional[DNDCheckResult]:
        """Get result from cache if not expired"""
        result = self._cache.get(phone)
        
        if result:
            age = datetime.now() - result.checked_at
            if age < self._cache_expiry:
                return result
            else:
                # Expired, remove from cache
                del self._cache[phone]
        
        return None
    
    def add_to_local_dnd(self, phone: str, category: str = "user_request"):
        """
        Add a number to local DND list (user opt-out)
        
        Args:
            phone: Phone number
            category: Reason for DND
        """
        self._cache[phone] = DNDCheckResult(
            phone=phone,
            is_dnd=True,
            checked_at=datetime.now(),
            source="local",
            category=category
        )
        
        logger.info(f"Added {phone} to local DND list: {category}")
    
    def remove_from_local_dnd(self, phone: str):
        """Remove a number from local DND list"""
        if phone in self._cache:
            del self._cache[phone]
            logger.info(f"Removed {phone} from local DND list")
    
    def export_local_dnd(self) -> List[Dict]:
        """Export local DND list for backup"""
        return [
            {
                "phone": result.phone,
                "is_dnd": result.is_dnd,
                "checked_at": result.checked_at.isoformat(),
                "source": result.source,
                "category": result.category
            }
            for result in self._cache.values()
            if result.is_dnd and result.source == "local"
        ]
    
    def import_local_dnd(self, data: List[Dict]):
        """Import local DND list from backup"""
        for item in data:
            self._cache[item["phone"]] = DNDCheckResult(
                phone=item["phone"],
                is_dnd=True,
                checked_at=datetime.fromisoformat(item["checked_at"]),
                source="local",
                category=item.get("category")
            )
        
        logger.info(f"Imported {len(data)} numbers to local DND list")
    
    @classmethod
    def get_compliance_message(cls) -> str:
        """Get compliance message for calls"""
        return (
            "This is an automated promotional call. "
            "If you do not wish to receive such calls, "
            "press 9 to be added to our do-not-call list."
        )
    
    @classmethod
    def get_hindi_compliance_message(cls) -> str:
        """Get compliance message in Hindi"""
        return (
            "Yeh ek automated promotional call hai. "
            "Agar aap aisi calls nahi chahte, "
            "toh 9 dabaiye aur hum aapko apni list se hata denge."
        )
