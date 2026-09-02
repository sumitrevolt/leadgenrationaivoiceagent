"""Speed-to-lead metric — READ-ONLY compute from existing stores (no hooks).

"5 minute me jawab = 21x zyada conversion" (classic lead-response research).
Yeh module sirf MEASURE karta hai ki inquiry aane ke kitni der baad pehla
touch (alert/callback/dialer call) hua — koi naya hot-path hook NAHI.

Evidence sources (sab existing, append-only):
  * data/inquiries.jsonl    — inquiry record (`at` UTC ISO, `phone`)
                              [shape: public_site.submit_inquiry]
  * data/lead_alerts.jsonl  — instant alert evidence (`phone` digits, `epoch`)
                              [shape: lead_alerts._log_alert]
  * data/dialer_logs.jsonl  — human dialer call (`phone`, ts/at best-effort)

first_touch_seconds = earliest evidence AFTER inquiry, per phone (estimate —
alert ~ same second as inquiry, dialer = real human touch).

  per_inquiry(days)  -> list of {phone, inquiry_at, first_touch_seconds, via}
  summary(days=30)   -> avg / median / under-2-min % + Hinglish verdict

Pure stdlib + file IO. NEVER raises.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")
_ALERTS_FILE = os.path.join("data", "lead_alerts.jsonl")
_DIALER_FILE = os.path.join("data", "dialer_logs.jsonl")
_CALLBACK_FILE = os.path.join("data", "callback_touches.jsonl")

_TARGET_SECONDS = 120  # 2-min target


def log_callback_touch(phone: str, *, placed: bool = True) -> None:
    """Record AI auto-callback as first-touch evidence (speed-to-lead). Never raises."""
    if not placed:
        return
    ph = _phone10(phone)
    if not ph:
        return
    try:
        os.makedirs(os.path.dirname(_CALLBACK_FILE) or ".", exist_ok=True)
        rec = {
            "phone": ph,
            "epoch": time.time(),
            "via": "ai_callback",
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with open(_CALLBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[speed_to_lead] callback touch log skip: {e}")


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except Exception as e:
        logger.debug(f"[speed_to_lead] read {path} skip: {e}")
    return out


def _phone10(val: Any) -> str:
    return re.sub(r"\D", "", str(val or ""))[-10:]


def _to_epoch(val: Any) -> float | None:
    """ISO string (Z/offset/naive-local) ya epoch number → epoch seconds.
    Defensive — kuch bhi parse na ho to None."""
    try:
        if val is None:
            return None
        if isinstance(val, int | float):
            return float(val) if float(val) > 0 else None
        s = str(val).strip()
        if not s:
            return None
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            return dt.timestamp()
        # Naive = local time (lead_alerts/dialer time.strftime se likhte hain)
        return time.mktime(dt.timetuple())
    except Exception:
        return None


def _evidence_epochs() -> dict[str, list[tuple[float, str]]]:
    """phone10 → [(epoch, via), ...] from alerts + dialer logs."""
    ev: dict[str, list[tuple[float, str]]] = {}

    for rec in _read_jsonl(_ALERTS_FILE):
        ph = _phone10(rec.get("phone"))
        ep = _to_epoch(rec.get("epoch")) or _to_epoch(rec.get("ts"))
        if ph and ep:
            ev.setdefault(ph, []).append((ep, "alert"))

    for rec in _read_jsonl(_DIALER_FILE):
        ph = _phone10(rec.get("phone"))
        ep = (
            _to_epoch(rec.get("ts")) or _to_epoch(rec.get("at")) or _to_epoch(rec.get("created_at"))
        )
        if ph and ep:
            ev.setdefault(ph, []).append((ep, "dialer_call"))

    for rec in _read_jsonl(_CALLBACK_FILE):
        ph = _phone10(rec.get("phone"))
        ep = _to_epoch(rec.get("epoch")) or _to_epoch(rec.get("ts"))
        if ph and ep:
            ev.setdefault(ph, []).append((ep, "ai_callback"))

    return ev


def per_inquiry(days: int = 30) -> list[dict[str, Any]]:
    """Har inquiry ka first-touch estimate (last N days). Never raises."""
    try:
        days = max(1, min(int(days or 30), 365))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        evidence = _evidence_epochs()
        rows: list[dict[str, Any]] = []
        for rec in _read_jsonl(_INQUIRIES_FILE):
            ph = _phone10(rec.get("phone"))
            inq_ep = _to_epoch(rec.get("at"))
            if not ph or not inq_ep or inq_ep < cutoff:
                continue
            best: tuple[float, str] | None = None
            # 60s grace pehle ka bhi accept (clock skew/local-vs-utc estimate)
            for ep, via in evidence.get(ph, []):
                if ep >= inq_ep - 60 and (best is None or ep < best[0]):
                    best = (ep, via)
            rows.append(
                {
                    "phone": ph,
                    "inquiry_at": rec.get("at"),
                    "source": rec.get("source") or "",
                    "first_touch_seconds": (max(0, round(best[0] - inq_ep)) if best else None),
                    "via": best[1] if best else None,
                }
            )
        return rows
    except Exception as e:
        logger.warning(f"[speed_to_lead] per_inquiry failed: {e}")
        return []


def summary(days: int = 30) -> dict[str, Any]:
    """Avg / median / under-2-min % + Hinglish verdict. Never raises."""
    try:
        rows = per_inquiry(days)
        touched = [
            r["first_touch_seconds"] for r in rows if r.get("first_touch_seconds") is not None
        ]
        total = len(rows)
        if not touched:
            return {
                "ok": True,
                "days": days,
                "total_inquiries": total,
                "touched": 0,
                "untouched": total,
                "avg_seconds": None,
                "median_seconds": None,
                "under_2min_pct": 0.0,
                "under_5min_pct": 0.0,
                "sla_5min_ok": False,
                "target_seconds": _TARGET_SECONDS,
                "world_class_target_seconds": 300,
                "verdict": (
                    "Abhi koi first-touch data nahi — inquiry aate hi 2 minute me "
                    "callback/alert ka system on rakho (lead 5 min me thanda hota hai)."
                ),
                "inquiries": rows[-50:],
            }
        touched_sorted = sorted(touched)
        n = len(touched_sorted)
        median = (
            touched_sorted[n // 2]
            if n % 2
            else (touched_sorted[n // 2 - 1] + touched_sorted[n // 2]) / 2
        )
        avg = sum(touched_sorted) / n
        under = sum(1 for s in touched_sorted if s <= _TARGET_SECONDS)
        under_pct = round(100.0 * under / n, 1)
        under_5 = sum(1 for s in touched_sorted if s <= 300)
        under_5_pct = round(100.0 * under_5 / n, 1)

        avg_min = avg / 60.0
        if under_pct >= 80:
            verdict = (
                f"Zabardast! {under_pct}% inquiries ko 2 min ke andar touch — "
                f"avg {avg_min:.1f} min. Yahi speed conversion jeetati hai. 🏆"
            )
        elif under_pct >= 50:
            verdict = (
                f"Theek chal raha hai — avg {avg_min:.1f} min me jawab, {under_pct}% "
                f"2-min target ke andar. Thoda aur tez = zyada conversion."
            )
        else:
            verdict = (
                f"Aap avg {avg_min:.1f} min me jawab dete ho — 2-min target hai. "
                f"Sirf {under_pct}% leads ko 2 min me touch mila; auto-callback/alert "
                f"on karke yeh number badhao (5 min baad lead thanda)."
            )
        sla_ok = bool(n) and (median <= 300)
        return {
            "ok": True,
            "days": days,
            "total_inquiries": total,
            "touched": n,
            "untouched": total - n,
            "avg_seconds": round(avg, 1),
            "median_seconds": round(float(median), 1),
            "under_2min_pct": under_pct,
            "under_5min_pct": under_5_pct,
            "sla_5min_ok": sla_ok,
            "target_seconds": _TARGET_SECONDS,
            "world_class_target_seconds": 300,
            "verdict": verdict,
            "inquiries": rows[-50:],
        }
    except Exception as e:
        logger.warning(f"[speed_to_lead] summary failed: {e}")
        return {"ok": False, "error": str(e)[:160]}


def _inquiry_matches_client(rec: dict, client_id: str, client_rec: dict | None) -> bool:
    """Same matching rules as customer_dashboard._inquiries_for_client (single row)."""
    cid = (client_id or "").strip().lower()
    slug = str((client_rec or {}).get("slug") or "").strip().lower()
    rec_id = str((client_rec or {}).get("id") or "").strip().lower()
    biz = str((client_rec or {}).get("business_name") or "").strip().lower()
    phone_d = "".join(ch for ch in str((client_rec or {}).get("phone") or "") if ch.isdigit())[-10:]
    r_slug = str(rec.get("source_slug") or "").strip().lower()
    r_cid = str(rec.get("client_id") or "").strip().lower()
    r_biz = str(rec.get("business_name") or "").strip().lower()
    r_ph = "".join(ch for ch in str(rec.get("phone") or "") if ch.isdigit())[-10:]
    if slug and r_slug == slug:
        return True
    if rec_id and r_cid == rec_id:
        return True
    if cid and r_cid == cid:
        return True
    if biz and r_biz == biz:
        return True
    if phone_d and r_ph and r_ph == phone_d:
        return True
    return False


def per_inquiry_for_client(
    client_id: str,
    client_rec: dict | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """per_inquiry() filtered to one client's inquiries. Never raises."""
    try:
        days = max(1, min(int(days or 30), 365))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        evidence = _evidence_epochs()
        rows: list[dict[str, Any]] = []
        for rec in _read_jsonl(_INQUIRIES_FILE):
            ph = _phone10(rec.get("phone"))
            inq_ep = _to_epoch(rec.get("at"))
            if not ph or not inq_ep or inq_ep < cutoff:
                continue
            if client_id and client_id not in ("", "demo"):
                if not _inquiry_matches_client(rec, client_id, client_rec):
                    continue
            best: tuple[float, str] | None = None
            for ep, via in evidence.get(ph, []):
                if ep >= inq_ep - 60 and (best is None or ep < best[0]):
                    best = (ep, via)
            rows.append(
                {
                    "phone": ph,
                    "inquiry_at": rec.get("at"),
                    "source": rec.get("source") or "",
                    "first_touch_seconds": (max(0, round(best[0] - inq_ep)) if best else None),
                    "via": best[1] if best else None,
                }
            )
        return rows
    except Exception as e:
        logger.warning(f"[speed_to_lead] per_inquiry_for_client failed: {e}")
        return []


def summary_for_client(
    client_id: str,
    client_rec: dict | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Client-scoped speed-to-lead summary (same shape as summary()). Never raises."""
    try:
        rows = per_inquiry_for_client(client_id, client_rec, days)
        touched = [
            r["first_touch_seconds"] for r in rows if r.get("first_touch_seconds") is not None
        ]
        total = len(rows)
        if not touched:
            return {
                "ok": True,
                "client_id": client_id,
                "days": days,
                "total_inquiries": total,
                "touched": 0,
                "untouched": total,
                "avg_seconds": None,
                "median_seconds": None,
                "under_2min_pct": 0.0,
                "target_seconds": _TARGET_SECONDS,
                "verdict": (
                    "Abhi koi inquiry response data nahi — enquiry aate hi 2 minute me "
                    "jawab dena conversion badhata hai."
                ),
                "inquiries": rows[-20:],
            }
        touched_sorted = sorted(touched)
        n = len(touched_sorted)
        median = (
            touched_sorted[n // 2]
            if n % 2
            else (touched_sorted[n // 2 - 1] + touched_sorted[n // 2]) / 2
        )
        avg = sum(touched_sorted) / n
        under = sum(1 for s in touched_sorted if s <= _TARGET_SECONDS)
        under_pct = round(100.0 * under / n, 1)
        avg_min = avg / 60.0
        if under_pct >= 80:
            verdict = (
                f"Zabardast! {under_pct}% inquiries ko 2 min ke andar touch — "
                f"avg {avg_min:.1f} min. 🏆"
            )
        elif under_pct >= 50:
            verdict = f"Theek — avg {avg_min:.1f} min me jawab, {under_pct}% 2-min target ke andar."
        else:
            verdict = (
                f"Avg {avg_min:.1f} min me jawab — 2-min target rakho; "
                f"auto-callback/alert se yeh number badhega."
            )
        return {
            "ok": True,
            "client_id": client_id,
            "days": days,
            "total_inquiries": total,
            "touched": n,
            "untouched": total - n,
            "avg_seconds": round(avg, 1),
            "median_seconds": round(float(median), 1),
            "under_2min_pct": under_pct,
            "target_seconds": _TARGET_SECONDS,
            "verdict": verdict,
            "inquiries": rows[-20:],
        }
    except Exception as e:
        logger.warning(f"[speed_to_lead] summary_for_client failed: {e}")
        return {"ok": False, "client_id": client_id, "error": str(e)[:160]}


__all__ = [
    "per_inquiry",
    "summary",
    "per_inquiry_for_client",
    "summary_for_client",
    "log_callback_touch",
]
