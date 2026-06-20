"""DLT-compliant SMS sender (India) — ready-to-flip.

TRAI DLT framework: India me commercial SMS ke liye entity + header (6-char sender
ID) + template DLT pe registered hone chahiye. SMS/RCS ko WhatsApp-jaisa app-opt-in
NAHI chahiye — sirf DLT consent. ₹0.10–0.20/msg, 100% reach (feature-phone + rural).

Yeh module ek **generic BSP HTTP sender** hai (MSG91 / AiSensy / Fast2SMS / koi bhi
DLT BSP). Default INERT — creds na ho to bhejta nahi (sirf {"ok":false,"inert":true}).
Ready-to-flip: DLT register ke baad ye env set karo aur 1-switch live:
    SMS_PROVIDER_URL   = BSP ka send endpoint
    SMS_API_KEY        = BSP API key
    SMS_SENDER_ID      = registered 6-char header (e.g. LDGNAI)
    SMS_DLT_ENABLED=1

Import-safe, kabhi raise nahi karta. Free-stack (BSP cost SMS pe).
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# DLT-style templates (placeholders {var}). Inhe BSP DLT portal pe approve karao,
# phir template_id env me daalo. Yahan content-of-record rakha hai.
TEMPLATES: dict[str, str] = {
    "intro": (
        "Namaste {biz}! LeadGen AI se - hum AI se aapki marketing + Google ranking + "
        "inquiry-calling sambhalte hain. 10 leads FREE. Demo: leadsgenai.in/audit"
    ),
    "followup": (
        "{biz} ji, AI voice agent aapke inquiries ko 2-min me call karke qualified leads "
        "deta hai. Free audit: leadsgenai.in/audit - LeadGen AI"
    ),
    "reminder": (
        "{biz}: aapka free Google Business audit ready hai - leadsgenai.in/audit. "
        "Sirf aaj. LeadGen AI"
    ),
}


def _enabled() -> bool:
    return os.environ.get("SMS_DLT_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def _creds() -> tuple[str, str, str]:
    return (
        os.environ.get("SMS_PROVIDER_URL", "").strip(),
        os.environ.get("SMS_API_KEY", "").strip(),
        os.environ.get("SMS_SENDER_ID", "").strip(),
    )


def render(template_key: str, **params: Any) -> str:
    """Template render (safe — missing var blank)."""
    tpl = TEMPLATES.get(template_key, TEMPLATES["intro"])
    try:
        return tpl.format_map(
            {k: str(v) for k, v in params.items()} | {"biz": params.get("biz", "ji")}
        )
    except Exception:
        return tpl.replace("{biz}", str(params.get("biz", "ji")))


def _norm_phone(p: str) -> str:
    d = "".join(c for c in str(p or "") if c.isdigit())
    return d[-10:] if len(d) >= 10 else ""


async def send_sms(to: str, message: str, template_id: str | None = None) -> dict[str, Any]:
    """Ek DLT SMS bhejo. Creds/flag na ho -> inert (kuch nahi bhejta). Kabhi raise nahi."""
    ph = _norm_phone(to)
    if not ph:
        return {"ok": False, "reason": "bad phone"}
    if not _enabled():
        return {"ok": False, "inert": True, "reason": "SMS_DLT_ENABLED off (DLT register karo)"}
    url, key, sender = _creds()
    if not (url and key and sender):
        return {
            "ok": False,
            "inert": True,
            "reason": "SMS BSP creds unset (SMS_PROVIDER_URL/API_KEY/SENDER_ID)",
        }
    try:
        import httpx

        # Generic BSP payload — adjust keys to your BSP (MSG91/AiSensy/Fast2SMS).
        payload = {
            "sender": sender,
            "to": "91" + ph,
            "message": message[:1000],
            "template_id": template_id or os.environ.get("SMS_DLT_TEMPLATE_ID", ""),
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
        ok = 200 <= r.status_code < 300
        if ok:
            logger.info(f"[sms_dlt] sent -> 91{ph}")
        return {"ok": ok, "status": r.status_code, "to": "91" + ph}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sms_dlt] send failed: {e}")
        return {"ok": False, "reason": str(e)[:160]}


async def send_template(to: str, template_key: str, **params: Any) -> dict[str, Any]:
    """Template se SMS (DLT). Default inert."""
    return await send_sms(to, render(template_key, **params), template_id=params.get("template_id"))


__all__ = ["TEMPLATES", "render", "send_sms", "send_template"]
