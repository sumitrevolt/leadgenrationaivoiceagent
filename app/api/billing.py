"""
Billing API Router
Endpoints for subscription management, payments, and invoices
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Stripe payment_gateway deleted 2026-07-10
from app.billing.subscription import PRICING_PLANS, billing_manager
from app.config import settings
from app.models.base import get_async_db
from app.models.payment import (
    Invoice,
    Payment,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    UsageRecord,
)
from app.utils.logger import setup_logger
from app.utils.redirect_security import validate_redirect_url

logger = setup_logger(__name__)
router = APIRouter()

# Fallback "from" address when a client has no email on file (matches Hostinger SMTP).
_FALLBACK_EMAIL = "admin@leadsgenai.in"

# --------------------------------------------------------------------------- #
# Auth dependency — resolve client_id from the caller's TOKEN, not a query param.
# Previously every billing endpoint trusted `client_id=...` from the query string
# (no auth) => cross-tenant IDOR: anyone could cancel/upgrade/credit/read any
# account. Now: customer token -> its own id; admin/super_admin/manager token ->
# explicit client_id (acting on behalf). Missing/invalid token -> 401.
# --------------------------------------------------------------------------- #
_bearer = HTTPBearer(auto_error=False)
_ADMIN_ROLES = ("admin", "super_admin", "manager")


def _decode_or_401(creds: HTTPAuthorizationCredentials | None) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        from app.api.admin import decode_token

        return decode_token(creds.credentials)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


async def _authed_client_id(
    client_id: str | None = Query(None, description="Client ID (admin acting on behalf)"),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    payload = _decode_or_401(creds)
    role = payload.get("role")
    if role == "customer":
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return str(sub)
    if role in _ADMIN_ROLES:
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id required for admin access")
        return str(client_id)
    raise HTTPException(status_code=403, detail="Not authorized for billing")


async def _authed_admin_client_id(
    client_id: str | None = Query(None, description="Client ID (admin only)"),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Admin-only: used for privileged mutations (e.g. direct plan swap) that a
    customer must NOT self-serve without payment. Customer upgrades go via checkout."""
    payload = _decode_or_401(creds)
    if payload.get("role") not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")
    return str(client_id)


# =============================================================================
# Helpers (client email resolution + gateway-config gating + usage provisioning)
# =============================================================================
def _client_email(client_id: str) -> str:
    """Best-effort REAL email for a client (never the fake client_{id}@example.com).

    Order: clients_store record (email / contact_email / owner_email) -> the customer
    login store (data/customer_auth.jsonl, reverse client_id->email) -> fallback admin
    address. Never raises.
    """
    cid = (client_id or "").strip()
    if not cid:
        return _FALLBACK_EMAIL
    # 1) clients_store record (future records may carry an email field)
    try:
        from app.marketing.clients_store import get_client

        rec = get_client(cid) or {}
        for key in ("email", "contact_email", "owner_email"):
            val = str(rec.get(key) or "").strip()
            if val and "@" in val:
                return val
    except Exception:
        pass
    # 2) customer auth store (admin set-password links email -> client_id)
    try:
        from app.api.customer_auth import _read as _read_auth

        for row in _read_auth() or []:
            if str(row.get("client_id") or "").strip() == cid:
                email = str(row.get("email") or "").strip()
                if email and "@" in email:
                    return email
    except Exception:
        pass
    return _FALLBACK_EMAIL


def _client_name(client_id: str) -> str:
    """Best-effort business name for a client (falls back to "Client <id>")."""
    try:
        from app.marketing.clients_store import get_client

        rec = get_client(client_id) or {}
        name = str(rec.get("business_name") or "").strip()
        if name:
            return name
    except Exception:
        pass
    return f"Client {client_id}"


def _ev(x):
    """Enum-or-str value: enum member ho to `.value`, warna as-is (None-safe).
    DB rows written outside the enum path (manual UPI activation) store plain
    strings — `.value` on those crashed the first real subscription response."""
    return getattr(x, "value", x)


def _billing_client_ids(client_id: str) -> list[str]:
    """Canonical id + legacy `billing_client_ids` aliases (ADR-095 family, ADR-106).

    WHY: jiya-makeover (the ONLY real paying customer) has Subscription/Invoice
    rows owned by legacy billing id `d79d690f61b3` while the marketing record is
    `jiya-makeover`. JWT may carry either id depending on login provisioning.
    Uses `resolve_client` so BOTH directions load the same id set for `.in_()`
    filters. Never raises — falls back to [client_id]."""
    ids = [str(client_id or "").strip()]
    try:
        from app.marketing.clients_store import resolve_client

        # resolve_client covers BOTH directions: marketing JWT (direct hit) and
        # billing-alias JWT (alias → marketing record). get_client alone missed
        # the billing-alias login case, so aliases never loaded for that JWT.
        rec = resolve_client(client_id) or {}
        canon = str(rec.get("id") or "").strip()
        if canon:
            ids.append(canon)
        aliases = rec.get("billing_client_ids") or []
        if isinstance(aliases, list | tuple | set):
            ids.extend(str(x or "").strip() for x in aliases)
    except Exception:
        pass
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out or [client_id]


def _stripe_configured() -> bool:
    # Stripe removed 2026-07-10 — always returns False.
    return False


def _stripe_webhook_configured() -> bool:
    # Stripe removed 2026-07-10 — always returns False.
    return False


# Razorpay removed 2026-06-18 — no online India gateway (payments via manual UPI).


def _provision_usage(
    client_id: str,
    plan_id: str | None,
    period_end: datetime | None,
    subscription_id: str | None,
    reset: bool = True,
    amount_inr: float | None = None,
) -> None:
    """Provision/refresh the minute ledger after a successful pay/renew. Never raises."""
    try:
        from app.billing import usage as usage_mod

        if client_id and plan_id:
            usage_mod.activate_plan(
                client_id, plan_id, subscription_id=subscription_id, period_end=period_end
            )
        if client_id and reset:
            usage_mod.reset_usage_period(client_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"usage provisioning skipped for {client_id}: {e}")

    # GST invoice (additive, fire-and-forget) — record hamesha; email gated AUTO_INVOICE=1.
    # payment_ref = sub-id + month => monthly renewals invoice hote, double-webhooks dedupe.
    try:
        if client_id and plan_id:
            import asyncio as _aio

            from app.billing import gst_invoice

            _ref = f"{subscription_id}:{datetime.utcnow():%Y-%m}" if subscription_id else ""
            _aio.get_running_loop().create_task(
                gst_invoice.on_payment_success(
                    client_id, plan_id, payment_ref=_ref, amount_inr=amount_inr
                )
            )
    except RuntimeError:
        pass  # no running loop (sync caller) — invoice manual API se ban sakta
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"invoice hook skipped for {client_id}: {e}")

    # Dunning: a successful pay/renew closes any open recovery case — else cases
    # stay open forever (BILL-002 council fix). Best-effort, never raises.
    try:
        if client_id:
            from app.billing import dunning

            dunning.mark_recovered(client_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"dunning mark_recovered skipped for {client_id}: {e}")


# =============================================================================
# Request/Response Models
# =============================================================================


# Request/Response models extracted to billing_models.py (behaviour-preserving).
# Re-exported here so existing `from app.api.billing import <Model>` keeps working.
from app.api.billing_models import (  # noqa: F401
    AddBalanceRequest,
    CancelSubscriptionRequest,
    CheckoutResponse,
    CreateCheckoutRequest,
    InvoiceResponse,
    PlanResponse,
    SubscriptionResponse,
    UsageResponse,
    VerifyPaymentRequest,
)

# =============================================================================
# Endpoints
# =============================================================================


@router.get("/billing/plans", response_model=list[PlanResponse], tags=["Billing"])
async def get_pricing_plans():
    """
    Get all available pricing plans
    """
    # PUBLIC pricing = sirf marketing packages wale plans (merged marketing automation
    # + advanced voice). Legacy internal plans (enterprise/per_lead/hybrid/data_*)
    # public page pe NAHI — /pricing page yahi endpoint render karta hai.
    try:
        from app.marketing.packages import get_public_packages as _get_public_packages

        _public_keys = [str(p.get("key")) for p in _get_public_packages()]
    except Exception:  # pragma: no cover - defensive
        _public_keys = ["starter", "advanced"]
    _public = [PRICING_PLANS[k] for k in _public_keys if k in PRICING_PLANS]

    plans = []
    for plan in _public or PRICING_PLANS.values():
        plans.append(
            PlanResponse(
                id=plan.id,
                name=plan.name,
                pricing_model=plan.pricing_model.value,
                monthly_price=float(plan.monthly_price),
                calls_per_month=plan.calls_per_month if plan.calls_per_month > 0 else "Unlimited",
                leads_per_month=plan.leads_per_month if plan.leads_per_month > 0 else "Unlimited",
                concurrent_campaigns=(
                    plan.concurrent_campaigns if plan.concurrent_campaigns > 0 else "Unlimited"
                ),
                features=plan.features,
                feature_groups=getattr(plan, "feature_groups", []) or [],
                quarterly_discount=plan.quarterly_discount * 100,
                yearly_discount=plan.yearly_discount * 100,
            )
        )

    return plans


def _public_plan_keys() -> set[str]:
    """Plan keys safe to expose on the public (unauthenticated) per-id endpoints.

    Mirrors the filter in GET /billing/plans so the hidden legacy `growth` plan and
    internal plans (enterprise/data_*/voice_*/combo_*) don't leak via the per-id
    vector either. Defensive fallback = the two public marketing plans.
    """
    try:
        from app.marketing.packages import get_public_packages as _get_public_packages

        return {str(p.get("key")) for p in _get_public_packages()}
    except Exception:  # pragma: no cover - defensive
        return {"starter", "advanced"}


@router.get("/billing/plans/{plan_id}", response_model=PlanResponse, tags=["Billing"])
async def get_plan_details(plan_id: str):
    """
    Get details for a specific pricing plan
    """
    if plan_id not in _public_plan_keys():
        # Hidden/legacy/internal plan — don't expose pricing via the public per-id vector.
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = billing_manager.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    return PlanResponse(
        id=plan.id,
        name=plan.name,
        pricing_model=plan.pricing_model.value,
        monthly_price=float(plan.monthly_price),
        calls_per_month=plan.calls_per_month if plan.calls_per_month > 0 else "Unlimited",
        leads_per_month=plan.leads_per_month if plan.leads_per_month > 0 else "Unlimited",
        concurrent_campaigns=(
            plan.concurrent_campaigns if plan.concurrent_campaigns > 0 else "Unlimited"
        ),
        features=plan.features,
        feature_groups=getattr(plan, "feature_groups", []) or [],
        quarterly_discount=plan.quarterly_discount * 100,
        yearly_discount=plan.yearly_discount * 100,
    )


@router.get("/billing/plans/{plan_id}/pricing", tags=["Billing"])
async def calculate_plan_pricing(
    plan_id: str, billing_cycle: str = Query("monthly", pattern="^(monthly|quarterly|yearly)$")
):
    """
    Calculate pricing for a plan with discounts
    """
    if plan_id not in _public_plan_keys():
        raise HTTPException(status_code=404, detail="Plan not found")
    from app.billing.subscription import BillingCycle as BC

    cycle_map = {"monthly": BC.MONTHLY, "quarterly": BC.QUARTERLY, "yearly": BC.YEARLY}

    pricing = billing_manager.calculate_price(plan_id, cycle_map[billing_cycle])
    if not pricing:
        raise HTTPException(status_code=404, detail="Plan not found")

    return {
        "plan_id": plan_id,
        "billing_cycle": billing_cycle,
        "subtotal": float(pricing["subtotal"]),
        "discount": float(pricing["discount"]),
        "discount_percentage": float(pricing["discount_percentage"]),
        "taxable": float(pricing["taxable"]),
        "tax": float(pricing["tax"]),
        "tax_rate": float(pricing["tax_rate"]),
        "total": float(pricing["total"]),
        "per_month": float(pricing["per_month"]),
        "currency": "INR",
    }


@router.post("/billing/checkout", response_model=CheckoutResponse, tags=["Billing"])
async def create_checkout_session(
    request: CreateCheckoutRequest,
    client_id: str = Depends(_authed_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a checkout session for subscription payment.

    Since Stripe was removed (2026-07-10), all payments are manual UPI.
    Returns a clean response so the frontend can redirect to the customer
    dashboard where the UPI QR + submit form live.
    """
    plan = billing_manager.get_plan(request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    return CheckoutResponse(
        checkout_url=f"/app/customer?plan={request.plan_id}",
        order_id="",
        session_id="",
        key_id="",
        amount=float(plan.monthly_price),
        currency="INR",
        gateway="upi",
    )


# /billing/verify-payment removed 2026-06-18 — Razorpay frontend signature
# verification gone (no online India gateway; payments via manual UPI).


@router.get("/billing/subscription", response_model=SubscriptionResponse, tags=["Billing"])
async def get_current_subscription(
    client_id: str = Depends(_authed_client_id), db: AsyncSession = Depends(get_async_db)
):
    """
    Get current subscription for a client (TRIAL / ACTIVE / PAUSED — so the UI can
    show a Resume control for a paused plan).
    """
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id.in_(_billing_client_ids(client_id)),
                Subscription.status.in_(
                    [
                        SubscriptionStatus.TRIAL,
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAUSED,
                    ]
                ),
            )
        )
        .order_by(Subscription.created_at.desc())
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")

    return SubscriptionResponse(
        id=subscription.id,
        plan_id=subscription.plan_id,
        plan_name=subscription.plan_name,
        # ADR-106 addendum: DB me kuch fields plain str hain (manual-UPI activation
        # ne payment_gateway='upi' raw string likha tha, enum member nahi) — `.value`
        # on str = AttributeError = 500 on the FIRST-EVER real subscription response.
        # `_ev()` enum ho to .value, warna value as-is (never raises).
        status=_ev(subscription.status),
        billing_cycle=_ev(subscription.billing_cycle) or "monthly",
        base_price=float(subscription.base_price) if subscription.base_price else 0,
        currency=subscription.currency,
        current_period_start=(
            subscription.current_period_start.isoformat()
            if subscription.current_period_start
            else None
        ),
        current_period_end=(
            subscription.current_period_end.isoformat() if subscription.current_period_end else None
        ),
        trial_ends_at=(
            subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None
        ),
        usage={
            "calls_used": subscription.calls_used,
            "calls_limit": subscription.calls_limit or "unlimited",
            "leads_generated": subscription.leads_generated,
            "leads_limit": subscription.leads_limit or "unlimited",
            "appointments_booked": subscription.appointments_booked,
        },
        payment_gateway=_ev(subscription.payment_gateway),
    )


@router.post("/billing/subscription/cancel", tags=["Billing"])
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    client_id: str = Depends(_authed_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Cancel current subscription
    """
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.client_id.in_(_billing_client_ids(client_id)),
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE]),
            )
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")

    try:
        # Cancel in payment gateway if applicable
        if subscription.stripe_subscription_id:
            # Stripe removed 2026-07-10 — no online gateway to cancel.
            pass
        # Razorpay removed 2026-06-18 — any legacy gateway row cancelled DB-side only.

        # Update database
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        subscription.cancel_reason = request.reason

        if request.cancel_immediately:
            subscription.ended_at = datetime.utcnow()

        await db.commit()

        # Customer webhook / flow-trigger fan-out (audit 2026-07-07: this was the
        # only SUPPORTED_EVENTS type with zero emit call-sites — a customer who
        # registered a "subscription.cancelled" webhook never received it).
        _emit_billing_customer_webhook(
            client_id,
            "subscription.cancelled",
            {
                "subscription_id": subscription.id,
                "reason": request.reason,
                "cancel_immediately": request.cancel_immediately,
            },
        )

        return {
            "success": True,
            "subscription_id": subscription.id,
            "effective_until": (
                subscription.current_period_end.isoformat()
                if not request.cancel_immediately
                else datetime.utcnow().isoformat()
            ),
            "message": "Subscription cancelled successfully",
        }

    except Exception as e:
        logger.error(f"Failed to cancel subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/billing/invoices", response_model=list[InvoiceResponse], tags=["Billing"])
async def get_invoices(
    client_id: str = Depends(_authed_client_id),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get invoice history for a client (Postgres + JSONL GST invoices merged).

    Alias-aware (ADR-106): JSONL rows may be owned by a legacy billing id
    (`d79d690f61b3`) while the JWT carries the canonical slug (`jiya-makeover`).
    """
    alias_ids = _billing_client_ids(client_id)

    # Query Postgres invoices
    result = await db.execute(
        select(Invoice).where(Invoice.client_id.in_(alias_ids)).order_by(Invoice.created_at.desc())
    )
    pg_invoices = result.scalars().all()

    # Also read JSONL GST invoices for this client + aliases
    all_invoices: list[InvoiceResponse] = []
    try:
        from app.billing import gst_invoice

        alias_set = set(alias_ids)
        jsonl_invoices = [
            r
            for r in gst_invoice.list_invoices(500)
            if str(r.get("client_id") or "") in alias_set and not r.get("voided")
        ]
        for inv in jsonl_invoices:
            all_invoices.append(
                InvoiceResponse(
                    id=str(inv.get("id") or inv.get("number") or ""),
                    invoice_number=str(inv.get("number") or ""),
                    status="paid",
                    total=float(inv.get("gross_inr") or 0),
                    amount_paid=float(inv.get("gross_inr") or 0),
                    amount_due=0,
                    currency="INR",
                    invoice_date=str(inv.get("date") or ""),
                    due_date=None,
                    pdf_url=None,
                    hosted_url=None,
                )
            )
    except Exception as e:
        logger.debug(f"[get_invoices] JSONL read failed: {e}")

    # Add Postgres invoices (dedup by invoice_number) — full InvoiceResponse fields
    seen_numbers = {inv.invoice_number for inv in all_invoices if inv.invoice_number}
    for inv in pg_invoices:
        if inv.invoice_number in seen_numbers:
            continue
        all_invoices.append(
            InvoiceResponse(
                id=inv.id,
                invoice_number=inv.invoice_number,
                status=_ev(inv.status) or "draft",
                total=float(inv.total) if inv.total else 0,
                amount_paid=float(inv.amount_paid) if inv.amount_paid else 0,
                amount_due=float(inv.amount_due) if inv.amount_due else 0,
                currency=inv.currency or "INR",
                invoice_date=inv.invoice_date.isoformat() if inv.invoice_date else "",
                due_date=inv.due_date.isoformat() if inv.due_date else None,
                pdf_url=inv.pdf_url,
                hosted_url=inv.hosted_invoice_url,
            )
        )
        seen_numbers.add(inv.invoice_number)

    # Sort by date descending, apply limit/offset
    all_invoices.sort(key=lambda x: x.invoice_date or "", reverse=True)
    return all_invoices[offset : offset + limit]


@router.get("/billing/invoices/{invoice_id}", tags=["Billing"])
async def get_invoice_details(
    invoice_id: str,
    client_id: str = Depends(_authed_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get detailed invoice information
    """
    result = await db.execute(
        select(Invoice).where(
            and_(Invoice.id == invoice_id, Invoice.client_id.in_(_billing_client_ids(client_id)))
        )
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return invoice.to_dict()


@router.get("/billing/usage", response_model=UsageResponse, tags=["Billing"])
async def get_current_usage(
    client_id: str = Depends(_authed_client_id), db: AsyncSession = Depends(get_async_db)
):
    """
    Get current billing period usage for a client
    """
    # Get active subscription
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.client_id.in_(_billing_client_ids(client_id)),
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE]),
            )
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        calls_limit = subscription.calls_limit or 0
        leads_limit = subscription.leads_limit or 0

        return UsageResponse(
            calls_used=subscription.calls_used,
            calls_limit=calls_limit if calls_limit > 0 else "Unlimited",
            calls_remaining=(
                max(0, calls_limit - subscription.calls_used) if calls_limit > 0 else "Unlimited"
            ),
            leads_generated=subscription.leads_generated,
            leads_limit=leads_limit if leads_limit > 0 else "Unlimited",
            leads_remaining=(
                max(0, leads_limit - subscription.leads_generated)
                if leads_limit > 0
                else "Unlimited"
            ),
            appointments_booked=subscription.appointments_booked,
            period_start=(
                subscription.current_period_start.isoformat()
                if subscription.current_period_start
                else None
            ),
            period_end=(
                subscription.current_period_end.isoformat()
                if subscription.current_period_end
                else None
            ),
        )

    # No subscription - return zeros
    return UsageResponse(
        calls_used=0,
        calls_limit=0,
        calls_remaining=0,
        leads_generated=0,
        leads_limit=0,
        leads_remaining=0,
        appointments_booked=0,
    )


@router.get("/billing/payment-methods", tags=["Billing"])
async def get_payment_methods(
    client_id: str = Depends(_authed_client_id), db: AsyncSession = Depends(get_async_db)
):
    """
    Get saved payment methods for a client
    """
    result = await db.execute(
        select(PaymentMethod)
        .where(
            and_(
                PaymentMethod.client_id.in_(_billing_client_ids(client_id)), PaymentMethod.is_active
            )
        )
        .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
    )
    methods = result.scalars().all()

    return [method.to_dict() for method in methods]


@router.post("/billing/balance/add", tags=["Billing"])
async def add_account_balance(
    request: AddBalanceRequest,
    client_id: str = Depends(_authed_client_id),
    success_url: str = Query(..., description="Success redirect URL"),
    cancel_url: str = Query(..., description="Cancel redirect URL"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Add balance to account (for per-lead pricing model).
    Stripe removed 2026-07-10 — returns clean 503.
    """
    # SECURITY FIX (P0-2, 2026-07-19): Validate redirect URLs to prevent open redirects
    _ = validate_redirect_url(success_url, is_dev=settings.app_env == "development")
    _ = validate_redirect_url(cancel_url, is_dev=settings.app_env == "development")

    raise HTTPException(
        status_code=503,
        detail="Online payment abhi setup ho raha hai — UPI ya contact se pay karein.",
    )


@router.get("/billing/balance", tags=["Billing"])
async def get_account_balance(
    client_id: str = Depends(_authed_client_id), db: AsyncSession = Depends(get_async_db)
):
    """
    Get current account balance (for per-lead pricing model)
    """
    result = await db.execute(
        select(Subscription)
        .where(Subscription.client_id.in_(_billing_client_ids(client_id)))
        .order_by(Subscription.created_at.desc())
    )
    subscription = result.scalar_one_or_none()

    balance = float(subscription.balance) if subscription and subscription.balance else 0

    return {
        "balance": balance,
        "currency": subscription.currency if subscription else settings.default_currency,
    }


@router.get("/billing/usage/history", tags=["Billing"])
async def get_usage_history(
    client_id: str = Depends(_authed_client_id),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get usage history for the specified number of days
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(UsageRecord)
        .where(
            and_(
                UsageRecord.client_id.in_(_billing_client_ids(client_id)),
                UsageRecord.usage_date >= start_date,
            )
        )
        .order_by(UsageRecord.usage_date.desc())
    )
    records = result.scalars().all()

    return [record.to_dict() for record in records]


# =============================================================================
# Unified payment webhook (one public URL for the Stripe gateway)
# =============================================================================
@router.post("/billing/webhook", tags=["Billing"])
async def unified_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Unified payment webhook — Stripe + Razorpay both removed.
    Returns 400 for any unrecognized webhook header (UPI-only payments).
    """
    raise HTTPException(
        status_code=400,
        detail="Payments via manual UPI only — no webhook gateway active (Stripe removed 2026-07-10).",
    )


@router.post("/billing/subscription/upgrade", tags=["Billing"])
async def upgrade_subscription(
    new_plan_id: str,
    client_id: str = Depends(_authed_admin_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Upgrade subscription to a new plan.

    ADMIN-ONLY: this performs a direct plan swap with NO payment/proration. A customer
    must not self-upgrade for free — customer-initiated upgrades go through
    /billing/checkout (which charges the new plan) and the webhook updates the plan.
    """
    # SECURITY FIX (P0-3, 2026-07-19): Add row-level locking to prevent concurrent modification
    # Use SELECT ... FOR UPDATE to prevent race conditions on subscription upgrades
    # This ensures only one request can modify the subscription at a time
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id.in_(_billing_client_ids(client_id)),
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE]),
            )
        )
        .with_for_update()  # Row-level pessimistic lock
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")

    # Get new plan
    new_plan = billing_manager.get_plan(new_plan_id)
    if not new_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Update subscription
    subscription.plan_id = new_plan_id
    subscription.plan_name = new_plan.name
    subscription.base_price = new_plan.monthly_price
    subscription.calls_limit = new_plan.calls_per_month
    subscription.leads_limit = new_plan.leads_per_month
    subscription.updated_at = datetime.utcnow()

    await db.commit()

    return {
        "success": True,
        "subscription_id": subscription.id,
        "new_plan": new_plan_id,
        "message": "Subscription upgraded successfully",
    }


# =============================================================================
# Stripe billing PORTAL (hosted card management)
# =============================================================================
class PortalRequest(BaseModel):
    """Create a billing-portal session request."""

    return_url: str = Field(..., description="Where Stripe sends the customer back")


@router.post("/billing/portal", tags=["Billing"])
async def create_billing_portal(
    request: PortalRequest,
    client_id: str = Depends(_authed_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """Open the gateway-hosted billing portal.

    Stripe: returns a Billing Portal URL (card/invoice management). Razorpay has no
    hosted self-serve portal -> returns ``{portal_url: null, ...}`` (manage via
    pause/cancel endpoints instead). Returns 503 if Stripe keys are not configured.
    """
    result = await db.execute(
        select(Subscription)
        .where(Subscription.client_id.in_(_billing_client_ids(client_id)))
        .order_by(Subscription.created_at.desc())
    )
    subscription = result.scalar_one_or_none()

    # Stripe path (only if a Stripe customer + keys exist).
    if subscription and subscription.stripe_customer_id:
        if not _stripe_configured():
            raise HTTPException(status_code=503, detail="Stripe gateway not configured")
        try:
            # Stripe removed 2026-07-10 — no billing portal available.
            raise HTTPException(
                status_code=503, detail="Billing portal not available (UPI-only payments)"
            )
        except Exception as e:
            logger.error(f"Failed to create billing portal: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Razorpay (or unknown) — no hosted portal.
    return {
        "portal_url": None,
        "gateway": (subscription.payment_gateway if subscription else None) or "razorpay",
        "message": "No hosted portal — manage your plan via pause/resume/cancel.",
    }


# =============================================================================
# PAUSE / RESUME subscription
# =============================================================================
async def _get_active_or_paused_sub(db: AsyncSession, client_id: str) -> Subscription:
    # SECURITY FIX (P0-3, 2026-07-19): Add row-level locking for pause/resume operations
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id.in_(_billing_client_ids(client_id)),
                Subscription.status.in_(
                    [
                        SubscriptionStatus.TRIAL,
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAUSED,
                    ]
                ),
            )
        )
        .order_by(Subscription.created_at.desc())
        .with_for_update()  # Row-level pessimistic lock
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")
    return sub


@router.post("/billing/subscription/pause", tags=["Billing"])
async def pause_subscription(
    client_id: str = Depends(_authed_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """Pause the client's subscription (gateway-side if linked, then DB status=PAUSED)."""
    subscription = await _get_active_or_paused_sub(db, client_id)
    try:
        if subscription.stripe_subscription_id and _stripe_configured():
            # Stripe removed 2026-07-10 — pause DB-side only.
            pass
        # Razorpay removed 2026-06-18 — legacy gateway rows pause DB-side only.
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    subscription.status = SubscriptionStatus.PAUSED
    subscription.updated_at = datetime.utcnow()
    await db.commit()
    return {"success": True, "subscription_id": subscription.id, "status": "paused"}


@router.post("/billing/subscription/resume", tags=["Billing"])
async def resume_subscription(
    client_id: str = Depends(_authed_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """Resume a paused subscription (gateway-side if linked, then DB status=ACTIVE)."""
    subscription = await _get_active_or_paused_sub(db, client_id)
    try:
        if subscription.stripe_subscription_id and _stripe_configured():
            # Stripe removed 2026-07-10 — resume DB-side only.
            pass
        # Razorpay removed 2026-06-18 — legacy gateway rows resume DB-side only.
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.updated_at = datetime.utcnow()
    await db.commit()
    return {"success": True, "subscription_id": subscription.id, "status": "active"}


# =============================================================================
# Signature-verified WEBHOOKS (Stripe + Razorpay)
# =============================================================================
def _period_dt(value) -> datetime | None:
    """Coerce a unix-timestamp / datetime into a datetime, else None."""
    try:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.utcfromtimestamp(int(value))
    except Exception:
        return None


async def _find_subscription_by_gateway_id(
    db: AsyncSession, *, stripe_id: str | None = None, razorpay_id: str | None = None
) -> Subscription | None:
    if stripe_id:
        res = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_id)
        )
        sub = res.scalar_one_or_none()
        if sub:
            return sub
    if razorpay_id:
        res = await db.execute(
            select(Subscription).where(Subscription.razorpay_subscription_id == razorpay_id)
        )
        sub = res.scalar_one_or_none()
        if sub:
            return sub
    return None


async def _activate_subscription_row(
    db: AsyncSession,
    *,
    client_id: str | None,
    plan_id: str | None,
    gateway: str,
    stripe_subscription_id: str | None = None,
    stripe_customer_id: str | None = None,
    razorpay_subscription_id: str | None = None,
    razorpay_customer_id: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> Subscription | None:
    """Find/create the Subscription row and mark it ACTIVE for the current period.

    Mirrors the existing cancel/upgrade DB patterns. Best-effort; returns the row or
    None when there isn't enough identity to act on.
    """
    sub = await _find_subscription_by_gateway_id(
        db, stripe_id=stripe_subscription_id, razorpay_id=razorpay_subscription_id
    )
    # Else by client + active/trial (the row created at checkout time).
    if sub is None and client_id:
        res = await db.execute(
            select(Subscription)
            .where(
                and_(
                    Subscription.client_id.in_(_billing_client_ids(client_id)),
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.TRIAL,
                            SubscriptionStatus.ACTIVE,
                            SubscriptionStatus.PAST_DUE,
                            SubscriptionStatus.PAUSED,
                        ]
                    ),
                )
            )
            .order_by(Subscription.created_at.desc())
        )
        sub = res.scalar_one_or_none()

    if sub is None:
        if not client_id:
            return None
        # Create a fresh row from the plan catalogue (no checkout row existed).
        plan = billing_manager.get_plan(plan_id) if plan_id else None
        sub = Subscription(
            id=str(uuid.uuid4()),
            client_id=client_id,
            plan_id=plan_id or "advanced",
            plan_name=plan.name if plan else (plan_id or "advanced"),
            status=SubscriptionStatus.ACTIVE,
            currency=settings.default_currency,
            base_price=plan.monthly_price if plan else 0,
            calls_limit=plan.calls_per_month if plan else 0,
            leads_limit=plan.leads_per_month if plan else 0,
        )
        db.add(sub)

    sub.status = SubscriptionStatus.ACTIVE
    sub.payment_gateway = gateway
    if stripe_subscription_id:
        sub.stripe_subscription_id = stripe_subscription_id
    if stripe_customer_id:
        sub.stripe_customer_id = stripe_customer_id
    if razorpay_subscription_id:
        sub.razorpay_subscription_id = razorpay_subscription_id
    if razorpay_customer_id:
        sub.razorpay_customer_id = razorpay_customer_id
    if period_start:
        sub.current_period_start = period_start
    if period_end:
        sub.current_period_end = period_end
    sub.updated_at = datetime.utcnow()
    return sub


def _emit_billing_customer_webhook(
    client_id: str | None, event_type: str, payload: dict[str, Any]
) -> None:
    """Customer webhook fan-out for billing events (gated CUSTOMER_WEBHOOKS)."""
    cid = (client_id or "").strip()
    if not cid:
        return
    try:
        from app.platform import customer_webhooks as _cw

        _cw.fire_emit(cid, event_type, {**payload, "client_id": cid})
    except Exception as e:
        logger.debug("[billing] customer webhook emit skip: %s", e)


@router.post("/billing/webhooks/stripe", tags=["Billing"])
async def stripe_webhook_removed(request: Request):
    """RETIRED. Stripe gateway removed 2026-07-10; manual UPI is canonical.

    This is a permanent fail-closed compatibility stub. The route stays
    registered so any stale caller gets a deterministic, documented refusal
    instead of a 404 that looks like a routing bug.

    It contains NO event parsing and NO activation capability, deliberately.
    It previously kept the full subscription-activation body (activation,
    minute-ledger provisioning, subscription status mutation, db.commit)
    physically below an unconditional `raise`. That is one deleted line away
    from executing against an unverified payload: a forged
    `checkout.session.completed` carrying any `metadata.client_id` could have
    activated a paid plan for an arbitrary tenant. A guard above dead code is
    not a fix — removing the capability is. Regression-locked by
    `tests/test_stripe_webhook_fail_closed.py`.

    400 is kept (not 410) because that is the status the endpoint already
    returned; changing it would be an unrequested contract change.

    Owner decision 2026-08-05: manual UPI only (issue #243, not_planned).
    Payments are reconciled through `/api/upi/*` with
    `payment_verification_method = owner_confirmed_upi` — never
    `PROVIDER_VERIFIED`.
    """
    raise HTTPException(
        status_code=400,
        detail="Stripe gateway removed — manual UPI is the canonical payment method",
    )


# /billing/webhooks/razorpay route removed 2026-06-18 — Razorpay gateway gone
# (no online India gateway; payments via manual UPI). Stripe webhook above remains
# the source of truth for subscription provisioning. Voice-minute / lead-pack
# top-ups now reconcile via manual UPI + admin tooling, not a payment webhook.
