"""
Telephony Service (Unified, Plug-and-Play Facade)
=================================================

One entry point for placing real phone calls across providers, with a working
SIMULATION fallback so the entire lead-gen pipeline runs end-to-end WITHOUT any
provider keys.

Provider selection (in priority order):
    1. TELEPHONY_PROVIDER env / setting, if explicitly set to one of:
       "vobiz" | "sip" | "none" | "simulation".
    2. Auto-detect: pick whichever provider's keys actually exist
       (sip -> vobiz).
    3. Else -> "simulation" mode (no keys needed).

Usage:
    from app.telephony.telephony_service import get_telephony_service

    svc = get_telephony_service()
    result = await svc.place_call("9876543210")
    # result -> CallResult(call_id, status, duration, provider, error)

Design goals:
    - import-safe: never crash at import or init even if SDKs/keys missing.
    - defensive: any provider error degrades gracefully (logged), and the
      caller always gets a CallResult.
"""

import asyncio
import os
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# Optional async callback to drive the conversation (STT -> LLM -> TTS) once the
# call is answered. Signature: async (call_id: str) -> Any
ScriptCallback = Callable[[str], Awaitable[Any]]


@dataclass
class CallResult:
    """Unified call result returned by TelephonyService for every provider."""

    call_id: str
    status: str  # initiated, connected, no_answer, busy, failed, not_configured, simulated
    duration: int  # seconds
    provider: str  # vobiz | sip:* | simulation
    error: str | None = None


def _env(name: str, default: str = "") -> str:
    """Read from settings (lowercased field) first, then raw env. Stripped str."""
    val = getattr(settings, name.lower(), None)
    if val is None or val == "":
        val = os.getenv(name, default)
    return (val or "").strip()


class TelephonyService:
    """
    Facade that selects the active telephony provider and routes place_call().

    Falls back to SIMULATION when nothing is configured, so the pipeline always
    runs. Use validate_config() to inspect the active provider and gaps.
    """

    VALID_PROVIDERS = ("vobiz", "sip", "tata_smartflo", "none", "simulation")

    def __init__(self, provider: str | None = None):
        self.provider = (provider or self._detect_provider()).lower()
        self._handler = None  # lazily constructed real handler (if any)

        # Try to construct the chosen real handler; on ANY failure, fall back to
        # simulation so we never crash.
        if self.provider in ("vobiz", "sip"):
            try:
                self._handler = self._build_handler(self.provider)
            except Exception as e:
                logger.error(
                    f"Failed to init '{self.provider}' handler ({e}); falling back to simulation."
                )
                self.provider = "simulation"

        if self.provider in ("none", "simulation"):
            self.provider = "simulation"
            logger.info(
                "📞 TelephonyService in SIMULATION mode — no provider keys needed. "
                "Calls are simulated end-to-end."
            )
        else:
            logger.info(f"📞 TelephonyService active provider: {self.provider}")

    # ------------------------------------------------------------------ #
    # Provider detection / construction
    # ------------------------------------------------------------------ #
    def _detect_provider(self) -> str:
        """Resolve provider from explicit setting or auto-detect from keys."""
        explicit = _env("TELEPHONY_PROVIDER").lower()
        if explicit:
            if explicit in self.VALID_PROVIDERS:
                return explicit
            logger.warning(
                f"Unknown TELEPHONY_PROVIDER='{explicit}'. "
                f"Valid: {self.VALID_PROVIDERS}. Auto-detecting instead."
            )

        # Auto-detect: cheapest-first (sip), then tata_smartflo, then vobiz.
        if _env("SIP_HOST") and _env("SIP_USERNAME") and _env("SIP_PASSWORD"):
            return "sip"
        if _env("TATA_SMARTFLO_API_TOKEN") and _env("TATA_SMARTFLO_API_KEY"):
            return "tata_smartflo"
        if _env("VOBIZ_AUTH_ID") and _env("VOBIZ_AUTH_TOKEN"):
            return "vobiz"

        return "simulation"

    def _build_handler(self, provider: str):
        """Construct the underlying provider handler. Imports are local so a
        missing module for one provider never breaks the others."""
        if provider == "vobiz":
            from app.telephony.vobiz_handler import VobizClient

            return VobizClient()
        if provider == "sip":
            from app.telephony.sip_handler import SIPHandler

            return SIPHandler()
        if provider == "tata_smartflo":
            from app.telephony.tata_smartflo_handler import TataSmartfloClient

            return TataSmartfloClient()
        raise ValueError(f"Unknown provider: {provider}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def place_call(
        self,
        to_number: str,
        from_number: str | None = None,
        script_callback: ScriptCallback | None = None,
        call_type: str = "promotional",
    ) -> CallResult:
        """
        Place an outbound call via the active provider.

        Never raises — any failure degrades to a failed/simulated CallResult.

        Args:
            to_number:       Destination phone number.
            from_number:     Optional caller-id override.
            script_callback: Optional async callback to drive the conversation
                             once answered (passed through to SIP; for
                             Vobiz the conversation is webhook-driven).
            call_type:       'promotional' (strict TCCCPR gate) or 'transactional'
                             (consented/known — lenient). REAL provider calls pass
                             the ComplianceGate; simulation is exempt (dev).
        """
        if self.provider == "simulation":
            return await self._simulate_call(to_number, from_number)

        # COMPLIANCE GATE (real providers only) — DND + calling hours + DLT/140.
        # A non-compliant promotional call is never dialled (TCCCPR; ₹10L risk).
        try:
            from app.telephony.compliance import CallType, get_compliance_gate

            ct = (
                CallType(call_type)
                if call_type in (c.value for c in CallType)
                else CallType.PROMOTIONAL
            )
            decision = await get_compliance_gate().check(to_number, ct)
            if not decision.allowed:
                logger.warning(f"place_call blocked by compliance: {decision.reasons}")
                return CallResult(
                    call_id=str(uuid.uuid4()),
                    status="blocked_compliance",
                    duration=0,
                    provider=self.provider,
                    error="; ".join(decision.reasons),
                )
        except Exception as e:
            if (call_type or "").lower() == "promotional":
                logger.error(f"compliance gate error ({e}) — blocking promo call.")
                return CallResult(
                    call_id=str(uuid.uuid4()),
                    status="blocked_compliance",
                    duration=0,
                    provider=self.provider,
                    error=f"gate_error:{e}",
                )

        try:
            if self.provider == "sip":
                # SIPHandler returns its own CallResult (same shape) — adapt it.
                sip_result = await self._handler.place_call(
                    to_number=to_number,
                    from_number=from_number,
                    on_answer=script_callback,
                )
                return CallResult(
                    call_id=sip_result.call_id,
                    status=sip_result.status,
                    duration=sip_result.duration,
                    provider=sip_result.provider,
                    error=sip_result.error,
                )

            if self.provider == "tata_smartflo":
                # TataSmartfloClient.place_call returns ref_id on success.
                # The C2C Support API is customer-first: Smartflo dials customer,
                # then bridges to the destination configured on the API key.
                call_id = str(uuid.uuid4())
                caller = from_number or _env("TATA_SMARTFLO_DID")
                result = await self._handler.place_call(
                    to=to_number,
                    caller_id=caller,
                    custom_identifier={
                        "source": "leadgen",
                        "call_id": call_id,
                    },
                )
                if result.get("status_code") == 200 and (
                    result.get("body") or {}
                ).get("success"):
                    ref_id = str(
                        (result.get("body") or {}).get("ref_id") or call_id
                    )
                    return CallResult(
                        call_id=ref_id,
                        status="initiated",
                        duration=0,
                        provider=self.provider,
                        error=None,
                    )
                return CallResult(
                    call_id=call_id,
                    status="failed",
                    duration=0,
                    provider=self.provider,
                    error=str(
                        (result.get("body") or {}).get("message")
                        or (result.get("body") or {}).get("error")
                        or "tata_smartflo: call not accepted"
                    ),
                )

            if self.provider == "vobiz":
                # VobizClient.place_call(to, answer_url, ...) — never raises;
                # success = status_code in 200/201/202. Compliance already ran
                # above, so skip the duplicate gate. answer_url best-effort points
                # at the public site (calls DLT/recharge-blocked → structural only).
                call_id = str(uuid.uuid4())
                base = (
                    os.getenv("PUBLIC_BASE_URL")
                    or os.getenv("SITE_BASE")
                    or settings.public_base_url
                    or ""
                ).rstrip("/")
                answer_url = f"{base}/api/webhooks/vobiz/answer" if base else ""
                result = await self._handler.place_call(
                    to=to_number,
                    answer_url=answer_url,
                    from_=from_number,
                    call_type=call_type,
                    skip_compliance=True,
                )
                if result.get("status_code") in (200, 201, 202):
                    call_sid = str((result.get("body") or {}).get("id") or call_id)
                    return CallResult(
                        call_id=call_sid,
                        status="initiated",
                        duration=0,
                        provider=self.provider,
                        error=None,
                    )
                return CallResult(
                    call_id=call_id,
                    status="failed",
                    duration=0,
                    provider=self.provider,
                    error=str((result.get("body") or {}).get("error") or "vobiz: no call id"),
                )

        except Exception as e:
            logger.error(f"place_call failed on provider '{self.provider}': {e}")
            return CallResult(
                call_id=str(uuid.uuid4()),
                status="failed",
                duration=0,
                provider=self.provider,
                error=str(e),
            )

        # Unreachable guard.
        return CallResult(
            call_id=str(uuid.uuid4()),
            status="failed",
            duration=0,
            provider=self.provider,
            error="No routing path for provider.",
        )

    async def _simulate_call(
        self,
        to_number: str,
        from_number: str | None,
    ) -> CallResult:
        """Run a realistic simulated call so the pipeline works without keys."""
        call_id = str(uuid.uuid4())
        logger.info(
            f"🎭 [SIMULATION] Placing call to {to_number} (from={from_number or 'sim-did'})"
        )

        # Brief async sleep to mimic ringing/connect latency.
        await asyncio.sleep(random.uniform(0.2, 0.8))

        # Weighted realistic outcomes.
        outcome = random.choices(
            ["connected", "no_answer", "busy"],
            weights=[0.6, 0.3, 0.1],
            k=1,
        )[0]

        if outcome == "connected":
            duration = random.randint(45, 240)  # 45s–4min talk time
        elif outcome == "busy":
            duration = 0
        else:  # no_answer
            duration = random.randint(15, 30)  # rings then drops

        logger.info(f"🎭 [SIMULATION] Call {call_id} -> {outcome} ({duration}s)")

        return CallResult(
            call_id=call_id,
            status=outcome,
            duration=duration,
            provider="simulation",
            error=None,
        )

    def validate_config(self) -> dict[str, Any]:
        """
        Report the active provider and what (if anything) is missing.

        Returns a dict like:
            {
              "active_provider": "simulation",
              "configured": True,
              "simulation_mode": True,
              "missing": [...],
              "available_providers": {...},
            }
        """
        missing: list = []

        # Per-provider key presence (for diagnostics / dashboard).
        available = {
            "vobiz": bool(_env("VOBIZ_AUTH_ID") and _env("VOBIZ_AUTH_TOKEN")),
            "sip": bool(_env("SIP_HOST") and _env("SIP_USERNAME") and _env("SIP_PASSWORD")),
        }

        if self.provider == "vobiz":
            for k in ("VOBIZ_AUTH_ID", "VOBIZ_AUTH_TOKEN", "VOBIZ_CALLER_ID"):
                if not _env(k):
                    missing.append(k)
        elif self.provider == "sip":
            for k in ("SIP_HOST", "SIP_USERNAME", "SIP_PASSWORD"):
                if not _env(k):
                    missing.append(k)

        return {
            "active_provider": self.provider,
            "configured": self.provider != "simulation" and not missing,
            "simulation_mode": self.provider == "simulation",
            "missing": missing,
            "available_providers": available,
            "note": (
                "Running in SIMULATION mode — set TELEPHONY_PROVIDER or provider "
                "keys to enable real calls. Cheapest: SIP trunk (~₹0.40/min)."
                if self.provider == "simulation"
                else f"Active provider '{self.provider}'."
            ),
        }


# ---------------------------------------------------------------------- #
# Module-level singleton
# ---------------------------------------------------------------------- #
_telephony_service: TelephonyService | None = None


def get_telephony_service() -> TelephonyService:
    """Return the process-wide TelephonyService singleton (lazy init)."""
    global _telephony_service
    if _telephony_service is None:
        _telephony_service = TelephonyService()
    return _telephony_service
