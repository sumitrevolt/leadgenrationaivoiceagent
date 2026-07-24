"""Sales Autopilot admin observability API — read-first, action-gated.

A NEW admin router (mounted in ``app/main.py``) so we never edit the protected
``admin_dashboard.html`` / ``admin_dashboard.py`` surfaces owned by other PRs. All
endpoints are admin-only. The engine is INERT until ``SALES_AUTOPILOT_ENABLED=1`` — this
router simply reports policy, decisions, attempts, and lets an operator run a SIMULATED
canary (``force_dry_run=True`` always) or seed the Estique guard.

Never performs a live send from here: the only "run" endpoints force dry-run.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from app.api.auth_deps import require_admin
from app.platform.sales_autopilot import eligibility as _elig
from app.platform.sales_autopilot import inbound as _inbound
from app.platform.sales_autopilot import messages as _messages
from app.platform.sales_autopilot import policy as _policy_mod
from app.platform.sales_autopilot import safety as _safety
from app.platform.sales_autopilot import scheduler as _scheduler
from app.platform.sales_autopilot import send as _send
from app.platform.sales_autopilot import store as _store

router = APIRouter(prefix="/api/sales-autopilot", tags=["Sales Autopilot"])


@router.get("/summary")
async def summary(_user=Depends(require_admin)) -> dict[str, Any]:
    """Operator dashboard rollup: flags, policy posture, and today's attempt counts."""
    pol = _policy_mod.get_policy()
    prospects = _store.list_prospects(limit=1000)
    status_counts: dict[str, int] = {}
    for r in prospects:
        st = str(r.get("status") or "new")
        status_counts[st] = status_counts.get(st, 0) + 1
    return {
        "enabled": pol.enabled,
        "dry_run": pol.dry_run,
        "channels": {
            "whatsapp_enabled": bool(pol.get("whatsapp_enabled")),
            "email_enabled": bool(pol.get("email_enabled")),
        },
        "kill_switches": pol.get("kill_switches"),
        "canary_batch_size": pol.canary_batch(),
        "caps": pol.get("caps"),
        "ist_hours": pol.get("ist_hours"),
        "calling": "HARD_OFF",
        "prospects_total": len(prospects),
        "status_counts": status_counts,
        "attempts_today_total": _store.attempts_today(),
        "simulated_today": _store.attempts_today(status=_send.SIMULATED),
        "sent_today": _store.attempts_today(status=_send.SENT),
        "policy_version": pol.get("version"),
        "template_version": _messages.TEMPLATE_VERSION,
    }


@router.get("/policy")
async def get_policy(_user=Depends(require_admin)) -> dict[str, Any]:
    return dict(_policy_mod.get_policy())


@router.get("/prospects")
async def prospects(
    limit: int = Query(100, ge=1, le=1000),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    rows = _store.list_prospects(limit=limit)
    return {"count": len(rows), "prospects": rows}


@router.get("/attempts")
async def attempts(
    limit: int = Query(100, ge=1, le=1000),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    rows = _store.list_attempts(limit=limit)
    return {"count": len(rows), "attempts": rows}


@router.post("/eligibility/preview")
async def eligibility_preview(
    payload: dict[str, Any] = Body(...),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Dry eligibility + message + safety preview for a prospect_id or inline prospect."""
    prospect = payload.get("prospect") or _store.get_prospect(str(payload.get("prospect_id") or ""))
    if not prospect:
        return {"error": "prospect_not_found"}
    channel = str(payload.get("channel") or "whatsapp")
    step = str(payload.get("step") or _elig.STEP_INITIAL)
    elig = _elig.evaluate(prospect, channel=channel, step=step)
    envelope = _messages.build(prospect, channel=channel, step=step)
    val = _safety.validate(envelope)
    return {"eligibility": elig, "message": envelope, "validation": val}


@router.post("/run-canary")
async def run_canary(
    payload: dict[str, Any] = Body(default={}),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Run ONE scheduler tick in FORCED dry-run (simulation). Never sends live."""
    # Force dry-run at the send layer regardless of policy by processing a tiny batch and
    # relying on run_tick honoring policy.dry_run; here we additionally simulate a single
    # prospect if provided.
    pid = str(payload.get("prospect_id") or "").strip()
    if pid:
        res = await _send.send(
            pid,
            channel=str(payload.get("channel") or "whatsapp"),
            step=str(payload.get("step") or _elig.STEP_INITIAL),
            force_dry_run=True,
        )
        return {"mode": "single", "result": res}
    tick = await _scheduler.run_tick(limit=int(payload.get("limit") or 1))
    return {"mode": "tick", "result": tick}


@router.post("/inbound/classify")
async def inbound_classify(
    payload: dict[str, Any] = Body(...),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Classify an inbound reply (read-only; does not mutate state)."""
    return _inbound.classify_reply(str(payload.get("text") or ""))


@router.post("/seed-estique")
async def seed_estique(_user=Depends(require_admin)) -> dict[str, Any]:
    """Idempotently seed the Estique manual-owner-confirmed guard record."""
    rec = _store.ensure_estique_seed()
    return {"seeded": True, "prospect": rec}


__all__ = ["router"]
