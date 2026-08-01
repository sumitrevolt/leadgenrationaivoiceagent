"""Self-hosted WhatsApp stack client — WAHA Core (our own API, no Meta verification).

WHY THIS EXISTS
---------------
The OFFICIAL Meta Cloud API (``app/integrations/whatsapp.py``) needs Meta **Business
verification** + a registered phone number + template approval. That verification — not
"having a number" — was the real blocker. A self-hosted WhatsApp-Web stack (WAHA Core,
GPL, single Docker container) links an EXISTING WhatsApp account by QR scan and exposes a
plain HTTP API, so we own the whole stack and skip Meta verification.

⚠️  BAN RISK — read before enabling
-----------------------------------
A Web-session stack has NO template / 24-hour-window protection that the Cloud API gives
you. So the ban-safety guards (suppression, daily cap, spacing, opt-out) matter MORE here,
not less. Safe use = **inbound auto-reply + warm 1-to-1 + low-volume opt-in**. Bulk
cold-blasting on a Web session is what gets a real number banned fast. Cloud API remains
the only truly ban-proof path; this is a deliberate verification-vs-banrisk tradeoff.

DESIGN
------
- Inert without ``WAHA_BASE_URL`` (returns ``{"error": "selfhost_not_configured"}``).
- Inert unless :func:`app.integrations.whatsapp.send_permitted` says yes — the §5
  ban-safety gate lives at the sender boundary (``WHATSAPP_AUTO_SEND`` + Owner-OS kill,
  canary ``WHATSAPP_SEND_ALLOWLIST``, DPDP/TCCCPR opt-out ledger; all fail-CLOSED) and is
  checked before ANY HTTP call, so a gated-off platform never touches WAHA. This is the
  engine that can actually get a real number banned, so it most needs the default-deny.
- Never raises — every send/HTTP path returns a dict on error so campaign runners stay
  crash-safe (same contract as the Cloud-API integration).
- Thin HTTP client. WAHA wire-format is isolated in private helpers so swapping the engine
  to Evolution API (AGPL drop-in: ``POST /message/sendText/{instance}``) is a small change.
- A number can be on EITHER Cloud API OR this Web-session stack — never both at once.

WAHA Core endpoints used (all free in Core):
  POST {base}/api/sendText               {session, chatId, text}     -> send a text
  GET  {base}/api/sessions/{session}     -> {"status": "WORKING"|"SCAN_QR_CODE"|...}
  POST {base}/api/sessions/start         {name: session}             -> start/relink session
  GET  {base}/api/{session}/auth/qr?format=image  -> image/png QR bytes (scan to link)
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.integrations.whatsapp import (
    WhatsAppMessageMixin,
    _record_whatsapp_failure,
    _record_whatsapp_success,
    auto_send_blocked,
    send_permitted,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# --------------------------------------------------------------------------- #
# Config helpers
# --------------------------------------------------------------------------- #
def _base_url() -> str:
    return (
        (os.getenv("WAHA_BASE_URL", "") or getattr(settings, "waha_base_url", "") or "")
        .strip()
        .rstrip("/")
    )


def _api_key() -> str:
    return (os.getenv("WAHA_API_KEY", "") or getattr(settings, "waha_api_key", "") or "").strip()


def _session() -> str:
    return (
        os.getenv("WAHA_SESSION", "") or getattr(settings, "waha_session", "") or "default"
    ).strip() or "default"


def is_configured() -> bool:
    """True only if a self-hosted WAHA base URL is set (the stack is reachable)."""
    return bool(_base_url())


def _business_number_digits() -> str:
    """Configured company WhatsApp number, digits only (WHATSAPP_BUSINESS_NUMBER)."""
    raw = (
        os.getenv("WHATSAPP_BUSINESS_NUMBER", "")
        or getattr(settings, "whatsapp_business_number", "")
        or ""
    )
    return "".join(c for c in str(raw) if c.isdigit())


# Cache the WAHA session's linked number so we don't status-probe on every send.
_LINKED_CACHE: dict[str, Any] = {"digits": None, "at": 0.0}
_LINKED_TTL_S = 300.0


async def linked_number_digits() -> str | None:
    """Digits of the number the WAHA session is currently logged into (me.id),
    cached for 5 min. None if unknown (status hiccup / not linked). Never raises."""
    import time as _t

    now = _t.monotonic()
    if _LINKED_CACHE["digits"] is not None and (now - _LINKED_CACHE["at"]) < _LINKED_TTL_S:
        return _LINKED_CACHE["digits"] or None
    try:
        st = await session_status()
        me = (st or {}).get("me") or {}
        raw = str(me.get("id") or "").split("@")[0]
        digits = "".join(c for c in raw if c.isdigit())
        _LINKED_CACHE["digits"] = digits
        _LINKED_CACHE["at"] = now
        return digits or None
    except Exception:
        return None


def is_active_provider() -> bool:
    """True if the operator selected the self-host stack as the active WhatsApp provider."""
    prov = (
        (
            os.getenv("WHATSAPP_PROVIDER", "")
            or getattr(settings, "whatsapp_provider", "")
            or "cloud"
        )
        .strip()
        .lower()
    )
    # Only "waha"/"selfhost" are wired (WAHA HTTP format). Evolution API is a documented
    # drop-in alt but a different wire-format — don't claim it until its client is added.
    return prov in ("waha", "selfhost", "self_host") and is_configured()


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        h["X-Api-Key"] = key
    return h


def _chat_id(number: str) -> str:
    """WAHA personal-chat id: ``<digits>@c.us``. Adds India CC for bare 10-digit numbers."""
    digits = "".join(c for c in (number or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    elif digits.startswith("0"):
        digits = "91" + digits[1:]
    return f"{digits}@c.us"


def _recipient_check_fail_open() -> bool:
    """Ops escape hatch for the recipient-check gate. Default ``0`` = fail-CLOSED.

    Set ``WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN=1`` only to restore the old behaviour where
    a recipient check that never completed (transport/HTTP error) still let the send
    through. Exists so a WAHA-side outage can be worked around without a code deploy.
    """
    return os.getenv("WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _render(body: str, params: list[str] | None) -> str:
    """Fill ``{{1}}``, ``{{2}}`` ... placeholders (Web sessions have no Meta templates)."""
    text = body or ""
    for i, p in enumerate(params or [], start=1):
        text = text.replace("{{%d}}" % i, str(p))
    return text


# --------------------------------------------------------------------------- #
# Client — same method shape as WhatsAppIntegration (so the selector is drop-in)
# --------------------------------------------------------------------------- #
class SelfHostWhatsApp(WhatsAppMessageMixin):
    """WAHA Core HTTP client. Mirrors ``WhatsAppIntegration`` send signatures.

    Inherits the lead-alert / appointment / callback / daily-report helpers from the mixin,
    so notification call-sites work identically on the self-hosted engine.
    """

    def __init__(self) -> None:
        self.base_url = _base_url()
        self.session = _session()

    async def _recipient_check(self, to_number: str) -> dict[str, Any]:
        """Check recipient registration before WAHA accepts a send.

        WAHA may return HTTP 201 before WhatsApp asynchronously rejects an
        unregistered/restricted contact. An explicit ``numberExists=false`` is
        therefore a hard block; older WAHA/fake responses without that field
        stay backward-compatible and continue through the existing path.
        """
        digits = "".join(c for c in (to_number or "") if c.isdigit())
        if len(digits) == 10:
            digits = "91" + digits
        elif digits.startswith("0"):
            digits = "91" + digits[1:]
        if not digits:
            return {"known": True, "exists": False, "reason": "invalid_recipient"}
        try:
            query = urlencode({"phone": digits, "session": self.session})
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.base_url}/api/contacts/check-exists?{query}",
                    headers=_headers(),
                    timeout=10.0,
                )
                if resp.status_code >= 400:
                    return {
                        "known": False,
                        "reason": "check_http_error",
                        "status": resp.status_code,
                        "transport_error": True,
                    }
                data = resp.json() if resp.content else {}
                if not isinstance(data, dict) or "numberExists" not in data:
                    # WAHA ANSWERED, we just can't read the shape (older WAHA / fake).
                    # Deliberately NOT a transport error — see the fail-closed note in
                    # send_text_message for why this one stays permissive.
                    return {"known": False, "reason": "check_shape_unknown"}
                exists = bool(data.get("numberExists"))
                return {
                    "known": True,
                    "exists": exists,
                    "chat_id": str(data.get("chatId") or "").strip(),
                }
        except Exception as e:
            logger.warning("waha recipient check failed: %s", e)
            return {"known": False, "reason": "check_unreachable", "transport_error": True}

    async def send_text_message(self, to_number: str, message: str) -> dict[str, Any]:
        """Send a plain text message via the self-hosted session. Never raises.

        Business-number guard (2026-07-04 owner-ask "messages company number se
        jaayein"): if WHATSAPP_BUSINESS_NUMBER is configured and the WAHA session
        is linked to a DIFFERENT number (e.g. an admin's personal WhatsApp got
        scanned by mistake), REFUSE the send instead of leaking a wrong sender to
        a customer. Fail-OPEN only when the linked number can't be determined
        (status hiccup) so a transient probe error never silently drops sends.
        Kill-switch: WHATSAPP_ENFORCE_BUSINESS_NUMBER=0.

        §5 BAN-SAFETY GATE (2026-07-31): :func:`send_permitted` is checked FIRST — before
        the business-number probe and before the recipient check — so a gated-off platform
        makes NO HTTP call at all, not merely no POST. That matters: ``_recipient_check``
        issues a ``GET /api/contacts/check-exists``, so gating later would still have the
        hourly ``onboard`` job hammering WAHA once per active client. The gate covers
        ``WHATSAPP_AUTO_SEND`` + Owner-OS kill, the canary allowlist, and the DPDP/TCCCPR
        opt-out ledger — all fail-CLOSED."""
        if not self.base_url:
            _record_whatsapp_failure("selfhost_not_configured")
            return {"error": "selfhost_not_configured"}
        ok, reason = send_permitted(to_number)
        if not ok:
            return auto_send_blocked(to_number, message, reason)
        if os.getenv("WHATSAPP_ENFORCE_BUSINESS_NUMBER", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        ):
            want = _business_number_digits()
            if want:
                linked = await linked_number_digits()
                if linked and linked[-10:] != want[-10:]:
                    logger.error(
                        "waha send BLOCKED — session linked to ***%s but business "
                        "number is ***%s. Re-scan WAHA QR with the company phone.",
                        linked[-4:],
                        want[-4:],
                    )
                    _record_whatsapp_failure("wrong_linked_number")
                    return {
                        "error": "wrong_linked_number",
                        "linked": linked[-4:],
                        "want": want[-4:],
                    }
        check = await self._recipient_check(to_number)
        if check.get("known") and check.get("exists") is False:
            reason = str(check.get("reason") or "recipient_not_on_whatsapp")
            # NOT an integration failure: WAHA answered correctly — this recipient
            # simply has no WhatsApp account. Recording it as an integration fault
            # let synthetic/test numbers (919123456780 etc.) drive whatsapp to
            # fail_rate 0.973 and write a DAILY false "WhatsApp integration failing"
            # into a real paying customer's delivery ledger while WhatsApp was fine.
            # Real integration faults (not_configured / wrong_linked_number / transport
            # errors in _post) are still recorded.
            logger.info("waha send blocked — recipient not on WhatsApp (%s)", reason)
            return {"error": "recipient_not_on_whatsapp", "status": "blocked", "reason": reason}
        # FAIL-CLOSED (2026-07-31): a recipient check that never COMPLETED (network error,
        # HTTP 4xx/5xx) used to fall straight through to a real send — the one guard on
        # this path failed OPEN. §5 treats send-path compliance gates as fail-closed, so
        # an unverifiable recipient is now a blocked send. Recorded as an integration
        # failure because, unlike recipient_not_on_whatsapp, this IS our side breaking.
        # Backward-compat: `check_shape_unknown` (older WAHA answered without
        # `numberExists`) is NOT a transport error and still proceeds.
        # Kill-switch: WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN=1.
        if check.get("transport_error") and not _recipient_check_fail_open():
            reason = str(check.get("reason") or "check_unreachable")
            logger.error("waha send BLOCKED — recipient check did not complete (%s)", reason)
            _record_whatsapp_failure(f"recipient_check_{reason}")
            return {"error": "recipient_check_failed", "status": "blocked", "reason": reason}
        payload = {
            "session": self.session,
            "chatId": str(check.get("chat_id") or _chat_id(to_number)),
            "text": message or "",
        }
        return await self._post("/api/sendText", payload)

    async def send_template_message(
        self,
        to_number: str,
        template_name: str,
        template_params: list[str] | None = None,
        language: str = "en",
    ) -> dict[str, Any]:
        """No real templates on a Web session — render the local template body to text.

        Looks up the template record (registered in the WhatsApp panel) and substitutes
        ``{{1}}`` params, then sends as a normal text message. Falls back to the raw
        template name if no body is on record.
        """
        if not self.base_url:
            _record_whatsapp_failure("selfhost_not_configured")
            return {"error": "selfhost_not_configured"}
        body = ""
        try:
            from app.marketing import wa_campaign_runner as runner

            tpl = runner.get_template(template_name, language)
            body = (tpl or {}).get("body", "") if tpl else ""
        except Exception:
            body = ""
        text = _render(body, template_params) if body else (template_name or "")
        return await self.send_text_message(to_number, text)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        # §5 EGRESS BACKSTOP — send_text_message already gated; this is the only function
        # that actually POSTs to WAHA, so a future caller that skips the public method
        # still cannot send (same 3-layer idea as platform_dial's hard-off).
        _to = str(payload.get("chatId") or "")
        ok, reason = send_permitted(_to)
        if not ok:
            return auto_send_blocked(_to, str(payload.get("text") or ""), reason)
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=_headers(), json=payload, timeout=30.0)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception:
                    data = {"ok": True}
                # Normalise to look like the Cloud-API success shape (id under messages[0].id)
                mid = ""
                if isinstance(data, dict):
                    mid = str(data.get("id") or (data.get("_data") or {}).get("id") or "")
                logger.info("waha send ok (%s) id=%s", self.session, mid[:40])
                _record_whatsapp_success()
                return {
                    "messages": [{"id": mid}] if mid else [],
                    "raw": data,
                    "accepted": True,
                    "delivery_status": "accepted",
                }
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text
            except Exception:
                pass
            logger.error("waha API error: %s", body[:300])
            _record_whatsapp_failure(f"waha_http_{getattr(e.response, 'status_code', 0)}")
            return {
                "error": "http_error",
                "status": getattr(e.response, "status_code", 0),
                "detail": body[:300],
            }
        except Exception as e:  # network / timeout / DNS
            logger.warning("waha request failed: %s", e)
            _record_whatsapp_failure(str(e)[:80])
            return {"error": "request_failed", "detail": str(e)[:200]}


# --------------------------------------------------------------------------- #
# Session management (link / status / QR) — used by admin endpoints
# --------------------------------------------------------------------------- #
async def session_status() -> dict[str, Any]:
    """Return the linked-session state. Never raises.

    status values (WAHA): STARTING / SCAN_QR_CODE / WORKING / FAILED / STOPPED.
    """
    base = _base_url()
    if not base:
        return {"configured": False, "status": "not_configured"}
    sess = _session()
    url = f"{base}/api/sessions/{sess}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=_headers(), timeout=15.0)
            if resp.status_code == 404:
                return {"configured": True, "session": sess, "status": "NOT_CREATED"}
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            status = str((data or {}).get("status", "")).upper() or "UNKNOWN"
            me = (data or {}).get("me") or {}
            out = {
                "configured": True,
                "session": sess,
                "status": status,
                "working": status == "WORKING",
            }
            # Expose the LINKED number so admin UIs can verify it's the company
            # WhatsApp, not an admin's personal one (2026-07-04). me.id = "<num>@c.us".
            if isinstance(me, dict) and me.get("id"):
                out["me"] = {"id": me.get("id"), "pushName": me.get("pushName")}
                out["me_number"] = str(me.get("id")).split("@")[0]
            return out
    except Exception as e:
        logger.warning("waha session_status err: %s", e)
        return {"configured": True, "session": sess, "status": "UNREACHABLE", "error": str(e)[:120]}


def _default_config() -> dict[str, Any]:
    """Session config used on (re)create — mirrors the container's own
    WHATSAPP_HOOK_URL/EVENTS env so a manually re-created session still wires
    to our inbound webhook."""
    token = (
        os.getenv("WAHA_WEBHOOK_TOKEN", "") or getattr(settings, "waha_webhook_token", "") or ""
    ).strip()
    base = (getattr(settings, "public_base_url", "") or "https://leadsgenai.in").rstrip("/")
    return {
        "webhooks": [
            {"url": f"{base}/api/wa/selfhost/webhook?token={token}", "events": ["message"]}
        ]
    }


async def start_session() -> dict[str, Any]:
    """Idempotent, self-healing start/relink of the session. Never raises.

    2026-07-04: the previous implementation always POSTed the deprecated
    singular ``/api/sessions/start`` — if the session was ALREADY running
    (e.g. someone linked it directly via the WAHA API, or a second dashboard
    click), WAHA replies 422 "Session 'default' is already started" and the
    dashboard showed a scary "Start failed". Now:
      - already WORKING/SCAN_QR_CODE/STARTING -> success no-op (nothing to do)
      - missing/NOT_CREATED -> create (with our webhook config) then start
      - FAILED -> WAHA's own guidance ("restart, if that doesn't help logout
        + start again") -> logout + delete + recreate + start
      - STOPPED -> start directly

    After this the session should be in SCAN_QR_CODE (or WORKING if already
    linked) — fetch the QR and scan it on the phone holding the business number.
    """
    base = _base_url()
    if not base:
        return {"ok": False, "error": "selfhost_not_configured"}
    sess = _session()
    cur = await session_status()
    st = str(cur.get("status") or "").upper()
    if st in ("WORKING", "SCAN_QR_CODE", "STARTING"):
        return {"ok": True, "status": st, "already_running": True}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if st in ("", "UNKNOWN", "NOT_CREATED"):
                await client.post(
                    f"{base}/api/sessions",
                    headers=_headers(),
                    json={"name": sess, "config": _default_config()},
                    timeout=15.0,
                )
            elif st == "FAILED":
                for path, method in (
                    (f"/api/sessions/{sess}/logout", "post"),
                    (f"/api/sessions/{sess}", "delete"),
                ):
                    try:
                        await getattr(client, method)(
                            f"{base}{path}", headers=_headers(), timeout=10.0
                        )
                    except Exception:
                        pass
                await client.post(
                    f"{base}/api/sessions",
                    headers=_headers(),
                    json={"name": sess, "config": _default_config()},
                    timeout=15.0,
                )
            resp = await client.post(
                f"{base}/api/sessions/{sess}/start", headers=_headers(), timeout=20.0
            )
            ok = resp.status_code < 400
            return {"ok": ok, "session": sess, "status_code": resp.status_code}
    except Exception as e:
        logger.warning("waha start_session err: %s", e)
        return {"ok": False, "session": sess, "error": str(e)[:160]}


async def qr_image() -> tuple[bytes | None, str]:
    """Fetch the link QR as image bytes. Returns ``(bytes_or_None, content_type)``. Never raises."""
    base = _base_url()
    if not base:
        return None, "application/json"
    sess = _session()
    url = f"{base}/api/{sess}/auth/qr?format=image"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=_headers(), timeout=20.0)
            if resp.status_code >= 400:
                return None, "application/json"
            return resp.content, resp.headers.get("content-type", "image/png")
    except Exception as e:
        logger.warning("waha qr_image err: %s", e)
        return None, "application/json"


__all__ = [
    "SelfHostWhatsApp",
    "is_configured",
    "is_active_provider",
    "session_status",
    "start_session",
    "qr_image",
]
