"""WhatsApp campaign sender — OFFICIAL Cloud API only, opt-in, ban-safe.

DEFAULT = ban-safe 1-click human-send links (current platform behaviour). ONLY when
``WHATSAPP_AUTO_SEND=1`` AND official Cloud API creds are configured
(``whatsapp_business_token`` + ``whatsapp_phone_number_id``) do we auto-send via the
**official WhatsApp Cloud API** (graph.facebook.com via `app/integrations/whatsapp.py`).
We NEVER use an unofficial gateway (baileys/web) — that gets the number banned.

⚠️ Even on the official API: respect the 24-hour session window + approved templates +
recipient opt-in. Bulk cold-blasting can still flag a number, so this sender spaces
messages out and stays OFF unless explicitly enabled. Never raises.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def auto_send_enabled() -> bool:
    return os.getenv("WHATSAPP_AUTO_SEND", "0").strip().lower() in ("1", "true", "yes", "on")


def wa_link(phone: str, message: str = "") -> str:
    """Ban-safe 1-click wa.me link (a human taps Send). Always available."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return f"https://wa.me/{digits}?text={quote(message or '')}"


async def send_one(phone: str, message: str) -> dict:
    """Send one message. Official API auto-send only if enabled+configured; else a link."""
    out = {"phone": phone, "sent": False, "mode": "link", "link": wa_link(phone, message)}
    if not auto_send_enabled():
        return out
    try:
        from app.integrations.whatsapp import WhatsAppIntegration

        wa = WhatsAppIntegration()
        if not getattr(wa, "token", ""):
            out["mode"] = "link_no_creds"  # official creds missing -> stay 1-click
            return out
        res = await wa.send_text_message(phone, message)
        out["sent"] = bool(res) and not (isinstance(res, dict) and res.get("error"))
        out["mode"] = "cloud_api"
    except Exception as e:
        logger.warning(f"whatsapp auto-send failed ({e}); falling back to 1-click link.")
        out["mode"] = "link_error"
    return out


async def send_campaign(items: list[dict], delay_s: float = 4.0) -> dict:
    """items = [{"phone","message"}]. Auto-sends (spaced) ONLY if enabled+configured,
    else returns 1-click links for human send. Returns a summary. Never raises."""
    items = items or []
    res: dict = {"total": len(items), "sent": 0, "links": 0, "auto": auto_send_enabled(), "items": []}
    for i, it in enumerate(items):
        r = await send_one(str(it.get("phone", "")), str(it.get("message", "")))
        res["items"].append(r)
        res["sent" if r.get("sent") else "links"] += 1
        if auto_send_enabled() and i < len(items) - 1:
            await asyncio.sleep(max(1.0, float(delay_s)))  # spacing = ban-safety
    if not auto_send_enabled():
        logger.info(
            "whatsapp_campaign: WHATSAPP_AUTO_SEND off -> %d 1-click links (ban-safe).", res["links"]
        )
    return res


__all__ = ["auto_send_enabled", "wa_link", "send_one", "send_campaign"]
