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
    }


def list_affiliates(limit: int = 100) -> list[dict[str, Any]]:
    return _read(_AFFILIATES)[-limit:]


__all__ = ["register_affiliate", "record_referral", "stats", "list_affiliates", "COMMISSION_PCT"]
