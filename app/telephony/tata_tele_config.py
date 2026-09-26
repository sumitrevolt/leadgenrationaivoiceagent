"""
Tata Tele Channel Configuration
Manages 5 Tata Tele (SmartFlo) channels for outbound/inbound calls.

DID resolution (2026-09-24)
--------------------------
This module is the single owner of "which Tata SmartFlo DIDs exist".

Before 2026-09-24 the five channels below were a scaffold that only
``scripts/smartflo_channel_verify.py`` ever read: the dial path
(``app/telephony/trunks.py``) built exactly ONE trunk from the single
``TATA_SMARTFLO_DID`` env value. With five DIDs provisioned in the SmartFlo
portal the dialer still could not rotate across them, and the built-in
``+9180698797xx`` numbers were unreachable from any real call path — the
"5 channels" claim was config, not capability.

Now:
  * real DIDs come from env only: ``TATA_SMARTFLO_DID`` (slot 1),
    ``TATA_SMARTFLO_DID_2`` .. ``TATA_SMARTFLO_DID_5``, or the comma-separated
    ``TATA_SMARTFLO_DIDS``;
  * :func:`configured_dids` returns ordered, de-duplicated REAL DIDs and drops
    anything matching the built-in placeholder set, so a placeholder can never
    become a caller-ID;
  * a channel is ``active`` only when a real DID is bound to it. The previous
    hard-coded ``channel 1 = active`` was scaffolding — see
    ``docs/coordination/SMARTFLO_PORTAL_SETUP_SPEC_2026-09-22.md`` and
    ``deliverables/telegram-p0-20260923/SMARTFLO_P0_AUDIT.md`` ("status: active
    is NOT activation evidence").

Outbound window
---------------
``is_outbound_allowed`` used a naive ``datetime.now()`` (host-local clock) against
a second, hard-coded 09:00–20:00 window. On a UTC host that made the check wrong
by 5h30m and it could disagree with the compliance gate. It now delegates to the
single window authority (``app.telephony.compliance.effective_promo_window``,
clamped to TRAI 09:00–21:00) and evaluates it in IST. The owner's requested
09:00–20:00 window is armed by ``COMPLIANCE_PROMO_END=20:00`` (owner policy
decision — not defaulted here).

Nothing in this module logs or returns credential values; DIDs only.
"""

import logging
import os
from datetime import time
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# DID pool
# --------------------------------------------------------------------------

# The five numbers the scaffold ships with. They are DOCUMENTATION PLACEHOLDERS
# (they match the ``+9180698797{01..05}`` pattern asserted by
# ``scripts/smartflo_channel_verify.py``) and are never treated as real DIDs.
PLACEHOLDER_DIDS: tuple = tuple(f"+9180698797{i:02d}" for i in range(1, 6))

DID_ENV_SINGLE = "TATA_SMARTFLO_DID"
DID_ENV_SLOT_FMT = "TATA_SMARTFLO_DID_{n}"
DID_ENV_LIST = "TATA_SMARTFLO_DIDS"

# The licence bundles 5 channels; a longer env list must not silently inflate the
# dial pool. Extras are ignored (with one warning, values never printed).
MAX_DIDS = 5


def normalize_did(number: str) -> str:
    """Return the digits-only form of an Indian DID ('' when unusable).

    Accepts ``+918069879757``, ``918069879757``, ``08069879757`` and
    ``8069879757``; strips the 91 country code / leading 0. Never raises.
    """
    if not number:
        return ""
    try:
        digits = "".join(ch for ch in str(number).strip() if ch.isdigit())
    except Exception:
        return ""
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def is_placeholder_did(number: str) -> bool:
    """True when ``number`` is one of the built-in scaffold placeholders.

    Exact match (digit-normalized) — a real DID that merely shares the
    ``+9180698797`` prefix is NOT a placeholder.
    """
    digits = normalize_did(number)
    if not digits:
        return False
    return digits in {normalize_did(p) for p in PLACEHOLDER_DIDS}


def _env_raw(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def configured_dids() -> list[str]:
    """Ordered, de-duplicated REAL Tata SmartFlo DIDs from env. Never raises.

    Order: ``TATA_SMARTFLO_DID`` (slot 1) → ``TATA_SMARTFLO_DID_2..5`` →
    comma-separated ``TATA_SMARTFLO_DIDS``. Placeholders, malformed values and
    duplicates are dropped, so the returned list is always safe to use as a
    caller-ID pool. Values are returned as configured (unmodified, minus
    surrounding whitespace); comparison is on the digit-normalized form.
    """
    candidates: list[str] = []
    first = _env_raw(DID_ENV_SINGLE)
    if first:
        candidates.append(first)
    for slot in range(2, MAX_DIDS + 1):
        value = _env_raw(DID_ENV_SLOT_FMT.format(n=slot))
        if value:
            candidates.append(value)
    listed = _env_raw(DID_ENV_LIST)
    if listed:
        candidates.extend(part.strip() for part in listed.split(","))

    pool: list[str] = []
    seen: set = set()
    dropped_placeholders = 0
    dropped_invalid = 0
    for raw in candidates:
        if not raw:
            continue
        digits = normalize_did(raw)
        if not digits:
            dropped_invalid += 1
            continue
        if is_placeholder_did(raw):
            dropped_placeholders += 1
            continue
        if digits in seen:
            continue
        seen.add(digits)
        pool.append(raw)

    if dropped_placeholders or dropped_invalid:
        # Diagnostic counts only — never the values.
        logger.warning(
            "[tata-tele] DID pool ignored %d placeholder and %d malformed entr(ies)",
            dropped_placeholders,
            dropped_invalid,
        )
    if len(pool) > MAX_DIDS:
        logger.warning(
            "[tata-tele] DID pool truncated to %d (licence bundles %d channels)",
            MAX_DIDS,
            MAX_DIDS,
        )
        pool = pool[:MAX_DIDS]
    return pool


def _promo_window() -> tuple:
    """``('HH:MM', 'HH:MM')`` from the single compliance window authority."""
    try:
        from app.telephony.compliance import effective_promo_window

        return effective_promo_window()
    except Exception:
        return "09:00", "19:00"


def _hhmm_to_time(value: str, fallback: time) -> time:
    try:
        hour, minute = str(value).split(":")[:2]
        return time(int(hour), int(minute))
    except Exception:
        return fallback


def _ist_now_time() -> time:
    """Current wall-clock time in IST (the clock the TRAI window is defined in)."""
    from datetime import datetime

    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Kolkata")).time()
    except Exception:
        return datetime.now().time()


class TataTeleConfig:
    """Configuration for Tata Tele 5 channels"""

    def __init__(self):
        self.channels = self._load_config()
        start, end = _promo_window()
        self.outbound_start = _hhmm_to_time(start, time(9, 0))  # 9 AM IST
        self.outbound_end = _hhmm_to_time(end, time(19, 0))  # compliance default
        self.inbound_24_7 = True

    def _load_config(self) -> list[dict[str, Any]]:
        """Load channel configuration — a channel is active only with a real DID."""
        dids = configured_dids()
        channels = []

        for i in range(1, 6):
            bound = dids[i - 1] if i - 1 < len(dids) else ""
            channels.append(
                {
                    "id": f"tata_channel_{i}",
                    "number": bound or PLACEHOLDER_DIDS[i - 1],
                    "did_env": DID_ENV_SINGLE if i == 1 else DID_ENV_SLOT_FMT.format(n=i),
                    "is_placeholder": not bound,
                    # 'active' = a real DID is bound from env. Portal activation is
                    # a separate, owner-side fact this file cannot observe.
                    "status": "active" if bound else "pending",
                    "type": "trunk",
                    "capacity_per_hour": 10,
                    "daily_limit": 240,  # 10 calls/hour × 24 hours
                    "outbound_enabled": True,
                    "inbound_enabled": True,
                    "products": self._get_products_for_channel(i),
                }
            )

        return channels

    def _get_products_for_channel(self, channel_num: int) -> list[str]:
        """Assign products to channels"""
        product_map = {
            1: ["marketing_starter", "marketing_advanced"],  # LIVE
            2: ["voice_starter", "voice_band_a"],  # Coming
            3: ["marketing_advanced", "combo_starter"],  # Coming
            4: ["enterprise", "combo_pro"],  # Coming
            5: ["voice_band_b", "voice_band_c"]  # Coming
        }
        return product_map.get(channel_num, ["all"])

    def configured_dids(self) -> list[str]:
        """Real DIDs available to the dial path (same as module ``configured_dids()``)."""
        return configured_dids()

    def get_active_channels(self) -> list[dict[str, Any]]:
        """Get all channels with a REAL DID bound (portal activation is separate)"""
        return [c for c in self.channels if c["status"] == "active"]

    def get_pending_channels(self) -> list[dict[str, Any]]:
        """Get channels with no real DID bound yet (placeholders only)"""
        return [c for c in self.channels if c["status"] == "pending"]

    def get_total_capacity(self) -> int:
        """Get total daily call capacity"""
        active = self.get_active_channels()
        return sum(c["daily_limit"] for c in active)

    def get_capacity_by_product(self) -> dict[str, int]:
        """Get capacity breakdown by product"""
        capacity = {}
        for channel in self.get_active_channels():
            for product in channel["products"]:
                capacity[product] = capacity.get(product, 0) + channel["daily_limit"]
        return capacity

    def is_outbound_allowed(self, now_ist: time | None = None) -> bool:
        """Is outbound calling allowed right now?

        Evaluated in IST against the compliance window authority (TRAI-legal
        09:00–21:00, clamped there), so this can never disagree with the gate it
        mirrors. ``now_ist`` is injectable for tests.
        """
        try:
            current = now_ist or _ist_now_time()
            start, end = _promo_window()
            start_t = _hhmm_to_time(start, time(9, 0))
            end_t = _hhmm_to_time(end, time(19, 0))
            if start_t <= end_t:
                return start_t <= current <= end_t
            # Window crossing midnight (not expected for TRAI, handled anyway).
            return current >= start_t or current <= end_t
        except Exception:
            return False

    def get_revenue_potential(self) -> dict[str, Any]:
        """Calculate revenue potential from channels"""
        total_calls = self.get_total_capacity()
        conversion_rate = 0.05  # 5% conservative
        avg_order_value = 2990  # ₹2,990 blended ARPU

        daily_customers = int(total_calls * conversion_rate)
        daily_revenue = daily_customers * avg_order_value
        monthly_revenue = daily_revenue * 30

        return {
            "daily_calls": total_calls,
            "daily_customers": daily_customers,
            "daily_revenue": daily_revenue,
            "monthly_revenue": monthly_revenue,
            "conversion_rate": conversion_rate,
            "avg_order_value": avg_order_value
        }

    def update_channel_status(self, channel_id: str, status: str):
        """Update channel status (e.g., when new channel becomes live)"""
        for channel in self.channels:
            if channel["id"] == channel_id:
                channel["status"] = status
                logger.info(f"Updated channel {channel_id} status to {status}")
                return True
        return False

# Singleton instance
_tata_config = None

def get_tata_config() -> TataTeleConfig:
    """Get Tata Tele configuration singleton"""
    global _tata_config
    if _tata_config is None:
        _tata_config = TataTeleConfig()
    return _tata_config

def get_active_channel_count() -> int:
    """Get number of channels with a real DID bound"""
    return len(get_tata_config().get_active_channels())

def get_total_daily_capacity() -> int:
    """Get total daily call capacity"""
    return get_tata_config().get_total_capacity()

def get_revenue_potential() -> dict[str, Any]:
    """Get revenue potential from channels"""
    return get_tata_config().get_revenue_potential()


__all__ = [
    "MAX_DIDS",
    "PLACEHOLDER_DIDS",
    "DID_ENV_LIST",
    "DID_ENV_SINGLE",
    "DID_ENV_SLOT_FMT",
    "TataTeleConfig",
    "configured_dids",
    "get_active_channel_count",
    "get_revenue_potential",
    "get_tata_config",
    "get_total_daily_capacity",
    "is_placeholder_did",
    "normalize_did",
]
