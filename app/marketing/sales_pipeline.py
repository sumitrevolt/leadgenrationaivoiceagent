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
STAGES = [
    "new",
    "contacted",
    "interested",
    "demo_sent",
    "proposal_sent",
    "negotiating",
    "won",
    "lost",
]

# Forward-only progress rank (data-integrity guard). The early-funnel stages
# new/contacted/interested are interchangeable ENTRY-LEVEL (same rank 0) — a lead
# can be "interested" before it is operationally "contacted", so moving between
# them is NOT a downgrade. Only a clearly-advanced deal (demo_sent and beyond,
# esp. negotiating/won) being pulled back to an earlier rank is a silent
# overwrite (e.g. a re-classified reply yanking a WON deal to interested).
# `lost` is a terminal sink that is ALWAYS allowed (marking a deal lost/churned
# is an intentional decision, never a silent reclassification artifact).
_STAGE_RANK = {
    "new": 0,
    "contacted": 0,
    "interested": 0,
    "demo_sent": 1,
    "proposal_sent": 2,
    "negotiating": 3,
    "won": 4,
    "lost": 0,
}
BASE = "https://leadsgenai.in"


def _is_downgrade(current: str | None, new_stage: str) -> bool:
    """True if new_stage would pull an existing deal BACKWARD (silent overwrite).

    Never raises. `lost` and unknown/missing stages are treated as non-downgrade
    so the guard only ever blocks an unambiguous backward move.
    """
    try:
        if not current or current == new_stage:
            return False
        if new_stage == "lost":  # terminal sink — always allowed
            return False
        return _STAGE_RANK.get(new_stage, 0) < _STAGE_RANK.get(current, 0)
    except Exception:
        return False


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
    # Cross-process lock + atomic replace — web workers (API deal/stage) aur
    # celery content-job (run_pipeline) ek saath rewrite kar sakte the.
    try:
        from app.utils.file_lock import locked_rewrite

        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        if not locked_rewrite(path, content):
            logger.warning(f"[sales] locked write failed: {path}")
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
            # Forward-only: never let a re-upsert (e.g. a re-classified "interested"
            # reply) silently pull an already-advanced deal (won/negotiating) back.
            if stage and stage in STAGES and not _is_downgrade(r.get("stage"), stage):
                r["stage"] = stage
                r["updated_at"] = _now()
            _write_all(_DEALS, rows)
            return r
    rec = {
        "id": uuid.uuid4().hex[:12],
        "business_name": lead.get("business_name") or lead.get("name") or "Lead",
        "phone": phone,
        "email": email,
        "niche": lead.get("niche") or "general",
        "city": lead.get("city") or "",
        "stage": stage if stage in STAGES else "interested",
        "created_at": _now(),
        "updated_at": _now(),
    }
    # Client-owned deal ko client_id se stamp karo (isolation): run_pipeline in
    # deals ko LeadGen ki apni sales cadence/actions se skip karta hai. CONDITIONAL
    # rakha hai taaki platform (no-client) deal ka record byte-identical rahe.
    _cid = str(lead.get("client_id") or "").strip()
    if _cid:
        rec["client_id"] = _cid
    rows.append(rec)
    _write_all(_DEALS, rows)
    return rec


def set_stage(deal_id: str, stage: str, allow_reverse: bool = False) -> bool:
    """Set a deal's stage. Forward-only by default — a backward move (e.g. a
    re-classified reply pulling a won/negotiating deal back to interested) is
    BLOCKED as a silent overwrite: the current stage is kept and the no-op still
    returns True (deal found). Pass allow_reverse=True for an explicit/admin
    downgrade. Invalid stage → False; deal not found → False. Never raises.
    """
    if stage not in STAGES:
        return False
    rows = _read(_DEALS)
    hit = False
    changed = False
    for r in rows:
        if r.get("id") == deal_id:
            hit = True
            current = r.get("stage")
            if not allow_reverse and _is_downgrade(current, stage):
                logger.warning(
                    f"[sales] blocked backward stage move deal={deal_id} "
                    f"{current} -> {stage} (keeping {current}; pass allow_reverse=True to force)"
                )
                continue  # keep current stage — no silent downgrade
            r["stage"] = stage
            r["updated_at"] = _now()
            changed = True
    if changed:
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
            return {
                "action": "send_intro",
                "channel": "email/cadence",
                "content": f"{biz} ko intro + free-audit ({BASE}/audit)",
            }
        if stage == "interested":
            return {
                "action": "send_demo_booking",
                "channel": "whatsapp/email",
                "content": f"Namaste {biz}! 2-min live demo: {BASE}/app/test-call — ya apna pasand ka time batao, booking: {BASE}/audit",
                "demo_link": f"{BASE}/app/test-call",
            }
        if stage == "demo_sent":
            from app.marketing import proposal

            p = await proposal.generate_proposal(biz, niche, city)
            return {
                "action": "send_proposal",
                "channel": "email/whatsapp",
                "content": p.get("proposal"),
                "payment_link": p.get("payment_link"),
            }
        if stage in ("proposal_sent", "negotiating"):
            return {
                "action": "send_payment_followup",
                "channel": "whatsapp/email",
                "content": f"{biz} ji, ready ho? Yahan se 2-min me account + 10 leads FREE: {BASE}/pricing",
                "payment_link": f"{BASE}/pricing",
            }
        if stage == "won":
            return {
                "action": "onboard",
                "channel": "auto",
                "content": f"{biz} won — auto-onboard (KB + first content).",
            }
        return {
            "action": "nurture",
            "channel": "email",
            "content": f"{biz} ko monthly value-content me daalo (re-engage).",
        }
    except Exception as e:  # noqa: BLE001
        return {"action": "skip", "error": str(e)[:100]}


async def run_pipeline(limit: int = 100) -> dict[str, Any]:
    """Active deals ke liye next-actions generate + safe auto-execute karo. GATED SALES_ENGINE."""
    if not _enabled():
        return {"ok": False, "reason": "SALES_ENGINE off"}
    rows = _read(_DEALS)
    produced = 0
    executed = 0
    for d in rows[:limit]:
        if d.get("stage") in ("won", "lost"):
            continue
        # Isolation: client-owned deal (client_id stamped) LeadGen ke apne
        # sales-funnel ka nahi hai — usko LeadGen cadence enroll / sales actions
        # se SKIP karo (warna client ka end-customer LeadGen ka "plan lo" draft paata).
        if str(d.get("client_id") or "").strip():
            continue
        act = await next_action(d)
        _append(
            _ACTIONS,
            {
                "deal_id": d["id"],
                "business_name": d["business_name"],
                "stage": d.get("stage"),
                **act,
                "at": _now(),
            },
        )
        produced += 1

        # Auto-execute safe actions (draft/enroll — auto-send kabhi nahi):
        action_type = act.get("action", "")
        try:
            if action_type == "send_intro" and d.get("stage") in ("new", "contacted"):
                # New deal → cadence enroll (email intro sequence)
                from app.marketing import cadence as _cad

                _cad.enroll(
                    {
                        "phone": d.get("phone") or "",
                        "email": d.get("email") or "",
                        "business_name": d.get("business_name") or "",
                        "niche": d.get("niche") or "",
                        "city": d.get("city") or "",
                    }
                )
                if d.get("stage") == "new":
                    set_stage(d["id"], "contacted")
                executed += 1
            elif action_type == "onboard":
                # Won deal → auto-onboard KB seed (gated AUTO_ONBOARD=1)
                cid = d.get("client_id") or ""
                if cid:
                    try:
                        import asyncio as _aio_sp

                        from app.marketing.onboarding import onboard_client

                        _aio_sp.create_task(onboard_client(cid))
                        executed += 1
                    except Exception:
                        pass
        except Exception as _exec_e:
            logger.debug(f"[pipeline] action execute skip ({action_type}): {_exec_e}")

    return {"ok": True, "deals_processed": produced, "actions_executed": executed, "stats": stats()}


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
    return {
        "total": len(rows),
        "by_stage": by_stage,
        "won": by_stage.get("won", 0),
        "open": sum(1 for r in rows if r.get("stage") not in ("won", "lost")),
        "engine_on": _enabled(),
    }


__all__ = [
    "STAGES",
    "upsert_deal",
    "set_stage",
    "next_action",
    "run_pipeline",
    "list_deals",
    "list_actions",
    "stats",
]
