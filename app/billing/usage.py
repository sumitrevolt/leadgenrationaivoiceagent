"""Minute-usage metering + prepaid enforcement for the AI-voice reselling stack.

`BillingRecord` has no balance column — it's a ledger — so we meter USAGE: each
finished call writes a TELEPHONY line (quantity = whole minutes), and remaining =
plan minutes - minutes used this period. Only the Advanced tier includes calling
(500 min/mo); other plans have no metered minutes so enforcement is fail-OPEN here
(their calling is governed by compliance/plan gating elsewhere).

Everything is best-effort and NEVER raises — a billing hiccup must not break a call.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Included calling minutes per marketing plan (matches packages.py: Advanced = 500/mo).
PLAN_MINUTES: dict[str, int] = {"starter": 0, "growth": 0, "advanced": 500}

# Combo plans (Product 3) — marketing+voice bundle; voice minutes same as advanced tier
_COMBO_PLAN_MINUTES: dict[str, int] = {
    "combo_starter_monthly": 500, "combo_starter_annual": 500,
    "combo_growth_monthly": 1000, "combo_growth_annual": 1000,
    "combo_pro_monthly": 2000, "combo_pro_annual": 2000,
    "combo_pilot": 0,  # pilot = 50 calls cap, not minute-metered
}

# Telephony cost estimate (paise/min) for the ledger `cost` column (informational).
_COST_PAISE_PER_MIN = 65  # ~₹0.65/min streaming (CLAUDE.md cost ladder)


def plan_minutes(plan: str | None) -> int:
    key = (plan or "").strip().lower()
    # Check combo plans first (Product 3 bundles)
    if key in _COMBO_PLAN_MINUTES:
        return _COMBO_PLAN_MINUTES[key]
    return PLAN_MINUTES.get(key, 0)


def _client_plan(client_id: str) -> str:
    try:
        from app.marketing.clients_store import get_client

        rec = get_client(client_id) or {}
        return str(rec.get("plan") or "starter").strip().lower()
    except Exception:
        return "starter"


def resolve_client_id(client_name: str) -> str:
    """Best-effort client_name -> client_id via clients_store (empty if not found)."""
    try:
        from app.marketing.clients_store import list_clients

        name = (client_name or "").strip().lower()
        if not name:
            return ""
        for c in list_clients() or []:
            if str(c.get("business_name") or "").strip().lower() == name:
                return str(c.get("id") or "")
    except Exception:
        pass
    return ""


def record_call_usage(
    client_id: str, duration_seconds: int, campaign_id: str | None = None, client_name: str = ""
) -> bool:
    """Post-call hook: write a TELEPHONY ledger line for this call's minutes. Best-effort.

    J.4: Also fans out a `call.completed` event to customer-registered webhooks
    (H.1). INERT when CUSTOMER_WEBHOOKS unset; NEVER blocks the billing path.
    """
    try:
        cid = (client_id or "").strip() or resolve_client_id(client_name)
        if not cid:
            return False
        minutes = max(0, math.ceil(int(duration_seconds or 0) / 60.0))
        if minutes <= 0:
            return False
        from app.models.base import get_db_session
        from app.models.billing_record import BillingRecord, BillingRecordType

        now = datetime.utcnow()
        with get_db_session() as db:
            db.add(
                BillingRecord(
                    id=str(uuid.uuid4()),
                    client_id=cid,
                    campaign_id=(campaign_id or None),
                    record_type=BillingRecordType.TELEPHONY,
                    period_year=now.year,
                    period_month=now.month,
                    quantity=minutes,
                    cost=minutes * _COST_PAISE_PER_MIN,
                    currency="INR",
                    description=f"AI voice call usage: {minutes} min",
                    created_at=now,
                )
            )
            db.commit()

        # J.4 customer-webhook fan-out — fire-and-forget; never raises.
        try:
            import asyncio as _asyncio

            from app.platform import customer_webhooks as _cw

            payload = {
                "client_id": cid,
                "duration_seconds": int(duration_seconds or 0),
                "minutes_billed": minutes,
                "campaign_id": campaign_id,
                "cost_paise": minutes * _COST_PAISE_PER_MIN,
                "currency": "INR",
                "completed_at": now.isoformat(),
            }
            try:
                _loop = _asyncio.get_running_loop()
                _loop.create_task(_cw.emit(cid, "call.completed", payload))
            except RuntimeError:
                try:
                    _asyncio.run(_cw.emit(cid, "call.completed", payload))
                except Exception:
                    pass
        except Exception:
            pass

        return True
    except Exception as e:
        logger.debug("record_call_usage skipped: %s", e)
        return False


def minutes_used_this_period(client_id: str) -> int:
    """Sum of TELEPHONY ledger minutes for this client in the current month. 0 on any error.

    Respects a per-client *period-start watermark* (set by ``reset_usage_period`` on a
    paid renewal): only ledger lines created at/after the watermark count. The watermark
    lives in the latest Subscription row's ``extra_data['usage_period_start']`` (ISO-8601,
    no schema change). If absent/unreadable, the whole calendar month counts (legacy
    behaviour — fully backward compatible).
    """
    try:
        cid = (client_id or "").strip()
        if not cid:
            return 0
        from sqlalchemy import func

        from app.models.base import get_db_session
        from app.models.billing_record import BillingRecord, BillingRecordType

        now = datetime.utcnow()
        watermark = _usage_period_start(cid)
        with get_db_session() as db:
            q = db.query(func.coalesce(func.sum(BillingRecord.quantity), 0)).filter(
                BillingRecord.client_id == cid,
                BillingRecord.record_type == BillingRecordType.TELEPHONY,
                BillingRecord.period_year == now.year,
                BillingRecord.period_month == now.month,
            )
            # A mid-month paid renewal zeroes usage from the renewal instant onward.
            if watermark is not None and watermark.year == now.year and watermark.month == now.month:
                q = q.filter(BillingRecord.created_at >= watermark)
            total = q.scalar()
        return int(total or 0)
    except Exception as e:
        logger.debug("minutes_used_this_period error: %s", e)
        return 0


def topup_minutes(client_id: str) -> int:
    """Is period ke purchased top-up minutes (latest Subscription extra_data se).

    Semantics: top-ups PERIOD-END pe EXPIRE hote (research-standard) — implemented by
    ``reset_usage_period`` clearing the counter on every paid renewal. 0 on any error.
    """
    try:
        cid = (client_id or "").strip()
        if not cid:
            return 0
        from app.models.base import get_db_session

        with get_db_session() as db:
            sub = _latest_subscription(db, cid)
            if not sub:
                return 0
            return max(0, int((sub.extra_data or {}).get("topup_minutes") or 0))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("topup_minutes skipped: %s", e)
        return 0


def add_topup_minutes(client_id: str, minutes: int) -> bool:
    """Top-up pack payment hook — minutes credit karo (Subscription extra_data counter).

    Best-effort, kabhi raise nahi. Subscription row na ho to False (top-up sirf
    subscribed clients ke liye makes sense).
    """
    cid = (client_id or "").strip()
    add = max(0, int(minutes or 0))
    if not cid or add <= 0:
        return False
    try:
        from app.models.base import get_db_session

        with get_db_session() as db:
            sub = _latest_subscription(db, cid)
            if sub is None:
                return False
            meta = dict(sub.extra_data or {})
            meta["topup_minutes"] = max(0, int(meta.get("topup_minutes") or 0)) + add
            sub.extra_data = meta
            db.commit()
        logger.info("add_topup_minutes: client=%s +%s min", cid, add)
        return True
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("add_topup_minutes skipped: %s", e)
        return False


def minutes_remaining(client_id: str, plan: str | None = None) -> int:
    cap = plan_minutes(plan or _client_plan(client_id))
    if cap <= 0:
        return 0
    return max(0, cap + topup_minutes(client_id) - minutes_used_this_period(client_id))


def has_minutes(client_id: str, plan: str | None = None) -> bool:
    """True if the client can place another metered call.

    Fail-OPEN: a plan with no metered calling cap (cap<=0) is NOT blocked here. A
    metered (Advanced) client is blocked once usage reaches cap + purchased top-ups.
    """
    cap = plan_minutes(plan or _client_plan(client_id))
    if cap <= 0:
        return True
    return minutes_used_this_period(client_id) < cap + topup_minutes(client_id)


# --------------------------------------------------------------------------- #
# Auto-provisioning hooks (called by the payment webhooks on a paid pay/renew) #
#                                                                              #
# SEMANTICS (documented choice): the minute ledger only ever DEBITS (one line  #
# per finished call) and is calendar-month based. To "give a client their plan #
# minutes" on payment we do NOT credit the ledger; instead:                    #
#   (1) activate_plan() ensures clients_store has the right `plan` so the cap   #
#       (PLAN_MINUTES) used by minutes_remaining()/has_minutes() is correct,    #
#       and stashes the gateway subscription id on the latest Subscription row. #
#   (2) reset_usage_period() drops a *watermark* (ISO ts) into that row's       #
#       extra_data['usage_period_start']; minutes_used_this_period() then only  #
#       counts ledger lines at/after the watermark *within the same month*.     #
# This is the simplest correct approach: a mid-period renewal zeroes usage      #
# WITHOUT deleting history or inventing credit lines, and needs no new columns. #
# Everything is best-effort and NEVER raises.                                   #
# --------------------------------------------------------------------------- #
def _latest_subscription(db, client_id: str):
    """Most-recent Subscription row for a client (any status), or None. Caller owns `db`."""
    from app.models.payment import Subscription

    return (
        db.query(Subscription)
        .filter(Subscription.client_id == client_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )


def _usage_period_start(client_id: str):
    """Read the renewal watermark from the latest Subscription's extra_data. None if absent."""
    try:
        cid = (client_id or "").strip()
        if not cid:
            return None
        from app.models.base import get_db_session

        with get_db_session() as db:
            sub = _latest_subscription(db, cid)
            if not sub:
                return None
            raw = (sub.extra_data or {}).get("usage_period_start")
            if not raw:
                return None
            return datetime.fromisoformat(str(raw).replace("Z", ""))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("_usage_period_start skipped: %s", e)
        return None


def activate_plan(
    client_id: str,
    plan: str,
    subscription_id: str | None = None,
    period_end: datetime | None = None,
) -> bool:
    """Provision a client's plan after a successful subscription pay/renew. Best-effort.

    - Sets the client's `plan` in clients_store so the minute cap is correct.
    - Stashes the gateway subscription id + period_end on the latest Subscription row's
      extra_data (no schema change) for traceability.
    Returns True if the plan was applied to clients_store, else False (never raises).
    """
    cid = (client_id or "").strip()
    plan_k = (plan or "").strip().lower()
    if not cid or not plan_k:
        return False

    applied = False
    try:
        from app.marketing.clients_store import get_client, update_client

        if get_client(cid):
            update_client(cid, plan=plan_k)
            applied = True
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("activate_plan clients_store skipped: %s", e)

    # Best-effort: annotate the latest Subscription row (traceability only).
    try:
        from app.models.base import get_db_session

        with get_db_session() as db:
            sub = _latest_subscription(db, cid)
            if sub is not None:
                meta = dict(sub.extra_data or {})
                meta["provisioned_plan"] = plan_k
                if subscription_id:
                    meta["gateway_subscription_id"] = subscription_id
                if period_end:
                    meta["provisioned_period_end"] = period_end.isoformat()
                sub.extra_data = meta
                db.commit()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("activate_plan subscription annotate skipped: %s", e)

    logger.info("activate_plan: client=%s plan=%s (applied=%s)", cid, plan_k, applied)
    return applied


def reset_usage_period(client_id: str, at: datetime | None = None) -> bool:
    """Zero metered usage from `at` (default now) onward by dropping a watermark.

    Stored in the latest Subscription row's extra_data['usage_period_start'] (ISO ts).
    minutes_used_this_period() then ignores ledger lines created before the watermark
    within the current month. Best-effort; returns True if the watermark was written.
    """
    cid = (client_id or "").strip()
    if not cid:
        return False
    when = at or datetime.utcnow()
    try:
        from app.models.base import get_db_session

        with get_db_session() as db:
            sub = _latest_subscription(db, cid)
            if sub is None:
                return False
            meta = dict(sub.extra_data or {})
            meta["usage_period_start"] = when.isoformat()
            meta["topup_minutes"] = 0  # top-ups period-end pe EXPIRE (renewal = naya period)
            sub.extra_data = meta
            db.commit()
        logger.info("reset_usage_period: client=%s watermark=%s", cid, when.isoformat())
        return True
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("reset_usage_period skipped: %s", e)
        return False


__all__ = [
    "PLAN_MINUTES",
    "plan_minutes",
    "resolve_client_id",
    "record_call_usage",
    "minutes_used_this_period",
    "minutes_remaining",
    "has_minutes",
    "topup_minutes",
    "add_topup_minutes",
    "activate_plan",
    "reset_usage_period",
]
