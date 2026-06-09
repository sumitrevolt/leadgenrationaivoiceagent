"""Sales pipeline automation — deal stages + auto next-best-action.

Interested lead → DEAL. Har stage ka ek automated next-action hota:
  new/contacted → intro (cadence)         interested → demo-link + booking bhejo
  demo_sent     → proposal bhejo          proposal_sent → payment-link + follow-up
  won           → auto-onboard            lost → nurture

Stages signals se aage badhte (reply→interested, demo→demo_sent, paid→won).
Self-serve CLOSE = /pricing→signup→pay (NO human). High-touch demo = human.
GATED `SALES_ENGINE=1`. Store data/deals.jsonl. Reuse proposal+sales_assistant+booking.
Import-safe, kabhi raise nahi karta.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DEALS = os.path.join("data", "deals.jsonl")
_ACTIONS = os.path.join("data", "deal_actions.jsonl")
STAGES = ["new", "contacted", "interested", "demo_sent", "proposal_sent", "negotiating", "won", "lost"]
BASE = "https://leadsgenai.in"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled() -> bool:
    return os.environ.get("SALES_ENGINE", "0").strip().lower() in ("1", "true", "yes")


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


def _write_all(path: str, rows: list[dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[sales] write failed: {e}")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def upsert_deal(lead: dict[str, Any], stage: str = "interested") -> dict[str, Any]:
    """Lead ko deal banao/update (dedupe by phone/email). Kabhi raise nahi."""
    phone = "".join(c for c in str(lead.get("phone") or "") if c.isdigit())[-10:]
    email = (lead.get("email") or "").strip().lower()
    rows = _read(_DEALS)
    for r in rows:
        if (phone and r.get("phone") == phone) or (email and r.get("email") == email):
            if stage and stage in STAGES:
                r["stage"] = stage
                r["updated_at"] = _now()
            _write_all(_DEALS, rows)
            return r
    rec = {
        "id": uuid.uuid4().hex[:12],
        "business_name": lead.get("business_name") or lead.get("name") or "Lead",
        "phone": phone, "email": email,
        "niche": lead.get("niche") or "general", "city": lead.get("city") or "",
        "stage": stage if stage in STAGES else "interested",
        "created_at": _now(), "updated_at": _now(),
    }
    rows.append(rec)
    _write_all(_DEALS, rows)
    return rec


def set_stage(deal_id: str, stage: str) -> bool:
    if stage not in STAGES:
        return False
    rows = _read(_DEALS)
    hit = False
    for r in rows:
        if r.get("id") == deal_id:
            r["stage"] = stage
            r["updated_at"] = _now()
            hit = True
    if hit:
        _write_all(_DEALS, rows)
    return hit


async def next_action(deal: dict[str, Any]) -> dict[str, Any]:
    """Deal ke current stage ka automated next-action (draft/link). Kabhi raise nahi."""
    stage = deal.get("stage", "interested")
    biz = deal.get("business_name", "Lead")
    niche = deal.get("niche", "general")
    city = deal.get("city", "")
    try:
        if stage in ("new", "contacted"):
            return {"action": "send_intro", "channel": "email/cadence",
                    "content": f"{biz} ko intro + free-audit ({BASE}/audit)"}
        if stage == "interested":
            return {"action": "send_demo_booking", "channel": "whatsapp/email",
                    "content": f"Namaste {biz}! 2-min live demo: {BASE}/app/test-call — ya apna pasand ka time batao, booking: {BASE}/audit",
                    "demo_link": f"{BASE}/app/test-call"}
        if stage == "demo_sent":
            from app.marketing import proposal

            p = await proposal.generate_proposal(biz, niche, city)
            return {"action": "send_proposal", "channel": "email/whatsapp",
                    "content": p.get("proposal"), "payment_link": p.get("payment_link")}
        if stage in ("proposal_sent", "negotiating"):
            return {"action": "send_payment_followup", "channel": "whatsapp/email",
                    "content": f"{biz} ji, ready ho? Yahan se 2-min me account + 10 leads FREE: {BASE}/pricing",
                    "payment_link": f"{BASE}/pricing"}
        if stage == "won":
            return {"action": "onboard", "channel": "auto",
                    "content": f"{biz} won — auto-onboard (KB + first content)."}
        return {"action": "nurture", "channel": "email",
                "content": f"{biz} ko monthly value-content me daalo (re-engage)."}
    except Exception as e:  # noqa: BLE001
        return {"action": "skip", "error": str(e)[:100]}


async def run_pipeline(limit: int = 100) -> dict[str, Any]:
    """Active deals ke liye next-actions generate karo (drafts/links). GATED SALES_ENGINE."""
    if not _enabled():
        return {"ok": False, "reason": "SALES_ENGINE off"}
    rows = _read(_DEALS)
    produced = 0
    for d in rows[:limit]:
        if d.get("stage") in ("won", "lost"):
            continue
        act = await next_action(d)
        _append(_ACTIONS, {"deal_id": d["id"], "business_name": d["business_name"],
                           "stage": d.get("stage"), **act, "at": _now()})
        produced += 1
    return {"ok": True, "deals_processed": produced, "stats": stats()}


def list_deals(stage: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    rows = _read(_DEALS)
    if stage:
        rows = [r for r in rows if r.get("stage") == stage]
    return rows[-limit:]


def list_actions(limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_read(_ACTIONS)))[:limit]


def stats() -> dict[str, Any]:
    rows = _read(_DEALS)
    by_stage = {s: sum(1 for r in rows if r.get("stage") == s) for s in STAGES}
    return {"total": len(rows), "by_stage": by_stage, "won": by_stage.get("won", 0),
            "open": sum(1 for r in rows if r.get("stage") not in ("won", "lost")),
            "engine_on": _enabled()}


__all__ = ["STAGES", "upsert_deal", "set_stage", "next_action", "run_pipeline",
           "list_deals", "list_actions", "stats"]
