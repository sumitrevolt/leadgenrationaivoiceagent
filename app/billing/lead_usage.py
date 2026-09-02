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
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_STORE = Path(os.getenv("DATA_DIR", "data")) / "lead_usage.jsonl"
_LOCK = threading.Lock()
_log = logging.getLogger("billing.lead_usage")


def _record_meter_failure(rec: dict) -> None:
    """Metering write fail-open hai (call kabhi block na ho) — par failure SILENT
    na rahe (revenue-leak risk). ERROR log (Loki/alertable) + best-effort DURABLE
    record main redis (REDIS_URL = noeviction, audit P0-1) ki list
    `billing:meter_failures` me → ops manual replay/reconcile kar sake. Kabhi raise
    nahi karta. Replay: `redis-cli lrange billing:meter_failures 0 -1`."""
    try:
        _log.error(
            "BILLING meter write FAILED (revenue-leak risk) — manual replay needed: %s",
            json.dumps(rec, ensure_ascii=False)[:300],
        )
    except Exception:
        pass
    try:
        import redis as _redis

        url = os.environ.get("REDIS_URL")  # main (noeviction) — NOT cache redis (evictable)
        if url:
            r = _redis.from_url(url, socket_timeout=2)
            r.lpush("billing:meter_failures", json.dumps(rec, ensure_ascii=False))
            r.ltrim("billing:meter_failures", 0, 4999)  # bounded
    except Exception:
        pass


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


def _ref_already_recorded(client_id: str, ref: str) -> bool:
    """Same call/ref qualified twice → skip (idempotent meter + webhook)."""
    rk = (ref or "").strip()
    if not rk:
        return False
    try:
        for rec in _iter_period(client_id):
            if rec.get("kind") == "qualified" and str(rec.get("ref") or "") == rk:
                return True
    except Exception:
        return False
    return False


def record_qualified_lead(client_id: str, ref: str = "", plan: str | None = None) -> bool:
    """Ek AI-qualified lead consume karo (call_qualifier 'interested' verdict pe).

    ref = call sid / qualification id (dispute-evidence link). Best-effort.
    Idempotent on ref within the billing period (duplicate qualify → no-op).

    I.2: After the meter row is written, fire-and-forget a `lead.qualified`
    event to the customer's subscribed webhooks (H.1). INERT when
    CUSTOMER_WEBHOOKS unset or the client has no matching subscription.
    """
    cid = (client_id or "").strip()
    if not cid:
        return False
    if _ref_already_recorded(cid, ref):
        return True
    rec = {
        "client_id": cid,
        "ts": _now().isoformat(),
        "kind": "qualified",
        "leads": 1,
        "ref": str(ref or ""),
        "plan": str(plan or ""),
    }
    ok = _append(rec)
    if not ok:
        _record_meter_failure(rec)  # silent revenue-leak na ho — log + durable replay-list

    # Customer webhook fan-out (best-effort, never blocks billing path).
    try:
        import asyncio as _asyncio

        from app.platform import customer_webhooks as _cw

        payload = {
            "client_id": cid,
            "lead_ref": str(ref or ""),
            "plan": str(plan or ""),
            "qualified_at": rec["ts"],
        }
        try:
            _loop = _asyncio.get_running_loop()
            _loop.create_task(_cw.emit(cid, "lead.qualified", payload))
        except RuntimeError:
            try:
                _asyncio.run(_cw.emit(cid, "lead.qualified", payload))
            except Exception:
                pass
    except Exception:
        pass

    # Obsidian second-brain — append qualified event to lead timeline (INERT if OBSIDIAN_SYNC unset).
    try:
        from app.platform import obsidian_sync as _obs

        phone_slug = str(ref or cid).replace("+", "").replace(" ", "")[:20]
        _obs.append_note(
            "Leads", phone_slug, f"qualified — plan={plan or '?'} ref={ref or '?'}", tags=["lead"]
        )
    except Exception:
        pass

    return ok


def add_topup_leads(client_id: str, leads: int, ref: str = "") -> bool:
    """Top-up pack credit (10-lead pack payment captured pe). Period-end EXPIRE."""
    cid = (client_id or "").strip()
    try:
        n = int(leads)
    except Exception:
        return False
    if not cid or n <= 0:
        return False
    rec = {
        "client_id": cid,
        "ts": _now().isoformat(),
        "kind": "topup",
        "leads": n,
        "ref": str(ref or ""),
    }
    ok = _append(rec)
    if not ok:
        # topup failure = customer ne PAY kiya par credit nahi mila — aur bhi critical
        _record_meter_failure(rec)
    return ok


def leads_used_this_period(client_id: str, period: str | None = None) -> int:
    try:
        return sum(
            int(r.get("leads") or 0)
            for r in _iter_period(client_id, period)
            if r.get("kind") == "qualified"
        )
    except Exception:
        return 0


def topup_leads_this_period(client_id: str, period: str | None = None) -> int:
    try:
        return sum(
            int(r.get("leads") or 0)
            for r in _iter_period(client_id, period)
            if r.get("kind") == "topup"
        )
    except Exception:
        return 0


def plan_quota(plan: str | None) -> int:
    """Voice ya combo plan -> leads/month (UNLIMITED_QUOTA for flat plans; non-voice => 0)."""
    try:
        from app.marketing.combo_packages import combo_plan_quota, is_combo_plan

        if is_combo_plan(plan):
            return combo_plan_quota(plan)
    except Exception:
        pass
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
