"""WhatsApp campaign sender — OFFICIAL Cloud API only, opt-in, ban-safe.

DEFAULT = ban-safe 1-click human-send links (current platform behaviour). ONLY when
``WHATSAPP_AUTO_SEND=1`` AND official Cloud API creds are configured
(``whatsapp_business_token`` + ``whatsapp_phone_number_id``) do we auto-send via the
**official WhatsApp Cloud API** (graph.facebook.com via `app/integrations/whatsapp.py`).
We NEVER use an unofficial gateway (baileys/web) — that gets the number banned.

⚠️ Even on the official API: respect the 24-hour session window + approved templates +
recipient opt-in. Bulk cold-blasting can still flag a number, so this sender:
  - stays OFF unless explicitly enabled (flag + creds),
  - spaces messages out (inter-message delay),
  - enforces a per-day cap (``WHATSAPP_DAILY_CAP``, default 250),
  - skips suppressed / failed / blocked numbers (suppression list), and
  - records delivery failures so a bad number is auto-suppressed next time.
Never raises.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# --------------------------------------------------------------------------- #
# Flags / config
# --------------------------------------------------------------------------- #
def auto_send_enabled() -> bool:
    """True only if the operator explicitly turned auto-send ON (default OFF = ban-safe)."""
    try:
        from app.platform.owner_os import kill_engaged

        if kill_engaged("owner_whatsapp_outbound"):
            return False
    except Exception:
        pass
    return os.getenv("WHATSAPP_AUTO_SEND", "0").strip().lower() in ("1", "true", "yes", "on")


def daily_cap() -> int:
    """Max auto-sends per UTC day (domain/number-reputation safety)."""
    try:
        return max(1, int(os.getenv("WHATSAPP_DAILY_CAP", "250")))
    except Exception:
        return 250


def send_spacing_s() -> float:
    """Default seconds between auto-sends (override via WHATSAPP_SEND_DELAY_S)."""
    try:
        return max(0.5, float(os.getenv("WHATSAPP_SEND_DELAY_S", "4")))
    except Exception:
        return 4.0


def provider() -> str:
    """Active WhatsApp backend: ``waha`` (self-host stack, when selected+configured) else ``cloud``."""
    try:
        from app.integrations import whatsapp_selfhost

        if whatsapp_selfhost.is_active_provider():
            return "waha"
    except Exception:
        pass
    return "cloud"


def cloud_creds_present() -> bool:
    """True only if official Meta Cloud API token + phone_number_id are configured."""
    try:
        from app.config import settings

        return bool(
            (getattr(settings, "whatsapp_business_token", "") or "").strip()
            and (getattr(settings, "whatsapp_phone_number_id", "") or "").strip()
        )
    except Exception:
        return False


def selfhost_present() -> bool:
    """True if the self-host (WAHA) stack is the active provider AND reachable-configured."""
    try:
        from app.integrations import whatsapp_selfhost

        return whatsapp_selfhost.is_active_provider()
    except Exception:
        return False


def creds_present() -> bool:
    """True if a usable send backend is configured: active self-host stack OR official Cloud creds.

    Used by the auto-send decision. For *which-provider* truthfulness use
    :func:`provider` / :func:`cloud_creds_present` / :func:`selfhost_present`.
    """
    return selfhost_present() or cloud_creds_present()


def _get_sender():
    """Return the active send client via the single dual-engine selector.

    Both clients expose the same ``send_text_message`` / ``send_template_message`` signatures,
    so every ban-safety guard (suppression, cap, spacing, opt-out) wraps them identically.
    """
    from app.integrations.whatsapp import get_whatsapp_sender

    return get_whatsapp_sender()


def auto_ready() -> bool:
    """Auto-send is live ONLY when flag is ON *and* a usable backend (self-host or cloud) exists."""
    return auto_send_enabled() and creds_present()


# --------------------------------------------------------------------------- #
# Links (always-available, ban-safe default)
# --------------------------------------------------------------------------- #
def wa_link(phone: str, message: str = "") -> str:
    """Ban-safe 1-click wa.me link (a human taps Send). Always available."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return f"https://wa.me/{digits}?text={quote(message or '')}"


def _digits(phone: str) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())


# --------------------------------------------------------------------------- #
# Single sends (text + approved template)
# --------------------------------------------------------------------------- #
async def send_one(phone: str, message: str) -> dict:
    """Send one TEXT message. Official API auto-send only if enabled+configured; else a link.

    NOTE: a free-text message only delivers inside a 24h customer-service window. For
    business-initiated (cold/drip/reactivation) outreach, prefer :func:`send_template`
    with a Meta-approved template — that is what stays compliant + un-banned.
    """
    out = {"phone": phone, "sent": False, "mode": "link", "link": wa_link(phone, message)}
    if not auto_send_enabled():
        return out
    # suppression guard (blocked / repeatedly-failed numbers)
    try:
        from app.marketing import wa_campaign_runner as wa_suppression

        if wa_suppression.is_suppressed(phone):
            out["mode"] = "suppressed"
            return out
    except Exception:
        pass
    if not creds_present():
        out["mode"] = "link_no_creds"  # official creds missing -> stay 1-click
        return out
    try:
        wa = _get_sender()
        res = await wa.send_text_message(phone, message)
        ok = bool(res) and not (isinstance(res, dict) and res.get("error"))
        out["sent"] = ok
        out["mode"] = "selfhost" if provider() == "waha" else "cloud_api"
        if not ok:
            _record_failure(
                phone, str((res or {}).get("error") if isinstance(res, dict) else "send_failed")
            )
    except Exception as e:
        logger.warning(f"whatsapp auto-send failed ({e}); falling back to 1-click link.")
        out["mode"] = "link_error"
        _record_failure(phone, str(e))
    return out


async def send_template(
    phone: str,
    template_name: str,
    params: list[str] | None = None,
    language: str = "en",
    fallback_text: str = "",
) -> dict:
    """Send a Meta-APPROVED TEMPLATE message (the compliant way to initiate a chat).

    Auto-sends only when enabled+configured AND the number isn't suppressed; otherwise
    returns a ban-safe 1-click link (using ``fallback_text``). Never raises.
    """
    params = [str(p) for p in (params or [])]
    out = {
        "phone": phone,
        "template": template_name,
        "sent": False,
        "mode": "link",
        "link": wa_link(phone, fallback_text),
    }
    if not auto_send_enabled():
        return out
    try:
        from app.marketing import wa_campaign_runner as wa_suppression

        if wa_suppression.is_suppressed(phone):
            out["mode"] = "suppressed"
            return out
    except Exception:
        pass
    if not creds_present():
        out["mode"] = "link_no_creds"
        return out
    if not (template_name or "").strip():
        out["mode"] = "no_template"
        return out
    try:
        wa = _get_sender()
        res = await wa.send_template_message(phone, template_name, params, language=language)
        ok = bool(res) and not (isinstance(res, dict) and res.get("error"))
        out["sent"] = ok
        out["mode"] = "selfhost" if provider() == "waha" else "cloud_api"
        if isinstance(res, dict):
            try:
                out["message_id"] = (res.get("messages") or [{}])[0].get("id")
            except Exception:
                pass
        if not ok:
            _record_failure(
                phone, str((res or {}).get("error") if isinstance(res, dict) else "send_failed")
            )
    except Exception as e:
        logger.warning(f"whatsapp template send failed ({e}); falling back to 1-click link.")
        out["mode"] = "link_error"
        _record_failure(phone, str(e))
    return out


def _record_failure(phone: str, reason: str) -> None:
    """Best-effort: log a delivery failure (auto-suppress after repeated failures)."""
    try:
        from app.marketing import wa_campaign_runner as wa_suppression

        wa_suppression.record_failure(phone, reason)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Campaign loop (text) — spaced + daily-cap + suppression aware
# --------------------------------------------------------------------------- #
async def send_campaign(items: list[dict], delay_s: float | None = None) -> dict:
    """items = [{"phone","message"}]. Auto-sends (spaced, capped) ONLY if enabled+configured,
    else returns 1-click links for human send. Returns a summary. Never raises."""
    items = items or []
    live = auto_ready()
    res: dict = {
        "total": len(items),
        "sent": 0,
        "links": 0,
        "skipped": 0,
        "auto": auto_send_enabled(),
        "live": live,
        "items": [],
    }
    delay = send_spacing_s() if delay_s is None else max(0.5, float(delay_s))
    sent_today = _sent_today() if live else 0
    cap = daily_cap()
    for i, it in enumerate(items):
        if live and sent_today >= cap:
            res["skipped"] += 1
            res["items"].append(
                {"phone": str(it.get("phone", "")), "sent": False, "mode": "daily_cap"}
            )
            continue
        r = await send_one(str(it.get("phone", "")), str(it.get("message", "")))
        res["items"].append(r)
        if r.get("sent"):
            res["sent"] += 1
            sent_today += 1
            _bump_sent_today()
        elif r.get("mode") == "suppressed":
            res["skipped"] += 1
        else:
            res["links"] += 1
        if live and r.get("sent") and i < len(items) - 1:
            await asyncio.sleep(delay)  # spacing = ban-safety
    if not auto_send_enabled():
        logger.info(
            "whatsapp_campaign: WHATSAPP_AUTO_SEND off -> %d 1-click links (ban-safe).",
            res["links"],
        )
    return res


# --------------------------------------------------------------------------- #
# Daily-cap counter (UTC day, tiny json state file)
# --------------------------------------------------------------------------- #
import json
from datetime import datetime, timezone

_CAP_FILE = os.path.join("data", "wa_send_counter.json")


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_counter() -> dict:
    try:
        if os.path.exists(_CAP_FILE):
            with open(_CAP_FILE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _sent_today() -> int:
    d = _read_counter()
    return int(d.get(_today_key(), 0)) if d.get("day") == _today_key() else 0


def _bump_sent_today(n: int = 1) -> None:
    try:
        os.makedirs(os.path.dirname(_CAP_FILE), exist_ok=True)
        d = _read_counter()
        key = _today_key()
        cur = int(d.get(key, 0)) if d.get("day") == key else 0
        with open(_CAP_FILE, "w", encoding="utf-8") as f:
            json.dump({"day": key, key: cur + n}, f)
    except Exception:
        pass


def sent_today_count() -> int:
    """Public read: how many auto-sends already went out this UTC day."""
    return _sent_today()


__all__ = [
    "auto_send_enabled",
    "creds_present",
    "cloud_creds_present",
    "selfhost_present",
    "provider",
    "auto_ready",
    "daily_cap",
    "send_spacing_s",
    "wa_link",
    "send_one",
    "send_template",
    "send_campaign",
    "sent_today_count",
]
