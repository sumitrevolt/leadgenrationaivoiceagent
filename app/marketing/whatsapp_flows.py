"""WhatsApp Flows — in-chat multi-step lead capture (India #1 2026 trend).

Customer ko website pe bhejne ke bajaye, WhatsApp ke ANDAR hi ek form (naam,
service, city) bhar leta — fir UPI/booking. Yeh module:
  * FLOW_LEAD_CAPTURE — ready Flow JSON (Meta Flow Builder me publish karo).
  * send_flow() — interactive flow message bhejo (Cloud API, GATED).
  * handle_flow_response() — flow submit -> EXISTING inquiry path (lead auto-create).

STATUS: ready-to-flip. Meta WhatsApp Flows ke liye chahiye — approved WABA +
published flow_id + `whatsapp_business_token`/`phone_number_id`. Creds/flow_id na
ho to send inert (link/log). handle_flow_response abhi se kaam karta (webhook se).
Free (official Meta API), ban-safe, import-safe.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Flow JSON (Meta Flow Builder me import/publish karo -> flow_id milega).
# Screens: lead-capture form -> thank you. Data exchange endpoint optional.
FLOW_LEAD_CAPTURE: dict[str, Any] = {
    "version": "5.0",
    "screens": [
        {
            "id": "LEAD",
            "title": "Quick enquiry",
            "terminal": True,
            "data": {},
            "layout": {
                "type": "SingleColumnLayout",
                "children": [
                    {"type": "TextHeading", "text": "Apni detail bhar dijiye 🙏"},
                    {"type": "TextInput", "name": "name", "label": "Naam", "required": True},
                    {
                        "type": "TextInput",
                        "name": "service",
                        "label": "Kya chahiye?",
                        "required": True,
                    },
                    {"type": "TextInput", "name": "city", "label": "City", "required": False},
                    {
                        "type": "Footer",
                        "label": "Submit",
                        "on-click-action": {"name": "complete", "payload": {}},
                    },
                ],
            },
        }
    ],
}


def _flow_id() -> str:
    return os.environ.get("WHATSAPP_LEAD_FLOW_ID", "").strip()


async def send_flow(
    to_number: str, flow_token: str = "lead", flow_cta: str = "Enquiry karein"
) -> dict[str, Any]:
    """Interactive Flow message bhejo (GATED). flow_id/creds na ho -> inert + reason."""
    flow_id = _flow_id()
    if not flow_id:
        return {
            "ok": False,
            "reason": "WHATSAPP_LEAD_FLOW_ID unset (Meta Flow publish karke set karo)",
            "inert": True,
        }
    try:
        from app.config import settings

        if not (
            getattr(settings, "whatsapp_business_token", "")
            and getattr(settings, "whatsapp_phone_number_id", "")
        ):
            return {"ok": False, "reason": "WhatsApp Cloud API creds unset", "inert": True}
        from app.integrations.whatsapp import WhatsAppIntegration

        wa = WhatsAppIntegration()
        payload = {
            "messaging_product": "whatsapp",
            "to": (
                wa._normalize_number(to_number) if hasattr(wa, "_normalize_number") else to_number
            ),
            "type": "interactive",
            "interactive": {
                "type": "flow",
                "body": {"text": "Niche button se 30 sec me enquiry bhejein 👇"},
                "action": {
                    "name": "flow",
                    "parameters": {
                        "flow_message_version": "3",
                        "flow_token": flow_token,
                        "flow_id": flow_id,
                        "flow_cta": flow_cta,
                        "flow_action": "navigate",
                        "flow_action_payload": {"screen": "LEAD"},
                    },
                },
            },
        }
        res = await wa._send_message(payload)
        return {"ok": not bool(res.get("error")), "result": res}
    except Exception as e:
        logger.warning(f"[wa_flows] send_flow failed: {e}")
        return {"ok": False, "reason": str(e)[:200]}


async def handle_flow_response(response: dict[str, Any], from_number: str = "") -> dict[str, Any]:
    """Flow submit ka data -> EXISTING inquiry path (lead auto-create). Webhook se call.

    response example: {"name": "...", "service": "...", "city": "..."}. Reuses
    public_site.submit_inquiry logic via direct lead save (best-effort).
    """
    data = response or {}
    name = str(data.get("name") or "").strip()
    service = str(data.get("service") or "").strip()
    city = str(data.get("city") or "").strip()
    phone = (from_number or str(data.get("phone") or "")).strip()
    if not (name or phone):
        return {"ok": False, "reason": "empty flow response"}
    rec = {
        "name": name or "WhatsApp lead",
        "business_name": name or "WhatsApp lead",
        "phone": phone,
        "city": city or None,
        "message": f"WhatsApp Flow enquiry: {service}" if service else "WhatsApp Flow enquiry",
        "source": "whatsapp_flow",
    }
    try:
        import uuid as _uuid
        from datetime import datetime as _dt

        from app.api.public_site import _append_jsonl, _save_lead_db
        from app.platform.inquiry_hooks import run_after_inquiry

        rec.setdefault("id", str(_uuid.uuid4()))
        rec.setdefault("at", _dt.utcnow().isoformat() + "Z")
        _append_jsonl(rec)
        lead_id = _save_lead_db(rec)
        if lead_id:
            rec["lead_id"] = lead_id
        await run_after_inquiry(rec, lead_id=lead_id)
        logger.info(f"[wa_flows] flow lead captured: {name} ***{str(phone)[-4:]}")
        return {"ok": True, "lead_id": lead_id}
    except Exception as e:
        logger.warning(f"[wa_flows] flow lead save failed: {e}")
        return {"ok": False, "reason": str(e)[:200]}


__all__ = ["FLOW_LEAD_CAPTURE", "send_flow", "handle_flow_response"]
