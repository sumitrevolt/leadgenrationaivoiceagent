"""Human Dialer Mode — disposition logging (NeoDove-style telecaller productivity).

Kyun: jin clients ke paas khud ka staff hai, unke telecallers ko ek simple
"agla lead → call → disposition" loop chahiye. Yeh module sirf dispositions
LOG karta hai (data/dialer_logs.jsonl) + best-effort prospect status update
(EXISTING prospector.mark_prospect / set_prospect_fields — koi naya store
nahi). Auto-call/auto-send kuch NAHI (tel:/wa.me links frontend pe human
click karta hai). Never raises.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIALER_LOGS = os.path.join("data", "dialer_logs.jsonl")

# Telecaller dispositions → prospector VALID_STATUSES ("ready","sent","replied","client","dead")
DISPOSITIONS = ("interested", "callback", "no-answer", "wrong-number", "not-interested")
_STATUS_MAP = {
    "interested": "replied",  # hot — follow-up pipeline me
    "callback": None,  # status mat chhedo; callback_at field set hota
    "no-answer": None,  # status same; attempt count field me
    "wrong-number": "dead",
    "not-interested": "dead",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phone_digits(raw: Any) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def status_for(disposition: str) -> str | None:
    """Disposition ka prospect-status mapping (None = status untouched).
    Pure function — tests ke liye."""
    return _STATUS_MAP.get((disposition or "").strip().lower())


def _read_logs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_DIALER_LOGS):
            return out
        with open(_DIALER_LOGS, encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[dialer] logs read failed: {e}")
    return out


def log_disposition(phone: str, disposition: str, notes: str = "") -> dict[str, Any]:
    """Call disposition log karo + best-effort prospect status sync. Never raises."""
    try:
        ph = _phone_digits(phone)
        disp = (disposition or "").strip().lower()
        if not ph:
            return {"error": "valid 10-digit phone chahiye"}
        if disp not in DISPOSITIONS:
            return {"error": f"disposition inme se ho: {', '.join(DISPOSITIONS)}"}
        rec = {
            "phone": ph,
            "disposition": disp,
            "notes": (notes or "").strip()[:500],
            "at": _now(),
        }
        os.makedirs(os.path.dirname(_DIALER_LOGS) or ".", exist_ok=True)
        with open(_DIALER_LOGS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

        # Best-effort prospect update (EXISTING prospector store fns; fail = log-only)
        updated = False
        try:
            from app.platform import prospector

            for p in prospector.list_prospects(limit=2000):
                if _phone_digits(p.get("phone")) == ph:
                    pid = p.get("id")
                    new_status = status_for(disp)
                    if pid and new_status:
                        updated = prospector.mark_prospect(pid, new_status)
                    if pid:
                        fields: dict[str, Any] = {"last_dialed_at": rec["at"]}
                        if disp == "callback":
                            fields["callback_requested_at"] = rec["at"]
                        if rec["notes"]:
                            fields["dialer_notes"] = rec["notes"]
                        prospector.set_prospect_fields(pid, fields)
                    break
        except Exception as e:
            logger.debug(f"[dialer] prospect sync skipped: {e}")

        return {"ok": True, "logged": rec, "prospect_updated": updated}
    except Exception as e:
        logger.warning(f"[dialer] log_disposition failed: {e}")
        return {"error": str(e)}


def stats_today() -> dict[str, Any]:
    """Aaj ke calls by disposition (UTC date). Never raises."""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        by: dict[str, int] = dict.fromkeys(DISPOSITIONS, 0)
        total = 0
        for r in _read_logs():
            if str(r.get("at") or "")[:10] != today:
                continue
            total += 1
            d = str(r.get("disposition") or "")
            if d in by:
                by[d] += 1
        return {"date": today, "total_calls": total, "by_disposition": by}
    except Exception as e:
        logger.debug(f"[dialer] stats failed: {e}")
        return {"date": "", "total_calls": 0, "by_disposition": {}, "error": str(e)}


__all__ = ["DISPOSITIONS", "status_for", "log_disposition", "stats_today"]
