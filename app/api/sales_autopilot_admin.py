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


def _scheduler_runtime() -> dict[str, Any]:
    """Runtime-wiring truth: is the canary tick actually registered in beat/staff, at what
    cadence, is it no-catch-up excluded, and what did the last tick do. Read-only; never
    raises (missing registration just reports ``scheduler_registered: False``)."""
    info: dict[str, Any] = {
        "scheduler_registered": False,
        "staff_job": "sales_autopilot",
        "beat_task": "staff-sales-autopilot-hourly",
        "cadence": None,
        "no_catch_up": False,
    }
    try:
        from app.platform.scheduler_config import JOB_META, RUN_DUE_EXCLUDE
        from app.tasks.staff_jobs import STAFF_JOBS

        info["scheduler_registered"] = ("sales_autopilot" in STAFF_JOBS) and (
            "sales_autopilot" in JOB_META
        )
        info["cadence"] = (JOB_META.get("sales_autopilot") or {}).get("cadence")
        info["no_catch_up"] = "sales_autopilot" in RUN_DUE_EXCLUDE
    except Exception:  # pragma: no cover - defensive
        pass
    info["last_tick"] = _store.get_last_tick()
    return info


@router.get("/summary")
async def summary(_user=Depends(require_admin)) -> dict[str, Any]:
    """Operator dashboard rollup: flags, policy posture, and today's attempt counts."""
    pol = _policy_mod.get_policy()
    prospects = _store.list_prospects(limit=1000)
    status_counts: dict[str, int] = {}
    unpaid = 0
    for r in prospects:
        st = str(r.get("status") or "new")
        status_counts[st] = status_counts.get(st, 0) + 1
        if st == getattr(_store, "STATUS_AWAITING_PAYMENT", "awaiting_payment"):
            unpaid += 1
    from app.platform.sales_autopilot import refill as _refill

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
        "scheduler": _scheduler_runtime(),
        "prospects_total": len(prospects),
        "status_counts": status_counts,
        "awaiting_payment_count": unpaid,
        "refill_enabled": _refill.refill_enabled(),
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
    from app.platform.sales_autopilot import pay_truth as _pay

    rows = [_pay.enrich_prospect(r) for r in _store.list_prospects(limit=limit)]
    return {"count": len(rows), "prospects": rows}


@router.post("/refill")
async def refill_now(
    payload: dict[str, Any] = Body(default={}),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Manual prospector→autopilot refill. force=1 bypasses SALES_AUTOPILOT_REFILL flag."""
    from app.platform.sales_autopilot import refill as _refill

    force = bool(payload.get("force"))
    limit = payload.get("limit")
    return _refill.refill_from_prospector(
        limit=int(limit) if limit is not None else None,
        force=force,
    )


@router.post("/pay-truth/reconcile")
async def pay_truth_reconcile(
    payload: dict[str, Any] = Body(default={}),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Reconcile converted vs ledger; optional chase. Never marks paid without proof."""
    from app.platform.sales_autopilot import pay_truth as _pay

    chase = payload.get("chase", True)
    return _pay.reconcile_pay_truth(chase=bool(chase))


@router.get("/pay-truth/unpaid")
async def pay_truth_unpaid(
    limit: int = Query(50, ge=1, le=200),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform.sales_autopilot import pay_truth as _pay

    cards = _pay.unpaid_chase_cards(limit=limit)
    return {"count": len(cards), "cards": cards}


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
    """Run ONE scheduler tick in FORCED dry-run (simulation). Never sends live.

    Both branches force dry-run at the SEND layer. The tick branch previously
    passed nothing and relied on ``policy.dry_run`` being set, which meant this
    docstring's promise was only as true as the stored config — a live-configured
    policy turned the canary into a real sender.
    """
    pid = str(payload.get("prospect_id") or "").strip()
    if pid:
        res = await _send.send(
            pid,
            channel=str(payload.get("channel") or "whatsapp"),
            step=str(payload.get("step") or _elig.STEP_INITIAL),
            force_dry_run=True,
        )
        return {"mode": "single", "result": res}
    tick = await _scheduler.run_tick(limit=int(payload.get("limit") or 1), force_dry_run=True)
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


@router.post("/prospects")
async def add_prospect(
    payload: dict[str, Any] = Body(...),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Operator: feed sales_autopilot with a consented prospect (GTM queue fill).

    Requires email and/or phone + explicit ``consent_basis`` (DPDP fail-closed).
    Does NOT mark ``manual_owner_confirmed`` (that blocks initial outreach).
    Never live-sends — next scheduler tick evaluates eligibility.
    """
    import uuid

    email = str(payload.get("email") or "").strip().lower()
    phone = str(payload.get("phone") or "").strip()
    if not email and not phone:
        return {"ok": False, "error": "email_or_phone_required"}
    consent = str(payload.get("consent_basis") or "").strip()
    if not consent:
        return {"ok": False, "error": "consent_basis_required"}
    pid = str(payload.get("id") or "").strip() or str(uuid.uuid4())
    name = str(payload.get("name") or payload.get("business_name") or "").strip()[:200]
    if not name:
        return {"ok": False, "error": "name_required"}
    rec = _store.upsert_prospect(
        {
            "id": pid,
            "name": name,
            "email": email,
            "phone": phone,
            "city": str(payload.get("city") or "")[:100],
            "niche": str(payload.get("niche") or "")[:60],
            "source": str(payload.get("source") or "admin_manual")[:80],
            "consent_basis": consent[:120],
            "status": _store.STATUS_NEW,
            "manual_owner_confirmed": False,
        }
    )
    if rec.get("error"):
        return {"ok": False, "error": rec.get("error")}
    return {"ok": True, "prospect": rec}


__all__ = ["router"]
