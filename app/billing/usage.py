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

# Telephony cost estimate (paise/min) for the ledger `cost` column (informational).
_COST_PAISE_PER_MIN = 65  # ~₹0.65/min streaming (CLAUDE.md cost ladder)


def plan_minutes(plan: str | None) -> int:
    return PLAN_MINUTES.get((plan or "").strip().lower(), 0)


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
    """Post-call hook: write a TELEPHONY ledger line for this call's minutes. Best-effort."""
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
        return True
    except Exception as e:
        logger.debug("record_call_usage skipped: %s", e)
        return False


def minutes_used_this_period(client_id: str) -> int:
    """Sum of TELEPHONY ledger minutes for this client in the current month. 0 on any error."""
    try:
        cid = (client_id or "").strip()
        if not cid:
            return 0
        from sqlalchemy import func

        from app.models.base import get_db_session
        from app.models.billing_record import BillingRecord, BillingRecordType

        now = datetime.utcnow()
        with get_db_session() as db:
            total = (
                db.query(func.coalesce(func.sum(BillingRecord.quantity), 0))
                .filter(
                    BillingRecord.client_id == cid,
                    BillingRecord.record_type == BillingRecordType.TELEPHONY,
                    BillingRecord.period_year == now.year,
                    BillingRecord.period_month == now.month,
                )
                .scalar()
            )
        return int(total or 0)
    except Exception as e:
        logger.debug("minutes_used_this_period error: %s", e)
        return 0


def minutes_remaining(client_id: str, plan: str | None = None) -> int:
    cap = plan_minutes(plan or _client_plan(client_id))
    if cap <= 0:
        return 0
    return max(0, cap - minutes_used_this_period(client_id))


def has_minutes(client_id: str, plan: str | None = None) -> bool:
    """True if the client can place another metered call.

    Fail-OPEN: a plan with no metered calling cap (cap<=0) is NOT blocked here. A
    metered (Advanced) client is blocked once usage reaches the cap.
    """
    cap = plan_minutes(plan or _client_plan(client_id))
    if cap <= 0:
        return True
    return minutes_used_this_period(client_id) < cap


__all__ = [
    "PLAN_MINUTES",
    "plan_minutes",
    "resolve_client_id",
    "record_call_usage",
    "minutes_used_this_period",
    "minutes_remaining",
    "has_minutes",
]
