"""
DND Checker
Check if phone numbers are on Do Not Disturb list
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class DNDCheckResult:
    """DND check result"""

    phone: str
    is_dnd: bool
    checked_at: datetime
    source: str
    category: str | None = None  # Full DND, Partial DND category
    verified: bool = True  # False = lookup failed/unverified -> compliance gate fails CLOSED


class DNDChecker:
    """
    Check phone numbers against DND (Do Not Disturb) registry

    India has NDNC (National Do Not Call) registry managed by TRAI.
    Calling DND numbers for marketing can result in penalties.

    This implementation:
    1. Local DND cache + opt-out ledger (always-on, authoritative for opt-outs)
    2. No external DND-lookup provider wired (Exotel removed 2026-06-18) — an
       un-cached number returns UNVERIFIED so the compliance gate fails CLOSED
       for promotional calls (TCCCPR-safe).
    3. Supports batch checking
    """

    # Cache DND results to reduce API calls
    _cache: dict[str, DNDCheckResult] = {}
    _cache_expiry: timedelta = timedelta(days=7)

    # Known DND prefixes (for quick filtering)
    KNOWN_DND_PREFIXES: set[str] = set()

    def __init__(self):
        # External DND-lookup provider removed (Exotel deprecated 2026-06-18).
        # Local cache + consent ledger remain the source of truth for opt-outs.
        pass

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

        # No external lookup provider — return unverified (gate fails CLOSED).
        result = await self._check_via_registry(phone)

        # Cache the result
        self._cache[phone] = result

        return result

    async def check_batch(
        self, phones: list[str], remove_dnd: bool = True
    ) -> dict[str, DNDCheckResult]:
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

            for phone, result in zip(uncached, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.error(f"DND check failed for ***{str(phone)[-4:]}: {result}")
                    # Not flagged DND, but UNVERIFIED (verified=False). Promotional gates
                    # (compliance.py, orchestrator_pipeline, filter_dnd) treat unverified as
                    # DND — so an error here = promotional BLOCK, not a pass. (2026-08-01:
                    # comment was "fail open for business continuity" — misleading; only
                    # confirmed non-DND numbers may be contacted. §5 TRAI fail-CLOSED.)
                    result = DNDCheckResult(
                        phone=phone,
                        is_dnd=False,
                        checked_at=datetime.now(),
                        source="error_fallback",
                        verified=False,
                    )
                results[phone] = result

        return results

    async def filter_dnd(self, phones: list[str]) -> list[str]:
        """
        Filter out DND numbers from a list

        Args:
            phones: List of phone numbers

        Returns:
            List of non-DND phone numbers

        FAIL-CLOSED (2026-08-01, enterprise-audit fix): unverified results
        (``verified=False`` — lookup error / no provider wired) ko non-DND maanna
        §5 TRAI invariant todta hai. Ab sirf PROVEN non-DND numbers pass hote hain.
        """
        results = await self.check_batch(phones)
        return [phone for phone, result in results.items() if result.verified and not result.is_dnd]

    async def _check_via_registry(self, phone: str) -> DNDCheckResult:
        """External DND lookup when configured; else carrier-delegated (Vobiz) or unverified.

        Vobiz scrubs NDNC on outbound path (docs.vobiz.ai/compliance/india/ucc).
        When ``DND_CARRIER_SCRUB=1`` + Vobiz creds, treat as verified (carrier scrubs).
        Without either, return UNVERIFIED → compliance gate fails CLOSED for promo.
        """
        url = (os.environ.get("DND_API_URL") or "").strip()
        key = (os.environ.get("DND_API_KEY") or "").strip()
        if url and key:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(
                        url,
                        json={"phone": phone, "api_key": key},
                        headers={"Authorization": f"Bearer {key}"},
                    )
                if resp.status_code == 200:
                    data = resp.json() if resp.content else {}
                    is_dnd = bool(
                        data.get("is_dnd")
                        or data.get("dnd")
                        or data.get("on_dnd")
                        or str(data.get("status", "")).lower() in ("dnd", "registered", "yes")
                    )
                    return DNDCheckResult(
                        phone=phone,
                        is_dnd=is_dnd,
                        checked_at=datetime.now(),
                        source="dnd_api",
                        verified=True,
                    )
            except Exception as e:
                logger.debug(f"DND API lookup failed for {phone[-4:]}: {e}")

        carrier_scrub = os.environ.get("DND_CARRIER_SCRUB", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        provider = (os.environ.get("TELEPHONY_PROVIDER") or "vobiz").strip().lower()
        vobiz_ok = bool(os.environ.get("VOBIZ_AUTH_ID") and os.environ.get("VOBIZ_AUTH_TOKEN"))
        if carrier_scrub and provider == "vobiz" and vobiz_ok:
            return DNDCheckResult(
                phone=phone,
                is_dnd=False,
                checked_at=datetime.now(),
                source="vobiz_carrier_scrub",
                verified=True,
            )

        return DNDCheckResult(
            phone=phone,
            is_dnd=False,
            checked_at=datetime.now(),
            source="no_provider",
            verified=False,
        )

    def _get_from_cache(self, phone: str) -> DNDCheckResult | None:
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
            phone=phone, is_dnd=True, checked_at=datetime.now(), source="local", category=category
        )

        logger.info(f"Added ***{str(phone)[-4:]} to local DND list: {category}")

    def remove_from_local_dnd(self, phone: str):
        """Remove a number from local DND list"""
        if phone in self._cache:
            del self._cache[phone]
            logger.info(f"Removed ***{str(phone)[-4:]} from local DND list")

    def export_local_dnd(self) -> list[dict]:
        """Export local DND list for backup"""
        return [
            {
                "phone": result.phone,
                "is_dnd": result.is_dnd,
                "checked_at": result.checked_at.isoformat(),
                "source": result.source,
                "category": result.category,
            }
            for result in self._cache.values()
            if result.is_dnd and result.source == "local"
        ]

    def import_local_dnd(self, data: list[dict]):
        """Import local DND list from backup"""
        for item in data:
            self._cache[item["phone"]] = DNDCheckResult(
                phone=item["phone"],
                is_dnd=True,
                checked_at=datetime.fromisoformat(item["checked_at"]),
                source="local",
                category=item.get("category"),
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
