"""
Tata Smartflo Webhook Receiver
===============================

Handles Smartflo call lifecycle webhooks (status updates, CDR events).

IMPORTANT — what Smartflo webhooks ARE and ARE NOT
--------------------------------------------------
Per the official Smartflo docs (docs.smartflo.tatatelebusiness.com/docs/webhook),
Smartflo webhooks are **one-way, fire-and-forget HTTP notifications** used to
push call events to a CRM. They are **NOT** call-control webhooks:

  - Smartflo does NOT parse our response body to play audio, gather DTMF,
    hang up, or redirect the call. No TwiML/CCXML-style response is supported.
  - Call control / AI conversation requires the separate bi-directional
    WebSocket streaming integration (see ``app/telephony/smartflo_stream.py``).
  - Delivery: up to 2 attempts (30s timeout, then 10s retry) if we don't answer.
    We therefore always answer 200 quickly.
  - Prerequisite: webhooks must be enabled for the account by Tata support,
    then configured at: portal -> API Connect -> Webhook -> Add Webhook.

Payload format (official variable names, documented with a ``$`` sigil)
-----------------------------------------------------------------------
Smartflo may deliver ``application/json`` or ``application/x-www-form-urlencoded``,
with variables such as:

    $uuid, $call_id, $ref_id, $call_status, $duration, $billsec,
    $caller_id_number, $call_to_number, $customer_no_with_prefix,
    $customer_number, $direction, $hangup_cause, $recording_url,
    $start_stamp, $answer_stamp, $end_stamp, $call_connected,
    $billing_circle, $telecom_operator, $telecom_circle, $digits_dialed

Because the docs use ``$`` as a variable sigil, real payloads may or may not
include the literal ``$`` prefix. We therefore normalise by stripping any
leading ``$`` and match on alias lists — this keeps us compatible with BOTH
the raw Smartflo format and the simplified internal format used in tests.

Webhook URL configured in the Smartflo portal:
    POST https://leadsgenai.in/api/webhooks/tata-smartflo

Security
--------
Smartflo sends NO authentication of its own. If ``SMARTFLO_WEBHOOK_SECRET`` is
set, we require a matching ``X-Smartflo-Secret`` header (constant-time compare).
When the env var is unset the endpoint stays open (backward compatible), so set
it in production and add the same header in the portal's "Headers" section.

This handler:
  - Logs the call event (CDR trail)
  - Triggers billing metering for connected/completed calls
  - Updates lead status if a CRM lead_id was supplied
  - Best-effort; never raises 500
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.utils.logger import setup_logger

# Module-level imports — tests patch these attributes directly.
# Wrapped in try/except to avoid circular import at module load time.
try:
    from app.marketing import niche_database
    from app.telephony.post_call_hooks import meter_call_completion
except ImportError:
    # Lazy fallback — functions are imported when first needed.
    meter_call_completion = None
    niche_database = None

logger = setup_logger(__name__)

router = APIRouter()

# In-memory recent webhooks for admin inspection (bounded, last 200)
_RECENT_WEBHOOKS: list[dict[str, Any]] = []
_MAX_RECENT = 200

# Statuses that mean "the call actually connected" (Smartflo is inconsistent
# across triggers, so we accept several spellings).
_CONNECTED_STATUSES = {
    "completed",
    "completed-answered",
    "completed_answered",
    "connected",
    "answered",
    "answered-answered",
}


def _webhook_secret() -> str:
    """Shared secret for webhook auth (empty = auth disabled)."""
    return os.getenv("SMARTFLO_WEBHOOK_SECRET", "") or ""


def _normalize_keys(body: dict[str, Any]) -> dict[str, Any]:
    """Strip Smartflo's ``$`` variable sigil so both formats resolve.

    ``{"$call_id": "X"}`` becomes ``{"$call_id": "X", "call_id": "X"}`` —
    the original key is preserved and the bare key added when absent.
    """
    out: dict[str, Any] = {}
    for key, value in body.items():
        if not isinstance(key, str):
            continue
        out[key] = value
        if key.startswith("$") and len(key) > 1:
            out.setdefault(key[1:], value)
    return out


def _pick(data: dict[str, Any], *names: str, default: Any = None) -> Any:
    """Return the first present, non-empty value among ``names``."""
    for name in names:
        value = data.get(name)
        if value is not None and value != "":
            return value
    return default


def _as_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion (Smartflo may send strings)."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    """Coerce custom payload fields to a dict.

    Smartflo sometimes delivers nested structures (e.g. ``lead_fields``) as a
    JSON string rather than an object.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
    return {}


@router.post("/tata-smartflo")
async def smartflo_webhook(request: Request) -> JSONResponse:
    """Receive a Smartflo call event webhook.

    Best-effort; returns 200 so Smartflo does not retry (it retries twice when
    we don't answer). Logs the event and triggers billing / lead updates.
    """
    # --- Optional shared-secret auth (Smartflo sends none of its own) -------
    secret = _webhook_secret()
    if secret:
        provided = request.headers.get("X-Smartflo-Secret", "")
        if not hmac.compare_digest(provided, secret):
            logger.warning("[smartflo-webhook] rejected: bad/missing secret")
            return JSONResponse(content={"ok": False}, status_code=401)

    # --- Parse body (JSON or form-urlencoded) -------------------------------
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        try:
            body = dict(await request.form())
        except Exception:
            body = {}

    # Smartflo documents variables with a ``$`` sigil; accept both forms.
    data = _normalize_keys(body)

    call_id = str(
        _pick(data, "call_id", "callId", "callid", "uuid", "id", default="unknown")
    )
    ref_id = str(_pick(data, "ref_id", "refId", "refid", default=""))
    status = str(
        _pick(
            data,
            "call_status",
            "status",
            "callStatus",
            "callstatus",
            default="unknown",
        )
    ).lower()

    duration = _as_int(_pick(data, "duration", default=0))
    # billsec is the carrier-billable duration; prefer it when present.
    billsec = _as_int(_pick(data, "billsec", default=0))

    from_number = str(
        _pick(
            data,
            "from",
            "from_number",
            "caller_id_number",
            "customer_no_with_prefix",
            "customer_number_with_prefix",
            default="",
        )
    )
    to_number = str(
        _pick(
            data,
            "to",
            "to_number",
            "customer_no_with_prefix",
            "customer_number",
            "call_to_number",
            default="",
        )
    )
    direction = str(_pick(data, "direction", default="outbound"))

    # Extra Smartflo fields worth keeping (no-op for the simplified format).
    hangup_cause = str(_pick(data, "hangup_cause", "reason_key", default=""))
    recording_url = str(
        _pick(data, "recording_url", "aws_call_recording_identifier", default="")
    )
    start_stamp = str(_pick(data, "start_stamp", "start_date", default=""))
    end_stamp = str(_pick(data, "end_stamp", "end_date", default=""))
    call_connected_raw = _pick(data, "call_connected", default=None)
    custom_id = _as_dict(
        _pick(data, "custom_identifier", "customIdentifier", "lead_fields", default={})
    )

    # Some triggers only carry the boolean flag, not a useful status string.
    call_connected_flag: bool | None = None
    if isinstance(call_connected_raw, str):
        call_connected_flag = call_connected_raw.strip().lower() in ("1", "true", "yes")
    elif isinstance(call_connected_raw, bool):
        call_connected_flag = call_connected_raw

    logger.info(
        f"[smartflo-webhook] status={status} call_id={call_id} "
        f"ref_id={ref_id} duration={duration}s billsec={billsec}s "
        f"from={from_number} to={to_number}"
    )

    # Store in recent buffer (bounded)
    _RECENT_WEBHOOKS.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "call_id": call_id,
            "ref_id": ref_id,
            "status": status,
            "duration": duration,
            "billsec": billsec,
            "from": from_number,
            "to": to_number,
            "direction": direction,
            "hangup_cause": hangup_cause,
            "recording_url": recording_url,
            "start_stamp": start_stamp,
            "end_stamp": end_stamp,
            "custom_identifier": custom_id,
        }
    )
    if len(_RECENT_WEBHOOKS) > _MAX_RECENT:
        _RECENT_WEBHOOKS.pop(0)

    # --- Downstream actions (all best-effort, never crash) ------------------
    # Treat as connected if the status says so, or if Smartflo only gave us
    # the call_connected boolean.
    connected = status in _CONNECTED_STATUSES or (
        call_connected_flag is True and status in ("unknown", "")
    )

    # 1. Billing metering for connected calls (billsec preferred over duration)
    if connected:
        billable_s = billsec if billsec > 0 else duration
        await _meter_call(call_id, billable_s, custom_id)

    # 2. Lead status update if CRM lead_id present
    lead_id = custom_id.get("lead_id") or custom_id.get("crm_lead_id")
    if lead_id and connected:
        await _update_lead_status(lead_id, status, billsec if billsec > 0 else duration)

    # 3. CDR logging
    await _log_cdr(
        call_id=call_id,
        ref_id=ref_id,
        status=status,
        duration_s=duration,
        billsec=billsec,
        from_number=from_number,
        to_number=to_number,
        direction=direction,
        hangup_cause=hangup_cause,
        recording_url=recording_url,
        start_stamp=start_stamp,
        end_stamp=end_stamp,
        custom_id=custom_id,
    )

    # Always return 200 to Smartflo (prevents webhook retries)
    return JSONResponse(content={"ok": True}, status_code=200)


def get_recent_webhooks(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent webhooks (for admin inspection)."""
    return list(_RECENT_WEBHOOKS)[-limit:]


# ---------------------------------------------------------------------------
# Downstream actions (best-effort, never raise)
# ---------------------------------------------------------------------------
async def _meter_call(
    call_id: str, duration_s: int, custom_id: dict[str, Any]
) -> None:
    """Trigger billing metering for a connected Smartflo call."""
    try:
        client_id = custom_id.get("client_id")
        await meter_call_completion(
            client_id=client_id,
            call_duration_s=duration_s,
            metadata={
                "provider": "tata_smartflo",
                "call_id": call_id,
                "source": custom_id.get("source", "webhook"),
            },
        )
        logger.info(f"[smartflo-webhook] metered call {call_id} ({duration_s}s)")
    except Exception as e:
        logger.debug(f"[smartflo-webhook] metering skipped: {e}")


async def _update_lead_status(lead_id: str, status: str, duration_s: int) -> None:
    """Update CRM lead status after a connected Smartflo call."""
    try:
        disposition = "called"
        if duration_s > 60:
            disposition = "qualified"  # longer call = likely interested

        niche_database.update_after_call(
            lead_id=lead_id,
            disposition=disposition,
            call_duration_s=duration_s,
            provider="tata_smartflo",
        )
        logger.info(f"[smartflo-webhook] lead {lead_id} -> {disposition}")
    except Exception as e:
        logger.debug(f"[smartflo-webhook] lead update skipped: {e}")


async def _log_cdr(
    call_id: str,
    ref_id: str,
    status: str,
    duration_s: int,
    billsec: int = 0,
    from_number: str = "",
    to_number: str = "",
    direction: str = "outbound",
    hangup_cause: str = "",
    recording_url: str = "",
    start_stamp: str = "",
    end_stamp: str = "",
    custom_id: dict[str, Any] | None = None,
) -> None:
    """Append a CDR record to the Smartflo call log file."""
    try:
        cdr_dir = os.path.join("data", "cdr")
        os.makedirs(cdr_dir, exist_ok=True)
        cdr_file = os.path.join(cdr_dir, "smartflo_cdr.jsonl")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "tata_smartflo",
            "call_id": call_id,
            "ref_id": ref_id,
            "status": status,
            "duration_s": duration_s,
            "billsec": billsec,
            "from": from_number,
            "to": to_number,
            "direction": direction,
            "hangup_cause": hangup_cause,
            "recording_url": recording_url,
            "start_stamp": start_stamp,
            "end_stamp": end_stamp,
            "custom_identifier": custom_id or {},
        }
        with open(cdr_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[smartflo-webhook] CDR log skipped: {e}")
