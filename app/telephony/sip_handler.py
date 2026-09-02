"""
SIP Trunk Handler (Cheapest Telephony Option for India)
========================================================

Generic SIP-trunk handler for the CHEAPEST way to make real PSTN phone calls
in India (~₹0.40/min) using a SIP trunk from providers like Plivo, Exotel,
FreJun, Twilio Elastic SIP, MyOperator, etc.

WHY SIP IS CHEAPEST
-------------------
Hosted voice APIs (Twilio/Exotel REST) bundle media + per-minute markup, so
you typically pay ₹0.60–0.90/min. A raw SIP trunk + your own self-hosted media
server (Asterisk/FreeSWITCH/PJSIP) bills only the carrier minutes — usually
₹0.30–0.45/min in India. You run the media; the provider only carries PSTN.

HOW TO CONNECT A REAL SIP TRUNK + ASTERISK (~₹0.40/min)
-------------------------------------------------------
1. Buy a SIP trunk + a DID (caller-id number) from a provider:
   - Plivo, Exotel SIP, FreJun, MyOperator, Knowlarity, etc.
   - They give you: SIP_HOST (registrar/proxy), SIP_USERNAME, SIP_PASSWORD,
     and a DID number to show as caller-id (SIP_DID).
2. Stand up a media server (any ONE):
   - Asterisk (PJSIP) — most common. Configure pjsip.conf with an endpoint,
     auth (SIP_USERNAME/SIP_PASSWORD), and a registration to SIP_HOST.
   - FreeSWITCH — sofia gateway pointed at SIP_HOST.
3. Bridge media to this AI voice agent:
   - Asterisk ARI / AudioSocket / chan_externalmedia streams raw audio over a
     WebSocket/TCP socket to the voice agent (STT -> LLM -> TTS loop).
   - On answer, Asterisk calls back into our pipeline; we wire that via the
     `on_answer` callback below.
4. Place calls:
   - Originate via ARI (POST /ari/channels) OR let the provider's REST API
     originate and bridge to your trunk. This handler supports the provider
     REST path out of the box (SIP_PROVIDER); for the self-hosted ARI path,
     point SIP_HOST at your Asterisk ARI endpoint and extend `_place_via_ari`.

This handler is intentionally defensive: if SIP infra is not configured it
returns a clear `not_configured` CallResult instead of crashing, so the rest of
the lead-gen pipeline keeps running (the TelephonyService falls back to
simulation mode in that case).
"""

import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# Type alias for the on-answer callback (async). Receives the call_id and may
# drive the STT -> LLM -> TTS conversation loop for the answered leg.
OnAnswerCallback = Callable[[str], Awaitable[Any]]


@dataclass
class CallResult:
    """Unified result of a SIP call attempt.

    This matches the shape used by TelephonyService so all providers return a
    consistent object to the caller.
    """

    call_id: str
    status: str  # initiated, connected, no_answer, busy, failed, not_configured
    duration: int  # seconds (0 if not connected / unknown at originate time)
    provider: str  # e.g. "sip:plivo", "sip:asterisk", "sip"
    error: str | None = None


def _get(name: str, default: str = "") -> str:
    """Read a config value from pydantic settings first, then raw env.

    SIP_* fields are not declared on Settings (extra='ignore'), so we fall back
    to os.environ. Always returns a stripped string, never None.
    """
    val = getattr(settings, name.lower(), None)
    if val is None or val == "":
        val = os.getenv(name, default)
    return (val or "").strip()


class SIPHandler:
    """
    Generic SIP-trunk telephony handler (cheapest India option).

    Config (from settings / environment):
        SIP_HOST      - SIP registrar/proxy host (or provider API base / ARI host)
        SIP_USERNAME  - SIP/trunk auth username
        SIP_PASSWORD  - SIP/trunk auth password
        SIP_DID       - DID number used as caller-id (E.164 or local)
        SIP_PROVIDER  - optional provider slug ("plivo", "exotel", "frejun",
                        "generic"). If set, place_call POSTs to that provider's
                        REST originate API. If empty, returns not_configured
                        (real SIP media needs self-hosted Asterisk/PJSIP).

    Notes:
        - Fully async / httpx based.
        - Never raises on missing config; returns a CallResult instead.
    """

    # Minimal REST originate endpoints for common providers. These are best
    # effort templates; tweak per your account. Self-hosted Asterisk users
    # should instead point SIP_HOST at ARI and extend _place_via_ari.
    _PROVIDER_ENDPOINTS: dict[str, str] = {
        "plivo": "https://api.plivo.com/v1/Account/{username}/Call/",
        "frejun": "https://api.frejun.com/api/v1/call/",
        "generic": "{host}/call",  # fully custom: SIP_HOST is the API base
    }

    def __init__(self):
        self.host = _get("SIP_HOST")
        self.username = _get("SIP_USERNAME")
        self.password = _get("SIP_PASSWORD")
        self.did = _get("SIP_DID")
        self.provider = _get("SIP_PROVIDER").lower()

        self.configured = bool(self.host and self.username and self.password)

        if self.configured:
            mode = self.provider or "self-hosted (no REST provider set)"
            logger.info(f"📞 SIP Handler initialized (provider={mode}, did={self.did or 'n/a'})")
        else:
            logger.warning(
                "SIP not configured (need SIP_HOST, SIP_USERNAME, SIP_PASSWORD). "
                "place_call() will return 'not_configured'."
            )

    def validate_config(self) -> dict[str, Any]:
        """Return what is configured / missing for SIP."""
        missing = []
        for key in ("SIP_HOST", "SIP_USERNAME", "SIP_PASSWORD"):
            if not _get(key):
                missing.append(key)
        return {
            "provider": "sip",
            "configured": self.configured,
            "rest_provider": self.provider or None,
            "did": self.did or None,
            "missing": missing,
        }

    @staticmethod
    def _normalize_number(number: str) -> str:
        """Normalize an Indian number to E.164 (+91...) best-effort."""
        if not number:
            return number
        n = number.strip()
        if n.startswith("+"):
            return n
        digits = "".join(filter(str.isdigit, n))
        if digits.startswith("91") and len(digits) == 12:
            return f"+{digits}"
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) == 10:
            return f"+91{digits}"
        return f"+{digits}" if digits else n

    async def place_call(
        self,
        to_number: str,
        from_number: str | None = None,
        on_answer: OnAnswerCallback | None = None,
    ) -> CallResult:
        """
        Place an outbound call over the SIP trunk.

        Args:
            to_number:   Destination phone number (Indian 10-digit or E.164).
            from_number: Caller-id to present; defaults to SIP_DID.
            on_answer:   Optional async callback invoked with call_id once the
                         provider reports the call as answered (best-effort;
                         only used on the self-hosted/ARI path).

        Returns:
            CallResult — never raises.
        """
        call_id = str(uuid.uuid4())
        caller_id = from_number or self.did or self.username

        if not self.configured:
            logger.warning("SIP place_call rejected: not configured")
            return CallResult(
                call_id=call_id,
                status="not_configured",
                duration=0,
                provider="sip",
                error="SIP_HOST/SIP_USERNAME/SIP_PASSWORD missing. "
                "Set them (and SIP_PROVIDER for REST) or use simulation mode.",
            )

        to_e164 = self._normalize_number(to_number)
        from_e164 = self._normalize_number(caller_id) if caller_id else caller_id

        # Path (a): provider REST originate.
        if self.provider:
            return await self._place_via_rest(call_id, to_e164, from_e164, on_answer)

        # Path (b): no REST provider => needs self-hosted Asterisk/PJSIP media.
        # We don't have raw SIP media here, so return a clear, non-crashing result.
        logger.warning(
            "SIP_PROVIDER not set — raw SIP media needs self-hosted Asterisk/PJSIP. "
            "See module docstring to wire ARI. Returning not_configured."
        )
        return CallResult(
            call_id=call_id,
            status="not_configured",
            duration=0,
            provider="sip:self-hosted",
            error="SIP trunk credentials present but no SIP_PROVIDER REST API and "
            "no Asterisk/ARI bridge configured. See sip_handler docstring.",
        )

    async def _place_via_rest(
        self,
        call_id: str,
        to_number: str,
        from_number: str | None,
        on_answer: OnAnswerCallback | None,
    ) -> CallResult:
        """Originate a call via a provider's REST API (Plivo/FreJun/generic)."""
        template = self._PROVIDER_ENDPOINTS.get(self.provider)
        if not template:
            return CallResult(
                call_id=call_id,
                status="failed",
                duration=0,
                provider=f"sip:{self.provider}",
                error=f"Unknown SIP_PROVIDER '{self.provider}'. "
                f"Supported: {', '.join(self._PROVIDER_ENDPOINTS)}.",
            )

        url = template.format(username=self.username, host=self.host.rstrip("/"))

        # Generic originate payload. Field names vary per provider; this covers
        # the common case and is easy to adapt.
        payload = {
            "from": from_number,
            "to": to_number,
            "caller_id": from_number,
            "answer_url": None,  # set if your provider needs an XML/answer URL
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    auth=(self.username, self.password),
                    timeout=30.0,
                )
                response.raise_for_status()

            try:
                data = response.json()
            except Exception:
                data = {}

            provider_call_id = (
                data.get("call_uuid") or data.get("call_id") or data.get("request_uuid") or call_id
            )

            logger.info(
                f"SIP call originated via {self.provider}: {provider_call_id} -> {to_number}"
            )

            # Best-effort: trigger the on_answer hook so the voice loop can start.
            if on_answer:
                try:
                    asyncio.create_task(on_answer(call_id))
                except Exception as cb_err:  # never let the callback crash us
                    logger.error(f"on_answer callback error: {cb_err}")

            return CallResult(
                call_id=str(provider_call_id),
                status="initiated",
                duration=int(time.monotonic() - start),
                provider=f"sip:{self.provider}",
                error=None,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"SIP REST originate HTTP error: {e.response.status_code} {e}")
            return CallResult(
                call_id=call_id,
                status="failed",
                duration=0,
                provider=f"sip:{self.provider}",
                error=f"HTTP {e.response.status_code}: {e}",
            )
        except Exception as e:
            logger.error(f"SIP REST originate failed: {e}")
            return CallResult(
                call_id=call_id,
                status="failed",
                duration=0,
                provider=f"sip:{self.provider}",
                error=str(e),
            )

    async def _place_via_ari(
        self,
        call_id: str,
        to_number: str,
        from_number: str | None,
        on_answer: OnAnswerCallback | None,
    ) -> CallResult:
        """
        STUB: originate via self-hosted Asterisk ARI.

        To enable the truly-cheapest path, run Asterisk with PJSIP registered to
        your SIP trunk and the ARI HTTP interface enabled, then implement an
        originate here, e.g.:

            POST {SIP_HOST}/ari/channels
                ?endpoint=PJSIP/{to_number}@trunk
                &callerId={from_number}
                &app=voiceagent

        Auth uses ARI username/password (reuse SIP_USERNAME/SIP_PASSWORD or
        dedicated ARI creds). The Stasis app 'voiceagent' then bridges media to
        this AI agent and invokes `on_answer` on StasisStart.
        """
        return CallResult(
            call_id=call_id,
            status="not_configured",
            duration=0,
            provider="sip:asterisk",
            error="ARI originate not implemented — see _place_via_ari docstring.",
        )
