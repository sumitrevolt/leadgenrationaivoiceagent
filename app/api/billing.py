"""
Billing API Router
Endpoints for subscription management, payments, and invoices
"""
from typing import Optional, List
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import uuid

from app.models.base import get_async_db
from app.models.payment import (
    Subscription, Payment, Invoice, PaymentMethod, UsageRecord,
    PaymentGateway, SubscriptionStatus, PaymentStatus, InvoiceStatus,
    BillingCycle, PricingPlanModel
)
from app.billing.subscription import PRICING_PLANS, billing_manager
from app.billing.payment_gateway import PaymentGatewayFactory, get_payment_gateway
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


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
    features: List[str]
    quarterly_discount: float
    yearly_discount: float


class CreateCheckoutRequest(BaseModel):
    """Create checkout session request"""
    plan_id: str
    billing_cycle: str = "monthly"
    success_url: str
    cancel_url: str
    currency: Optional[str] = None


class CheckoutResponse(BaseModel):
    """Checkout session response"""
    checkout_url: Optional[str] = None
    order_id: Optional[str] = None
    session_id: Optional[str] = None
    key_id: Optional[str] = None  # For Razorpay
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
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    trial_ends_at: Optional[str] = None
    usage: dict
    payment_gateway: Optional[str] = None


class CancelSubscriptionRequest(BaseModel):
    """Cancel subscription request"""
    reason: Optional[str] = None
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
    due_date: Optional[str] = None
    pdf_url: Optional[str] = None
    hosted_url: Optional[str] = None


class UsageResponse(BaseModel):
    """Usage statistics response"""
    calls_used: int
    calls_limit: int | str
    calls_remaining: int | str
    leads_generated: int
    leads_limit: int | str
    leads_remaining: int | str
    appointments_booked: int
    period_start: Optional[str] = None
    period_end: Optional[str] = None


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

@router.get("/billing/plans", response_model=List[PlanResponse], tags=["Billing"])
async def get_pricing_plans():
    """
    Get all available pricing plans
    """
    plans = []
    for plan in PRICING_PLANS.values():
        plans.append(PlanResponse(
            id=plan.id,
            name=plan.name,
            pricing_model=plan.pricing_model.value,
            monthly_price=float(plan.monthly_price),
            calls_per_month=plan.calls_per_month if plan.calls_per_month > 0 else "Unlimited",
            leads_per_month=plan.leads_per_month if plan.leads_per_month > 0 else "Unlimited",
            concurrent_campaigns=plan.concurrent_campaigns if plan.concurrent_campaigns > 0 else "Unlimited",
            features=plan.features,
            quarterly_discount=plan.quarterly_discount * 100,
            yearly_discount=plan.yearly_discount * 100
        ))
    
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
        concurrent_campaigns=plan.concurrent_campaigns if plan.concurrent_campaigns > 0 else "Unlimited",
        features=plan.features,
        quarterly_discount=plan.quarterly_discount * 100,
        yearly_discount=plan.yearly_discount * 100
    )


@router.get("/billing/plans/{plan_id}/pricing", tags=["Billing"])
async def calculate_plan_pricing(
    plan_id: str,
    billing_cycle: str = Query("monthly", pattern="^(monthly|quarterly|yearly)$")
):
    """
    Calculate pricing for a plan with discounts
    """
    from app.billing.subscription import BillingCycle as BC
    
    cycle_map = {
        "monthly": BC.MONTHLY,
        "quarterly": BC.QUARTERLY,
        "yearly": BC.YEARLY
    }
    
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
        "currency": "INR"
    }


@router.post("/billing/checkout", response_model=CheckoutResponse, tags=["Billing"])
async def create_checkout_session(
    request: CreateCheckoutRequest,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
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
    pricing = billing_manager.calculate_price(request.plan_id, cycle_map.get(request.billing_cycle, BC.MONTHLY))
    
    amount = pricing["total"]
    currency = request.currency or settings.default_currency
    
    # Get appropriate gateway
    gateway = get_payment_gateway(currency=currency)
    
    try:
        # Check if customer exists, create if not
        # In production, get customer from DB
        customer_result = await gateway.create_customer(
            email=f"client_{client_id}@example.com",  # Replace with actual email
            name=f"Client {client_id}",
            metadata={"client_id": client_id}
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
                "type": "subscription"
            }
        )
        
        return CheckoutResponse(
            checkout_url=result.get("checkout_url"),
            order_id=result.get("order_id"),
            session_id=result.get("session_id"),
            key_id=result.get("key_id"),
            amount=float(amount),
            currency=currency,
            gateway=result["gateway"]
        )
        
    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/billing/verify-payment", tags=["Billing"])
async def verify_razorpay_payment(
    request: VerifyPaymentRequest,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Verify Razorpay payment signature (called from frontend after payment)
    """
    from app.billing.payment_gateway import get_razorpay_gateway
    
    try:
        gateway = get_razorpay_gateway()
        is_valid = await gateway.verify_payment_signature(
            order_id=request.order_id,
            payment_id=request.payment_id,
            signature=request.signature
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
            completed_at=datetime.utcnow()
        )
        db.add(payment)
        await db.commit()
        
        return {
            "success": True,
            "payment_id": request.payment_id,
            "message": "Payment verified successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment verification failed: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed")


@router.get("/billing/subscription", response_model=SubscriptionResponse, tags=["Billing"])
async def get_current_subscription(
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current subscription for a client
    """
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id == client_id,
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE])
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
        current_period_start=subscription.current_period_start.isoformat() if subscription.current_period_start else None,
        current_period_end=subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        trial_ends_at=subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
        usage={
            "calls_used": subscription.calls_used,
            "calls_limit": subscription.calls_limit or "unlimited",
            "leads_generated": subscription.leads_generated,
            "leads_limit": subscription.leads_limit or "unlimited",
            "appointments_booked": subscription.appointments_booked
        },
        payment_gateway=subscription.payment_gateway.value if subscription.payment_gateway else None
    )


@router.post("/billing/subscription/cancel", tags=["Billing"])
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Cancel current subscription
    """
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id == client_id,
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE])
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
                cancel_at_period_end=not request.cancel_immediately
            )
        elif subscription.razorpay_subscription_id:
            from app.billing.payment_gateway import get_razorpay_gateway
            gateway = get_razorpay_gateway()
            await gateway.cancel_subscription(
                subscription.razorpay_subscription_id,
                cancel_at_period_end=not request.cancel_immediately
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
            "effective_until": subscription.current_period_end.isoformat() if not request.cancel_immediately else datetime.utcnow().isoformat(),
            "message": "Subscription cancelled successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to cancel subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/billing/invoices", response_model=List[InvoiceResponse], tags=["Billing"])
async def get_invoices(
    client_id: str = Query(..., description="Client ID"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db)
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
            hosted_url=inv.hosted_invoice_url
        )
        for inv in invoices
    ]


@router.get("/billing/invoices/{invoice_id}", tags=["Billing"])
async def get_invoice_details(
    invoice_id: str,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get detailed invoice information
    """
    result = await db.execute(
        select(Invoice)
        .where(and_(Invoice.id == invoice_id, Invoice.client_id == client_id))
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    return invoice.to_dict()


@router.get("/billing/usage", response_model=UsageResponse, tags=["Billing"])
async def get_current_usage(
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current billing period usage for a client
    """
    # Get active subscription
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id == client_id,
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE])
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
            calls_remaining=max(0, calls_limit - subscription.calls_used) if calls_limit > 0 else "Unlimited",
            leads_generated=subscription.leads_generated,
            leads_limit=leads_limit if leads_limit > 0 else "Unlimited",
            leads_remaining=max(0, leads_limit - subscription.leads_generated) if leads_limit > 0 else "Unlimited",
            appointments_booked=subscription.appointments_booked,
            period_start=subscription.current_period_start.isoformat() if subscription.current_period_start else None,
            period_end=subscription.current_period_end.isoformat() if subscription.current_period_end else None
        )
    
    # No subscription - return zeros
    return UsageResponse(
        calls_used=0,
        calls_limit=0,
        calls_remaining=0,
        leads_generated=0,
        leads_limit=0,
        leads_remaining=0,
        appointments_booked=0
    )


@router.get("/billing/payment-methods", tags=["Billing"])
async def get_payment_methods(
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get saved payment methods for a client
    """
    result = await db.execute(
        select(PaymentMethod)
        .where(and_(PaymentMethod.client_id == client_id, PaymentMethod.is_active == True))
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
    db: AsyncSession = Depends(get_async_db)
):
    """
    Add balance to account (for per-lead pricing model)
    """
    gateway = get_payment_gateway(currency=request.currency)
    
    try:
        # Create customer if needed
        customer_result = await gateway.create_customer(
            email=f"client_{client_id}@example.com",
            name=f"Client {client_id}",
            metadata={"client_id": client_id}
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
                "amount": str(request.amount)
            }
        )
        
        return {
            "checkout_url": result.get("checkout_url"),
            "order_id": result.get("order_id"),
            "amount": request.amount,
            "currency": request.currency,
            "gateway": result["gateway"]
        }
        
    except Exception as e:
        logger.error(f"Failed to create balance top-up: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/billing/balance", tags=["Billing"])
async def get_account_balance(
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
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
        "currency": subscription.currency if subscription else settings.default_currency
    }


@router.get("/billing/usage/history", tags=["Billing"])
async def get_usage_history(
    client_id: str = Query(..., description="Client ID"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get usage history for the specified number of days
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(UsageRecord)
        .where(
            and_(
                UsageRecord.client_id == client_id,
                UsageRecord.usage_date >= start_date
            )
        )
        .order_by(UsageRecord.usage_date.desc())
    )
    records = result.scalars().all()
    
    return [record.to_dict() for record in records]


@router.post("/billing/subscription/upgrade", tags=["Billing"])
async def upgrade_subscription(
    new_plan_id: str,
    client_id: str = Query(..., description="Client ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Upgrade subscription to a new plan
    """
    # Get current subscription
    result = await db.execute(
        select(Subscription)
        .where(
            and_(
                Subscription.client_id == client_id,
                Subscription.status.in_([SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE])
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
        "message": "Subscription upgraded successfully"
    }
