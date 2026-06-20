"""
service_reminders.py — repeat-service reminders (NiceJob parity).
==================================================================

Client (local business) ke END-CUSTOMERS ke service cycles track karo
(AC service har 6 mahine, RO filter har 3 mahine, car service har saal...)
aur due hote hi Hinglish WhatsApp reminder DRAFT ready karo — 1-click
wa.me link, KABHI auto-send nahi (WA bulk auto = number ban).

Store: data/service_reminders.jsonl (append-only event log):
  {"type":"cycle", id, client_id, customer{name,phone}, service,
   interval_days, last_service_date, next_due, active}
  {"type":"reminded", id, next_due}   (same-cycle dedupe marker)
  Latest "cycle" record per id wins (mark_serviced = naya cycle append).

Public API (sab never-raise, pure stdlib):
  - set_cycle(client_id, customer, service, interval_days, last_service_date="")
  - due(days_ahead=3)            -> abhi/jaldi due cycles (un-reminded)
  - draft(reminder)              -> Hinglish WA reminder draft + wa.me link
  - run_due(days_ahead=3)        -> drafts list + reminded markers (dedupe)
  - run_due_if_enabled()         -> scheduler hook, GATED `SERVICE_REMINDERS=1`
  - mark_serviced(cycle_id)      -> service ho gayi → agla cycle shuru
  - list_cycles(client_id=None)  -> saved cycles

Scheduler wiring is module ki NAHI hai — suggestion: team_scheduler `content`
job me `service_reminders.run_due_if_enabled()` (flag OFF = graceful skip).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "service_reminders.jsonl")
_FLAG = "SERVICE_REMINDERS"


# --------------------------------------------------------------------------- #
# Store helpers
# --------------------------------------------------------------------------- #
def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        rec["ts"] = datetime.now(timezone.utc).isoformat()
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[service_reminders] append failed: {e}")


def _load_state() -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]]]:
    """(cycles by id — latest wins, reminded {(id, next_due)} set)."""
    cycles: dict[str, dict[str, Any]] = {}
    reminded: set[tuple[str, str]] = set()
    try:
        if os.path.isfile(_PATH):
            with open(_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    rid = str(r.get("id") or "")
                    if not rid:
                        continue
                    if r.get("type") == "cycle":
                        cycles[rid] = r
                    elif r.get("type") == "reminded":
                        reminded.add((rid, str(r.get("next_due") or "")))
    except Exception as e:
        logger.warning(f"[service_reminders] load failed: {e}")
    return cycles, reminded


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _interval_hinglish(days: int) -> str:
    try:
        days = int(days)
        if days >= 360 and days % 360 in (0, 5):
            return f"{max(1, round(days / 365))} saal"
        if days >= 30 and days % 30 == 0:
            return f"{days // 30} mahine"
        return f"{days} din"
    except Exception:
        return "kuch time"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def set_cycle(
    client_id: str,
    customer: dict[str, Any] | None,
    service: str,
    interval_days: int,
    last_service_date: str = "",
) -> dict[str, Any]:
    """Customer ka repeat-service cycle save karo. Returns {ok, cycle}.
    last_service_date (YYYY-MM-DD) default = aaj. Never raises."""
    try:
        cust = customer if isinstance(customer, dict) else {}
        name = str(cust.get("name") or "").strip() or "Customer"
        phone = "".join(ch for ch in str(cust.get("phone") or "") if ch.isdigit())
        if not phone:
            return {"ok": False, "error": "customer.phone zaroori hai"}
        service = str(service or "").strip() or "service"
        try:
            interval = max(1, min(int(interval_days), 3650))
        except Exception:
            return {"ok": False, "error": "interval_days number do (din me)"}
        last = _parse_date(last_service_date) or date.today()
        next_due = (last + timedelta(days=interval)).isoformat()
        cid = hashlib.sha1(f"{client_id}|{phone}|{service.lower()}".encode()).hexdigest()[:12]
        rec = {
            "type": "cycle",
            "id": cid,
            "client_id": str(client_id or "").strip(),
            "customer": {"name": name, "phone": phone},
            "service": service,
            "interval_days": interval,
            "last_service_date": last.isoformat(),
            "next_due": next_due,
            "active": True,
        }
        _append(rec)
        return {"ok": True, "cycle": rec}
    except Exception as e:
        logger.warning(f"[service_reminders] set_cycle failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def list_cycles(client_id: str | None = None) -> list[dict[str, Any]]:
    """Saved cycles (latest state). Never raises."""
    try:
        cycles, _ = _load_state()
        rows = list(cycles.values())
        if client_id:
            rows = [r for r in rows if str(r.get("client_id") or "") == str(client_id)]
        return sorted(rows, key=lambda r: str(r.get("next_due") or ""))
    except Exception as e:
        logger.warning(f"[service_reminders] list failed: {e}")
        return []


def due(days_ahead: int = 3) -> list[dict[str, Any]]:
    """Aaj se `days_ahead` din ke andar due (active, is cycle me ab tak
    un-reminded) cycles. Never raises."""
    out: list[dict[str, Any]] = []
    try:
        try:
            days_ahead = max(0, min(int(days_ahead), 60))
        except Exception:
            days_ahead = 3
        horizon = (date.today() + timedelta(days=days_ahead)).isoformat()
        cycles, reminded = _load_state()
        for r in cycles.values():
            if not r.get("active", True):
                continue
            nd = str(r.get("next_due") or "")
            if not nd or nd > horizon:
                continue
            if (str(r.get("id") or ""), nd) in reminded:
                continue
            out.append(r)
        out.sort(key=lambda r: str(r.get("next_due") or ""))
    except Exception as e:
        logger.warning(f"[service_reminders] due failed: {e}")
    return out


def _client_name(client_id: str) -> str:
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id)  # type: ignore[attr-defined]
        if isinstance(c, dict):
            return str(c.get("business_name") or "").strip()
    except Exception:
        pass
    return ""


def draft(reminder: dict[str, Any] | None) -> dict[str, Any]:
    """Ek due cycle → Hinglish WA reminder DRAFT (1-click wa.me, NO auto-send).
    Never raises."""
    try:
        r = reminder if isinstance(reminder, dict) else {}
        cust = r.get("customer") or {}
        name = str(cust.get("name") or "").strip() or "ji"
        phone = "".join(ch for ch in str(cust.get("phone") or "") if ch.isdigit())
        service = str(r.get("service") or "service").strip()
        interval_h = _interval_hinglish(int(r.get("interval_days") or 0))
        biz = _client_name(str(r.get("client_id") or ""))
        sign = f"\n— {biz}" if biz else ""
        message = (
            f"Namaste {name} ji! 🙏 Aapki {service} ko {interval_h} ho gaye hain — "
            f"time par service se machine lambi chalti hai aur kharcha bachta hai. "
            f"Is week ka slot book kar lein? Abhi book karne par 10% off! 😊{sign}"
        )
        if len(phone) == 10:
            phone = "91" + phone
        wa_link = f"https://wa.me/{phone}?text={quote(message)}" if phone else ""
        return {
            "ok": True,
            "id": r.get("id"),
            "client_id": r.get("client_id"),
            "customer": {"name": name, "phone": phone},
            "service": service,
            "next_due": r.get("next_due"),
            "message": message,
            "wa_link": wa_link,
            "status": "draft",  # NEVER auto-sent — human 1-click only
        }
    except Exception as e:
        logger.warning(f"[service_reminders] draft failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def run_due(days_ahead: int = 3) -> dict[str, Any]:
    """Saare due cycles ke reminder DRAFTS banao + reminded marker (same cycle
    dobara nahi). Auto-send KABHI nahi. Never raises."""
    try:
        drafts: list[dict[str, Any]] = []
        for r in due(days_ahead=days_ahead):
            d = draft(r)
            if not d.get("ok"):
                continue
            _append(
                {
                    "type": "reminded",
                    "id": str(r.get("id") or ""),
                    "next_due": str(r.get("next_due") or ""),
                }
            )
            drafts.append(d)
            try:
                from app.platform.team import log_event

                log_event(
                    "kavya",
                    "service_reminder",
                    f"{d['customer']['name']} — {d['service']} due ({d.get('next_due')})",
                )
            except Exception:
                pass
        return {
            "ok": True,
            "drafts": drafts,
            "count": len(drafts),
            "note": "Auto-send NAHI hota — wa_link se 1-click bhejo (ban-safe).",
        }
    except Exception as e:
        logger.warning(f"[service_reminders] run_due failed: {e}")
        return {"ok": False, "error": str(e)[:200], "drafts": []}


async def run_due_if_enabled() -> dict[str, Any]:
    """Scheduler hook — sirf `SERVICE_REMINDERS=1` pe chalta (default OFF)."""
    flag = (os.getenv(_FLAG) or "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return {"ok": True, "skipped": True, "reason": f"{_FLAG} flag OFF"}
    return run_due()


def mark_serviced(cycle_id: str, service_date: str = "") -> dict[str, Any]:
    """Service complete — naya cycle shuru (next_due = date + interval). Never raises."""
    try:
        cycles, _ = _load_state()
        r = cycles.get(str(cycle_id or "").strip())
        if not r:
            return {"ok": False, "error": "cycle nahi mila"}
        last = _parse_date(service_date) or date.today()
        rec = dict(r)
        rec["last_service_date"] = last.isoformat()
        rec["next_due"] = (last + timedelta(days=int(r.get("interval_days") or 30))).isoformat()
        rec["type"] = "cycle"
        _append(rec)
        return {"ok": True, "cycle": rec}
    except Exception as e:
        logger.warning(f"[service_reminders] mark_serviced failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = [
    "set_cycle",
    "list_cycles",
    "due",
    "draft",
    "run_due",
    "run_due_if_enabled",
    "mark_serviced",
]
