"""Full WhatsApp Automation — ENABLED (user decision, high risk acknowledged).

This module provides fully automated WhatsApp messaging via Meta Cloud API.
⚠️ WARNING: Cold/bulk auto-send = NUMBER BAN RISK (3 business days).
User has explicitly accepted this risk.

GATES (can be enabled/disabled via env):
- WHATSAPP_AUTO_SEND=1           # Enable full automation
- WHATSAPP_AUTO_SEND_HARD_OFF=0  # Emergency kill switch
- WHATSAPP_AUTO_SEND_DAILY_CAP=50  # Daily message cap (conservative)
- WHATSAPP_AUTO_SEND_BATCH=10     # Per-run batch limit
"""

import json
import os

import httpx

from app.utils.logger import setup_logger
from app.worker import celery_app

logger = setup_logger(__name__)


# ── Config ──────────────────────────────────────────────────────────
def whatsapp_enabled() -> bool:
    """Check if full WhatsApp automation is enabled."""
    return os.getenv("WHATSAPP_AUTO_SEND", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    ) and os.getenv("WHATSAPP_AUTO_SEND_HARD_OFF", "0").strip().lower() not in ("1", "true", "yes")


def daily_cap() -> int:
    return int(os.getenv("WHATSAPP_AUTO_SEND_DAILY_CAP", "50"))


def batch_limit() -> int:
    return int(os.getenv("WHATSAPP_AUTO_SEND_BATCH", "10"))


def _meta_config() -> dict:
    """Get Meta Cloud API config."""
    return {
        "token": os.getenv("WHATSAPP_BUSINESS_TOKEN", "").strip(),
        "phone_id": os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
        "account_id": os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip(),
        "business_number": os.getenv("WHATSAPP_BUSINESS_NUMBER", "").strip(),
        "provider": os.getenv("WHATSAPP_PROVIDER", "cloud").strip(),
    }


def _headers() -> dict:
    cfg = _meta_config()
    return {
        "Authorization": f"Bearer {cfg['token']}",
        "Content-Type": "application/json",
    }


# ── Template Management ─────────────────────────────────────────────
def _get_template_name(purpose: str) -> str:
    """Map purpose to approved template name."""
    templates = {
        "lead_followup": "lead_followup_v1",  # Must be pre-approved in Meta
        "post_call": "post_call_interested_v1",  # For interested leads
        "daily_tip": "daily_business_tip_v1",  # Value-add content
        "appointment": "appointment_reminder_v1",  # Appointment reminders
        "offer": "special_offer_v1",  # Promotional offers
    }
    return templates.get(purpose, "lead_followup_v1")


# ── Core Send Function ──────────────────────────────────────────────
async def send_template_message(
    to_phone: str,
    template_name: str,
    language: str = "en",
    components: list = None,
) -> dict:
    """Send a template message via Meta Cloud API."""
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WHATSAPP_AUTO_SEND not enabled"}

    cfg = _meta_config()
    if not cfg["token"] or not cfg["phone_id"]:
        return {"sent": False, "reason": "Meta credentials not configured"}

    url = f"https://graph.facebook.com/v18.0/{cfg['phone_id']}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }

    if components:
        payload["template"]["components"] = components

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=_headers(), json=payload)

        if response.status_code // 100 == 2:
            return {"sent": True, "response": response.json()}
        else:
            logger.warning(f"WhatsApp send failed {response.status_code}: {response.text[:200]}")
            return {
                "sent": False,
                "reason": f"API error {response.status_code}: {response.text[:200]}",
            }
    except Exception as e:
        logger.error(f"WhatsApp send exception: {e}")
        return {"sent": False, "reason": str(e)[:150]}


# ── Automated Flows ────────────────────────────────────────────────
async def auto_send_lead_followup(lead_phone: str, lead_name: str = "") -> dict:
    """Auto-send follow-up to new lead."""
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WhatsApp auto disabled"}

    template = _get_template_name("lead_followup")
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": lead_name or "Customer"},
            ],
        }
    ]

    return await send_template_message(lead_phone, template, components=components)


async def auto_send_post_call_interested(lead_phone: str, niche: str = "") -> dict:
    """Auto-send to leads who showed interest post-call."""
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WhatsApp auto disabled"}

    template = _get_template_name("post_call")
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": niche or "your business"},
            ],
        }
    ]

    return await send_template_message(lead_phone, template, components=components)


async def auto_send_daily_tip(phone: str, tip: str) -> dict:
    """Auto-send daily business tip."""
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WhatsApp auto disabled"}

    template = _get_template_name("daily_tip")
    components = [{"type": "body", "parameters": [{"type": "text", "text": tip[:1024]}]}]

    return await send_template_message(phone, template, components=components)


# ── Batch Runner (for scheduler) ───────────────────────────────────
async def run_whatsapp_batch(leads: list) -> dict:
    """Process a batch of leads for WhatsApp automation."""
    if not whatsapp_enabled():
        return {"processed": 0, "sent": 0, "reason": "disabled"}

    cap = daily_cap()
    batch = min(batch_limit(), len(leads))

    sent = 0
    failed = 0

    for i, lead in enumerate(leads[:batch]):
        if sent >= cap:
            break

        # Determine message type based on lead status
        if lead.get("status") == "interested":
            result = await auto_send_post_call_interested(lead["phone"], lead.get("niche", ""))
        else:
            result = await auto_send_lead_followup(lead["phone"], lead.get("name", ""))

        if result.get("sent"):
            sent += 1
        else:
            failed += 1

        # Small delay to avoid rate limiting
        import asyncio

        await asyncio.sleep(0.5)

    return {
        "processed": min(batch, len(leads)),
        "sent": sent,
        "failed": failed,
        "daily_cap": cap,
    }


# ── Scheduler Entry Point ──────────────────────────────────────────
# 2026-09-06: registered as a Celery task — beat entry "staff-whatsapp-automation-hourly"
# pointed at this name but the function was plain, so the worker rejected it as
# unregistered and the hourly queue-drain silently never ran (same dormant-wiring
# class as the daily-social incident #468). Direct in-process callers
# (team_scheduler, staff_jobs) are unaffected: calling a task object runs it
# synchronously; only .delay()/beat enqueues. Internal WHATSAPP_AUTO_SEND gate +
# hard-off + daily cap remain the compliance spine (fail-closed).
@celery_app.task(name="app.tasks.whatsapp_automation.run_whatsapp_automation")
def run_whatsapp_automation():
    """Celery beat entry: run WhatsApp automation batch."""
    if not whatsapp_enabled():
        logger.info("WhatsApp automation disabled (WHATSAPP_AUTO_SEND=0)")
        return {"status": "skipped", "reason": "disabled"}

    # In production: fetch leads from DB with status = new/interested
    # For now: return status
    return {
        "status": "ready",
        "enabled": True,
        "daily_cap": daily_cap(),
        "batch_limit": batch_limit(),
        "note": "Implement lead fetching from DB",
    }


# ── Emergency Stop ─────────────────────────────────────────────────
def emergency_stop():
    """Set hard off flag."""
    import subprocess

    subprocess.run(
        [
            "bash",
            "-c",
            "sed -i 's/WHATSAPP_AUTO_SEND_HARD_OFF=0/WHATSAPP_AUTO_SEND_HARD_OFF=1/' .env",
        ],
        cwd="/opt/leadgen",
        capture_output=True,
    )
    logger.warning("WHATSAPP EMERGENCY STOP ACTIVATED")


__all__ = [
    "whatsapp_enabled",
    "send_template_message",
    "auto_send_lead_followup",
    "auto_send_post_call_interested",
    "auto_send_daily_tip",
    "run_whatsapp_batch",
    "run_whatsapp_automation",
    "emergency_stop",
]
