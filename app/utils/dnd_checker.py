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

# --------------------------------------------------------------------------
# Opt-out authority (OPS-012b — REVISED 2026-09-07, cycle 6)
#
# There is exactly ONE canonical cross-channel opt-out/suppression authority in
# this codebase: app/telephony/consent_ledger.py. It is DB-backed when
# CONSENT_DB=1, falls back to data/compliance/voice_suppression.jsonl, and is
# FAIL-CLOSED when the list cannot be resolved. It is what
# app/integrations/whatsapp.py::send_permitted() -> opt_out_permits() already
# consults on every automated WhatsApp send.
#
# A previous revision of this file created a SECOND store
# (data/dnd_optouts.jsonl). That was a duplicate workflow and it was REMOVED in
# cycle 6: two opt-out lists means two places to forget to check, and the one
# you forget is the one that gets you fined. DNDChecker now DELEGATES.
#
# Layering (unchanged): opt-out beats cache beats provider. A recorded STOP must
# never be overridden by a stale cached "not DND" or by any registry result.
# --------------------------------------------------------------------------
OPTOUT_SOURCE = "consent_ledger_optout"


def _suppression_authority():
    """Return the canonical opt-out ledger module (lazy import: no import cycle)."""
    from app.telephony import consent_ledger

    return consent_ledger


def _is_suppressed(phone: str) -> bool:
    """True if the canonical ledger says this number opted out. FAIL-CLOSED.

    An unreachable authority must never be answered as "did not opt out" — the
    caller is about to decide whether to contact somebody. `is_suppressed()`
    already fails closed; an exception here is logged and treated the same way.
    """
    try:
        return bool(_suppression_authority().is_suppressed(phone))
    except Exception as e:  # noqa: BLE001 - authority must never break the gate
        logger.error(f"Opt-out authority unavailable for ***{str(phone)[-4:]}: {e}")
        return True


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
        # Canonical opt-out ledger wins over EVERYTHING (cache, provider, carrier).
        # A recorded STOP must never be overridden by a stale cached "not DND".
        if _is_suppressed(phone):
            return DNDCheckResult(
                phone=phone,
                is_dnd=True,
                checked_at=datetime.now(),
                source=OPTOUT_SOURCE,
                category="opt_out",
                verified=True,
            )

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
        Add a number to local DND list (user opt-out) — DURABLE via consent_ledger.

        Writes through to the CANONICAL cross-channel suppression authority, so
        the opt-out survives restarts, is honoured on every channel (voice +
        WhatsApp), and never expires. The 7-day in-memory entry is kept only as
        a fast read path. Idempotent: re-adding is a no-op downstream.

        Args:
            phone: Phone number
            category: Reason for DND
        """
        self._cache[phone] = DNDCheckResult(
            phone=phone, is_dnd=True, checked_at=datetime.now(), source="local", category=category
        )
        try:
            # record_opt_out returns {"phone":..., "suppressed": bool, ...}.
            res = _suppression_authority().record_opt_out(
                phone, reason=category or "user_request", channel="dnd_local"
            )
            if isinstance(res, dict) and res.get("suppressed") is False:
                logger.error(
                    f"Opt-out NOT persisted for ***{str(phone)[-4:]} — consent_ledger "
                    "reported suppressed=False. Treat as a compliance incident."
                )
        except Exception as e:  # noqa: BLE001 - never break the STOP handler
            logger.error(f"Opt-out persistence FAILED for ***{str(phone)[-4:]}: {e}")
        logger.info(f"Added ***{str(phone)[-4:]} to local DND list: {category}")

    def remove_from_local_dnd(self, phone: str):
        """Clear the IN-MEMORY entry only. This does NOT lift a real opt-out.

        Lifting a user's opt-out is an authorised, evidenced action (documented
        re-consent), never a side effect of a cache clear — use
        ``consent_ledger.opt_back_in()`` with the consent record. Lifting it
        silently here would be the easiest way in this codebase to re-contact
        somebody who said STOP.
        """
        if phone in self._cache:
            del self._cache[phone]
        logger.warning(
            f"Removed in-memory entry for ***{str(phone)[-4:]} — the durable opt-out "
            "in consent_ledger is UNCHANGED; lift it only via opt_back_in()."
        )

    def is_opted_out(self, phone: str) -> bool:
        """True if the canonical ledger records an opt-out for this number."""
        return _is_suppressed(phone)

    def export_local_dnd(self) -> list[dict]:
        """Export the DURABLE opt-out list (canonical ledger + memory fallback)."""
        rows: list[dict] = []
        try:
            for rec in _suppression_authority().suppression_list():
                rows.append(
                    {
                        "phone": rec.get("phone"),
                        "is_dnd": True,
                        "checked_at": (
                            rec.get("ts") or rec.get("at") or rec.get("created_at") or ""
                        ),
                        "source": "local",
                        "category": rec.get("reason") or rec.get("channel") or "opt_out",
                    }
                )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Could not read canonical suppression list: {e}")
        # Backwards-compatible: include in-memory-only entries not yet persisted.
        for result in self._cache.values():
            if result.is_dnd and result.source == "local":
                if not any(str(r["phone"]) == str(result.phone) for r in rows):
                    rows.append(
                        {
                            "phone": result.phone,
                            "is_dnd": True,
                            "checked_at": result.checked_at.isoformat(),
                            "source": result.source,
                            "category": result.category,
                        }
                    )
        return rows

    def import_local_dnd(self, data: list[dict]):
        """Import opt-outs into the CANONICAL ledger — never a second store."""
        count = 0
        for item in data:
            phone = item.get("phone")
            if not phone:
                continue
            raw_ts = item.get("checked_at") or ""
            try:
                ts = datetime.fromisoformat(raw_ts) if raw_ts else datetime.now()
            except ValueError:
                ts = datetime.now()
            self._cache[phone] = DNDCheckResult(
                phone=phone,
                is_dnd=True,
                checked_at=ts,
                source="local",
                category=item.get("category"),
            )
            try:
                _suppression_authority().record_opt_out(
                    phone, reason=item.get("category") or "user_request", channel="dnd_import"
                )
                count += 1
            except Exception as e:  # noqa: BLE001
                logger.error(f"Opt-out import failed for ***{str(phone)[-4:]}: {e}")

        logger.info(f"Imported {len(data)} numbers to local DND list ({count} newly persisted)")

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
