"""Affiliate / referral program — viral loop (telephony-free).

Koi bhi (client, partner, friend) ek unique referral-link se naye customer laaye →
commission. Higher LTV (referred customers 89% retain vs 58%). Track + payout.

Store: data/affiliates.jsonl (registered) + data/affiliate_referrals.jsonl (conversions).
Pure-Python, import-safe, kabhi raise nahi. Commission default 20% of first month.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_AFFILIATES = os.path.join("data", "affiliates.jsonl")
_REFERRALS = os.path.join("data", "affiliate_referrals.jsonl")
COMMISSION_PCT = 20  # % of first-month subscription
BASE_URL = "https://leadsgenai.in"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[affiliate] append failed: {e}")


def _code(name: str) -> str:
    base = "".join(c for c in (name or "ref").lower() if c.isalnum())[:8] or "ref"
    return f"{base}{uuid.uuid4().hex[:4]}"


def register_affiliate(name: str, email: str = "", phone: str = "") -> dict[str, Any]:
    """Naya affiliate register karo → unique code + referral link. Dedupe by email/phone."""
    name = (name or "Affiliate").strip()
    email = (email or "").strip().lower()
    phone = "".join(c for c in str(phone or "") if c.isdigit())[-10:]
    rows = _read(_AFFILIATES)
    for r in rows:
        if (email and r.get("email") == email) or (phone and r.get("phone") == phone):
            return {"ok": True, "existing": True, **r, "link": f"{BASE_URL}/?ref={r['code']}"}
    code = _code(name)
    rec = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "email": email,
        "phone": phone,
        "code": code,
        "created_at": _now(),
    }
    _append(_AFFILIATES, rec)
    return {
        "ok": True,
        "existing": False,
        **rec,
        "link": f"{BASE_URL}/?ref={code}",
        "commission": f"{COMMISSION_PCT}% of first month per paying customer",
    }


def record_referral(code: str, lead: dict[str, Any], status: str = "lead") -> dict[str, Any]:
    """Ek referral track karo (code se aaya lead/conversion). status: lead|paid."""
    code = (code or "").strip()
    if not code:
        return {"ok": False, "reason": "no code"}
    rec = {
        "id": uuid.uuid4().hex[:12],
        "code": code,
        "status": status,
        "business_name": lead.get("business_name") or lead.get("name"),
        "email": lead.get("email"),
        "phone": lead.get("phone"),
        "amount": lead.get("amount", 0),
        "at": _now(),
    }
    _append(_REFERRALS, rec)
    return {"ok": True, "referral": rec}


def mark_referral_paid_by_contact(
    contact: str = "",
    email: str = "",
    phone: str = "",
    amount: float = 0,
) -> int:
    """Referral rows ko 'lead' → 'paid' flip karo jab customer PAY kar de.

    Revenue-sprint fix (2026-08-23): pehle referral kabhi 'paid' nahi hota tha
    (koi caller hi nahi) — commission_earned hamesha ₹0 dikhta tha aur payout
    loop dead tha. Match normalized contact se (email lowercase ya phone ke
    last 10 digits). Idempotent: already-paid rows skip. Locked atomic rewrite
    (offers.py convention). Returns flipped count; never raises.
    """
    try:
        em = (email or contact or "").strip().lower()
        em = em if "@" in em else ""
        ph = "".join(c for c in (phone or contact or "") if c.isdigit())[-10:]
        if not em and len(ph) != 10:
            return 0

        def _hit(r: dict[str, Any]) -> bool:
            if r.get("status") == "paid":
                return False
            r_email = str(r.get("email") or "").strip().lower()
            r_phone = "".join(c for c in str(r.get("phone") or "") if c.isdigit())[-10:]
            return bool((em and r_email == em) or (len(ph) == 10 and r_phone == ph))

        from app.utils.file_lock import file_lock

        with file_lock(_REFERRALS) as locked:
            if not locked:
                return 0
            rows = _read(_REFERRALS)
            flipped = 0
            for r in rows:
                if _hit(r):
                    r["status"] = "paid"
                    try:
                        r["amount"] = float(amount or r.get("amount", 0) or 0)
                    except Exception:
                        pass
                    r["paid_at"] = _now()
                    flipped += 1
            if not flipped:
                return 0
            tmp = f"{_REFERRALS}.tmp.{os.getpid()}"
            os.makedirs(os.path.dirname(_REFERRALS) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, _REFERRALS)
            return flipped
    except Exception as e:
        logger.warning(f"[affiliate] mark_referral_paid failed: {e}")
        return 0


def stats(code: str | None = None) -> dict[str, Any]:
    refs = _read(_REFERRALS)
    if code:
        refs = [r for r in refs if r.get("code") == code]
    paid = [r for r in refs if r.get("status") == "paid"]
    earned = sum(float(r.get("amount", 0) or 0) * COMMISSION_PCT / 100 for r in paid)
    return {
        "affiliates": len(_read(_AFFILIATES)),
        "referrals": len(refs),
        "paid_conversions": len(paid),
        "commission_earned": round(earned),
        "commission_pct": COMMISSION_PCT,
        "detail": affiliate_detail(),
    }


def affiliate_detail() -> list[dict[str, Any]]:
    """Per-affiliate admin rows: referrals, paid conversions, earned (₹)."""
    affs = _read(_AFFILIATES)
    refs = _read(_REFERRALS)
    out: list[dict[str, Any]] = []
    for a in reversed(affs):
        mine = [r for r in refs if r.get("code") == a.get("code")]
        paid = [r for r in mine if r.get("status") == "paid"]
        earned = sum(float(r.get("amount", 0) or 0) * COMMISSION_PCT / 100 for r in paid)
        out.append(
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "email": a.get("email", ""),
                "phone": a.get("phone", ""),
                "code": a.get("code"),
                "link": f"{BASE_URL}/?ref={a.get('code')}",
                "created_at": a.get("created_at", ""),
                "referrals": len(mine),
                "paid_conversions": len(paid),
                "earned": round(earned),
            }
        )
    return out


def referral_kit(name: str, email: str = "", phone: str = "") -> dict[str, Any]:
    """Affiliate ka shareable kit — link + WhatsApp-ready text (owner 1-tap send).

    Reward framing Hinglish + honest: referral code se jo naya customer pays
    usse affiliate ko first-month ka 20% commission milta hai.
    """
    reg = register_affiliate(name, email, phone)
    link = reg["link"]
    text = (
        f"Namaste! 🙏 Maine LeadGen AI use karke results dekh liye — ab aapke liye "
        f"bhi ek special referral link hai.\n\n"
        f"LeadGen AI aapki business ke liye AI se marketing, leads aur follow-ups "
        f"automate karta hai — bina jhol ke. Mera referral code use karke signup "
        f"karo: {link}\n\n"
        f"Jab aap subscribe karo ge, mujhe first month ka 20% referral reward "
        f"milta hai — aur aapko market-best AI marketing automation ₹1999/month me. "
        f"Try karo, free audit pehle: https://leadsgenai.in/audit"
    )
    return {
        "ok": True,
        "existing": bool(reg.get("existing")),
        "code": reg["code"],
        "link": link,
        "whatsapp_text": text,
        "commission": f"{COMMISSION_PCT}% of first month per paying customer",
    }


def list_affiliates(limit: int = 100) -> list[dict[str, Any]]:
    return _read(_AFFILIATES)[-limit:]


__all__ = [
    "register_affiliate",
    "record_referral",
    "mark_referral_paid_by_contact",
    "stats",
    "list_affiliates",
    "referral_kit",
    "affiliate_detail",
    "COMMISSION_PCT",
]
