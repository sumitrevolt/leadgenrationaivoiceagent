"""
Tata Tele Smartflo Click-to-Call Handler
=========================================

Tata Teleservices Smartflo Pro Plan (₹1,250/license/month, ₹10,000 one-time):
- Unlimited calling within India (5000 min FUP/user, pooled)
- 1 Standard DID bundled per agent/license
- 6-month call recording retention
- No IVR limitations

API endpoint:
  POST https://api-smartflo.tatateleservices.com/v1/click_to_call_support

Auth:
  - Authorization: Bearer <TATA_SMARTFLO_API_TOKEN>
  - Request body: api_key (Click-to-Call Support API Key from Smartflo portal)

The API is ASYNC — it returns ref_id immediately and actual call status
comes via webhooks. Webhook URL must be configured in the Smartflo portal.

Env vars (from .env):
  TATA_SMARTFLO_API_TOKEN  - Bearer token from Smartflo portal
  TATA_SMARTFLO_API_KEY    - Click-to-Call Support API Key
  TATA_SMARTFLO_DID        - Caller ID DID (bundled with license)

NOTE: Authorization header becomes MANDATORY after 30 Sep 2026.
      We always send it.

Import-safe: no network at import time; httpx imported lazily.
"""

import os
import uuid
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

SMARTFLO_C2C_ENDPOINT = (
    "https://api-smartflo.tatateleservices.com/v1/click_to_call_support"
)


def _env(name: str, default: str = "") -> str:
    val = getattr(settings, name.lower(), None)
    if val is None or val == "":
        val = os.getenv(name, default)
    return (val or "").strip()


class TataSmartfloClient:
    """
    Thin async client for the Tata Smartflo Click-to-Call Support API.

    Follows the same pattern as VobizClient — methods return
    {"status_code": int, "body": dict}, never raise.
    """

    def __init__(self) -> None:
        self.api_token = _env("TATA_SMARTFLO_API_TOKEN")
        self.api_key = _env("TATA_SMARTFLO_API_KEY")
        self.did = _env("TATA_SMARTFLO_DID")

    def available(self) -> bool:
        """True when both token and key are configured."""
        return bool(self.api_token and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _safe_body(resp: Any) -> dict[str, Any]:
        try:
            body = resp.json()
            return body if isinstance(body, dict) else {"data": body}
        except Exception:
            return {"raw": (resp.text or "")[:500]}

    async def place_call(
        self,
        to: str,
        caller_id: str | None = None,
        call_timeout: int = 300,
        customer_ring_timeout: int = 30,
        custom_identifier: dict[str, str] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        POST click_to_call_support — place an outbound call.

        The Smartflo C2C Support flow:
          1. Smartflo first dials the customer_number (first leg)
          2. Once customer ANSWERS, Smartflo dials the configured destination
             (second leg — the agent/destination bound to the api_key)
          3. Customer + destination are bridged

        For our AI voice agent use case: the destination (second leg) should
        point at our voice agent endpoint. This requires the api_key to be
        configured in the Smartflo portal with our callback URL.

        Args:
            to:             Customer's phone number (10-12 digit Indian number)
            caller_id:      DID to show to customer (defaults to TATA_SMARTFLO_DID)
            call_timeout:   Max call duration in seconds (auto-hangup)
            customer_ring_timeout: Max seconds to ring customer (10-30)
            custom_identifier: Up to 10 custom key-value pairs for webhook correlation
            **extra:        Forwarded to API payload

        Returns:
            {"status_code": int, "body": dict} — never raises.

        On success (200):
            body = {"success": true, "message": "Originate successfully queued", "ref_id": "..."}
        """
        if not self.available():
            logger.warning("Tata Smartflo place_call rejected: not configured")
            return {
                "status_code": 0,
                "body": {
                    "error": (
                        "TATA_SMARTFLO_API_TOKEN / TATA_SMARTFLO_API_KEY missing. "
                        "Get them from the Smartflo portal → API section."
                    )
                },
            }

        # Build clean 10-digit number for Smartflo API
        to_clean = self._clean_number(to)
        caller = caller_id or self.did

        payload: dict[str, Any] = {
            "customer_number": to_clean,
            "api_key": self.api_key,
            "async": 1,  # mandatory: Smartflo only supports async mode
        }
        if caller:
            payload["caller_id"] = self._clean_number(caller)
        if call_timeout:
            payload["call_timeout"] = min(max(call_timeout, 30), 3600)
        if customer_ring_timeout:
            payload["customer_ring_timeout"] = min(max(customer_ring_timeout, 10), 30)
        if custom_identifier:
            # Smartflo limits total custom_identifier JSON to 512 chars
            payload["custom_identifier"] = dict(list(custom_identifier.items())[:10])

        payload.update(extra)

        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True
            ) as client:
                resp = await client.post(
                    SMARTFLO_C2C_ENDPOINT,
                    json=payload,
                    headers=self._headers(),
                )
            body = self._safe_body(resp)
            if resp.status_code == 200 and body.get("success"):
                ref_id = body.get("ref_id", "unknown")
                logger.info(
                    f"📞 Tata Smartflo call queued → ref_id={ref_id} "
                    f"(to={to_clean[-4:]:>4})"
                )
            else:
                logger.warning(
                    f"Tata Smartflo call rejected: {resp.status_code} "
                    f"{body.get('message', body)}"
                )
            return {"status_code": resp.status_code, "body": body}
        except Exception as e:
            _err = f"{type(e).__name__}: {e}".rstrip(": ")
            _is_transport = any(
                t in type(e).__name__
                for t in ("Timeout", "ConnectError", "ConnectTimeout", "NetworkError")
            )
            if _is_transport:
                logger.warning(f"Tata Smartflo place_call transport error: {_err}")
            else:
                logger.error(f"Tata Smartflo place_call failed: {_err}")
            return {"status_code": 0, "body": {"error": _err}}

    @staticmethod
    def _clean_number(number: str) -> str:
        """Strip to digits, ensure 10-digit Indian number for Smartflo API."""
        if not number:
            return number
        n = number.strip().lstrip("+")
        digits = "".join(filter(str.isdigit, n))
        # Remove leading 91 country code
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        # Remove leading 0
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        return digits

    def validate_config(self) -> dict[str, Any]:
        """Return what is configured / missing for Tata Smartflo."""
        missing = []
        if not _env("TATA_SMARTFLO_API_TOKEN"):
            missing.append("TATA_SMARTFLO_API_TOKEN")
        if not _env("TATA_SMARTFLO_API_KEY"):
            missing.append("TATA_SMARTFLO_API_KEY")
        if not _env("TATA_SMARTFLO_DID"):
            missing.append("TATA_SMARTFLO_DID")
        return {
            "provider": "tata_smartflo",
            "configured": self.available(),
            "did": self.did or None,
            "plan": "Smartflo Pro ₹1,250/license/month (5000 min FUP)",
            "missing": missing,
        }
