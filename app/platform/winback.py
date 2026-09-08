"""
winback.py — inactive prospects/customers ko wapas lao (re-engagement drafts).
===============================================================================

"2 mahine ho gaye!" — jo prospects/customers lambe time se chup hain, unke
liye Hinglish WA + email win-back DRAFTS ready karo. KABHI auto-send nahi
(WA bulk auto = number ban; email bhi yahan draft-only — human 1-click).

Sources (sab lazy + best-effort, koi bhi fail = skip):
  - prospector store (data/prospects.jsonl) — last touch = emailed_at /
    updated_at / created_at; status dead/client/replied skip
  - customer_crm (crm_lite store) — per marketing-client end-customers
    (added_at se age; date missing = skip, guess nahi karte)

Public API (sab never-raise):
  - find_inactive(days=60, limit=200)  -> [{type, name, phone, email, ...}]
  - draft(entity)                      -> Hinglish WA msg + email subject/body + wa.me
  - run_due_if_enabled()               -> async; GATED `WINBACK_ENGINE=1`:
                                          drafts -> data/winback_drafts.jsonl
                                          (30-din dedupe per phone/email) + team event
  - list_drafts(limit=100)             -> saved drafts (newest last)

Store: data/winback_drafts.jsonl. Free stack, pure stdlib. Never raises.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DRAFTS_PATH = os.path.join("data", "winback_drafts.jsonl")
_FLAG = "WINBACK_ENGINE"
_DEDUPE_DAYS = 30  # ek hi entity ko 30 din me dobara draft nahi
_MAX_DRAFTS_PER_RUN = 25
_SITE_URL = "https://leadsgenai.in"

_DONE_STATUSES = {"dead", "client", "replied", "unsubscribed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return (os.getenv(_FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_ts(s: Any) -> datetime | None:
    raw = str(s or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _days_since(s: Any) -> float | None:
    dt = _parse_ts(s)
    if dt is None:
        return None
    try:
        return (_now() - dt).total_seconds() / 86400.0
    except Exception:
        return None


def _wa_link(phone: str, message: str) -> str:
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(d) == 10:
        d = "91" + d
    if not d:
        return ""
    return f"https://wa.me/{d}?text={quote(message)}"


# --------------------------------------------------------------------------- #
# Find inactive (prospects + end-customers)
# --------------------------------------------------------------------------- #
def _inactive_prospects(days: int, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from app.platform import prospector

        for p in prospector.list_prospects(limit=500) or []:
            try:
                if str(p.get("status") or "ready").lower() in _DONE_STATUSES:
                    continue
                last = (
                    p.get("emailed_at") or p.get("updated_at") or p.get("created_at") or p.get("ts")
                )
                age = _days_since(last)
                if age is None or age < days:
                    continue
                out.append(
                    {
                        "type": "prospect",
                        "id": p.get("id"),
                        "name": str(p.get("business_name") or "").strip() or "Business",
                        "phone": str(p.get("phone") or "").strip(),
                        "email": str(p.get("email") or "").strip(),
                        "niche": str(p.get("niche") or ""),
                        "city": str(p.get("city") or ""),
                        "last_activity": str(last or ""),
                        "days_inactive": round(age, 1),
                    }
                )
                if len(out) >= limit:
                    break
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[winback] prospects source skip: {e}")
    return out


def _inactive_customers(days: int, limit: int) -> list[dict[str, Any]]:
    """Marketing-clients ke end-customers (crm_lite store). Date missing = skip."""
    out: list[dict[str, Any]] = []
    try:
        from app.marketing import clients_store, crm_lite

        for c in clients_store.list_clients() or []:
            cid = str(c.get("id") or "").strip()
            if not cid:
                continue
            biz = str(c.get("business_name") or "").strip()
            try:
                customers = crm_lite.list_customers(cid) or []
            except Exception:
                continue
            for cust in customers:
                try:
                    last = cust.get("last_visit") or cust.get("added_at") or cust.get("ts")
                    age = _days_since(last)
                    if age is None or age < days:
                        continue
                    out.append(
                        {
                            "type": "customer",
                            "client_id": cid,
                            "business_name": biz,
                            "name": str(cust.get("name") or "").strip() or "Customer",
                            "phone": str(cust.get("phone") or "").strip(),
                            "email": str(cust.get("email") or "").strip(),
                            "last_activity": str(last or ""),
                            "days_inactive": round(age, 1),
                        }
                    )
                    if len(out) >= limit:
                        return out
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[winback] customers source skip: {e}")
    return out


def find_inactive(days: int = 60, limit: int = 200) -> list[dict[str, Any]]:
    """Inactive prospects + end-customers (days se purani last activity).
    Sorted: sabse purane pehle. Never raises."""
    try:
        try:
            days = max(7, min(int(days), 3650))
        except Exception:
            days = 60
        try:
            limit = max(1, min(int(limit), 500))
        except Exception:
            limit = 200
        rows = _inactive_prospects(days, limit) + _inactive_customers(days, limit)
        rows.sort(key=lambda r: -float(r.get("days_inactive") or 0))
        return rows[:limit]
    except Exception as e:
        logger.warning(f"[winback] find_inactive failed: {e}")
        return []


# --------------------------------------------------------------------------- #
# Draft (Hinglish WA + email — DRAFT only, no send)
# --------------------------------------------------------------------------- #
def draft(entity: dict[str, Any] | None) -> dict[str, Any]:
    """Ek inactive entity -> win-back draft (WA msg + wa.me + email subject/body).
    Never raises."""
    try:
        ent = entity if isinstance(entity, dict) else {}
        name = str(ent.get("name") or "").strip() or "ji"
        phone = str(ent.get("phone") or "").strip()
        email = str(ent.get("email") or "").strip()
        etype = str(ent.get("type") or "prospect")
        days = ent.get("days_inactive")
        try:
            months = max(1, round(float(days or 60) / 30))
        except Exception:
            months = 2

        if etype == "customer":
            biz = str(ent.get("business_name") or "").strip() or "Hum"
            wa_msg = (
                f"Namaste {name} ji! 🙏 {months} mahine ho gaye — humein aapki yaad aayi! "
                f"{biz} pe is week wapas aaiye aur 15% off paaiye. "
                f"Bas yeh message dikhayein. Milte hain! 😊\n— {biz}"
            )
            subject = f"{name} ji, {months} mahine ho gaye — 15% off ke saath wapas aaiye!"
            body = (
                f"Namaste {name} ji,\n\n{months} mahine ho gaye aapko dekhe hue — "
                f"humein aapki yaad aayi! {biz} pe is week aaiye aur special 15% off "
                f"paaiye (yeh email dikhana kaafi hai).\n\nMilte hain!\n— {biz}"
            )
        else:
            wa_msg = (
                f"Namaste {name} ji! 🙏 Kuch mahine pehle humne baat ki thi — "
                "AI marketing se naye customers laane ke baare me. Ab hamare paas "
                "naye features + ₹1,999/mahina starter plan hai. 2-minute ka FREE "
                f"Google audit dekh lijiye: {_SITE_URL}/audit?utm_source=winback 😊"
            )
            subject = f"{name} — wapas hello! (free audit + naya ₹1,999 plan)"
            body = (
                f"Namaste,\n\n{name} ke liye kuch time pehle humne free marketing "
                "audit offer kiya tha. Tab busy honge — koi baat nahi!\n\n"
                "Ab hamare paas aur bhi features hain (AI posts, Google ranking, "
                "review automation) aur starter plan sirf ₹1,999/mahina.\n\n"
                f"2 minute me apna FREE audit dekh lijiye: {_SITE_URL}/audit?utm_source=winback\n\n"
                "Shukriya,\nLeadGen AI team"
            )

        return {
            "ok": True,
            "type": etype,
            "name": name,
            "phone": phone,
            "email": email,
            "client_id": ent.get("client_id") or "",
            "wa_message": wa_msg,
            "wa_link": _wa_link(phone, wa_msg),
            "email_subject": subject,
            "email_body": body,
            "days_inactive": days,
            "status": "draft",  # NEVER auto-sent — human 1-click only
        }
    except Exception as e:
        logger.warning(f"[winback] draft failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


# --------------------------------------------------------------------------- #
# Run (gated) + drafts store
# --------------------------------------------------------------------------- #
def _read_drafts() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.isfile(_DRAFTS_PATH):
            with open(_DRAFTS_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"[winback] drafts read failed: {e}")
    return rows


def list_drafts(limit: int = 100) -> list[dict[str, Any]]:
    """Saved win-back drafts (newest last). Never raises."""
    try:
        limit = max(1, min(int(limit), 1000))
    except Exception:
        limit = 100
    return _read_drafts()[-limit:]


def _recent_keys(days: int = _DEDUPE_DAYS) -> set[str]:
    keys: set[str] = set()
    for r in _read_drafts():
        age = _days_since(r.get("created_at"))
        if age is not None and age > days:
            continue
        for k in (r.get("phone"), r.get("email")):
            k = str(k or "").strip().lower()
            if k:
                keys.add(k)
    return keys


async def run_due_if_enabled(days: int = 60) -> dict[str, Any]:
    """Scheduler hook — GATED `WINBACK_ENGINE=1` (default OFF = graceful skip).
    Drafts banata hai (NO auto-send), 30-din dedupe per phone/email. Never raises."""
    if not _enabled():
        return {"ok": True, "skipped": True, "reason": f"{_FLAG} flag OFF"}
    try:
        seen = _recent_keys()
        created: list[dict[str, Any]] = []
        for ent in find_inactive(days=days, limit=200):
            if len(created) >= _MAX_DRAFTS_PER_RUN:
                break
            key_phone = str(ent.get("phone") or "").strip().lower()
            key_email = str(ent.get("email") or "").strip().lower()
            if (key_phone and key_phone in seen) or (key_email and key_email in seen):
                continue
            if not key_phone and not key_email:
                continue  # contact hi nahi — draft bekaar
            d = draft(ent)
            if not d.get("ok"):
                continue
            d["created_at"] = _now().isoformat()
            try:
                os.makedirs(os.path.dirname(_DRAFTS_PATH) or ".", exist_ok=True)
                with open(_DRAFTS_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
            except Exception as e:
                logger.warning(f"[winback] draft write failed: {e}")
                continue
            for k in (key_phone, key_email):
                if k:
                    seen.add(k)
            created.append(d)
        if created:
            try:
                from app.platform.team import log_event

                log_event(
                    "rohan",
                    "winback_drafts",
                    f"{len(created)} win-back drafts ready ({days}+ din inactive)",
                )
            except Exception:
                pass
        return {
            "ok": True,
            "drafts_created": len(created),
            "drafts": created,
            "note": "Auto-send NAHI hota — wa_link/email se human 1-click bhejo (ban-safe).",
        }
    except Exception as e:
        logger.warning(f"[winback] run failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["find_inactive", "draft", "run_due_if_enabled", "list_drafts"]
