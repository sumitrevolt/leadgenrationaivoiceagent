"""Sales Autopilot prospect refill — prospector → autopilot store (flag-gated).

``SALES_AUTOPILOT_REFILL=1`` pe scored/ready Maps prospects ko idempotent upsert
karta hai (status=new). Dedupe by phone digits + email + existing id. Kabhi
provider send nahi — sirf store fill. Cap per call via ``SALES_AUTOPILOT_REFILL_CAP``
(default 10). Never raises.
"""

from __future__ import annotations

import os
from typing import Any

from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "SALES_AUTOPILOT_REFILL"
_CAP_ENV = "SALES_AUTOPILOT_REFILL_CAP"
_MIN_SCORE_ENV = "SALES_AUTOPILOT_REFILL_MIN_SCORE"
_DEFAULT_CAP = 10
_DEFAULT_MIN_SCORE = 40


def refill_enabled() -> bool:
    raw = (os.getenv(_FLAG) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _cap() -> int:
    try:
        return max(1, min(int(os.getenv(_CAP_ENV) or _DEFAULT_CAP), 50))
    except Exception:
        return _DEFAULT_CAP


def _min_score() -> int:
    try:
        return max(0, min(int(os.getenv(_MIN_SCORE_ENV) or _DEFAULT_MIN_SCORE), 100))
    except Exception:
        return _DEFAULT_MIN_SCORE


def _digits(phone: str) -> str:
    return _store.digits(phone)[-10:]


def _existing_keys() -> tuple[set[str], set[str], set[str]]:
    ids: set[str] = set()
    phones: set[str] = set()
    emails: set[str] = set()
    for r in _store.list_prospects(limit=5000):
        pid = str(r.get("id") or "").strip()
        if pid:
            ids.add(pid)
        ph = _digits(str(r.get("phone") or ""))
        if len(ph) >= 10:
            phones.add(ph)
        em = str(r.get("email") or "").strip().lower()
        if em and "@" in em:
            emails.add(em)
    return ids, phones, emails


def _candidate_ok(row: dict[str, Any], min_score: int) -> bool:
    if (row.get("status") or "ready") != "ready":
        return False
    email = str(row.get("email") or "").strip()
    phone = _digits(str(row.get("phone") or ""))
    if not email and len(phone) < 10:
        return False
    if row.get("is_hot_lead"):
        return True
    try:
        score = int(row.get("lead_score") or 0)
    except Exception:
        score = 0
    return score >= min_score


def _map_row(row: dict[str, Any]) -> dict[str, Any]:
    pid = str(row.get("id") or "").strip()
    name = (
        str(row.get("business_name") or row.get("name") or row.get("company") or "").strip()
        or "Prospect"
    )
    return {
        "id": pid,
        "name": name[:120],
        "phone": str(row.get("phone") or "").strip(),
        "email": str(row.get("email") or "").strip(),
        "city": str(row.get("city") or "").strip(),
        "niche": str(row.get("niche") or row.get("category") or "").strip(),
        "source": "prospector_refill",
        "consent_basis": "public_business_listing",
        "lead_score": row.get("lead_score") or 0,
        "status": _store.STATUS_NEW,
    }


def refill_from_prospector(
    *,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Upsert eligible prospector rows into the autopilot store.

    ``force=True`` bypasses the env flag (admin manual refill). Never raises.
    """
    out: dict[str, Any] = {
        "enabled": refill_enabled(),
        "forced": bool(force),
        "scanned": 0,
        "upserted": 0,
        "skipped_dup": 0,
        "skipped_filter": 0,
        "ids": [],
    }
    if not force and not refill_enabled():
        out["skip_reason"] = "refill_disabled"
        return out
    try:
        from app.platform import prospector as _prospector

        cap = _cap() if limit is None else max(1, min(int(limit), 50))
        min_score = _min_score()
        ids, phones, emails = _existing_keys()
        # Pull a wider window then filter — newest-first list is OK for refill.
        rows = _prospector.list_prospects(status="ready", limit=500)
        out["scanned"] = len(rows)
        for row in rows:
            if out["upserted"] >= cap:
                break
            if not _candidate_ok(row, min_score):
                out["skipped_filter"] += 1
                continue
            pid = str(row.get("id") or "").strip()
            if not pid:
                out["skipped_filter"] += 1
                continue
            ph = _digits(str(row.get("phone") or ""))
            em = str(row.get("email") or "").strip().lower()
            if pid in ids or (len(ph) >= 10 and ph in phones) or (em and em in emails):
                out["skipped_dup"] += 1
                continue
            # Never refill terminal / converted-looking statuses from prospector id collision.
            existing = _store.get_prospect(pid)
            if existing and existing.get("status") in (
                _store.STATUS_CONVERTED,
                _store.STATUS_AWAITING_PAYMENT,
                _store.STATUS_OPTED_OUT,
                _store.STATUS_REMOVED,
                _store.STATUS_MANUAL_OWNER_CONFIRMED,
            ):
                out["skipped_dup"] += 1
                continue
            mapped = _map_row(row)
            rec = _store.upsert_prospect(mapped)
            if rec.get("error"):
                out["skipped_filter"] += 1
                continue
            ids.add(pid)
            if len(ph) >= 10:
                phones.add(ph)
            if em:
                emails.add(em)
            out["upserted"] += 1
            out["ids"].append(pid)
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.refill] failed: %s", e)
        out["error"] = str(e)[:160]
        return out


__all__ = ["refill_enabled", "refill_from_prospector"]
