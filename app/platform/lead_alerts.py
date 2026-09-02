"""Instant lead alerts (speed-to-lead) — naya inquiry/lead aate hi MALIK ko turant
email ping. GHL ka killer feature, free-stack me.

Channel (gated, fail-soft):
  - Email: NOTIFY_EMAIL pe (EmailSender reuse — ops_watchdog wala pattern).
    NOTIFY_EMAIL unset = silent skip.

Dedupe: max 1 alert / phone / hour (data/lead_alerts.jsonl). Total budget ~8s
(asyncio.wait_for). NEVER raises — callers fire-and-forget.

  notify_new_lead(rec)    -> async, awaitable result dict
  notify_new_lead_bg(rec) -> sync-safe scheduler (create_task / daemon thread)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "lead_alerts.jsonl")
_DEDUPE_SECONDS = 3600


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", str(phone or ""))[-12:]


def _recently_alerted(phone_d: str) -> bool:
    """Pichhle 1 ghante me isi phone ka alert gaya? (file scan — chhota store)."""
    try:
        if not phone_d or not os.path.isfile(_PATH):
            return False
        cutoff = time.time() - _DEDUPE_SECONDS
        with open(_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("phone") == phone_d and float(rec.get("epoch") or 0) >= cutoff:
                    return True
        return False
    except Exception:
        return False


def _log_alert(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"lead_alerts log failed: {e}")


def _lookup_client(rec: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.marketing import clients_store

        cid = str(rec.get("client_id") or "").strip()
        if cid:
            c = clients_store.get_client(cid)
            if c:
                return c
        slug = str(rec.get("source_slug") or rec.get("slug") or "").strip()
        if slug:
            return clients_store.get_by_slug(slug) or {}
    except Exception:
        pass
    return {}


def _alert_text(rec: dict[str, Any], client: dict[str, Any]) -> tuple[str, str]:
    """(subject, body) — Hinglish, action-ready (wa.me + dashboard link)."""
    name = str(rec.get("name") or "Naya lead").strip()[:80]
    phone_d = _digits(rec.get("phone") or "")
    source = str(
        rec.get("source") or rec.get("source_slug") or rec.get("utm_source") or "website"
    ).strip()[:60]
    niche = str(rec.get("niche") or client.get("niche") or "").strip()[:60]
    msg = str(rec.get("message") or "").strip()[:200]
    biz = str(client.get("business_name") or "").strip()[:80]

    try:
        from app.marketing.embed_widget import site_base

        base = site_base()
    except Exception:
        base = "https://leadsgenai.in"

    wa = f"https://wa.me/91{phone_d[-10:]}" if len(phone_d) >= 10 else ""
    lines = [
        "🔥 NAYA LEAD — turant call/WhatsApp karo (5-min me reply = 9x conversion)!",
        f"👤 Naam: {name}",
        f"📞 Phone: {phone_d or 'nahi mila'}",
        f"📍 Source: {source}" + (f" · Niche: {niche}" if niche else ""),
    ]
    if biz:
        lines.append(f"🏪 Client: {biz}")
    if msg:
        lines.append(f"💬 Message: {msg}")
    if wa:
        lines.append(f"➡️ WhatsApp: {wa}")
    lines.append(f"📊 Dashboard: {base}/app/clients")
    subject = f"🔥 Naya lead: {name} ({phone_d[-10:] if phone_d else source})"
    return subject, "\n".join(lines)


def _notify_email_to() -> str:
    try:
        from app.config import settings

        v = (getattr(settings, "notify_email", "") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv("NOTIFY_EMAIL") or "").strip()


async def _send_email(subject: str, body: str) -> bool:
    try:
        to = _notify_email_to()
        if not to:
            return False
        from app.integrations.email_sender import EmailSender

        return bool(await EmailSender().send_email([to], subject, body))
    except Exception as e:
        logger.debug(f"lead_alerts email skipped: {e}")
        return False


def _client_alert_enabled() -> bool:
    """CLIENT_HOT_LEAD_ALERT default ON (=1). '0'/'false'/'no' se OFF."""
    return os.environ.get("CLIENT_HOT_LEAD_ALERT", "1").strip().lower() not in ("0", "false", "no")


def _client_dedupe_key(rec: dict[str, Any], client: dict[str, Any]) -> str:
    """Per-(client|lead) dedupe key — same lead ke liye client ko double WA na jaye.
    lead id na ho to phone pe fall back (admin dedupe wala hi phone digits)."""
    cid = str(client.get("id") or rec.get("client_id") or "").strip()
    lead_marker = str(
        rec.get("lead_id") or rec.get("id") or _digits(rec.get("phone") or "")
    ).strip()
    return f"client:{cid}:{lead_marker}"


def _client_recently_alerted(key: str) -> bool:
    """Is client-lead marker ka WA alert pichhle 1 ghante me gaya? (same store scan)."""
    try:
        if not key or not os.path.isfile(_PATH):
            return False
        cutoff = time.time() - _DEDUPE_SECONDS
        with open(_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("client_key") == key and float(r.get("epoch") or 0) >= cutoff:
                    return True
        return False
    except Exception:
        return False


def _client_owner_text(rec: dict[str, Any], client: dict[str, Any]) -> str:
    """Client-owner ke liye chhota Hinglish WA alert (naam/phone/wa.me)."""
    name = str(rec.get("name") or "Naya lead").strip()[:80]
    phone_d = _digits(rec.get("phone") or "")
    source = str(
        rec.get("source") or rec.get("source_slug") or rec.get("utm_source") or "website"
    ).strip()[:60]
    msg = str(rec.get("message") or "").strip()[:200]
    wa = f"https://wa.me/91{phone_d[-10:]}" if len(phone_d) >= 10 else ""
    lines = [
        "🔥 Naya lead aaya hai — 5 min me call/WhatsApp = 9x conversion!",
        f"👤 {name}",
        f"📞 {phone_d or 'nahi mila'}",
        f"📍 Source: {source}",
    ]
    if msg:
        lines.append(f"💬 {msg}")
    if wa:
        lines.append(f"➡️ {wa}")
    return "\n".join(lines)


async def _notify_client_owner(rec: dict[str, Any], client: dict[str, Any]) -> bool:
    """Lead ka client_id ho to us CLIENT ke owner ko bhi WA alert bhejo (promised
    'Hot-lead instant alert'). Gated CLIENT_HOT_LEAD_ALERT (default ON), 1 msg/lead
    (per-client-lead dedupe), client-phone na ho to no-op. KABHI raise nahi karta."""
    try:
        if not _client_alert_enabled():
            return False
        if not isinstance(client, dict) or not client:
            return False
        owner_phone = str(client.get("phone") or "").strip()
        if not owner_phone:
            return False
        key = _client_dedupe_key(rec, client)
        if _client_recently_alerted(key):
            return False
        # pehle log (double-send window chhota), fir send.
        _log_alert(
            {
                "ts": _now_iso(),
                "epoch": time.time(),
                "client_key": key,
                "channel": "client_whatsapp",
            }
        )
        from app.integrations.whatsapp import get_whatsapp_sender

        sender = get_whatsapp_sender()  # dual-engine: self-host (WAHA) ya Cloud API
        if sender is None:
            return False
        res = await sender.send_text_message(owner_phone, _client_owner_text(rec, client))
        return not (isinstance(res, dict) and res.get("error"))
    except Exception as e:
        logger.debug(f"lead_alerts client owner notify skipped: {e}")
        return False


def _ntfy_alert_enabled() -> bool:
    """LEAD_NTFY_ALERT default ON (=1). '0'/'false'/'no' se OFF. Alag se
    ntfy.enabled() (NTFY_URL+NTFY_TOPIC) bhi chahiye — dono par push jaata."""
    return os.environ.get("LEAD_NTFY_ALERT", "1").strip().lower() not in ("0", "false", "no")


async def _notify_owner_ntfy(rec: dict[str, Any], client: dict[str, Any]) -> bool:
    """Speed-to-lead: platform owner ke PHONE pe instant ntfy push — email
    (inbox me dab jaata) ka complement. 1-tap 'WhatsApp' action seedha lead ko
    reply karne ke liye. Gated LEAD_NTFY_ALERT (default ON) + ntfy.enabled().
    Dedupe upstream (_recently_alerted) se hota. KABHI raise nahi karta."""
    try:
        if not _ntfy_alert_enabled():
            return False
        from app.integrations import ntfy

        if not ntfy.enabled():
            return False
        name = str(rec.get("name") or "Naya lead").strip()[:80]
        phone_d = _digits(rec.get("phone") or "")
        niche = str(rec.get("niche") or (client or {}).get("niche") or "").strip()[:50]
        source = str(
            rec.get("source") or rec.get("source_slug") or rec.get("utm_source") or "website"
        ).strip()[:50]
        lines = [f"{name} · 📞 {phone_d or 'phone nahi mila'}"]
        lines.append(f"Source: {source}" + (f" · {niche}" if niche else ""))
        msg = str(rec.get("message") or "").strip()[:160]
        if msg:
            lines.append(f"💬 {msg}")
        actions: list[dict[str, Any]] = []
        if len(phone_d) >= 10:
            actions.append(
                {"action": "view", "label": "WhatsApp", "url": f"https://wa.me/91{phone_d[-10:]}"}
            )
        try:
            from app.marketing.embed_widget import site_base

            base = site_base()
        except Exception:
            base = "https://leadsgenai.in"
        actions.append({"action": "view", "label": "Dashboard", "url": f"{base}/app/clients"})
        return bool(
            await ntfy.push(
                f"🔥 Naya lead: {name}",
                "\n".join(lines),
                priority="high",
                tags=["fire"],
                actions=actions[:3],
            )
        )
    except Exception as e:  # never-raise — alert flow ko kabhi nahi todta
        logger.debug(f"lead_alerts ntfy owner push skipped: {e}")
        return False


async def _do_notify(rec: dict[str, Any]) -> dict[str, Any]:
    client = _lookup_client(rec)
    subject, body = _alert_text(rec, client)
    try:
        em = await _send_email(subject, body)
    except Exception:
        em = False
    # Owner ke PHONE pe instant ntfy push (email complement — speed-to-lead:
    # "5-min me reply = 9x conversion"). Gated + never-raise.
    try:
        push_ok = await _notify_owner_ntfy(rec, client)
    except Exception:
        push_ok = False
    # Lead record me client_id ho to us client ke owner ko bhi turant WA ping
    # (platform admin ke alawa). Never-raise, gated CLIENT_HOT_LEAD_ALERT.
    try:
        client_wa = await _notify_client_owner(rec, client)
    except Exception:
        client_wa = False
    return {
        "ok": True,
        "email_sent": em is True,
        "push_sent": push_ok is True,
        "client_notified": client_wa is True,
        "deduped": False,
    }


async def notify_new_lead(rec: dict[str, Any]) -> dict[str, Any]:
    """Naye lead ka instant alert — dedupe + ~8s hard budget. NEVER raises."""
    try:
        rec = rec if isinstance(rec, dict) else {}
        phone_d = _digits(rec.get("phone") or "")
        if phone_d and _recently_alerted(phone_d):
            return {"ok": True, "deduped": True, "email_sent": False}
        # pehle log (concurrent double-alert window chhota karo), fir send
        _log_alert(
            {
                "ts": _now_iso(),
                "epoch": time.time(),
                "phone": phone_d,
                "name": str(rec.get("name") or "")[:80],
                "source": str(rec.get("source") or rec.get("source_slug") or "")[:60],
            }
        )
        return await asyncio.wait_for(_do_notify(rec), timeout=8.0)
    except asyncio.TimeoutError:
        logger.warning("lead_alerts notify timed out (8s budget)")
        return {"ok": False, "error": "timeout", "deduped": False}
    except Exception as e:
        logger.warning(f"lead_alerts notify failed: {e}")
        return {"ok": False, "error": str(e)[:160], "deduped": False}


def notify_new_lead_bg(rec: dict[str, Any]) -> None:
    """Sync-safe fire-and-forget — loop chal raha to create_task, warna daemon
    thread me apna mini-loop. Caller ka request path KABHI block/raise nahi hota."""
    try:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(notify_new_lead(rec))
            return
        except RuntimeError:
            pass  # koi running loop nahi (sync context)
        threading.Thread(target=lambda: asyncio.run(notify_new_lead(rec)), daemon=True).start()
    except Exception as e:
        logger.debug(f"lead_alerts bg schedule skipped: {e}")


__all__ = ["notify_new_lead", "notify_new_lead_bg"]
