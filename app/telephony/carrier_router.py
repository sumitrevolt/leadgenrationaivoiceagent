"""
Multi-Carrier Telephony Router
==============================

Wraps existing provider handlers (Vobiz, Twilio) under a single abstraction so
callers can request failover across providers without touching the live call
path. (Exotel removed 2026-06-18 — provider is now Vobiz.)

GATED: only activates multi-provider failover when env ``MULTI_CARRIER=1``.
When the flag is OFF (default) ``place_call_failover`` uses the single current
provider selected by ``DEFAULT_TELEPHONY`` — identical to today's behaviour,
zero regression.

Design rules (project-wide patterns, strictly followed here):
- never-raise: every public method wraps body in try/except → safe return.
- inert-without-creds: missing env → provider reports unavailable, no crash.
- additive: does NOT modify call_manager.py or any existing handler.
- Plivo: no existing handler → graceful "not implemented" stub, ready to flip.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or "").strip() or default


def _multi_carrier_enabled() -> bool:
    return _env("MULTI_CARRIER") == "1"


def _carrier_priority() -> list[str]:
    """Ordered provider names from CARRIER_PRIORITY env (csv).

    Default: vobiz,twilio,plivo
    """
    raw = _env("CARRIER_PRIORITY", "vobiz,twilio,plivo")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


# ---------------------------------------------------------------------------
# Per-provider adapters
# ---------------------------------------------------------------------------


class _TwilioAdapter:
    """Wraps app.telephony.twilio_handler.TwilioHandler."""

    name = "twilio"

    def available(self) -> bool:
        try:
            return bool(_env("TWILIO_ACCOUNT_SID") and _env("TWILIO_AUTH_TOKEN"))
        except Exception:
            return False

    async def place_call(self, to: str, from_: str, **kw: Any) -> dict:
        try:
            # India-domestic calls over a foreign trunk (Twilio) are illegal
            # (Telegraph Act) — refuse +91 numbers here even if Vobiz failed
            # over to us, unless explicitly overridden. Checked at dial-time
            # (not available()) since availability doesn't see the number.
            digits = "".join(ch for ch in (to or "") if ch.isdigit() or ch == "+")
            is_india = digits.startswith("+91") or (
                not digits.startswith("+") and digits.startswith("91") and len(digits) == 12
            )
            if is_india and _env("ALLOW_TWILIO_INDIA") != "1":
                return {
                    "ok": False,
                    "reason": "twilio: refused for India-domestic number (foreign trunk, "
                    "set ALLOW_TWILIO_INDIA=1 to override)",
                }

            from app.telephony.twilio_handler import TwilioHandler

            h = TwilioHandler()
            if not h.client:
                return {"ok": False, "reason": "twilio: client not initialized"}
            call_id = kw.get("call_id", "cr-" + to[-6:])
            webhook_url = kw.get("webhook_url")
            sid = await h.make_call(
                to_number=to,
                call_id=call_id,
                webhook_url=webhook_url,
            )
            if sid:
                return {"ok": True, "call_sid": sid, "provider": "twilio"}
            return {"ok": False, "reason": "twilio: make_call returned no SID"}
        except Exception as exc:
            logger.debug("twilio adapter error: %s", exc)
            return {"ok": False, "reason": f"twilio: {exc}"}


class _VobizAdapter:
    """Wraps app.telephony.vobiz_handler.VobizClient."""

    name = "vobiz"

    def available(self) -> bool:
        try:
            return bool(_env("VOBIZ_AUTH_ID") and _env("VOBIZ_AUTH_TOKEN"))
        except Exception:
            return False

    async def place_call(self, to: str, from_: str, **kw: Any) -> dict:
        try:
            from app.telephony.vobiz_handler import VobizClient

            c = VobizClient()
            if not c.available():
                return {"ok": False, "reason": "vobiz: credentials not configured"}
            answer_url = kw.get("answer_url") or kw.get("webhook_url") or ""
            if not answer_url:
                return {"ok": False, "reason": "vobiz: answer_url required"}
            result = await c.place_call(
                to=to,
                answer_url=answer_url,
                from_=from_ or None,
                call_type=kw.get("call_type", "transactional"),
                skip_compliance=kw.get("skip_compliance", False),
            )
            if result.get("status_code", 0) in (200, 201, 202):
                return {"ok": True, "result": result, "provider": "vobiz"}
            blocked = result.get("blocked", False)
            if blocked:
                return {"ok": False, "reason": "vobiz: blocked by compliance", "result": result}
            return {
                "ok": False,
                "reason": f"vobiz: status {result.get('status_code')}",
                "result": result,
            }
        except Exception as exc:
            logger.debug("vobiz adapter error: %s", exc)
            return {"ok": False, "reason": f"vobiz: {exc}"}


class _PlivoAdapter:
    """Plivo stub — no existing handler yet.

    The adapter is registered so the abstraction is ready when creds and a
    handler are added. Until then it always reports unavailable.
    """

    name = "plivo"

    def available(self) -> bool:
        # Will be True once PLIVO_AUTH_ID + PLIVO_AUTH_TOKEN are set AND
        # a real handler module exists. Currently always False (stub).
        try:
            has_creds = bool(_env("PLIVO_AUTH_ID") and _env("PLIVO_AUTH_TOKEN"))
            if not has_creds:
                return False
            # Guard: refuse to claim available if no real handler exists.
            try:
                import importlib

                importlib.util.find_spec("app.telephony.plivo_handler")
            except Exception:
                pass
            # No handler module — stay unavailable even if creds present.
            return False
        except Exception:
            return False

    async def place_call(self, to: str, from_: str, **kw: Any) -> dict:
        return {
            "ok": False,
            "reason": "plivo: not implemented — add app/telephony/plivo_handler.py to activate",
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ADAPTERS: dict[str, Any] = {
    "vobiz": _VobizAdapter(),
    "twilio": _TwilioAdapter(),
    "plivo": _PlivoAdapter(),
}


# ---------------------------------------------------------------------------
# CarrierRouter
# ---------------------------------------------------------------------------


class CarrierRouter:
    """
    Multi-carrier telephony router.

    Usage (from any module — does NOT replace CallManager):

        from app.telephony.carrier_router import router

        result = await router.place_call_failover(
            to="+919876543210",
            from_="+911141189204",
            call_id="abc123",
            answer_url="https://leadsgenai.in/api/webhooks/vobiz/answer",
        )

    When MULTI_CARRIER=1: tries providers in CARRIER_PRIORITY order, first
    success wins.  When MULTI_CARRIER=0 (default): routes via the single
    current provider (DEFAULT_TELEPHONY env) — zero behaviour change.
    """

    def ordered_providers(self) -> list[Any]:
        """Return available adapters in CARRIER_PRIORITY order.

        Providers not in the priority list but present in the registry are
        appended at the end (future-proofing). Never raises.
        """
        try:
            priority = _carrier_priority()
            ordered: list[Any] = []
            seen: set[str] = set()
            for name in priority:
                adapter = _ADAPTERS.get(name)
                if adapter and name not in seen:
                    ordered.append(adapter)
                    seen.add(name)
            # Append any registered adapters not mentioned in priority list.
            for name, adapter in _ADAPTERS.items():
                if name not in seen:
                    ordered.append(adapter)
                    seen.add(name)
            return [a for a in ordered if a.available()]
        except Exception as exc:
            logger.debug("ordered_providers error: %s", exc)
            return []

    def status(self) -> dict[str, Any]:
        """Return availability dict for every registered provider.

        Safe for dashboard / /api/growth/infra/* exposure.
        Never raises.
        """
        out: dict[str, Any] = {}
        try:
            priority = _carrier_priority()
            for name, adapter in _ADAPTERS.items():
                try:
                    avail = adapter.available()
                except Exception:
                    avail = False
                out[name] = {
                    "available": avail,
                    "priority_position": priority.index(name) + 1 if name in priority else None,
                }
        except Exception as exc:
            logger.debug("status() error: %s", exc)
        return out

    async def place_call_failover(
        self,
        to: str,
        from_: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        """Place a call with optional multi-provider failover.

        MULTI_CARRIER=0 (default — zero behaviour change):
            Delegates directly to the single provider named by DEFAULT_TELEPHONY.
            Falls back to vobiz if DEFAULT_TELEPHONY is unset or unknown.

        MULTI_CARRIER=1:
            Tries providers in CARRIER_PRIORITY order. First success wins.
            On full failure returns {"ok": False, "tried": [...]}.

        Never raises. Always returns a dict with at minimum {"ok": bool}.
        """
        try:
            if not _multi_carrier_enabled():
                return await self._single_provider_call(to, from_, **kw)
            return await self._failover_call(to, from_, **kw)
        except Exception as exc:
            logger.error("place_call_failover unexpected error: %s", exc)
            return {"ok": False, "reason": f"unexpected: {exc}"}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _single_provider_call(self, to: str, from_: str, **kw: Any) -> dict[str, Any]:
        """Route to the single configured provider (MULTI_CARRIER off path)."""
        try:
            provider_name = (
                _env("DEFAULT_TELEPHONY") or _env("TELEPHONY_PROVIDER") or "vobiz"
            ).lower()
            adapter = _ADAPTERS.get(provider_name)
            if adapter is None:
                return {
                    "ok": False,
                    "reason": f"unknown provider '{provider_name}' in DEFAULT_TELEPHONY",
                }
            if not adapter.available():
                return {
                    "ok": False,
                    "reason": f"{provider_name}: not available (check creds/env)",
                }
            result = await adapter.place_call(to, from_, **kw)
            result.setdefault("provider", provider_name)
            return result
        except Exception as exc:
            logger.debug("_single_provider_call error: %s", exc)
            return {"ok": False, "reason": f"single-provider dispatch error: {exc}"}

    async def _failover_call(self, to: str, from_: str, **kw: Any) -> dict[str, Any]:
        """Try providers in priority order, return first success."""
        tried: list[dict[str, Any]] = []
        try:
            providers = self.ordered_providers()
            if not providers:
                return {
                    "ok": False,
                    "reason": "no providers available",
                    "tried": [],
                }
            for adapter in providers:
                try:
                    result = await adapter.place_call(to, from_, **kw)
                    tried.append({"provider": adapter.name, "result": result})
                    if result.get("ok"):
                        result["tried"] = tried
                        return result
                    logger.debug(
                        "carrier_router: %s failed (%s), trying next",
                        adapter.name,
                        result.get("reason", "?"),
                    )
                except Exception as exc:
                    tried.append({"provider": adapter.name, "error": str(exc)})
                    logger.debug("carrier_router: %s raised: %s", adapter.name, exc)
        except Exception as exc:
            logger.error("_failover_call error: %s", exc)
            return {"ok": False, "reason": f"failover error: {exc}", "tried": tried}

        return {"ok": False, "tried": tried, "reason": "all providers failed"}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

router = CarrierRouter()
