"""End-customer loyalty/coupons — SMB ke APNE customers ke liye (Dhanda-style edge).

Client (dukaan) coupon campaign banata: "SOLAR20-XXXX" type codes → customer ko WA/print
se do → redeem pe record. Referral: redeem record me referrer_phone — repeat referrer
dikhe to client ko pata chale. Free-stack, jsonl stores, NEVER raises.

Stores: data/loyalty_campaigns.jsonl · data/loyalty_redemptions.jsonl
"""

from __future__ import annotations

import json
import os
import random
import string
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CAMPAIGNS = os.path.join("data", "loyalty_campaigns.jsonl")
_REDEMPTIONS = os.path.join("data", "loyalty_redemptions.jsonl")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _read(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"loyalty read failed: {e}")
        return []


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"loyalty append failed: {e}")


def create_campaign(
    client_id: str,
    title: str,
    kind: str = "percent",  # percent | flat | freebie
    value: int = 10,
    expiry_days: int = 30,
    max_redemptions: int = 100,
) -> dict[str, Any]:
    """Coupon campaign + shareable code. WA share-text bhi deta (1-click human send)."""
    client_id = (client_id or "").strip()
    if not client_id or not (title or "").strip():
        return {"ok": False, "error": "client_id + title required"}
    prefix = "".join(c for c in title.upper() if c.isalnum())[:6] or "OFFER"
    code = f"{prefix}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    rec = {
        "id": code,
        "client_id": client_id,
        "title": title.strip()[:80],
        "kind": kind if kind in ("percent", "flat", "freebie") else "percent",
        "value": max(0, int(value)),
        "created_at": _now(),
        "expires_at": time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + max(1, expiry_days) * 86400)
        ),
        "max_redemptions": max(1, int(max_redemptions)),
        "active": True,
    }
    _append(_CAMPAIGNS, rec)
    off = (
        f"{rec['value']}% off"
        if rec["kind"] == "percent"
        else (f"₹{rec['value']} off" if rec["kind"] == "flat" else title)
    )
    rec["share_text"] = (
        f"🎁 {title}! Code *{code}* dikhao aur {off} pao. Valid till {rec['expires_at'][:10]}."
    )
    return {"ok": True, "campaign": rec}


def check_code(code: str) -> dict[str, Any]:
    """Public: code valid hai? (dukaan-staff counter pe check kare)."""
    code = (code or "").strip().upper()
    camp = next((c for c in _read(_CAMPAIGNS) if c.get("id") == code), None)
    if not camp:
        return {"valid": False, "reason": "code not found"}
    if not camp.get("active", True):
        return {"valid": False, "reason": "inactive"}
    if camp.get("expires_at", "9999") < _now():
        return {"valid": False, "reason": "expired"}
    used = sum(1 for r in _read(_REDEMPTIONS) if r.get("code") == code)
    if used >= int(camp.get("max_redemptions", 100)):
        return {"valid": False, "reason": "limit reached"}
    return {
        "valid": True,
        "title": camp.get("title"),
        "kind": camp.get("kind"),
        "value": camp.get("value"),
        "used": used,
    }


def redeem(
    code: str, customer_phone: str = "", referrer_phone: str = "", note: str = ""
) -> dict[str, Any]:
    chk = check_code(code)
    if not chk.get("valid"):
        return {"ok": False, **chk}
    _append(
        _REDEMPTIONS,
        {
            "ts": _now(),
            "code": (code or "").strip().upper(),
            "customer_phone": (customer_phone or "").strip()[-10:],
            "referrer_phone": (referrer_phone or "").strip()[-10:],
            "note": (note or "")[:120],
        },
    )
    return {"ok": True, "redeemed": chk}


def stats(client_id: str = "") -> dict[str, Any]:
    camps = _read(_CAMPAIGNS)
    reds = _read(_REDEMPTIONS)
    if client_id:
        ids = {c["id"] for c in camps if c.get("client_id") == client_id}
        camps = [c for c in camps if c.get("client_id") == client_id]
        reds = [r for r in reds if r.get("code") in ids]
    by_ref: dict[str, int] = {}
    for r in reds:
        if r.get("referrer_phone"):
            by_ref[r["referrer_phone"]] = by_ref.get(r["referrer_phone"], 0) + 1
    top_referrers = sorted(by_ref.items(), key=lambda x: -x[1])[:10]
    return {"campaigns": camps, "redemptions": len(reds), "top_referrers": top_referrers}
