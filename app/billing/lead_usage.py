"""
Qualified-LEAD usage metering — AI Voice Calling Agent (Product 2) ka billing meter.
=====================================================================================

ADR-009: voice product ka billable unit = AI-qualified "interested" lead
(call_qualifier verdict). Minutes NAHI (wo marketing-Advanced FEATURE ka meter
hai, `usage.py`), PER-LEAD bhi nahi — 10-lead UNITS: tier quota + top-up packs.

Design (usage.py minute-meter ke pattern pe, par DB-migration-free):
  - Ledger: data/lead_usage.jsonl (append-only) — {client_id, ts, kind, leads, ref}
    kind: "qualified" (1 lead consume) | "topup" (pack credit add)
  - Period = calendar month (IST-agnostic UTC) — quota + top-ups period-end EXPIRE.
  - FAIL-OPEN: client_id na ho / voice plan na ho / error => block NAHI
    (usage.py has_minutes jaisa hi safety posture — billing bug se calls na rukein).

Kabhi raise nahi karta. Import-safe (heavy deps nahi).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_STORE = Path(os.getenv("DATA_DIR", "data")) / "lead_usage.jsonl"
_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _period_key(at: datetime | None = None) -> str:
    d = at or _now()
    return f"{d.year:04d}-{d.month:02d}"


def _append(rec: dict) -> bool:
    try:
        with _LOCK:
            _STORE.parent.mkdir(parents=True, exist_ok=True)
            with _STORE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _iter_period(client_id: str, period: str | None = None):
    pk = period or _period_key()
    try:
        if not _STORE.exists():
            return
        with _STORE.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("client_id") != client_id:
                    continue
                if str(rec.get("ts", ""))[:7] != pk:
                    continue
                yield rec
    except Exception:
        return


def record_qualified_lead(client_id: str, ref: str = "", plan: str | None = None) -> bool:
    """Ek AI-qualified lead consume karo (call_qualifier 'interested' verdict pe).

    ref = call sid / qualification id (dispute-evidence link). Best-effort.
    """
    cid = (client_id or "").strip()
    if not cid:
        return False
    return _append(
        {
            "client_id": cid,
            "ts": _now().isoformat(),
            "kind": "qualified",
            "leads": 1,
            "ref": str(ref or ""),
            "plan": str(plan or ""),
        }
    )


def add_topup_leads(client_id: str, leads: int, ref: str = "") -> bool:
    """Top-up pack credit (10-lead pack payment captured pe). Period-end EXPIRE."""
    cid = (client_id or "").strip()
    try:
        n = int(leads)
    except Exception:
        return False
    if not cid or n <= 0:
        return False
    return _append(
        {"client_id": cid, "ts": _now().isoformat(), "kind": "topup", "leads": n, "ref": str(ref or "")}
    )


def leads_used_this_period(client_id: str, period: str | None = None) -> int:
    try:
        return sum(int(r.get("leads") or 0) for r in _iter_period(client_id, period) if r.get("kind") == "qualified")
    except Exception:
        return 0


def topup_leads_this_period(client_id: str, period: str | None = None) -> int:
    try:
        return sum(int(r.get("leads") or 0) for r in _iter_period(client_id, period) if r.get("kind") == "topup")
    except Exception:
        return 0


def plan_quota(plan: str | None) -> int:
    """Voice plan (band-suffixed ya base key) -> leads/month (non-voice => 0)."""
    try:
        from app.marketing.voice_packages import plan_lead_quota

        return plan_lead_quota(plan)
    except Exception:
        return 0


def leads_remaining(client_id: str, plan: str | None = None) -> int:
    cid = (client_id or "").strip()
    if not cid:
        return 0
    try:
        cap = plan_quota(plan) + topup_leads_this_period(cid)
        return max(0, cap - leads_used_this_period(cid))
    except Exception:
        return 0


def has_lead_quota(client_id: str | None, plan: str | None = None) -> bool:
    """Campaign-call gate — FAIL-OPEN (no client / non-voice plan / error => True).
    Flat monthly plans (UNLIMITED_QUOTA=9999) => hamesha True.
    """
    try:
        from app.marketing.voice_packages import UNLIMITED_QUOTA
        cid = (client_id or "").strip()
        if not cid:
            return True
        q = plan_quota(plan)
        if q <= 0:
            return True  # voice plan hi nahi — meter apply nahi hota
        if q >= UNLIMITED_QUOTA:
            return True  # flat monthly plan — unlimited calls
        return leads_remaining(cid, plan) > 0
    except Exception:
        return True


def usage_summary(client_id: str, plan: str | None = None) -> dict:
    """Dashboard/API payload — kabhi raise nahi."""
    cid = (client_id or "").strip()
    used = leads_used_this_period(cid) if cid else 0
    topup = topup_leads_this_period(cid) if cid else 0
    quota = plan_quota(plan)
    return {
        "client_id": cid,
        "period": _period_key(),
        "plan": str(plan or ""),
        "quota_leads": quota,
        "topup_leads": topup,
        "used_leads": used,
        "remaining_leads": max(0, quota + topup - used),
        "unit": "qualified_lead",
        "pack_size": 10,
    }


__all__ = [
    "record_qualified_lead",
    "add_topup_leads",
    "leads_used_this_period",
    "topup_leads_this_period",
    "leads_remaining",
    "has_lead_quota",
    "plan_quota",
    "usage_summary",
]
