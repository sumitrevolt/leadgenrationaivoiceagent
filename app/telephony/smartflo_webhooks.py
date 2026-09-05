"""
Tata Smartflo Webhook Receiver
===============================

Handles Smartflo call lifecycle webhooks (status updates, CDR events).

Smartflo webhook payload (from docs):
  {
    "call_id": "...",
    "ref_id": "...",
    "status": "completed|failed|no-answer|busy|...",
    "duration": 120,
    "from": "919876543210",
    "to": "918012345678",
    "direction": "outbound",
    "started_at": "2026-09-02T10:30:00Z",
    "ended_at": "2026-09-02T10:32:00Z",
    "custom_identifier": {"source": "admin_test", "niche": "salon_spa"}
  }

Webhook URL to configure in Smartflo portal:
  POST https://leadsgenai.in/api/webhooks/tata-smartflo

This handler:
  - Logs the call event (CDR trail)
  - Triggers billing metering for completed calls
  - Updates lead status if CRM lead_id was in custom_identifier
  - Best-effort; never raises 500
"""

from __future__ import annotations

import json
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


@router.post("/tata-smartflo")
async def smartflo_webhook(request: Request) -> JSONResponse:
    """Receive Smartflo call status webhook.

    Best-effort; always returns 200 to Smartflo (prevents retries).
    Logs the event and triggers downstream actions (billing, lead status).
    """
    try:
        body = await request.json()
    except Exception:
        try:
            body = dict(await request.form())
        except Exception:
            body = {}

    # Normalize fields (Smartflo may use different key names)
    call_id = (
        body.get("call_id")
        or body.get("callSid")
        or body.get("CallSid")
        or body.get("id")
        or "unknown"
    )
    ref_id = body.get("ref_id") or body.get("refId") or ""
    status = (
        body.get("status")
        or body.get("CallStatus")
        or body.get("call_status")
        or "unknown"
    ).lower()
    duration = int(body.get("duration") or body.get("duration_seconds") or 0)
    from_number = body.get("from") or body.get("from_number") or ""
    to_number = body.get("to") or body.get("to_number") or ""
    direction = body.get("direction") or "outbound"
    custom_id = body.get("custom_identifier") or body.get("customIdentifier") or {}

    logger.info(
        f"[smartflo-webhook] status={status} call_id={call_id} "
        f"ref_id={ref_id} duration={duration}s from={from_number} to={to_number}"
    )

    # Store in recent buffer (bounded)
    _RECENT_WEBHOOKS.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "call_id": call_id,
        "ref_id": ref_id,
        "status": status,
        "duration": duration,
        "from": from_number,
        "to": to_number,
        "direction": direction,
        "custom_identifier": custom_id,
    })
    if len(_RECENT_WEBHOOKS) > _MAX_RECENT:
        _RECENT_WEBHOOKS.pop(0)

    # --- Downstream actions (all best-effort, never crash) ---

    # 1. Billing metering for completed calls
    if status in ("completed", "connected", "completed-answered"):
        await _meter_call(call_id, duration, custom_id)

    # 2. Lead status update if CRM lead_id present
    lead_id = custom_id.get("lead_id") or custom_id.get("crm_lead_id")
    if lead_id and status in ("completed", "connected"):
        await _update_lead_status(lead_id, status, duration)

    # 3. CDR logging
    await _log_cdr(call_id, ref_id, status, duration, from_number, to_number, custom_id)

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
    """Trigger billing metering for a completed Smartflo call."""
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


async def _update_lead_status(
    lead_id: str, status: str, duration_s: int
) -> None:
    """Update CRM lead status after a completed Smartflo call."""
    try:
        # Map Smartflo status to our lead disposition
        if status in ("completed", "connected"):
            disposition = "called"
            if duration_s > 60:
                disposition = "qualified"  # longer call = likely interested
        else:
            disposition = "no_answer"

        niche_database.update_after_call(
            lead_id=lead_id,
            disposition=disposition,
            call_duration_s=duration_s,
            provider="tata_smartflo",
        )
        logger.info(f"[smartflo-webhook] lead {lead_id} → {disposition}")
    except Exception as e:
        logger.debug(f"[smartflo-webhook] lead update skipped: {e}")


async def _log_cdr(
    call_id: str,
    ref_id: str,
    status: str,
    duration_s: int,
    from_number: str,
    to_number: str,
    custom_id: dict[str, Any],
) -> None:
    """Append CDR record to the call log file."""
    try:
        import os

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
            "from": from_number,
            "to": to_number,
            "custom_identifier": custom_id,
        }
        with open(cdr_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[smartflo-webhook] CDR log skipped: {e}")
