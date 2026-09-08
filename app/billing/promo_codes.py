"""promo_codes.py — platform-level launch/promo code engine (Lago-inspired).

7-day revenue sprint (2026-08-23). Research finding: platform par KOI coupon /
promo redemption mechanism nahi tha — sirf billing-cycle discount (annual 1/6)
exist karta tha. Launch-offer urgency (real deadline) + WhatsApp close links ke
saath discount dena is engine ka kaam hai.

DATA MODEL (Lago ka 2-object split, minimal)
--------------------------------------------
* ``definition`` row — code ka contract: kind (``fixed_inr`` | ``pct``),
  value, plan restriction (``plan_ids``), ``once_per_customer``,
  ``max_redemptions`` (0 = unlimited), ``expires_at`` (ISO), ``tags``
  (e.g. ``["launch"]`` pricing-page countdown ke liye).
* ``applied`` ledger row — ek redemption: code, purana/naya order_ref,
  discount_inr, customer_key (normalized contact), timestamp.

IMMUTABILITY (billing-truth invariant §5)
-----------------------------------------
Ek issued offer kabhi mutate nahi hota. Discount lagane par NAYA offer banta
hai jo purane ko ``supersedes`` karta hai (offers.py ki existing chain) —
original quote auditable rehta hai. Stacking OFF: ek order par sirf EK promo
(derived offer par dobara apply refuse).

Store: ``data/promo_codes.jsonl`` — single family, locked read-modify-write,
atomic rewrite (offers.py convention). Pure storage + logic: no network, no
LLM, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "promo_codes.jsonl")

KIND_FIXED = "fixed_inr"
KIND_PCT = "pct"
_KINDS = {KIND_FIXED, KIND_PCT}

TAG_LAUNCH = "launch"

__all__ = [
    "KIND_FIXED",
    "KIND_PCT",
    "TAG_LAUNCH",
    "active_launch_offer",
    "apply_promo_to_order",
    "create_code",
    "get_definition",
    "list_applied",
    "list_definitions",
    "validate_code",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9_-]", "", (code or "").upper())[:40]


def _norm_key(contact: str) -> str:
    """Customer key — email lowercase, ya phone ke last 10 digits."""
    raw = (contact or "").strip().lower()
    if "@" in raw:
        return raw[:120]
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if digits else ""


def _read() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception as e:
        logger.warning("[promo] read failed: %s", e)
    return rows


def _write_all(rows: list[dict[str, Any]]) -> bool:
    """Atomic rewrite (tmp + os.replace) — caller holds file_lock."""
    tmp = f"{_STORE}.tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _STORE)
        return True
    except Exception as e:
        logger.warning("[promo] write failed: %s", e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def _parse_ts(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat((value or "").strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def get_definition(code: str) -> dict[str, Any] | None:
    norm = _norm_code(code)
    if not norm:
        return None
    for r in _read():
        if r.get("type") == "definition" and str(r.get("code") or "") == norm:
            return dict(r)
    return None


def create_code(
    code: str,
    kind: str,
    value: float,
    *,
    plan_ids: list[str] | None = None,
    once_per_customer: bool = True,
    max_redemptions: int = 0,
    expires_at: str = "",
    label: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Naya promo code define karo (ya existing update). Never raises.

    Fail-closed validation: unknown kind, non-positive/oversized value, ya
    invalid expiry → ``{"ok": False, "reason": ...}``. Same code dobara create
    karne par definition UPDATE hoti hai (applied ledger untouched).
    """
    norm = _norm_code(code)
    k = (kind or "").strip()
    try:
        val = float(value)
    except Exception:
        return {"ok": False, "reason": "invalid_value"}
    if not norm:
        return {"ok": False, "reason": "invalid_code"}
    if k not in _KINDS:
        return {"ok": False, "reason": "invalid_kind"}
    if val <= 0 or (k == KIND_PCT and val > 90) or (k == KIND_FIXED and val > 50_000):
        return {"ok": False, "reason": "value_out_of_range"}
    if expires_at and _parse_ts(expires_at) is None:
        return {"ok": False, "reason": "invalid_expires_at"}

    rec: dict[str, Any] = {
        "type": "definition",
        "code": norm,
        "kind": k,
        "value": val,
        "plan_ids": [str(p).lower() for p in (plan_ids or [])],
        "once_per_customer": bool(once_per_customer),
        "max_redemptions": max(0, int(max_redemptions or 0)),
        "expires_at": (expires_at or "").strip(),
        "label": (label or "").strip()[:120],
        "tags": [str(t).lower() for t in (tags or [])],
        "updated_at": _now_iso(),
    }
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_STORE) as locked:
            if not locked:
                return {"ok": False, "reason": "store_locked"}
            rows = [r for r in _read() if not (
                r.get("type") == "definition" and str(r.get("code") or "") == norm
            )]
            rows.append(rec)
            if not _write_all(rows):
                return {"ok": False, "reason": "write_failed"}
            return {"ok": True, **rec}
    except Exception as e:
        logger.warning("[promo] create failed: %s", e)
        return {"ok": False, "reason": "internal"}


def _applied_rows(rows: list[dict[str, Any]], code: str, customer_key: str = "") -> list[dict]:
    out = [
        r
        for r in rows
        if r.get("type") == "applied" and str(r.get("code") or "") == code
    ]
    if customer_key:
        out = [r for r in out if str(r.get("customer_key") or "") == customer_key]
    return out


def validate_code(
    code: str,
    package_code: str,
    amount_inr: float,
    *,
    customer_key: str = "",
) -> dict[str, Any]:
    """Promo code ko (plan, amount, customer) ke against check karo.

    Returns ``{ok, reason?, discount_inr, effective_inr}`` — never raises.
    Reasons: ``unknown`` · ``expired`` · ``plan_not_eligible`` ·
    ``already_used`` · ``exhausted`` · ``amount_too_small``.
    """
    norm = _norm_code(code)
    defn = get_definition(norm)
    if not defn:
        return {"ok": False, "reason": "unknown", "discount_inr": 0, "effective_inr": amount_inr}

    exp = _parse_ts(str(defn.get("expires_at") or ""))
    if exp and datetime.now(timezone.utc) >= exp:
        return {"ok": False, "reason": "expired", "discount_inr": 0, "effective_inr": amount_inr}

    plans = [str(p) for p in (defn.get("plan_ids") or [])]
    pkg = (package_code or "").strip().lower()
    if plans and pkg not in plans:
        return {
            "ok": False,
            "reason": "plan_not_eligible",
            "discount_inr": 0,
            "effective_inr": amount_inr,
        }

    try:
        amount = float(amount_inr or 0)
    except Exception:
        amount = 0.0
    if amount <= 0:
        return {
            "ok": False,
            "reason": "amount_too_small",
            "discount_inr": 0,
            "effective_inr": amount_inr,
        }

    ckey = _norm_key(customer_key)
    try:
        all_rows = _read()
    except Exception:
        all_rows = []
    if defn.get("once_per_customer") and ckey:
        if _applied_rows(all_rows, norm, ckey):
            return {
                "ok": False,
                "reason": "already_used",
                "discount_inr": 0,
                "effective_inr": amount_inr,
            }
    max_red = int(defn.get("max_redemptions") or 0)
    if max_red > 0 and len(_applied_rows(all_rows, norm)) >= max_red:
        return {
            "ok": False,
            "reason": "exhausted",
            "discount_inr": 0,
            "effective_inr": amount_inr,
        }

    val = float(defn.get("value") or 0)
    discount = round(amount * val / 100.0) if defn.get("kind") == KIND_PCT else round(val)
    discount = max(0, min(discount, int(amount)))
    effective = int(amount) - discount
    if effective < 99:  # ₹0/近-zero UPI order = sale nahi — fail-closed
        return {
            "ok": False,
            "reason": "discount_exceeds_floor",
            "discount_inr": discount,
            "effective_inr": effective,
        }
    return {"ok": True, "discount_inr": discount, "effective_inr": effective}


def apply_promo_to_order(
    order_ref: str,
    code: str,
    *,
    customer_contact: str = "",
) -> dict[str, Any]:
    """Payable order par promo lagao → DISCOUNTED superseding offer.

    Original offer immutable rehta hai (supersede chain). Stacking refuse:
    jis offer par pehle se koi promo laga hai uspe dobara nahi. Ledger row
    append hoti hai. Returns ``{ok, order_ref, quoted_amount, discount_inr,
    expires_at, ...}`` ya ``{ok: False, reason}``.
    """
    ref = (order_ref or "").strip()
    if not ref:
        return {"ok": False, "reason": "no_order"}
    try:
        from app.marketing import offers

        off, reason = offers.resolve_payable(ref)
        if not off:
            return {"ok": False, "reason": f"order_not_payable ({reason})"}
        if off.get("promo_code"):
            return {"ok": False, "reason": "promo_already_applied"}

        base_amount = float(off.get("quoted_amount") or 0)
        ckey = _norm_key(customer_contact)
        chk = validate_code(
            code, str(off.get("package_code") or ""), base_amount, customer_key=ckey
        )
        if not chk.get("ok"):
            return {"ok": False, "reason": chk.get("reason") or "invalid"}

        norm = _norm_code(code)
        new_off = offers.issue_custom_offer(
            str(off.get("deal_id") or ""),
            str(off.get("package_code") or ""),
            int(chk["effective_inr"]),
            label=str(off.get("label") or ""),
            client_id=str(off.get("client_id") or ""),
            prospect_id=str(off.get("prospect_id") or ""),
            supersedes=ref,
            reuse_live=False,
        )
        if not new_off or str(new_off.get("order_ref") or "") == ref:
            return {"ok": False, "reason": "derive_failed"}

        # Stamp the promo provenance on the DERIVED offer (append-only rewrite).
        try:
            from app.utils.file_lock import file_lock

            with file_lock(offers._store()) as locked:
                if locked:
                    rows = offers._read()
                    for r in rows:
                        if r.get("order_ref") == new_off.get("order_ref"):
                            r["promo_code"] = norm
                            r["promo_discount_inr"] = int(chk["discount_inr"])
                    offers._write_all(rows)
        except Exception as e:
            logger.warning("[promo] stamp failed: %s", e)

        try:
            from app.utils.file_lock import file_lock

            with file_lock(_STORE) as locked:
                if locked:
                    rows = _read()
                    rows.append(
                        {
                            "type": "applied",
                            "code": norm,
                            "customer_key": ckey,
                            "order_ref_old": ref,
                            "order_ref_new": str(new_off.get("order_ref") or ""),
                            "discount_inr": int(chk["discount_inr"]),
                            "at": _now_iso(),
                        }
                    )
                    _write_all(rows)
        except Exception as e:
            logger.warning("[promo] ledger append failed: %s", e)

        return {
            "ok": True,
            "order_ref": str(new_off.get("order_ref") or ""),
            "quoted_amount": int(chk["effective_inr"]),
            "discount_inr": int(chk["discount_inr"]),
            "package_code": new_off.get("package_code"),
            "expires_at": new_off.get("expires_at"),
        }
    except Exception as e:
        logger.warning("[promo] apply failed: %s", e)
        return {"ok": False, "reason": "internal"}


def list_applied(limit: int = 200) -> list[dict[str, Any]]:
    rows = [r for r in _read() if r.get("type") == "applied"]
    rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    return rows[: max(1, min(int(limit or 200), 1000))]


def list_definitions() -> list[dict[str, Any]]:
    """Saari promo definitions (latest update pehle). Admin listing ke liye."""
    seen: dict[str, dict[str, Any]] = {}
    for r in _read():
        if r.get("type") == "definition":
            seen[str(r.get("code") or "")] = r
    out = list(seen.values())
    out.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    return out


def active_launch_offer() -> dict[str, Any] | None:
    """Pricing-page countdown ke liye: sabse naya LIVE 'launch'-tagged code.

    Sirf wo offer return hota hai jo abhi bhi valid hai (expiry future me,
    redemptions bachi hue). Server-side deadline hi source-of-truth hai —
    frontend JS sirf DISPLAY karta hai (honest urgency, fake timer nahi).
    """
    defs = [
        r
        for r in _read()
        if r.get("type") == "definition"
        and TAG_LAUNCH in [str(t).lower() for t in (r.get("tags") or [])]
    ]
    defs.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    try:
        all_rows = _read()
    except Exception:
        all_rows = []
    for d in defs:
        exp = _parse_ts(str(d.get("expires_at") or ""))
        if exp and datetime.now(timezone.utc) >= exp:
            continue
        max_red = int(d.get("max_redemptions") or 0)
        if max_red > 0 and len(_applied_rows(all_rows, str(d.get("code") or ""))) >= max_red:
            continue
        return d
    return None
