"""
WhatsApp Business API Integration
Send lead notifications and follow-ups via WhatsApp

OFFICIAL Meta Cloud API only (graph.facebook.com). Never uses an unofficial
gateway (baileys/web get the number banned). Send helpers degrade gracefully —
on any error they return a dict with an ``error`` key instead of raising, so
background campaign runners never crash. Webhook payload signatures are verified
with the Meta App Secret (``WHATSAPP_APP_SECRET``) via :func:`verify_meta_signature`.

🚨 §5 BAN-SAFETY BOUNDARY GATE (2026-07-31)
-------------------------------------------
``WHATSAPP_AUTO_SEND`` is enforced HERE, at the sender boundary — not only in the
campaign modules. Before this, only campaign-level callers
(``whatsapp_campaign`` / ``review_engine`` / ``product_one_delivery``) consulted the
flag, so any OTHER caller sent for real with nothing gating it. The hourly ``onboard``
scheduler job was doing exactly that: ``onboarding._send_whatsapp`` →
``get_whatsapp_sender().send_text_message`` → a live ``POST /api/sendText`` to every
active client's ``contact_phone``, hourly, with no flag in the chain. Only a FAILED WAHA
session was stopping real delivery.

Every send now passes :func:`send_permitted` and, when it denies, returns the
:func:`auto_send_blocked` "would-send" result carrying a ban-safe 1-click ``wa.me``
link instead of POSTing. New callers are therefore gated by DEFAULT rather than by
each caller remembering.

:func:`send_permitted` composes three fail-CLOSED stages, cheapest-and-most-likely-to-
deny first, so a gated-off platform touches neither the opt-out ledger nor the network::

    WHATSAPP_AUTO_SEND (+ Owner-OS kill)  ->  canary allowlist  ->  opt-out ledger

The allowlist exists because flipping the flag must not immediately reach every client,
and the opt-out check moved here because only the CAMPAIGN path used to consult it —
`onboarding` / `customer_delivery` / `lead_delivery` / `post_call_hooks` would otherwise
message a number that had explicitly opted out (DPDP + §5).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.utils.file_lock import file_lock
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# Graph API version is overridable without a code change (Meta deprecates old graph versions).
GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_VERSION", "v18.0").strip() or "v18.0"


def _record_whatsapp_failure(note: str = "") -> None:
    """Best-effort Integration Health signal. Never raise on a send path."""
    try:
        from app.platform import integration_health

        integration_health.record_failure("whatsapp", note)
    except Exception:
        pass


def _record_whatsapp_success() -> None:
    """Best-effort Integration Health signal. Never raise on a send path."""
    try:
        from app.platform import integration_health

        integration_health.record_success("whatsapp")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# §5 ban-safety boundary gate — the single choke point every send passes through
# --------------------------------------------------------------------------- #
def _wa_link(to_number: str, message: str = "") -> str:
    """Ban-safe 1-click ``wa.me`` link (a human taps Send). Always available, never raises."""
    digits = "".join(c for c in str(to_number or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    elif digits.startswith("0"):
        digits = "91" + digits[1:]
    return f"https://wa.me/{digits}?text={quote(message or '')}"


def auto_send_allowed() -> bool:
    """§5 gate for EVERY automatic WhatsApp send. **Fail-CLOSED.**

    Delegates to :func:`app.marketing.whatsapp_campaign.auto_send_enabled` so there is
    exactly ONE definition of "auto-send is on" — that helper folds in both
    ``WHATSAPP_AUTO_SEND`` and the Owner-OS ``owner_whatsapp_outbound`` kill switch.
    Imported lazily (send-path idiom; also keeps ``integrations`` free of a marketing
    import at module scope).

    Unreadable gate == DENY. This is a compliance gate (§5 ban-safety), not a billing
    meter — the fail-OPEN convention does not apply here.
    """
    try:
        from app.marketing.whatsapp_campaign import auto_send_enabled

        return bool(auto_send_enabled())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("whatsapp auto-send gate unreadable -> DENY: %s", exc)
        return False


def auto_send_blocked(
    to_number: str, message: str = "", reason: str = "auto_send_disabled"
) -> dict[str, Any]:
    """The "would-send" result returned INSTEAD of POSTing when the gate is off.

    Carries an ``error`` key on purpose: every caller in this repo detects success with
    ``bool(res) and not res.get("error")`` (onboarding.py:215, reply_agent.py:1493,
    whatsapp_campaign.py:162), so a shape without it would be read as a successful send.
    NOT recorded as an integration failure — nothing is broken, the operator just has
    auto-send off.

    The would-send is ALSO persisted to the pending-drafts inbox (see
    :func:`_persist_pending_draft`) so the block counter is not the only artefact of a
    real customer intent. Persistence is strictly best-effort: it sits on a hot
    outbound path and must leave this function's return value byte-for-byte identical
    even when storage is unavailable.
    """
    _record_block(reason)
    logger.info("whatsapp auto-send BLOCKED (%s) — 1-click link only (§5 ban-safety)", reason)
    result = {
        "error": reason,
        "status": "blocked",
        "mode": "link",
        "would_send": True,
        "link": _wa_link(to_number, message),
    }
    try:
        _persist_pending_draft(
            {
                "id": _new_draft_id(),
                "ts": _now_iso(),
                "to": _digits_only(to_number),
                "message": (message or "")[:_DRAFT_MSG_MAX],
                "link": result["link"],
                "reason": reason,
                "sent": False,
                "sent_ts": None,
            }
        )
    except Exception as exc:  # pragma: no cover - storage must never break a send path
        logger.debug("whatsapp draft not persisted (send path unaffected): %s", exc)
    return result


# --------------------------------------------------------------------------- #
# Canary allowlist + opt-out — the two gates that matter the DAY the flag goes on
# --------------------------------------------------------------------------- #
def _digits_only(number: str) -> str:
    """India-normalised digits (bare 10-digit and leading-0 forms get the 91 CC)."""
    digits = "".join(c for c in str(number or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    elif digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits


def send_allowlist() -> list[str]:
    """Normalised ``WHATSAPP_SEND_ALLOWLIST`` entries. Empty = nobody. ``*`` = everybody.

    Canary posture: turning ``WHATSAPP_AUTO_SEND=1`` on must NOT immediately reach every
    client. The operator names the canary recipients first, verifies, and only then
    graduates by setting the list to ``*``. The ``*``-means-explicit-all convention is
    copied from ``VIDEO_CUSTOMER_REVIEW_CLIENTS`` rather than invented here.

    Never raises. Numbers live in ``.env`` only — never in a tracked file.
    """
    raw = os.getenv("WHATSAPP_SEND_ALLOWLIST", "") or ""
    out: list[str] = []
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        tok = part.strip()
        if not tok:
            continue
        if tok == "*":
            return ["*"]
        d = _digits_only(tok)
        if d:
            out.append(d)
    return out


def allowlist_permits(to_number: str) -> tuple[bool, str]:
    """(allowed, reason). **Fail-CLOSED** — unreadable or empty list denies."""
    try:
        allow = send_allowlist()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("whatsapp allowlist unreadable -> DENY: %s", exc)
        return False, "allowlist_unreadable"
    if not allow:
        return False, "allowlist_empty"
    if allow == ["*"]:
        return True, ""
    return (True, "") if _digits_only(to_number) in allow else (False, "recipient_not_allowlisted")


def opt_out_permits(to_number: str) -> tuple[bool, str]:
    """(allowed, reason). **Fail-CLOSED** on the DPDP/TCCCPR opt-out ledger.

    Until now only the CAMPAIGN path consulted suppression — `onboarding`,
    `customer_delivery`, `lead_delivery` and `post_call_hooks` could message a number
    that had explicitly opted out. §5 requires opt-out to be an INSTANT cross-channel
    suppression, so the check belongs at the boundary every send crosses, not in the
    callers that happened to remember it.

    ``consent_ledger.is_suppressed`` is already fail-closed when the ledger cannot be
    resolved; the local suppression store (repeatedly-failed / blocked numbers) is
    consulted too. An exception here denies.
    """
    try:
        from app.telephony import consent_ledger

        if consent_ledger.is_suppressed(to_number):
            return False, "opted_out"
    except Exception as exc:
        logger.warning("whatsapp opt-out ledger unreadable -> DENY: %s", exc)
        return False, "opt_out_unreadable"
    try:
        from app.marketing import wa_campaign_runner

        if wa_campaign_runner.is_suppressed(to_number):
            return False, "suppressed"
    except Exception as exc:
        logger.warning("whatsapp suppression store unreadable -> DENY: %s", exc)
        return False, "suppression_unreadable"
    return True, ""


def send_permitted(to_number: str) -> tuple[bool, str]:
    """The ONE composite decision every automated WhatsApp send passes. Fail-CLOSED.

    Order is deliberate — cheapest and most-likely-to-deny first, so a gated-off
    platform never touches the opt-out ledger or the network::

        WHATSAPP_AUTO_SEND (+ Owner-OS kill)  ->  canary allowlist  ->  opt-out ledger

    Returns ``(True, "")`` or ``(False, <machine-readable reason>)``.
    """
    if not auto_send_allowed():
        return False, "auto_send_disabled"
    ok, reason = allowlist_permits(to_number)
    if not ok:
        return False, reason
    return opt_out_permits(to_number)


# In-process block counters. Deliberately NOT `team.log_event`: the onboard job alone
# would write ~216 DB rows/day of "still blocked", which is noise, not an audit trail.
# NO phone number and NO message content is ever recorded here — reason codes only.
_BLOCK_COUNTS: dict[str, int] = {}


def _record_block(reason: str) -> None:
    """Count one blocked send by REASON. No PII. Never raises."""
    try:
        _BLOCK_COUNTS[reason] = _BLOCK_COUNTS.get(reason, 0) + 1
    except Exception:  # pragma: no cover - defensive
        pass


def block_stats() -> dict[str, int]:
    """Blocked-send counts by reason, for admin visibility. No PII."""
    return dict(_BLOCK_COUNTS)


# --------------------------------------------------------------------------- #
# Pending-drafts inbox — the queue a human actually works
# --------------------------------------------------------------------------- #
# `_record_block` above counts a blocked send but throws the would-send away: the
# wa.me link and the message it just built were discarded, so 1800+ real customer
# intents a day produced a counter and nothing to click. This store is that inbox.
# It is an OPERATOR queue for HUMAN sending — it never POSTs anything anywhere.
#
# PII: rows contain phone numbers and message bodies. They live under `data/`
# (runtime, untracked) like every other store in this repo, and must never be logged.
_DRAFT_MSG_MAX = 2000
_DEFAULT_DRAFT_CAP = 500
_DRAFT_CAP_MAX = 5000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _drafts_path() -> str:
    """Resolved per call (never frozen at import) so tests can monkeypatch."""
    try:
        from app.platform import runtime_data_authority as _auth

        return str(
            _auth.resolve_store_path(
                store_id="whatsapp.pending_drafts",
                legacy_path=Path("data/whatsapp_pending_drafts.jsonl"),
                target_segments=("messaging", "whatsapp_pending_drafts.jsonl"),
            )
        )
    except Exception:
        return os.path.join("data", "whatsapp_pending_drafts.jsonl")


def draft_cap() -> int:
    """Pending rows retained. Garbage -> 500, <=0 -> 1, huge -> 5000."""
    try:
        cap = int((os.getenv("WHATSAPP_DRAFT_CAP", "") or "").strip())
    except Exception:
        return _DEFAULT_DRAFT_CAP
    return max(1, min(cap, _DRAFT_CAP_MAX))


def _new_draft_id() -> str:
    """12 hex chars. Seeded from urandom, NOT from the number/message."""
    return hashlib.sha256(os.urandom(24)).hexdigest()[:12]


def _msg_hash(message: str) -> str:
    return hashlib.sha256((message or "").encode("utf-8")).hexdigest()[:16]


def _read_drafts() -> list[dict[str, Any]]:
    """Every row in file order. Unparseable lines skipped. Never raises."""
    rows: list[dict[str, Any]] = []
    try:
        path = _drafts_path()
        if not os.path.exists(path):
            return rows
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict) and row.get("id"):
                    rows.append(row)
    except Exception:
        return rows
    return rows


def _write_drafts_locked(path: str, rows: list[dict[str, Any]]) -> bool:
    """Rewrite of the whole store. Caller MUST hold `file_lock(path)`. Never raises."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _trim_drafts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest `cap` PENDING rows; bound the sent history to `cap` too.

    Pending rows are trimmed first because they are the queue someone works —
    sent/dismissed history is only kept bounded so the file cannot grow forever.
    """
    cap = draft_cap()
    pending = [r for r in rows if not r.get("sent")]
    sent = [r for r in rows if r.get("sent")]
    key = lambda r: str(r.get("ts") or "")  # noqa: E731 - ISO sorts lexicographically
    pending.sort(key=key)
    sent.sort(key=key)
    return pending[-cap:] + sent[-cap:]


def _persist_pending_draft(record: dict[str, Any]) -> bool:
    """Append one would-send draft, or refresh an identical pending one. Never raises.

    Dedupe key is (to, sha256(message)[:16]). Without it the hourly onboarding job
    alone (~1800 blocked sends/day, mostly the same message to the same number)
    would bury the operator in identical rows. On a repeat we refresh `ts` AND
    `reason`: the LATEST gate reason is the one a human must see, because a row that
    later blocks as `opted_out` must not be resent off the back of an older
    `auto_send_disabled` draft.

    Phone numbers / message bodies are persisted under `data/` (runtime, untracked),
    consistent with the other stores here, and are never logged.
    """
    try:
        path = _drafts_path()
        to = str(record.get("to") or "")
        mh = _msg_hash(str(record.get("message") or ""))
        with file_lock(path):
            rows = _read_drafts()
            hit = None
            for row in rows:
                if (
                    not row.get("sent")
                    and str(row.get("to") or "") == to
                    and _msg_hash(str(row.get("message") or "")) == mh
                ):
                    hit = row
                    break
            if hit is not None:
                hit["ts"] = record["ts"]
                hit["link"] = record["link"]
                hit["reason"] = record["reason"]
            else:
                rows.append(record)
            return _write_drafts_locked(path, _trim_drafts(rows))
    except Exception as exc:  # pragma: no cover - a queue must never break a send
        logger.debug("whatsapp draft store unavailable: %s", exc)
        return False


def pending_drafts_count() -> int:
    """Not-sent rows — the operator's backlog size. Never raises."""
    try:
        return sum(1 for r in _read_drafts() if not r.get("sent"))
    except Exception:
        return 0


def list_pending_drafts(limit: int = 50) -> list[dict[str, Any]]:
    """Pending drafts, newest first. Never raises."""
    try:
        rows = [r for r in _read_drafts() if not r.get("sent")]
        rows.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
        return rows[: max(1, limit)]
    except Exception:
        return []


def mark_draft_sent(draft_id: str) -> dict[str, Any] | None:
    """Mark a draft sent. Idempotent — a second call is a no-op. Never raises.

    Returns the row (plus an `already` flag) or ``None`` for an unknown id. Nothing is
    transmitted here: the human tapped the wa.me link themselves.
    """
    did = (draft_id or "").strip()
    if not did:
        return None
    try:
        path = _drafts_path()
        with file_lock(path):
            rows = _read_drafts()
            for row in rows:
                if str(row.get("id") or "") != did:
                    continue
                already = bool(row.get("sent"))
                if not already:
                    row["sent"] = True
                    row["sent_ts"] = _now_iso()
                    _write_drafts_locked(path, _trim_drafts(rows))
                return {**row, "already": already}
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("whatsapp mark-sent failed: %s", exc)
    return None


def dismiss_draft(draft_id: str) -> bool:
    """Drop a row from pending — a human judged it not worth sending.

    ``False`` when the id is unknown (so a repeat call 404s). Never raises.
    """
    did = (draft_id or "").strip()
    if not did:
        return False
    try:
        path = _drafts_path()
        with file_lock(path):
            rows = _read_drafts()
            kept = [r for r in rows if str(r.get("id") or "") != did]
            if len(kept) == len(rows):
                return False
            _write_drafts_locked(path, _trim_drafts(kept))
            return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("whatsapp dismiss failed: %s", exc)
        return False


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verify a Meta webhook payload using the App Secret (X-Hub-Signature-256).

    Returns ``True`` only on a valid HMAC-SHA256 match. If no App Secret is
    configured (``WHATSAPP_APP_SECRET`` / settings.whatsapp_app_secret), returns
    ``True`` so local/dev still works — production MUST set the secret. Never raises.
    """
    secret = (
        os.getenv("WHATSAPP_APP_SECRET", "") or getattr(settings, "whatsapp_app_secret", "") or ""
    ).strip()
    if not secret:
        # Fail-CLOSED in production: an unverified opt-out/inbound webhook could suppress
        # arbitrary numbers (DoS) or inject reply drafts. Only skip in dev/local.
        try:
            from app.config import settings as _s

            if getattr(_s, "is_production", False):
                return False
        except Exception:
            pass
        return True  # dev/local only -> don't hard-block
    try:
        sig = (signature_header or "").strip()
        if sig.startswith("sha256="):
            sig = sig[len("sha256=") :]
        expected = hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False


@dataclass
class WhatsAppMessage:
    """WhatsApp message data"""

    to: str
    message_type: str  # text, template, image, document
    content: str
    template_name: str | None = None
    template_params: list[str] | None = None


class WhatsAppMessageMixin:
    """Pre-built business message helpers (lead alert / appointment / callback / report).

    Each formats a message then calls ``self.send_text_message`` — so BOTH the Cloud-API
    client (:class:`WhatsAppIntegration`) and the self-hosted WAHA client
    (:class:`app.integrations.whatsapp_selfhost.SelfHostWhatsApp`) share one implementation.
    That is what makes the dual-engine provider switch work *everywhere*, not just on the
    campaign path. Never raises (delegates to a never-raise ``send_text_message``).
    """

    async def send_lead_alert(
        self, sales_team_number: str, lead_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Send hot lead alert to sales team"""
        message = (
            "NEW HOT LEAD!\n\n"
            f"Company: {lead_data.get('company_name', 'N/A')}\n"
            f"Contact: {lead_data.get('contact_name', 'N/A')}\n"
            f"Phone: {lead_data.get('phone', 'N/A')}\n"
            f"City: {lead_data.get('city', 'N/A')}\n\n"
            f"Lead Score: {lead_data.get('lead_score', 0)}/100\n"
            f"Interest: {lead_data.get('detected_intent', 'N/A')}\n\n"
            f"Notes: {lead_data.get('notes', 'No additional notes')}\n"
            f"Call Time: {lead_data.get('call_time', 'N/A')}\n\n"
            "Reply with 'CLAIM' to assign this lead to yourself."
        )
        return await self.send_text_message(sales_team_number, message)

    async def send_appointment_confirmation(
        self,
        to_number: str,
        client_name: str,
        appointment_date: str,
        appointment_time: str,
        meeting_link: str | None = None,
    ) -> dict[str, Any]:
        """Send appointment confirmation to lead"""
        message = (
            "Appointment Confirmed!\n\n"
            f"Thank you for scheduling a meeting with {client_name}.\n\n"
            f"Date: {appointment_date}\n"
            f"Time: {appointment_time}\n"
        )
        if meeting_link:
            message += f"Meeting Link: {meeting_link}\n"
        message += "\nWe look forward to speaking with you!"
        return await self.send_text_message(to_number, message)

    async def send_callback_reminder(
        self, to_number: str, client_name: str, callback_time: str
    ) -> dict[str, Any]:
        """Send callback reminder to sales team"""
        message = (
            "CALLBACK REMINDER\n\n"
            "A lead requested a callback:\n\n"
            f"Client: {client_name}\n"
            f"Number: {to_number}\n"
            f"Requested Time: {callback_time}\n\n"
            "Please call them back at the requested time."
        )
        return await self.send_text_message(settings.smtp_user, message)

    async def send_daily_report(self, to_number: str, stats: dict[str, Any]) -> dict[str, Any]:
        """Send daily campaign report"""
        message = (
            "DAILY CAMPAIGN REPORT\n\n"
            f"Calls Made: {stats.get('calls_made', 0)}\n"
            f"Connected: {stats.get('calls_connected', 0)}\n"
            f"Connection Rate: {stats.get('connection_rate', 0):.1%}\n\n"
            "Outcomes:\n"
            f"  Interested: {stats.get('interested', 0)}\n"
            f"  Appointments: {stats.get('appointments', 0)}\n"
            f"  Callbacks: {stats.get('callbacks', 0)}\n"
            f"  Not Interested: {stats.get('not_interested', 0)}\n\n"
            f"Hot Leads Today: {stats.get('hot_leads', 0)}\n"
            f"Estimated Value: Rs {stats.get('estimated_value', 0):,.0f}\n"
        )
        return await self.send_text_message(to_number, message)


class WhatsAppIntegration(WhatsAppMessageMixin):
    """
    WhatsApp Business API Integration

    Used for:
    - Sending hot lead alerts to sales team
    - Appointment confirmations
    - Lead follow-ups
    - Daily/weekly reports
    """

    def __init__(self):
        self.token = settings.whatsapp_business_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{self.phone_number_id}"

        if self.token:
            logger.info("WhatsApp Integration initialized")
        else:
            logger.warning("WhatsApp credentials not configured")

    async def send_text_message(self, to_number: str, message: str) -> dict[str, Any]:
        """
        Send a simple text message

        Args:
            to_number: Recipient phone number (with country code)
            message: Message text
        """
        if not self.token:
            _record_whatsapp_failure("cloud_not_configured")
            return {"error": "whatsapp_not_configured"}

        # §5 ban-safety gate — before ANY network call. Default OFF/INERT.
        ok, reason = send_permitted(to_number)
        if not ok:
            return auto_send_blocked(to_number, message, reason)

        to_number = self._normalize_number(to_number)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }

        return await self._send_message(payload)

    async def send_template_message(
        self, to_number: str, template_name: str, template_params: list[str], language: str = "en"
    ) -> dict[str, Any]:
        """
        Send a pre-approved template message

        Template messages are required for initiating conversations
        """
        if not self.token:
            _record_whatsapp_failure("cloud_not_configured")
            return {"error": "whatsapp_not_configured"}

        # §5 ban-safety gate. Templates build their OWN payload and call _send_message
        # directly, so gating send_text_message alone would leave this path open.
        ok, reason = send_permitted(to_number)
        if not ok:
            return auto_send_blocked(to_number, template_name, reason)

        to_number = self._normalize_number(to_number)

        components = []
        if template_params:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": param} for param in template_params],
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components,
            },
        }

        return await self._send_message(payload)

    async def _send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send message via WhatsApp Cloud API.

        Returns the Graph API JSON on success, or ``{"error": ...}`` on failure
        (never raises) so background campaign runners stay crash-safe.
        """
        # §5 EGRESS BACKSTOP — the public methods already gate, but this is the one
        # function that actually talks to Graph. Re-checking here means a future method
        # that forgets the gate still cannot send (same 3-layer idea as platform_dial).
        _to = str(payload.get("to") or "")
        ok, reason = send_permitted(_to)
        if not ok:
            return auto_send_blocked(_to, "", reason)

        url = f"{self.base_url}/messages"

        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload, timeout=30.0)
                response.raise_for_status()

                result = response.json()
                logger.info(f"WhatsApp message sent: {result.get('messages', [{}])[0].get('id')}")
                _record_whatsapp_success()
                return result

            except httpx.HTTPStatusError as e:
                body = ""
                try:
                    body = e.response.text
                except Exception:
                    pass
                logger.error(f"WhatsApp API error: {body}")
                _record_whatsapp_failure(f"http_{getattr(e.response, 'status_code', 0)}")
                return {
                    "error": "http_error",
                    "status": getattr(e.response, "status_code", 0),
                    "detail": body[:500],
                }
            except Exception as e:
                logger.error(f"WhatsApp error: {e}")
                _record_whatsapp_failure(str(e)[:80])
                return {"error": "request_failed", "detail": str(e)[:300]}

    def _normalize_number(self, number: str) -> str:
        """Normalize phone number to WhatsApp format"""
        digits = "".join(filter(str.isdigit, number))

        if len(digits) == 10:
            digits = "91" + digits
        elif digits.startswith("0"):
            digits = "91" + digits[1:]

        return digits


class WhatsAppWebhookHandler:
    """
    Handle incoming WhatsApp messages

    Can be used for:
    - Lead responses
    - Sales team commands (CLAIM, STATUS, etc.)
    - Two-way conversations
    """

    def __init__(self, integration: WhatsAppIntegration):
        self.whatsapp = integration

    async def handle_incoming_message(
        self, from_number: str, message_body: str, message_id: str
    ) -> str | None:
        """
        Process incoming WhatsApp message

        Returns response message if any
        """
        message_lower = message_body.lower().strip()

        if message_lower == "claim":
            return await self._handle_claim_command(from_number)
        elif message_lower == "status":
            return await self._handle_status_command(from_number)
        elif message_lower == "help":
            return self._get_help_message()

        return None

    async def _handle_claim_command(self, from_number: str) -> str:
        """Handle lead claim command from sales team"""
        return "Lead claimed successfully! The lead details have been assigned to you."

    async def _handle_status_command(self, from_number: str) -> str:
        """Handle status request"""
        return "Campaign is running. Use the dashboard for detailed stats."

    def _get_help_message(self) -> str:
        """Return help message"""
        return (
            "Available Commands:\n\n"
            "CLAIM - Claim the last hot lead\n"
            "STATUS - Get current campaign status\n"
            "HELP - Show this message\n\n"
            "For detailed reports, visit the dashboard."
        )


# --------------------------------------------------------------------------- #
# Provider selector — the single source of truth for "which WhatsApp backend".
# --------------------------------------------------------------------------- #
def get_whatsapp_sender():
    """Return the ACTIVE WhatsApp send client (dual-engine).

    Self-hosted WAHA stack when it is the selected+configured provider
    (``WHATSAPP_PROVIDER=waha`` + ``WAHA_BASE_URL``), else the official Meta Cloud API.
    Both classes inherit :class:`WhatsAppMessageMixin`, so every caller — campaign sends
    AND notification helpers (lead alerts, daily reports, appointment confirmations) — gets
    the same method surface on either engine. Falls back to Cloud API if anything errors.
    """
    try:
        from app.integrations import whatsapp_selfhost

        if whatsapp_selfhost.is_active_provider():
            return whatsapp_selfhost.SelfHostWhatsApp()
    except Exception:
        pass
    return WhatsAppIntegration()
