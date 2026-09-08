"""Minute-usage metering + prepaid enforcement for the AI-voice reselling stack.

`BillingRecord` has no balance column — it's a ledger — so we meter USAGE: each
finished call writes a TELEPHONY line (quantity = whole minutes), and remaining =
plan minutes - minutes used this period. Only the Advanced tier includes calling
(500 min/mo); other plans have no metered minutes so enforcement is fail-OPEN here
(their calling is governed by compliance/plan gating elsewhere).

Everything is best-effort and NEVER raises — a billing hiccup must not break a call.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime, timedelta

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _record_meter_failure(rec: dict) -> None:
    """Minute-meter write fail-open hai (call kabhi block na ho) — par failure SILENT
    na rahe (revenue-leak risk: marketing-Advanced prepaid-minutes ka billable path).
    Mirror of lead_usage._record_meter_failure: ERROR log (Loki/alertable) + best-effort
    DURABLE record main redis (REDIS_URL = noeviction) ki list `billing:meter_failures`
    me → ops manual replay/reconcile kar sake. Kabhi raise nahi karta.
    Replay: `redis-cli lrange billing:meter_failures 0 -1`."""
    try:
        logger.error(
            "BILLING minute-meter write FAILED (revenue-leak risk) — manual replay needed: %s",
            json.dumps(rec, ensure_ascii=False, default=str)[:300],
        )
    except Exception:
        pass
    try:
        import redis as _redis

        url = os.environ.get("REDIS_URL")  # main (noeviction) — NOT cache redis (evictable)
        if url:
            r = _redis.from_url(url, socket_timeout=2)
            r.lpush("billing:meter_failures", json.dumps(rec, ensure_ascii=False, default=str))
            r.ltrim("billing:meter_failures", 0, 4999)  # bounded
    except Exception:
        pass


# Included calling minutes per marketing plan (matches packages.py: Advanced = 500/mo).
PLAN_MINUTES: dict[str, int] = {"starter": 0, "growth": 0, "advanced": 500}

# Combo plans (Product 3) — marketing+voice bundle; voice minutes same as advanced tier
_COMBO_PLAN_MINUTES: dict[str, int] = {
    "combo_starter_monthly": 500,
    "combo_starter_annual": 500,
    "combo_growth_monthly": 1000,
    "combo_growth_annual": 1000,
    "combo_pro_monthly": 2000,
    "combo_pro_annual": 2000,
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
    """Best-effort client_name -> billing Client.id (empty if not found).

    BillingRecord.client_id is an FK to SQL `clients.id`, while Product-1
    ledgers often use JSON marketing-client ids (for example `leadgenai-self`).
    Prefer SQL ids so minute metering does not create FK failures for own-brand
    platform calls; fall back to the legacy JSON lookup for older no-DB callers.
    """
    name = (client_name or "").strip().lower()
    if not name:
        return ""
    try:
        from app.models.base import get_db_session
        from app.models.client import Client

        with get_db_session() as db:
            # Own-brand/self calls are stored in SQL as id=platform and business_name
            # "LeadGen AI (self/internal)"; exact name lookup would miss and fall
            # through to the JSON marketing id leadgenai-self, which violates the
            # BillingRecord.client_id FK.
            if name in {"leadgen ai", "leadsgenai", "leadsgen ai"}:
                rec = db.query(Client).filter(Client.id == "platform").first()
                if rec and getattr(rec, "id", None):
                    return str(rec.id)
            rec = db.query(Client).filter(Client.business_name.ilike(client_name.strip())).first()
            if not rec:
                rec = (
                    db.query(Client)
                    .filter(Client.business_name.ilike(f"{client_name.strip()}%"))
                    .first()
                )
            if rec and getattr(rec, "id", None):
                return str(rec.id)
    except Exception:
        pass
    try:
        from app.marketing.clients_store import list_clients

        for c in list_clients() or []:
            if str(c.get("business_name") or "").strip().lower() == name:
                return str(c.get("id") or "")
    except Exception:
        pass
    return ""


def _billing_client_id(client_id: str, client_name: str = "") -> str:
    """Return a SQL `clients.id` suitable for BillingRecord FK, or ''.

    Accepts already-SQL ids, legacy marketing ids with `billing_client_ids`, and
    client-name lookup. Never raises.
    """
    raw = (client_id or "").strip()
    try:
        from app.models.base import get_db_session
        from app.models.client import Client

        with get_db_session() as db:
            if raw:
                if db.query(Client.id).filter(Client.id == raw).first():
                    return raw
            by_name = resolve_client_id(client_name)
            if by_name and db.query(Client.id).filter(Client.id == by_name).first():
                return by_name
            if raw:
                try:
                    from app.marketing.clients_store import resolve_client

                    m = resolve_client(raw) or {}
                    aliases = m.get("billing_client_ids") or []
                    if isinstance(aliases, list | tuple | set):
                        for alias in aliases:
                            aid = str(alias or "").strip()
                            if aid and db.query(Client.id).filter(Client.id == aid).first():
                                return aid
                    mname = str(m.get("business_name") or "").strip()
                    if mname:
                        rec = db.query(Client).filter(Client.business_name.ilike(mname)).first()
                        if rec and getattr(rec, "id", None):
                            return str(rec.id)
                except Exception:
                    pass
    except Exception:
        pass
    return raw or resolve_client_id(client_name)


def record_call_usage(
    client_id: str, duration_seconds: int, campaign_id: str | None = None, client_name: str = ""
) -> bool:
    """Post-call hook: write a TELEPHONY ledger line for this call's minutes. Best-effort.

    J.4: Also fans out a `call.completed` event to customer-registered webhooks
    (H.1). INERT when CUSTOMER_WEBHOOKS unset; NEVER blocks the billing path.
    """
    try:
        cid = _billing_client_id(client_id, client_name)
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
        # Fail-OPEN: call kabhi block na ho. Par minute-meter write fail = silent
        # revenue-leak (Advanced prepaid-minutes path) — durable record karo taaki
        # ops replay/reconcile kar sake + meter_watch alert utha sake. NEVER raises.
        try:
            _record_meter_failure(
                {
                    "client_id": (client_id or "").strip(),
                    "ts": datetime.utcnow().isoformat(),
                    "kind": "minutes",
                    "duration_seconds": int(duration_seconds or 0),
                    "campaign_id": str(campaign_id or ""),
                    "client_name": str(client_name or ""),
                    "error": str(e)[:200],
                }
            )
        except Exception:
            pass
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
            if (
                watermark is not None
                and watermark.year == now.year
                and watermark.month == now.month
            ):
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


def _plan_price_inr(plan_k: str) -> float:
    """Monthly-equivalent INR price for any plan key (marketing/voice/combo).
    0.0 for unknown/free — informational (base_price on the Subscription row)."""
    try:
        from app.marketing.packages import get_packages

        for p in get_packages(include_trial=True) or []:
            if str((p or {}).get("key") or "").strip().lower() == plan_k:
                return float(p.get("price_inr_month") or 0)
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        from app.marketing.voice_packages import voice_plan_price

        v = voice_plan_price(plan_k)
        if v:
            return float(v)
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        from app.marketing.combo_packages import combo_plan_price

        v = combo_plan_price(plan_k)
        if v:
            return float(v)
    except Exception:  # pragma: no cover - defensive
        pass
    return 0.0


def _ensure_db_client(db, cid: str) -> bool:
    """Ensure a DB Client row exists for `cid` (FK target for Subscription).

    Self-serve signup clients live only in clients_store jsonl — mirror the
    minimum NOT-NULL fields into Postgres. Returns True when the row exists
    (already or created); False when it can't be safely created (e.g. the
    contact email is already taken by a DIFFERENT client id — fail-open,
    caller skips subscription creation rather than corrupt tenancy)."""
    from app.models.client import Client, ClientStatus

    if db.query(Client).filter(Client.id == cid).first() is not None:
        return True
    rec = None
    try:
        from app.marketing.clients_store import get_client

        rec = get_client(cid)
    except Exception:  # pragma: no cover - defensive
        rec = None
    if not rec:
        return False
    email = str(rec.get("email") or rec.get("contact_email") or "").strip().lower()
    if not email:
        email = f"{cid}@upi.local"  # unique synthetic — FK/NOT-NULL integrity only
    other = db.query(Client).filter(Client.contact_email == email).first()
    if other is not None:
        logger.warning(
            "activate_plan: email %s already on DB client %s (wanted %s) — skip row create",
            email,
            other.id,
            cid,
        )
        return False
    name = str(rec.get("business_name") or "Client").strip()[:255] or "Client"
    db.add(
        Client(
            id=cid,
            business_name=name,
            contact_name=str(rec.get("contact_name") or name)[:255],
            contact_email=email,
            contact_phone=str(rec.get("phone") or "")[:20],
            industry=str(rec.get("niche") or "")[:100] or None,
            city=str(rec.get("city") or "")[:100] or None,
            status=ClientStatus.ACTIVE,
        )
    )
    db.flush()
    return True


def _create_subscription_row(db, cid: str, plan_k: str, period_end: datetime | None):
    """Fresh ACTIVE Subscription row for a manual/UPI payment — parity with the
    Stripe webhook's _activate_subscription_row (which the UPI path never hits).
    Returns the row or None. Caller owns commit + never-raise wrapper."""
    from app.models.payment import BillingCycle, Subscription, SubscriptionStatus

    if not _ensure_db_client(db, cid):
        return None
    yearly = "annual" in plan_k or "yearly" in plan_k
    now = datetime.utcnow()
    # Best-effort: seed this cycle's CustomerDeliverable rows now that the DB
    # Client row is guaranteed to exist (FK target) — doing this here instead
    # of on every dashboard/cockpit read avoids a per-request DB round-trip
    # that silently FK-violated for clients without a DB Client row (database-
    # architect audit, 2026-07-08). Idempotent; never blocks activation.
    try:
        from app.marketing.product_one_delivery import initialize_deliverables_for_client

        initialize_deliverables_for_client(db, cid, plan_k, now.strftime("%Y-%m"))
    except Exception as exc:
        logger.debug("deliverable init skipped for %s: %s", cid, exc)
    price = _plan_price_inr(plan_k)
    sub = Subscription(
        client_id=cid,
        plan_id=plan_k,
        plan_name=plan_k,
        status=SubscriptionStatus.ACTIVE,
        billing_cycle=BillingCycle.YEARLY if yearly else BillingCycle.MONTHLY,
        payment_gateway="upi",
        currency="INR",
        base_price=(price * 10) if yearly else price,
        current_period_start=now,
        current_period_end=period_end or (now + timedelta(days=365 if yearly else 30)),
    )
    db.add(sub)
    db.flush()
    return sub


def activate_plan(
    client_id: str,
    plan: str,
    subscription_id: str | None = None,
    period_end: datetime | None = None,
    ensure_subscription: bool = False,
) -> bool:
    """Provision a client's plan after a successful subscription pay/renew. Best-effort.

    - Sets the client's `plan` in clients_store so the minute cap is correct.
    - Stashes the gateway subscription id + period_end on the latest Subscription row's
      extra_data (no schema change) for traceability.
    - ``ensure_subscription=True`` (UPI/manual-payment paths ONLY — audit 2026-07-04):
      creates an ACTIVE Subscription row when none exists and flips the latest row to
      ACTIVE. Without it the portal /billing/subscription 404s after a UPI approval
      (pay-box shows forever) and reset_usage_period() has no row for its watermark.
      Stripe/webhook callers keep the default False — they manage their own row —
      and the signup pre-payment provisioning path must NEVER create one.
    Returns True if the plan was applied to clients_store, else False (never raises).
    """
    cid = (client_id or "").strip()
    plan_k = (plan or "").strip().lower()
    if not cid or not plan_k:
        return False

    applied = False
    marketing_cid = cid
    try:
        from app.marketing.clients_store import link_billing_alias, resolve_client, update_client

        # Resolve billing-alias login ids to the marketing record before plan write
        # (Jiya: subscription/invoice may stay on billing id; plan lives on marketing).
        rec = resolve_client(cid)
        if rec and str(rec.get("id") or "").strip():
            marketing_cid = str(rec.get("id")).strip()
            update_client(marketing_cid, plan=plan_k)
            applied = True
            # Record the activation id as an alias when it differs (idempotent).
            link_billing_alias(marketing_cid, cid, actor="activate_plan")
            try:
                from app.marketing import delivery_ledger

                delivery_ledger.log_event(
                    marketing_cid, "plan_activated", detail=plan_k, key="lc:activated"
                )
            except Exception as le:  # pragma: no cover
                logger.debug("activate_plan ledger log skip: %s", le)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("activate_plan clients_store skipped: %s", e)

    # Best-effort: annotate (and, for manual/UPI payments, ensure) the Subscription row.
    try:
        from app.models.base import get_db_session

        with get_db_session() as db:
            sub = _latest_subscription(db, cid)
            if sub is None and ensure_subscription and applied:
                sub = _create_subscription_row(db, cid, plan_k, period_end)
            if sub is not None:
                if ensure_subscription:
                    from app.models.payment import SubscriptionStatus as _SS

                    sub.status = _SS.ACTIVE
                    sub.plan_id = plan_k
                    sub.payment_gateway = "upi"
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
    if applied:
        try:
            from app.marketing.product_one_delivery import initialize_deliverables_for_client
            from app.models.base import get_db_session

            with get_db_session() as db:
                current_month = datetime.utcnow().strftime("%Y-%m")
                initialize_deliverables_for_client(db, cid, plan_k, current_month)
        except Exception as de:
            logger.debug("activate_plan deliverables init skipped: %s", de)

        try:
            from app.marketing.packages import get_packages
            from app.platform import revenue_attribution

            pkgs = {p.get("key", ""): p for p in get_packages()}
            amt = int((pkgs.get(plan_k) or {}).get("price_inr_month") or 0)
            revenue_attribution.record_touch(
                client_id=cid,
                channel="billing",
                event="payment",
                amount_inr=amt,
            )
        except Exception:
            pass
        # W3.5: customer webhook emits (documented but unwired) — fire-and-forget,
        # CUSTOMER_WEBHOOKS-gated inside emit + never-raises. Plan provisioned = subscriber notify.
        try:
            from app.platform import customer_webhooks

            _wh_payload = {
                "client_id": cid,
                "plan": plan_k,
                "subscription_id": subscription_id,
                "period_end": period_end.isoformat() if period_end else None,
            }
            customer_webhooks.fire_emit(cid, "subscription.activated", _wh_payload)
            customer_webhooks.fire_emit(cid, "payment.received", _wh_payload)
        except Exception:
            pass
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
