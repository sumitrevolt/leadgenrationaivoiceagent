"""
payment_links.py — Razorpay Payment Links for CLIENT'S customers (GHL-style invoicing).
========================================================================================

Client (local business) apne customer se paisa collect karne ke liye 1-click
payment link banata hai — hum Razorpay Payment Links REST API use karte hain
(wahi creds jo subscription billing me hain: settings.razorpay_key_id/secret).

  create_payment_link(client_id, amount_inr, purpose, ...) ->
      {ok, short_url, plink_id, wa_share_link} | {ok:False, error}

SAFETY:
- Creds unset => INERT (graceful {error}) — kabhi crash nahi.
- KOI auto-send nahi: Razorpay ka apna SMS/email notify bhi OFF (notify
  sms/email = False). Hum sirf link + wa.me 1-click share link dete hain.
- Sirf payment-link CREATE — koi auto-charge/transfer/refund yahan nahi.

Store: data/payment_links.jsonl (audit trail). Never raises.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE_PATH = os.path.join("data", "payment_links.jsonl")
_RZP_PLINK_URL = "https://api.razorpay.com/v1/payment_links"
_MIN_INR = 1
_MAX_INR = 500000  # sanity cap — bade amounts manual Razorpay dashboard se


def _creds() -> tuple[str, str]:
    """Razorpay key id/secret — EXACTLY wahi config jo billing use karta hai."""
    try:
        from app.config import settings

        return (
            (settings.razorpay_key_id or "").strip(),
            (settings.razorpay_key_secret or "").strip(),
        )
    except Exception as e:
        logger.debug(f"[payment_links] settings load skip: {e}")
        return "", ""


def is_configured() -> bool:
    kid, ksec = _creds()
    return bool(kid and ksec)


def _digits_intl(phone: Any) -> str:
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(d) == 10:
        d = "91" + d
    elif d.startswith("0") and len(d) == 11:
        d = "91" + d[1:]
    return d if 11 <= len(d) <= 14 else ""


def build_wa_share_link(customer_phone: Any, customer_name: str, business: str, purpose: str, amount_inr: float, short_url: str) -> str:
    """wa.me 1-click share link (prefilled Hinglish payment message). '' = no phone."""
    d = _digits_intl(customer_phone)
    nm = (customer_name or "").strip()
    msg = (
        f"Namaste{(' ' + nm) if nm else ''} ji! 🙏 "
        f"{(business or 'Hamari team').strip()} ki taraf se aapka payment link: "
        f"{short_url}\n"
        f"Amount: ₹{int(amount_inr) if abs(amount_inr - int(amount_inr)) < 1e-9 else amount_inr}"
        + (f" ({purpose.strip()})" if (purpose or "").strip() else "")
        + "\nSecure Razorpay link hai — UPI/card/netbanking sab chalta hai. Dhanyawad!"
    )
    if not d:
        return ""
    return f"https://wa.me/{d}?text={quote(msg)}"


def _append_store(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE_PATH) or ".", exist_ok=True)
        with open(_STORE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[payment_links] store write failed: {e}")


def list_payment_links(client_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Saved payment links (newest last). Optional client filter. Never raises."""
    rows: list[dict[str, Any]] = []
    try:
        if os.path.isfile(_STORE_PATH):
            with open(_STORE_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if isinstance(r, dict):
                            rows.append(r)
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"[payment_links] store read failed: {e}")
    cid = (client_id or "").strip()
    if cid:
        rows = [r for r in rows if str(r.get("client_id") or "") == cid]
    return rows[-max(1, min(int(limit or 50), 500)):]


async def create_payment_link(
    client_id: str,
    amount_inr: Any,
    purpose: str,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    business_name: str = "",
) -> dict[str, Any]:
    """Razorpay Payment Link banao (CREATE only — koi charge/transfer nahi).

    Returns {ok, short_url, plink_id, wa_share_link, amount_inr} ya
    {ok:False, error}. Creds unset = INERT graceful error. Never raises.
    """
    try:
        try:
            amt = round(float(str(amount_inr).replace("₹", "").replace(",", "").strip()), 2)
        except Exception:
            return {"ok": False, "error": "Amount samajh nahi aaya — number bhejo (e.g. 499)."}
        if amt < _MIN_INR or amt > _MAX_INR:
            return {"ok": False, "error": f"Amount ₹{_MIN_INR}–₹{_MAX_INR} ke beech hona chahiye."}
        desc = (purpose or "").strip()[:255] or "Payment"

        kid, ksec = _creds()
        if not (kid and ksec):
            return {
                "ok": False,
                "error": "Razorpay creds set nahi hain (RAZORPAY_KEY_ID/SECRET) — payment links abhi inactive.",
            }

        payload: dict[str, Any] = {
            "amount": int(round(amt * 100)),  # paise
            "currency": "INR",
            "description": desc,
            "notify": {"sms": False, "email": False},  # NO auto-send (policy)
            "reminder_enable": False,
            "notes": {"client_id": str(client_id or "")[:80], "purpose": desc[:120], "via": "leadsgenai"},
        }
        cust: dict[str, str] = {}
        nm = (customer_name or "").strip()[:100]
        ph = _digits_intl(customer_phone)
        if nm:
            cust["name"] = nm
        if ph:
            cust["contact"] = "+" + ph
        if cust:
            payload["customer"] = cust

        import httpx  # lazy

        async with httpx.AsyncClient(timeout=20, auth=(kid, ksec)) as cx:
            r = await cx.post(_RZP_PLINK_URL, json=payload)
        if r.status_code not in (200, 201):
            err = ""
            try:
                err = (r.json().get("error") or {}).get("description") or ""
            except Exception:
                err = r.text[:120]
            logger.warning(f"[payment_links] razorpay {r.status_code}: {err[:200]}")
            return {"ok": False, "error": f"Razorpay error ({r.status_code}): {err[:160] or 'unknown'}"}

        data = r.json()
        short_url = str(data.get("short_url") or "")
        plink_id = str(data.get("id") or "")
        wa_link = build_wa_share_link(customer_phone, nm, business_name, desc, amt, short_url) if short_url else ""

        rec = {
            "plink_id": plink_id,
            "client_id": str(client_id or ""),
            "amount_inr": amt,
            "purpose": desc,
            "customer_name": nm,
            "customer_phone": ph,
            "short_url": short_url,
            "wa_share_link": wa_link,
            "status": str(data.get("status") or "created"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _append_store(rec)
        return {
            "ok": True,
            "plink_id": plink_id,
            "short_url": short_url,
            "wa_share_link": wa_link,
            "amount_inr": amt,
            "note": "Link customer ko KHUD bhejo (wa_share_link 1-click) — hum auto-send nahi karte.",
        }
    except Exception as e:
        logger.warning(f"[payment_links] create failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["create_payment_link", "list_payment_links", "build_wa_share_link", "is_configured"]
