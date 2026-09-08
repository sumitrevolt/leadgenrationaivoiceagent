"""
Webhooks / Events Emitter
=========================
External systems ko events ke baare me notify karta hai (Retell/Vapi style
webhooks). Jab pipeline me kuch hota hai — call start/end, lead scrape/qualify,
appointment book, transfer, voicemail, campaign complete, error — to ye emitter
har subscribed URL par ek signed JSON envelope POST kar deta hai.

Design (lead_delivery.py jaisa defensive):
  - httpx LAZILY import hota hai (import-safe) — agar httpx installed na ho to
    module import phir bhi nahi todhta; emit gracefully fail (logs) ho jata hai.
  - emit() KABHI raise nahi karta — har failure log hoke EmitResult me aa jata hai.
  - Zero config (koi URL nahi) => no-op, sirf log. Bilkul safe.
  - Har request retry hota hai exponential backoff ke saath (max 3 attempts).
  - HMAC-SHA256 signature `X-Signature` header me bheji jaati hai (sha256=<hex>).

Envelope shape (har event ke liye standard):
    {
      "id":        "<uuid4 hex>",          # unique event id
      "event":     "call.started",         # WebhookEvent value
      "timestamp": "2026-06-06T10:00:00Z", # ISO-8601 UTC
      "client_id": "acme-solar" | None,    # optional tenant/client id
      "data":      { ... }                 # event-specific payload (kuch bhi)
    }

Signing scheme:
    body      = json.dumps(envelope) ka UTF-8 bytes (compact, sorted keys)
    signature = "sha256=" + HMAC_SHA256(secret, body).hexdigest()
    header    = X-Signature: sha256=<hex>
    (receiver WebhookEmitter.verify_signature(secret, body, signature) se verify kare)

Usage example:
    from app.integrations.webhooks_emitter import (
        get_webhook_emitter, WebhookEvent, WebhookEmitter,
    )

    emitter = get_webhook_emitter()

    # In-process subscribe (env ke alawa runtime par bhi add kar sakte ho)
    emitter.subscribe("https://client.example.com/hooks", events=[WebhookEvent.LEAD_QUALIFIED])

    # Emit ek event
    result = await emitter.emit(
        WebhookEvent.LEAD_QUALIFIED,
        {"business": "Acme Solar", "phone": "+9198xxxxxxx", "score": "Hot"},
        client_id="acme-solar",
    )
    print(result.delivered, result.failed)   # e.g. 1 0

    # Receiver side — incoming webhook verify karo
    ok = WebhookEmitter.verify_signature(
        secret="my-secret",
        body=raw_request_body_bytes,
        signature=request.headers.get("X-Signature", ""),
    )
"""

import asyncio
import hashlib
import hmac
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# =============================================================================
# EVENT CONSTANTS
# =============================================================================


class WebhookEvent:
    """
    Supported webhook event names. String constants (Retell/Vapi style
    dotted names) taaki JSON me readable rahe aur enum import-overhead na ho.
    """

    CALL_STARTED = "call.started"
    CALL_ENDED = "call.ended"
    LEAD_SCRAPED = "lead.scraped"
    LEAD_QUALIFIED = "lead.qualified"
    APPOINTMENT_BOOKED = "appointment.booked"
    TRANSFER_INITIATED = "transfer.initiated"
    VOICEMAIL_DETECTED = "voicemail.detected"
    CAMPAIGN_COMPLETED = "campaign.completed"
    ERROR = "error"

    @classmethod
    def all(cls) -> list[str]:
        """Saare supported event names ki list."""
        return [
            cls.CALL_STARTED,
            cls.CALL_ENDED,
            cls.LEAD_SCRAPED,
            cls.LEAD_QUALIFIED,
            cls.APPOINTMENT_BOOKED,
            cls.TRANSFER_INITIATED,
            cls.VOICEMAIL_DETECTED,
            cls.CAMPAIGN_COMPLETED,
            cls.ERROR,
        ]

    @classmethod
    def is_valid(cls, event: str) -> bool:
        return event in cls.all()


# =============================================================================
# RESULT DATA STRUCTURES
# =============================================================================


@dataclass
class EmitResult:
    """
    Ek emit() call ka result — kaunse subscribers ko deliver hua / fail.

    delivered : kitne URLs par successfully POST hua
    failed    : kitne URLs par fail hua (sab retries ke baad)
    results   : per-URL detail (url, ok, status, attempts, error)
    event     : kaunsa event tha
    event_id  : envelope ka unique id
    """

    event: str = ""
    event_id: str = ""
    delivered: int = 0
    failed: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def any_delivered(self) -> bool:
        return self.delivered > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "event_id": self.event_id,
            "delivered": self.delivered,
            "failed": self.failed,
            "results": self.results,
            "any_delivered": self.any_delivered,
        }


@dataclass
class _Subscriber:
    """Ek registered subscriber endpoint + optional event filter."""

    url: str
    # None => saare events; warna sirf in events par bhejo
    events: set | None = None

    def wants(self, event: str) -> bool:
        return self.events is None or event in self.events


# =============================================================================
# WEBHOOK EMITTER
# =============================================================================


class WebhookEmitter:
    """
    Signed webhook event emitter — Retell/Vapi style.

    httpx ko lazily import karta hai (import-safe), taaki httpx missing hone par
    bhi module import na todhe. emit() kabhi raise nahi karta — har failure log
    hoke EmitResult me aata hai.

    Config sources (env/settings):
        WEBHOOK_URLS   : comma-separated subscriber endpoints (saare events)
        WEBHOOK_SECRET : HMAC signing secret (X-Signature ke liye)
        WEBHOOK_TIMEOUT_SECONDS  : per-request timeout (default 5.0)
        WEBHOOK_MAX_RETRIES      : max attempts (default 3)
    """

    def __init__(self):
        # --- Signing secret ---
        self.secret: str = getattr(settings, "webhook_secret", "") or ""

        # --- HTTP behaviour ---
        try:
            self.timeout: float = float(getattr(settings, "webhook_timeout_seconds", 5.0) or 5.0)
        except (ValueError, TypeError):
            self.timeout = 5.0
        try:
            self.max_retries: int = int(getattr(settings, "webhook_max_retries", 3) or 3)
        except (ValueError, TypeError):
            self.max_retries = 3
        if self.max_retries < 1:
            self.max_retries = 1

        # --- Subscribers (env-configured + in-process) ---
        # url -> _Subscriber (env subscribers get None event filter = all events)
        self._subscribers: dict[str, _Subscriber] = {}

        for url in self._parse_urls(getattr(settings, "webhook_urls", "")):
            self._subscribers[url] = _Subscriber(url=url, events=None)

        # Lazily-loaded httpx module (False = load failed sentinel)
        self._httpx = None

        if self._subscribers:
            logger.info(
                f"🔔 WebhookEmitter initialized — {len(self._subscribers)} endpoint(s) "
                f"configured, signing={'on' if self.secret else 'off'}"
            )
        else:
            logger.info(
                "🔔 WebhookEmitter initialized — no WEBHOOK_URLS configured "
                "(emit will be a safe no-op until subscribers are added)"
            )

    # ---------------------------------------------------------------------
    # Lazy / import-safe httpx accessor
    # ---------------------------------------------------------------------

    def _get_httpx(self):
        """httpx ko lazily import karo. Missing/error => None (no crash)."""
        if self._httpx is None:
            try:
                import httpx  # type: ignore

                self._httpx = httpx
            except Exception as e:
                logger.error(f"httpx not available — webhooks disabled: {e}")
                self._httpx = False  # sentinel: load failed
        return self._httpx or None

    # ---------------------------------------------------------------------
    # Subscription management (in-process)
    # ---------------------------------------------------------------------

    def subscribe(self, url: str, events: Iterable[str] | None = None) -> bool:
        """
        Runtime par ek subscriber register/update karo.

        Args:
            url    : endpoint URL (POST yahan hoga)
            events : optional list of WebhookEvent values — sirf in events par
                     bhejo. None => saare events.

        Returns:
            True agar register/update ho gaya, False agar url khaali tha.
        """
        url = (url or "").strip()
        if not url:
            logger.error("subscribe: empty url ignored")
            return False
        event_set = set(events) if events else None
        self._subscribers[url] = _Subscriber(url=url, events=event_set)
        logger.info(
            f"Webhook subscribed: {url} "
            f"(events={'all' if event_set is None else sorted(event_set)})"
        )
        return True

    def unsubscribe(self, url: str) -> bool:
        """Ek subscriber hata do. True agar tha aur hata diya."""
        url = (url or "").strip()
        if url in self._subscribers:
            del self._subscribers[url]
            logger.info(f"Webhook unsubscribed: {url}")
            return True
        logger.info(f"unsubscribe: {url} not found (no-op)")
        return False

    def list_subscribers(self) -> list[dict[str, Any]]:
        """Current subscribers ki readable list (debugging ke liye)."""
        return [
            {"url": s.url, "events": (None if s.events is None else sorted(s.events))}
            for s in self._subscribers.values()
        ]

    # ---------------------------------------------------------------------
    # PUBLIC API — emit
    # ---------------------------------------------------------------------

    async def emit(
        self,
        event: str,
        payload: dict[str, Any] | None = None,
        client_id: str | None = None,
    ) -> EmitResult:
        """
        Ek event ko saare matching subscribers par bhejo. KABHI raise nahi karta.

        Args:
            event     : WebhookEvent value (e.g. WebhookEvent.CALL_ENDED)
            payload   : event-specific data dict (envelope.data me jayega)
            client_id : optional tenant/client id (envelope.client_id)

        Returns:
            EmitResult — delivered/failed counts + per-url results.
        """
        result = EmitResult(event=str(event))

        try:
            envelope = self._build_envelope(event, payload, client_id)
            result.event_id = envelope["id"]

            # Matching subscribers (event filter respect karo)
            targets = [s for s in self._subscribers.values() if s.wants(event)]

            if not targets:
                # No-op path — zero config safe
                logger.info(
                    f"emit({event}): no matching subscribers — skipped (event_id={result.event_id})"
                )
                return result

            httpx_mod = self._get_httpx()
            if httpx_mod is None:
                # httpx missing — har target ko failed mark karo, par raise nahi
                logger.error(f"emit({event}): httpx unavailable, cannot deliver")
                for sub in targets:
                    result.failed += 1
                    result.results.append(
                        {
                            "url": sub.url,
                            "ok": False,
                            "status": None,
                            "attempts": 0,
                            "error": "httpx not installed",
                        }
                    )
                return result

            # Serialize once + sign once (same body har subscriber ko)
            body = self._serialize(envelope)
            signature = self._sign(body)
            headers = self._build_headers(signature, envelope)

            # Saare targets ko parallel me bhejo
            tasks = [self._post_with_retry(httpx_mod, sub.url, body, headers) for sub in targets]
            per_url = await asyncio.gather(*tasks, return_exceptions=True)

            for sub, res in zip(targets, per_url, strict=False):
                if isinstance(res, Exception):
                    # gather me exception aa hi nahi sakta (handler safe hai),
                    # par double-defensive
                    logger.error(f"emit({event}): unexpected error for {sub.url}: {res}")
                    result.failed += 1
                    result.results.append(
                        {
                            "url": sub.url,
                            "ok": False,
                            "status": None,
                            "attempts": 0,
                            "error": str(res),
                        }
                    )
                    continue
                result.results.append(res)
                if res.get("ok"):
                    result.delivered += 1
                else:
                    result.failed += 1

            logger.info(
                f"emit({event}) done — delivered={result.delivered} "
                f"failed={result.failed} event_id={result.event_id}"
            )
            return result

        except Exception as e:
            # Top-level safety net — emit NEVER raises
            logger.error(f"emit({event}): unexpected top-level error: {e}")
            return result

    async def emit_batch(
        self,
        events: Iterable[tuple[str, dict[str, Any] | None, str | None]],
    ) -> list[EmitResult]:
        """
        Multiple events ek saath emit karo.

        Args:
            events : iterable of (event, payload, client_id) tuples.
                     payload/client_id optional hain — tuple chhota bhi ho sakta:
                       (event,)
                       (event, payload)
                       (event, payload, client_id)

        Returns:
            List[EmitResult] — har event ka result. Ek fail ho to baaki continue.
        """
        results: list[EmitResult] = []
        for item in events or []:
            try:
                if not isinstance(item, (tuple, list)):
                    # Sirf event name diya ho
                    event, payload, client_id = item, None, None
                else:
                    event = item[0] if len(item) > 0 else WebhookEvent.ERROR
                    payload = item[1] if len(item) > 1 else None
                    client_id = item[2] if len(item) > 2 else None
                res = await self.emit(event, payload, client_id)
            except Exception as e:
                # emit vaise hi safe hai, par batch-level double-defensive
                logger.error(f"emit_batch: error processing an event: {e}")
                res = EmitResult(event=str(item))
            results.append(res)
        logger.info(f"emit_batch complete: {len(results)} event(s) processed")
        return results

    # ---------------------------------------------------------------------
    # SIGNATURE VERIFICATION (for receivers)
    # ---------------------------------------------------------------------

    @staticmethod
    def verify_signature(secret: str, body: Any, signature: str) -> bool:
        """
        Incoming webhook ki HMAC-SHA256 signature verify karta hai (receiver side).

        Args:
            secret    : wahi WEBHOOK_SECRET jo emit karte waqt use hua
            body      : raw request body (bytes ya str)
            signature : "X-Signature" header value — "sha256=<hex>" ya raw "<hex>"

        Returns:
            True agar signature valid hai. Constant-time compare use karta hai.
            Koi bhi error/missing input par False (kabhi raise nahi).
        """
        try:
            if not secret or not signature:
                return False

            if isinstance(body, str):
                body_bytes = body.encode("utf-8")
            elif isinstance(body, (bytes, bytearray)):
                body_bytes = bytes(body)
            else:
                # dict/other => same compact serialization jaise emit karta hai
                body_bytes = WebhookEmitter._serialize_static(body)

            # "sha256=" prefix strip karo agar ho
            sig = signature.strip()
            if sig.lower().startswith("sha256="):
                sig = sig[len("sha256=") :]

            expected = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

            return hmac.compare_digest(expected, sig)
        except Exception as e:
            logger.error(f"verify_signature error: {e}")
            return False

    # ---------------------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------------------

    def _build_envelope(
        self,
        event: str,
        payload: dict[str, Any] | None,
        client_id: str | None,
    ) -> dict[str, Any]:
        """Standard event envelope banao."""
        return {
            "id": uuid.uuid4().hex,
            "event": str(event),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "client_id": client_id,
            "data": payload or {},
        }

    @staticmethod
    def _serialize_static(envelope: dict[str, Any]) -> bytes:
        """
        Envelope -> deterministic compact UTF-8 bytes. sorted_keys taaki sender
        aur receiver dono same bytes par HMAC compute karein (signature match ho).
        """
        return json.dumps(envelope, separators=(",", ":"), sort_keys=True, default=str).encode(
            "utf-8"
        )

    def _serialize(self, envelope: dict[str, Any]) -> bytes:
        return self._serialize_static(envelope)

    def _sign(self, body: bytes) -> str:
        """HMAC-SHA256 hex signature ("sha256=<hex>"). Secret na ho to "" return."""
        if not self.secret:
            return ""
        try:
            digest = hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            return f"sha256={digest}"
        except Exception as e:
            logger.error(f"signing error: {e}")
            return ""

    def _build_headers(self, signature: str, envelope: dict[str, Any]) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LeadGenAI-Webhooks/1.0",
            "X-Webhook-Event": str(envelope.get("event", "")),
            "X-Webhook-Id": str(envelope.get("id", "")),
        }
        if signature:
            headers["X-Signature"] = signature
        return headers

    async def _post_with_retry(
        self,
        httpx_mod,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """
        Ek URL par POST with exponential backoff retry. Kabhi raise nahi karta —
        per-url result dict return karta hai.
        """
        attempts = 0
        last_error = ""
        last_status: int | None = None

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                async with httpx_mod.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, content=body, headers=headers)
                    last_status = resp.status_code
                    if 200 <= resp.status_code < 300:
                        logger.info(f"webhook POST ok: {url} (status={resp.status_code})")
                        return {
                            "url": url,
                            "ok": True,
                            "status": resp.status_code,
                            "attempts": attempt,
                            "error": None,
                        }
                    # Non-2xx — retryable for 5xx / 429, else give up
                    last_error = f"HTTP {resp.status_code}"
                    if resp.status_code < 500 and resp.status_code != 429:
                        logger.error(f"webhook POST non-retryable: {url} status={resp.status_code}")
                        break
                    logger.error(
                        f"webhook POST retryable fail: {url} status={resp.status_code} "
                        f"(attempt {attempt}/{self.max_retries})"
                    )
            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"webhook POST error: {url} ({e}) (attempt {attempt}/{self.max_retries})"
                )

            # Backoff before next attempt (last attempt ke baad nahi)
            if attempt < self.max_retries:
                backoff = min(2 ** (attempt - 1), 30)  # 1s, 2s, 4s ... capped 30s
                try:
                    await asyncio.sleep(backoff)
                except Exception:
                    pass

        return {
            "url": url,
            "ok": False,
            "status": last_status,
            "attempts": attempts,
            "error": last_error or "unknown error",
        }

    @staticmethod
    def _parse_urls(raw: Any) -> list[str]:
        """Comma-separated URL string ko clean list me todho."""
        if not raw:
            return []
        if isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            items = str(raw).split(",")
        out: list[str] = []
        for item in items:
            u = str(item).strip()
            if u and u not in out:
                out.append(u)
        return out


# =============================================================================
# SINGLETON
# =============================================================================

_webhook_emitter_instance: WebhookEmitter | None = None


def get_webhook_emitter() -> WebhookEmitter:
    """Process-wide singleton WebhookEmitter instance return karta hai."""
    global _webhook_emitter_instance
    if _webhook_emitter_instance is None:
        _webhook_emitter_instance = WebhookEmitter()
    return _webhook_emitter_instance
