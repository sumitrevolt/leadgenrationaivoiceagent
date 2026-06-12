"""
Billing API Router
Endpoints for subscription management, payments, and invoices
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.payment_gateway import get_payment_gateway
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

logger = setup_logger(__name__)
router = APIRouter()

# Fallback "from" address when a client has no email on file (matches Hostinger SMTP).
_FALLBACK_EMAIL = "admin@leadsgenai.in"


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


def _stripe_configured() -> bool:
    return bool((settings.stripe_secret_key or "").strip())


def _stripe_webhook_configured() -> bool:
    return bool((settings.stripe_webhook_secret or "").strip())


def _razorpay_configured() -> bool:
    return bool(
        (settings.razorpay_key_id or "").strip() and (settings.razorpay_key_secret or "").strip()
    )


def _razorpay_webhook_configured() -> bool:
    return bool((settings.razorpay_webhook_secret or "").strip())


def _provision_usage(client_id: str, plan_id: str | None, period_end: datetime | None,
                     subscription_id: str | None, reset: bool = True) -> None:
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
                gst_invoice.on_payment_success(client_id, plan_id, payment_ref=_ref)
            )
    except RuntimeError:
        pass  # no running loop (sync caller) — invoice manual API se ban sakta
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"invoice hook skipped for {client_id}: {e}")


# =============================================================================
# Request/Response Models
# =============================================================================


class PlanResponse(BaseModel):
    """Pricing plan response"""

    id: str
    name: str
    pricing_model: str
    monthly_price: float
    calls_per_month: int | str
    leads_per_month: int | str
    concurrent_campaigns: int | str
    features: list[str]
    quarterly_discount: float
    yearly_discount: float


class CreateCheckoutRequest(BaseModel):
    """Create checkout session request"""

    plan_id: str
    billing_cycle: str = "monthly"
    success_url: str
    cancel_url: str
    currency: str | None = None


class CheckoutResponse(BaseModel):
    """Checkout session response"""

    checkout_url: str | None = None
    order_id: str | None = None
    session_id: str | None = None
    key_id: str | None = None  # For Razorpay
    amount: float
    currency: str
    gateway: str


class SubscriptionResponse(BaseModel):
    """Subscription details response"""

    id: str
    plan_id: str
    plan_name: str
    status: str
    billing_cycle: str
    base_price: float
    currency: str
    current_period_start: str | None = None
    current_period_end: str | None = None
    trial_ends_at: str | None = None
    usage: dict
    payment_gateway: str | None = None


class CancelSubscriptionRequest(BaseModel):
    """Cancel subscription request"""

    reason: str | None = None
    cancel_immediately: bool = False


class InvoiceResponse(BaseModel):
    """Invoice response"""

    id: str
    invoice_number: str
    status: str
    total: float
    amount_paid: float
    amount_due: float
    currency: str
    invoice_date: str
    due_date: str | None = None
    pdf_url: str | None = None
    hosted_url: str | None = None


class UsageResponse(BaseModel):
    """Usage statistics response"""

    calls_used: int
    calls_limit: int | str
    calls_remaining: int | str
    leads_generated: int
    leads_limit: int | str
    leads_remaining: int | str
    appointments_booked: int
    period_start: str | None = None
    period_end: str | None = None


class VerifyPaymentRequest(BaseModel):
    """Verify Razorpay payment request"""

    order_id: str
    payment_id: str
    signature: str


class AddBalanceRequest(BaseModel):
    """Add balance for per-lead model"""

    amount: float = Field(..., gt=0)
    currency: str = "INR"


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/billing/plans", response_model=list[PlanResponse], tags=["Billing"])
async def get_pricing_plans():
    """
    Get all available pricing plans
    """
    # PUBLIC pricing = sirf marketing packages wale plans (starter/growth/advanced).
    # Legacy internal plans (enterprise/per_lead/hybrid/data_*) public page pe NAHI —
    # /pricing page yahi endpoint render karta hai (BUG FIX 2026-06-10: pehle saare
    # legacy ₹15k+ plans dikh rahe the).
    try:
        from app.marketing.packages import PACKAGES as _PKGS

        _public_keys = [str(p.get("key")) for p in _PKGS]
    except Exception:  # pragma: no cover - defensive
        _public_keys = ["starter", "growth", "advanced"]
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
                quarterly_discount=plan.quarterly_discount * 100,
                yearly_discount=plan.yearly_discount * 100,
            )
        )

    return plans


@router.get("/billing/plans/{plan_id}", response_model=PlanResponse, tags=["Billing"])
async def get_plan_details(plan_id: str):
    """
    Get details for a specific pricing plan
    """
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
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Create a checkout session for subscription payment.
    Returns Stripe checkout URL or Razorpay order details.
    """
    # Get plan details
    plan = billing_manager.get_plan(request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Calculate pricing
    from app.billing.subscription import BillingCycle as BC

    cycle_map = {"monthly": BC.MONTHLY, "quarterly": BC.QUARTERLY, "yearly": BC.YEARLY}
    pricing = billing_manager.calculate_price(
        request.plan_id, cycle_map.get(request.billing_cycle, BC.MONTHLY)
    )

    amount = pricing["total"]
    currency = request.currency or settings.default_currency

    # Get appropriate gateway
    gateway = get_payment_gateway(currency=currency)

    try:
        # Check if customer exists, create if not
        # Use the client's REAL email (clients_store / customer-auth store; fallback admin).
        customer_result = await gateway.create_customer(
            email=_client_email(client_id),
            name=_client_name(client_id),
            metadata={"client_id": client_id},
        )

        # Create checkout session
        result = await gateway.create_checkout_session(
            customer_id=customer_result["customer_id"],
            plan_id=request.plan_id,
            amount=amount,
            currency=currency,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata={
                "client_id": client_id,
                "plan_id": request.plan_id,
                "billing_cycle": request.billing_cycle,
                "type": "subscription",
            },
        )

        return CheckoutResponse(
            checkout_url=result.get("checkout_url"),
            order_id=result.get("order_id"),
            session_id=result.get("session_id"),
            key_id=result.get("key_id"),
            amount=float(amount),
            currency=currency,
            gateway=result["gateway"],
        )

    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/billing/verify-payment", tags=["Billing"])
async def verify_razorpay_payment(
    request: VerifyPaymentRequest,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Verify Razorpay payment signature (called from frontend after payment)
    """
    from app.billing.payment_gateway import get_razorpay_gateway

    try:
        gateway = get_razorpay_gateway()
        is_valid = await gateway.verify_payment_signature(
            order_id=request.order_id, payment_id=request.payment_id, signature=request.signature
        )

        if not is_valid:
            raise HTTPException(status_code=400, detail="Invalid payment signature")

        # Record the payment in database
        payment = Payment(
            id=str(uuid.uuid4()),
            client_id=client_id,
            payment_gateway=PaymentGateway.RAZORPAY,
            gateway_payment_id=request.payment_id,
            gateway_order_id=request.order_id,
            amount=Decimal("0"),  # Will be updated from webhook
            currency="INR",
            status=PaymentStatus.COMPLETED,
            completed_at=datetime.utcnow(),
        )
        db.add(payment)
        await db.commit()

        return {
            "success": True,
            "payment_id": request.payment_id,
            "message": "Payment verified successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment verification failed: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed")


@router.get("/billing/subscription", response_model=SubscriptionResponse, tags=["Billing"])
async def get_current_subscription(
    client_id: str = Query(..., description="Client ID"), db: AsyncSession = Depends(get_async_db)
):
    """
    Get current subscription for a client (TRIAL / ACTIVE / PAUSED — so the UI can
    show a Resume control for a paused plan).
    """
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id == client_id,
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
        status=subscription.status.value,
        billing_cycle=subscription.billing_cycle.value if subscription.billing_cycle else "monthly",
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
        payment_gateway=(
            subscription.payment_gateway.value if subscription.payment_gateway else None
        ),
    )


@router.post("/billing/subscription/cancel", tags=["Billing"])
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Cancel current subscription
    """
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.client_id == client_id,
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
            from app.billing.payment_gateway import get_stripe_gateway

            gateway = get_stripe_gateway()
            await gateway.cancel_subscription(
                subscription.stripe_subscription_id,
                cancel_at_period_end=not request.cancel_immediately,
            )
        elif subscription.razorpay_subscription_id:
            from app.billing.payment_gateway import get_razorpay_gateway

            gateway = get_razorpay_gateway()
            await gateway.cancel_subscription(
                subscription.razorpay_subscription_id,
                cancel_at_period_end=not request.cancel_immediately,
            )

        # Update database
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        subscription.cancel_reason = request.reason

        if request.cancel_immediately:
            subscription.ended_at = datetime.utcnow()

        await db.commit()

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
    client_id: str = Query(..., description="Client ID"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get invoice history for a client
    """
    result = await db.execute(
        select(Invoice)
        .where(Invoice.client_id == client_id)
        .order_by(Invoice.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    invoices = result.scalars().all()

    return [
        InvoiceResponse(
            id=inv.id,
            invoice_number=inv.invoice_number,
            status=inv.status.value if inv.status else "draft",
            total=float(inv.total) if inv.total else 0,
            amount_paid=float(inv.amount_paid) if inv.amount_paid else 0,
            amount_due=float(inv.amount_due) if inv.amount_due else 0,
            currency=inv.currency,
            invoice_date=inv.invoice_date.isoformat() if inv.invoice_date else "",
            due_date=inv.due_date.isoformat() if inv.due_date else None,
            pdf_url=inv.pdf_url,
            hosted_url=inv.hosted_invoice_url,
        )
        for inv in invoices
    ]


@router.get("/billing/invoices/{invoice_id}", tags=["Billing"])
async def get_invoice_details(
    invoice_id: str,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get detailed invoice information
    """
    result = await db.execute(
        select(Invoice).where(and_(Invoice.id == invoice_id, Invoice.client_id == client_id))
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return invoice.to_dict()


@router.get("/billing/usage", response_model=UsageResponse, tags=["Billing"])
async def get_current_usage(
    client_id: str = Query(..., description="Client ID"), db: AsyncSession = Depends(get_async_db)
):
    """
    Get current billing period usage for a client
    """
    # Get active subscription
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.client_id == client_id,
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
    client_id: str = Query(..., description="Client ID"), db: AsyncSession = Depends(get_async_db)
):
    """
    Get saved payment methods for a client
    """
    result = await db.execute(
        select(PaymentMethod)
        .where(and_(PaymentMethod.client_id == client_id, PaymentMethod.is_active))
        .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
    )
    methods = result.scalars().all()

    return [method.to_dict() for method in methods]


@router.post("/billing/balance/add", tags=["Billing"])
async def add_account_balance(
    request: AddBalanceRequest,
    client_id: str = Query(..., description="Client ID"),
    success_url: str = Query(..., description="Success redirect URL"),
    cancel_url: str = Query(..., description="Cancel redirect URL"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Add balance to account (for per-lead pricing model)
    """
    gateway = get_payment_gateway(currency=request.currency)

    try:
        # Create customer if needed (REAL email — no fake example.com).
        customer_result = await gateway.create_customer(
            email=_client_email(client_id),
            name=_client_name(client_id),
            metadata={"client_id": client_id},
        )

        # Create checkout for balance top-up
        result = await gateway.create_checkout_session(
            customer_id=customer_result["customer_id"],
            plan_id="balance_topup",
            amount=Decimal(str(request.amount)),
            currency=request.currency,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "client_id": client_id,
                "type": "balance_topup",
                "amount": str(request.amount),
            },
        )

        return {
            "checkout_url": result.get("checkout_url"),
            "order_id": result.get("order_id"),
            "amount": request.amount,
            "currency": request.currency,
            "gateway": result["gateway"],
        }

    except Exception as e:
        logger.error(f"Failed to create balance top-up: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/billing/balance", tags=["Billing"])
async def get_account_balance(
    client_id: str = Query(..., description="Client ID"), db: AsyncSession = Depends(get_async_db)
):
    """
    Get current account balance (for per-lead pricing model)
    """
    result = await db.execute(
        select(Subscription)
        .where(Subscription.client_id == client_id)
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
    client_id: str = Query(..., description="Client ID"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get usage history for the specified number of days
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(UsageRecord)
        .where(and_(UsageRecord.client_id == client_id, UsageRecord.usage_date >= start_date))
        .order_by(UsageRecord.usage_date.desc())
    )
    records = result.scalars().all()

    return [record.to_dict() for record in records]


# =============================================================================
# Unified payment webhook (one public URL for both gateways)
# =============================================================================
@router.post("/billing/webhook", tags=["Billing"])
async def unified_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Unified payment webhook — ek hi public URL Stripe + Razorpay dono ke liye.

    Provider request header se detect hota hai:
      - ``Stripe-Signature``      -> Stripe events  (checkout / invoice / subscription.*)
      - ``X-Razorpay-Signature``  -> Razorpay events (payment / subscription.*)

    Verification + event dispatch EXISTING handlers (``app.api.webhooks``) ko delegate
    hota hai — single source of truth. Wahi handlers subscription renewals/pauses/
    cancellations + plan minute-provisioning (``usage.activate_plan`` /
    ``reset_usage_period``) karte hain. Existing ``/api/webhooks/stripe`` aur
    ``/api/webhooks/razorpay`` bhi as-is chalte (backward compatible).

    Bina valid provider-signature header ke -> 400. Signature galat -> handler 401
    deta hai (provider retry karega). Koi unhandled 500 nahi (handlers contain errors).
    """
    from app.api import webhooks as _wh

    headers = request.headers
    stripe_sig = headers.get("Stripe-Signature") or headers.get("stripe-signature")
    rzp_sig = headers.get("X-Razorpay-Signature") or headers.get("x-razorpay-signature")

    if stripe_sig:
        return await _wh.stripe_webhook(request=request, stripe_signature=stripe_sig, db=db)
    if rzp_sig:
        return await _wh.razorpay_webhook(request=request, x_razorpay_signature=rzp_sig, db=db)

    raise HTTPException(
        status_code=400,
        detail="Unrecognized payment webhook (Stripe-Signature / X-Razorpay-Signature header missing)",
    )


@router.post("/billing/subscription/upgrade", tags=["Billing"])
async def upgrade_subscription(
    new_plan_id: str,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Upgrade subscription to a new plan
    """
    # Get current subscription
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.client_id == client_id,
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE]),
            )
        )
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
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """Open the gateway-hosted billing portal.

    Stripe: returns a Billing Portal URL (card/invoice management). Razorpay has no
    hosted self-serve portal -> returns ``{portal_url: null, ...}`` (manage via
    pause/cancel endpoints instead). Returns 503 if Stripe keys are not configured.
    """
    result = await db.execute(
        select(Subscription)
        .where(Subscription.client_id == client_id)
        .order_by(Subscription.created_at.desc())
    )
    subscription = result.scalar_one_or_none()

    # Stripe path (only if a Stripe customer + keys exist).
    if subscription and subscription.stripe_customer_id:
        if not _stripe_configured():
            raise HTTPException(status_code=503, detail="Stripe gateway not configured")
        try:
            from app.billing.payment_gateway import get_stripe_gateway

            gateway = get_stripe_gateway()
            session = await gateway.create_billing_portal_session(
                customer_id=subscription.stripe_customer_id, return_url=request.return_url
            )
            return {"portal_url": session["portal_url"], "gateway": "stripe"}
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
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id == client_id,
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
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="No subscription found")
    return sub


@router.post("/billing/subscription/pause", tags=["Billing"])
async def pause_subscription(
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """Pause the client's subscription (gateway-side if linked, then DB status=PAUSED)."""
    subscription = await _get_active_or_paused_sub(db, client_id)
    try:
        if subscription.stripe_subscription_id and _stripe_configured():
            from app.billing.payment_gateway import get_stripe_gateway

            await get_stripe_gateway().pause_subscription(subscription.stripe_subscription_id)
        elif subscription.razorpay_subscription_id and _razorpay_configured():
            from app.billing.payment_gateway import get_razorpay_gateway

            try:
                await get_razorpay_gateway().pause_subscription(
                    subscription.razorpay_subscription_id
                )
            except Exception as e:
                # Razorpay pause may be unavailable for the plan — fall back to DB-only.
                logger.warning(f"Razorpay pause unavailable, DB-only pause: {e}")
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
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """Resume a paused subscription (gateway-side if linked, then DB status=ACTIVE)."""
    subscription = await _get_active_or_paused_sub(db, client_id)
    try:
        if subscription.stripe_subscription_id and _stripe_configured():
            from app.billing.payment_gateway import get_stripe_gateway

            await get_stripe_gateway().resume_subscription(subscription.stripe_subscription_id)
        elif subscription.razorpay_subscription_id and _razorpay_configured():
            from app.billing.payment_gateway import get_razorpay_gateway

            try:
                await get_razorpay_gateway().resume_subscription(
                    subscription.razorpay_subscription_id
                )
            except Exception as e:
                logger.warning(f"Razorpay resume unavailable, DB-only resume: {e}")
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
                    Subscription.client_id == client_id,
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


@router.post("/billing/webhooks/stripe", tags=["Billing"])
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Stripe webhook (signature-verified). 503 if keys missing; never crashes.

    Handled: checkout.session.completed, invoice.paid / invoice.payment_succeeded,
    customer.subscription.created/updated/deleted/paused/resumed. On a successful
    pay/renew -> mark the Subscription ACTIVE + provision the minute ledger.
    """
    if not _stripe_configured() or not _stripe_webhook_configured():
        raise HTTPException(status_code=503, detail="Stripe gateway not configured")

    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    try:
        from app.billing.payment_gateway import get_stripe_gateway

        event = await get_stripe_gateway().verify_webhook(payload, signature)
    except Exception as e:
        logger.warning(f"Stripe webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event.get("event_type", "")
    obj = event.get("data") or {}
    # event.data.object is a stripe object; coerce to plain dict access.
    get = obj.get if isinstance(obj, dict) else (lambda k, d=None: getattr(obj, k, d))
    meta = get("metadata", {}) or {}
    client_id = (meta.get("client_id") if isinstance(meta, dict) else None) or None
    plan_id = (meta.get("plan_id") if isinstance(meta, dict) else None) or None

    try:
        if event_type == "checkout.session.completed":
            sub_id = get("subscription")
            customer_id = get("customer")
            mode = get("mode")
            if mode == "subscription" or sub_id:
                sub = await _activate_subscription_row(
                    db,
                    client_id=client_id,
                    plan_id=plan_id,
                    gateway=PaymentGateway.STRIPE.value,
                    stripe_subscription_id=sub_id,
                    stripe_customer_id=customer_id,
                )
                await db.commit()
                _provision_usage(
                    client_id or (sub.client_id if sub else None),
                    plan_id or (sub.plan_id if sub else None),
                    sub.current_period_end if sub else None,
                    sub_id,
                )

        elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
            sub_id = get("subscription")
            customer_id = get("customer")
            lines = get("lines", {}) or {}
            period_start = period_end = None
            try:
                line0 = (lines.get("data") or [{}])[0] if isinstance(lines, dict) else {}
                period = (line0 or {}).get("period") or {}
                period_start = _period_dt(period.get("start"))
                period_end = _period_dt(period.get("end"))
            except Exception:
                pass
            sub = await _activate_subscription_row(
                db,
                client_id=client_id,
                plan_id=plan_id,
                gateway=PaymentGateway.STRIPE.value,
                stripe_subscription_id=sub_id,
                stripe_customer_id=customer_id,
                period_start=period_start,
                period_end=period_end,
            )
            await db.commit()
            _provision_usage(
                client_id or (sub.client_id if sub else None),
                plan_id or (sub.plan_id if sub else None),
                period_end,
                sub_id,
            )

        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.resumed",
        ):
            sub_id = get("id")
            status_raw = (get("status") or "").lower()
            paused = bool(get("pause_collection"))
            period_start = _period_dt(get("current_period_start"))
            period_end = _period_dt(get("current_period_end"))
            sub = await _find_subscription_by_gateway_id(db, stripe_id=sub_id)
            if sub:
                if paused:
                    sub.status = SubscriptionStatus.PAUSED
                elif status_raw in ("active", "trialing"):
                    sub.status = SubscriptionStatus.ACTIVE
                elif status_raw == "past_due":
                    sub.status = SubscriptionStatus.PAST_DUE
                if period_start:
                    sub.current_period_start = period_start
                if period_end:
                    sub.current_period_end = period_end
                sub.updated_at = datetime.utcnow()
                await db.commit()
                if sub.status == SubscriptionStatus.ACTIVE:
                    _provision_usage(sub.client_id, sub.plan_id, period_end, sub_id, reset=False)

        elif event_type in ("customer.subscription.deleted", "customer.subscription.paused"):
            sub_id = get("id")
            sub = await _find_subscription_by_gateway_id(db, stripe_id=sub_id)
            if sub:
                sub.status = (
                    SubscriptionStatus.PAUSED
                    if event_type.endswith("paused")
                    else SubscriptionStatus.CANCELLED
                )
                if event_type.endswith("deleted"):
                    sub.ended_at = datetime.utcnow()
                sub.updated_at = datetime.utcnow()
                await db.commit()
    except Exception as e:  # never 500 a webhook for a downstream hiccup
        logger.error(f"Stripe webhook handling error ({event_type}): {e}")

    return {"received": True, "event": event_type}


@router.post("/billing/webhooks/razorpay", tags=["Billing"])
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Razorpay webhook (HMAC-SHA256 verified). 503 if secret missing; never crashes.

    Handled: payment.captured, subscription.activated/charged/halted/cancelled/
    paused/resumed. On a successful pay/renew -> mark the Subscription ACTIVE +
    provision the minute ledger. client_id is read from notes.
    """
    if not _razorpay_configured() or not _razorpay_webhook_configured():
        raise HTTPException(status_code=503, detail="Razorpay gateway not configured")

    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify signature (HMAC) ourselves so we can inspect the full event tree.
    import hashlib
    import hmac
    import json as _json

    try:
        expected = hmac.new(
            (settings.razorpay_webhook_secret or "").encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature mismatch")
        event = _json.loads(payload.decode("utf-8"))
    except Exception as e:
        logger.warning(f"Razorpay webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event.get("event", "")
    payload_tree = event.get("payload", {}) or {}
    sub_entity = (payload_tree.get("subscription", {}) or {}).get("entity", {}) or {}
    pay_entity = (payload_tree.get("payment", {}) or {}).get("entity", {}) or {}

    notes = sub_entity.get("notes") or pay_entity.get("notes") or {}
    client_id = (notes.get("client_id") if isinstance(notes, dict) else None) or None
    plan_id = (notes.get("plan_id") if isinstance(notes, dict) else None) or None
    rzp_sub_id = sub_entity.get("id")
    rzp_customer_id = sub_entity.get("customer_id") or pay_entity.get("customer_id")
    period_start = _period_dt(sub_entity.get("current_start"))
    period_end = _period_dt(sub_entity.get("current_end"))

    try:
        if event_type in ("subscription.activated", "subscription.charged", "subscription.resumed"):
            sub = await _activate_subscription_row(
                db,
                client_id=client_id,
                plan_id=plan_id,
                gateway=PaymentGateway.RAZORPAY.value,
                razorpay_subscription_id=rzp_sub_id,
                razorpay_customer_id=rzp_customer_id,
                period_start=period_start,
                period_end=period_end,
            )
            await db.commit()
            # Both first-activation and renewals start a fresh metered period -> reset usage.
            _provision_usage(
                client_id or (sub.client_id if sub else None),
                plan_id or (sub.plan_id if sub else None),
                period_end,
                rzp_sub_id,
                reset=True,
            )
            # Sales pipeline: paid subscription = deal "won". Best-effort.
            try:
                from app.marketing import sales_pipeline as _sp
                from app.marketing.clients_store import get_client

                _cid_here = client_id or (sub.client_id if sub else None) or ""
                _client_rec = get_client(_cid_here) if _cid_here else {}
                if _client_rec:
                    _sp.upsert_deal(
                        {
                            "phone": _client_rec.get("phone") or "",
                            "email": _client_rec.get("email") or "",
                            "business_name": _client_rec.get("business_name") or _cid_here,
                            "niche": _client_rec.get("niche") or "",
                            "source": "subscription",
                            "plan": plan_id or "",
                        },
                        stage="won",
                    )
            except Exception as _spe:
                logger.debug(f"[billing] sales_pipeline won skip: {_spe}")

        elif event_type == "payment.captured":
            # Phone push: paisa aaya (self-hosted ntfy, gated — best-effort, kabhi block nahi).
            try:
                from app.integrations import ntfy

                _amt = float(pay_entity.get("amount") or 0) / 100.0
                ntfy.push_bg(
                    "Payment aaya 💰",
                    f"₹{_amt:,.0f} captured — client={client_id or '?'} plan={plan_id or '?'}",
                    priority="high",
                    tags=["moneybag"],
                )
            except Exception:
                pass
            # Voice-minute TOP-UP pack (payment-link/order with notes plan_id="topup_*"):
            # plan activate NAHI hota — sirf minutes credit + invoice. (Warna activate_plan
            # client ka plan 'topup_100' kar deta = plan break.)
            if client_id and str(plan_id or "").startswith("topup"):
                try:
                    from app.billing import usage as _usage
                    from app.marketing.packages import topup_pack

                    pack = topup_pack(str(plan_id))
                    minutes = int(pack.get("minutes") or 0)
                    if minutes > 0:
                        _usage.add_topup_minutes(client_id, minutes)
                        amount_inr = float(pay_entity.get("amount") or 0) / 100.0
                        from app.billing import gst_invoice

                        await gst_invoice.on_payment_success(
                            client_id,
                            str(plan_id),
                            payment_ref=str(pay_entity.get("id") or ""),
                            gateway="razorpay",
                            amount_inr=amount_inr or float(pack.get("price_inr") or 0),
                        )
                        logger.info(f"topup credited: client={client_id} +{minutes} min")
                except Exception as te:  # pragma: no cover - defensive
                    logger.warning(f"topup credit failed for {client_id}: {te}")
            # Qualified-LEAD top-up pack (Product 2: voice agent, ADR-009) —
            # notes plan_id="lead_pack_10" + band. Plan activate NAHI hota.
            elif client_id and str(plan_id or "").startswith("lead_pack"):
                try:
                    from app.billing import lead_usage as _lead_usage
                    from app.marketing.voice_packages import LEAD_TOPUP_PACK, lead_topup_price

                    band = str((notes or {}).get("band") or "A").upper()
                    leads = int(LEAD_TOPUP_PACK.get("leads") or 10)
                    if _lead_usage.add_topup_leads(
                        client_id, leads, ref=str(pay_entity.get("id") or "")
                    ):
                        amount_inr = float(pay_entity.get("amount") or 0) / 100.0
                        from app.billing import gst_invoice

                        await gst_invoice.on_payment_success(
                            client_id,
                            str(plan_id),
                            payment_ref=str(pay_entity.get("id") or ""),
                            gateway="razorpay",
                            amount_inr=amount_inr or float(lead_topup_price(band)),
                        )
                        logger.info(f"lead pack credited: client={client_id} +{leads} leads")
                except Exception as te:  # pragma: no cover - defensive
                    logger.warning(f"lead pack credit failed for {client_id}: {te}")
            # One-off captured payment (e.g. order-based checkout / annual prepay).
            elif client_id:
                sub = await _activate_subscription_row(
                    db,
                    client_id=client_id,
                    plan_id=plan_id,
                    gateway=PaymentGateway.RAZORPAY.value,
                    period_end=period_end,
                )
                await db.commit()
                _provision_usage(
                    client_id, plan_id or (sub.plan_id if sub else None), period_end, rzp_sub_id
                )
                # Lifecycle nurture: trial/free → paid conversion signal.
                # run_due() already does paid-check internally — yahan enroll se converted hoga.
                try:
                    from app.marketing import lifecycle_nurture as _ln

                    _ln.enroll(client_id)  # idempotent — already enrolled = no-op
                except Exception as _lne:
                    logger.debug(f"[billing] lifecycle enroll skip: {_lne}")
                # Affiliate: referral code se aaya tha to commission mark karo.
                try:
                    from app.marketing.affiliate import record_referral
                    from app.marketing.clients_store import get_client

                    _crec = get_client(client_id) or {}
                    _rcode = (_crec.get("ref_code") or "").strip()
                    if _rcode:
                        record_referral(
                            _rcode,
                            {
                                "client_id": client_id,
                                "plan": plan_id or "",
                                "status": "paid",
                            },
                        )
                except Exception as _afe:
                    logger.debug(f"[billing] affiliate paid record skip: {_afe}")

        elif event_type in ("subscription.halted", "subscription.cancelled"):
            sub = await _find_subscription_by_gateway_id(db, razorpay_id=rzp_sub_id)
            if sub:
                sub.status = (
                    SubscriptionStatus.PAST_DUE
                    if event_type.endswith("halted")
                    else SubscriptionStatus.CANCELLED
                )
                if event_type.endswith("cancelled"):
                    sub.ended_at = datetime.utcnow()
                sub.updated_at = datetime.utcnow()
                await db.commit()

        elif event_type == "subscription.paused":
            sub = await _find_subscription_by_gateway_id(db, razorpay_id=rzp_sub_id)
            if sub:
                sub.status = SubscriptionStatus.PAUSED
                sub.updated_at = datetime.utcnow()
                await db.commit()
    except Exception as e:  # never 500 a webhook
        logger.error(f"Razorpay webhook handling error ({event_type}): {e}")

    return {"received": True, "event": event_type}
