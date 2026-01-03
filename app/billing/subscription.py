"""
Billing & Subscription Module
Handles recurring subscriptions and per-lead pricing

Pricing Models:
1. Subscription-based (Monthly plans)
2. Per-lead pricing (Pay per qualified lead)
3. Hybrid (Base subscription + per-lead charges)
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class PricingModel(Enum):
    """Pricing model types"""
    SUBSCRIPTION = "subscription"
    PER_LEAD = "per_lead"
    HYBRID = "hybrid"


class BillingCycle(Enum):
    """Billing cycle options"""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class SubscriptionStatus(Enum):
    """Subscription status"""
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class PaymentStatus(Enum):
    """Payment status"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class PricingPlan:
    """Pricing plan configuration"""
    id: str
    name: str
    pricing_model: PricingModel
    
    # Subscription pricing (monthly)
    monthly_price: Decimal = Decimal("0")
    
    # Per-lead pricing
    price_per_qualified_lead: Decimal = Decimal("0")
    price_per_appointment: Decimal = Decimal("0")
    price_per_call: Decimal = Decimal("0")  # For metered calling
    
    # Limits
    calls_per_month: int = 0  # 0 = unlimited
    leads_per_month: int = 0
    concurrent_campaigns: int = 1
    
    # Features
    features: List[str] = field(default_factory=list)
    
    # Discounts
    quarterly_discount: float = 0.10  # 10% off
    yearly_discount: float = 0.20  # 20% off
    
    # Trial
    trial_days: int = 7
    trial_calls: int = 100


# =============================================================================
# PRICING PLANS
# =============================================================================

PRICING_PLANS = {
    "trial": PricingPlan(
        id="trial",
        name="7-Day Free Trial",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("0"),
        calls_per_month=100,
        leads_per_month=50,
        concurrent_campaigns=1,
        trial_days=7,
        trial_calls=100,
        features=[
            "AI Voice Agent",
            "Basic Analytics",
            "WhatsApp Notifications",
            "Google Sheets Integration",
            "Email Support"
        ]
    ),
    
    "starter": PricingPlan(
        id="starter",
        name="Starter Plan",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("15000"),  # ₹15,000/month
        calls_per_month=500,
        leads_per_month=200,
        concurrent_campaigns=2,
        features=[
            "AI Voice Agent",
            "Full Analytics Dashboard",
            "WhatsApp Automation",
            "CRM Integration (HubSpot/Zoho)",
            "Google Sheets",
            "Basic Objection Handling",
            "Email + Chat Support",
            "1 Industry Script"
        ]
    ),
    
    "growth": PricingPlan(
        id="growth",
        name="Growth Plan",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("25000"),  # ₹25,000/month
        calls_per_month=2000,
        leads_per_month=800,
        concurrent_campaigns=5,
        features=[
            "Everything in Starter",
            "Advanced AI Brain",
            "ML-Powered Objection Handling",
            "Multi-Language Support",
            "Call Transfer to Reps",
            "Priority Support",
            "5 Industry Scripts",
            "Custom Voice Training"
        ]
    ),
    
    "enterprise": PricingPlan(
        id="enterprise",
        name="Enterprise Plan",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("50000"),  # ₹50,000/month
        calls_per_month=0,  # Unlimited
        leads_per_month=0,  # Unlimited
        concurrent_campaigns=0,  # Unlimited
        features=[
            "Everything in Growth",
            "Unlimited Calls",
            "White-Label Dashboard",
            "Custom API Integration",
            "Dedicated Account Manager",
            "Custom AI Training",
            "SLA Guarantee",
            "24/7 Phone Support"
        ]
    ),
    
    "per_lead": PricingPlan(
        id="per_lead",
        name="Pay Per Lead",
        pricing_model=PricingModel.PER_LEAD,
        price_per_qualified_lead=Decimal("25"),  # ₹25 per qualified lead
        price_per_appointment=Decimal("50"),  # ₹50 per appointment
        price_per_call=Decimal("2"),  # ₹2 per call
        features=[
            "No Monthly Commitment",
            "Pay for Results Only",
            "All Features Included",
            "Minimum ₹5,000 Top-up"
        ]
    ),
    
    "hybrid_starter": PricingPlan(
        id="hybrid_starter",
        name="Hybrid Starter",
        pricing_model=PricingModel.HYBRID,
        monthly_price=Decimal("10000"),  # ₹10,000/month base
        price_per_qualified_lead=Decimal("15"),  # ₹15 per qualified lead above limit
        price_per_appointment=Decimal("30"),  # ₹30 per appointment above limit
        calls_per_month=300,  # Included
        leads_per_month=100,  # Included
        features=[
            "Base 300 calls included",
            "Base 100 leads included",
            "Pay extra only when you exceed",
            "All Growth features"
        ]
    ),
}


@dataclass
class UsageRecord:
    """Track usage for billing"""
    tenant_id: str
    date: datetime
    calls_made: int = 0
    qualified_leads: int = 0
    appointments_booked: int = 0
    call_minutes: float = 0


@dataclass
class Invoice:
    """Invoice for billing"""
    id: str
    tenant_id: str
    subscription_id: str
    billing_period_start: datetime
    billing_period_end: datetime
    
    # Amounts
    base_amount: Decimal = Decimal("0")
    usage_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    
    # Usage breakdown
    usage_breakdown: Dict[str, Any] = field(default_factory=dict)
    
    # Status
    status: PaymentStatus = PaymentStatus.PENDING
    payment_due_date: datetime = None
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Subscription:
    """Tenant subscription"""
    id: str
    tenant_id: str
    plan_id: str
    status: SubscriptionStatus
    billing_cycle: BillingCycle
    
    # Dates
    started_at: datetime
    trial_ends_at: Optional[datetime] = None
    current_period_start: datetime = None
    current_period_end: datetime = None
    cancelled_at: Optional[datetime] = None
    
    # Usage
    calls_used: int = 0
    leads_generated: int = 0
    appointments_booked: int = 0
    
    # Payment
    last_payment: Optional[datetime] = None
    next_payment: Optional[datetime] = None
    payment_method: Optional[str] = None
    
    # Balance (for per-lead model)
    balance: Decimal = Decimal("0")


class BillingManager:
    """
    Manages billing and subscriptions
    """
    
    def __init__(self):
        self.subscriptions: Dict[str, Subscription] = {}
        self.invoices: Dict[str, Invoice] = {}
        self.usage_records: List[UsageRecord] = []
        
        self.plans = PRICING_PLANS
        self.tax_rate = Decimal("0.18")  # 18% GST
        
        logger.info("💰 Billing Manager initialized")
    
    def get_plan(self, plan_id: str) -> Optional[PricingPlan]:
        """Get pricing plan by ID"""
        return self.plans.get(plan_id)
    
    def calculate_price(
        self,
        plan_id: str,
        billing_cycle: BillingCycle = BillingCycle.MONTHLY
    ) -> Dict[str, Decimal]:
        """
        Calculate price with discounts
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return {}
        
        base_price = plan.monthly_price
        
        if billing_cycle == BillingCycle.QUARTERLY:
            months = 3
            discount_rate = Decimal(str(plan.quarterly_discount))
        elif billing_cycle == BillingCycle.YEARLY:
            months = 12
            discount_rate = Decimal(str(plan.yearly_discount))
        else:
            months = 1
            discount_rate = Decimal("0")
        
        subtotal = base_price * months
        discount = subtotal * discount_rate
        taxable = subtotal - discount
        tax = taxable * self.tax_rate
        total = taxable + tax
        
        return {
            "subtotal": subtotal,
            "discount": discount,
            "discount_percentage": discount_rate * 100,
            "taxable": taxable,
            "tax": tax,
            "tax_rate": self.tax_rate * 100,
            "total": total,
            "per_month": total / months
        }
    
    async def create_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        billing_cycle: BillingCycle = BillingCycle.MONTHLY,
        start_with_trial: bool = True
    ) -> Subscription:
        """
        Create a new subscription
        """
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Invalid plan: {plan_id}")
        
        now = datetime.now()
        subscription_id = str(uuid.uuid4())
        
        # Determine trial period
        if start_with_trial and plan.trial_days > 0:
            status = SubscriptionStatus.TRIAL
            trial_ends = now + timedelta(days=plan.trial_days)
            period_end = trial_ends
        else:
            status = SubscriptionStatus.ACTIVE
            trial_ends = None
            if billing_cycle == BillingCycle.MONTHLY:
                period_end = now + timedelta(days=30)
            elif billing_cycle == BillingCycle.QUARTERLY:
                period_end = now + timedelta(days=90)
            else:
                period_end = now + timedelta(days=365)
        
        subscription = Subscription(
            id=subscription_id,
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            billing_cycle=billing_cycle,
            started_at=now,
            trial_ends_at=trial_ends,
            current_period_start=now,
            current_period_end=period_end,
            next_payment=period_end if status == SubscriptionStatus.ACTIVE else trial_ends
        )
        
        self.subscriptions[subscription_id] = subscription
        logger.info(f"✅ Created subscription {subscription_id} for tenant {tenant_id}")
        
        return subscription
    
    def record_usage(
        self,
        tenant_id: str,
        calls: int = 0,
        qualified_leads: int = 0,
        appointments: int = 0,
        call_minutes: float = 0
    ):
        """
        Record usage for a tenant
        """
        record = UsageRecord(
            tenant_id=tenant_id,
            date=datetime.now(),
            calls_made=calls,
            qualified_leads=qualified_leads,
            appointments_booked=appointments,
            call_minutes=call_minutes
        )
        self.usage_records.append(record)
        
        # Update subscription counters
        for sub in self.subscriptions.values():
            if sub.tenant_id == tenant_id:
                sub.calls_used += calls
                sub.leads_generated += qualified_leads
                sub.appointments_booked += appointments
    
    def check_limits(self, tenant_id: str) -> Dict[str, Any]:
        """
        Check if tenant is within their plan limits
        """
        subscription = self._get_tenant_subscription(tenant_id)
        if not subscription:
            return {"error": "No subscription found"}
        
        plan = self.get_plan(subscription.plan_id)
        if not plan:
            return {"error": "Invalid plan"}
        
        # Check limits
        calls_limit = plan.calls_per_month if plan.calls_per_month > 0 else float('inf')
        leads_limit = plan.leads_per_month if plan.leads_per_month > 0 else float('inf')
        
        return {
            "calls_used": subscription.calls_used,
            "calls_limit": calls_limit,
            "calls_remaining": max(0, calls_limit - subscription.calls_used),
            "calls_exceeded": subscription.calls_used > calls_limit,
            "leads_generated": subscription.leads_generated,
            "leads_limit": leads_limit,
            "leads_remaining": max(0, leads_limit - subscription.leads_generated),
            "leads_exceeded": subscription.leads_generated > leads_limit,
            "plan": plan.name,
            "status": subscription.status.value
        }
    
    def _get_tenant_subscription(self, tenant_id: str) -> Optional[Subscription]:
        """Get active subscription for tenant"""
        for sub in self.subscriptions.values():
            if sub.tenant_id == tenant_id and sub.status in [
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.ACTIVE
            ]:
                return sub
        return None
    
    async def generate_invoice(
        self,
        tenant_id: str,
        subscription_id: str
    ) -> Invoice:
        """
        Generate invoice for subscription period
        """
        subscription = self.subscriptions.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription not found: {subscription_id}")
        
        plan = self.get_plan(subscription.plan_id)
        
        # Calculate amounts
        pricing = self.calculate_price(subscription.plan_id, subscription.billing_cycle)
        
        # Calculate usage charges for hybrid/per-lead
        usage_amount = Decimal("0")
        usage_breakdown = {}
        
        if plan.pricing_model in [PricingModel.PER_LEAD, PricingModel.HYBRID]:
            # Get usage for period
            period_usage = self._get_period_usage(
                tenant_id,
                subscription.current_period_start,
                subscription.current_period_end
            )
            
            # Calculate excess usage for hybrid
            if plan.pricing_model == PricingModel.HYBRID:
                excess_leads = max(0, period_usage["leads"] - plan.leads_per_month)
                excess_appointments = max(0, period_usage["appointments"] - 0)  # No included appointments
                
                usage_amount = (
                    Decimal(str(excess_leads)) * plan.price_per_qualified_lead +
                    Decimal(str(excess_appointments)) * plan.price_per_appointment
                )
                
                usage_breakdown = {
                    "excess_leads": excess_leads,
                    "lead_charge": str(plan.price_per_qualified_lead),
                    "excess_appointments": excess_appointments,
                    "appointment_charge": str(plan.price_per_appointment)
                }
            
            # Pure per-lead model
            else:
                usage_amount = (
                    Decimal(str(period_usage["calls"])) * plan.price_per_call +
                    Decimal(str(period_usage["leads"])) * plan.price_per_qualified_lead +
                    Decimal(str(period_usage["appointments"])) * plan.price_per_appointment
                )
                
                usage_breakdown = {
                    "calls": period_usage["calls"],
                    "call_charge": str(plan.price_per_call),
                    "leads": period_usage["leads"],
                    "lead_charge": str(plan.price_per_qualified_lead),
                    "appointments": period_usage["appointments"],
                    "appointment_charge": str(plan.price_per_appointment)
                }
        
        # Calculate totals
        base_amount = pricing.get("subtotal", Decimal("0"))
        discount = pricing.get("discount", Decimal("0"))
        taxable = base_amount - discount + usage_amount
        tax = taxable * self.tax_rate
        total = taxable + tax
        
        invoice = Invoice(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            billing_period_start=subscription.current_period_start,
            billing_period_end=subscription.current_period_end,
            base_amount=base_amount,
            usage_amount=usage_amount,
            discount_amount=discount,
            tax_amount=tax,
            total_amount=total,
            usage_breakdown=usage_breakdown,
            payment_due_date=subscription.current_period_end + timedelta(days=7)
        )
        
        self.invoices[invoice.id] = invoice
        logger.info(f"📄 Generated invoice {invoice.id}: ₹{total}")
        
        return invoice
    
    def _get_period_usage(
        self,
        tenant_id: str,
        start: datetime,
        end: datetime
    ) -> Dict[str, int]:
        """Get usage for a billing period"""
        calls = 0
        leads = 0
        appointments = 0
        
        for record in self.usage_records:
            if (record.tenant_id == tenant_id and 
                start <= record.date <= end):
                calls += record.calls_made
                leads += record.qualified_leads
                appointments += record.appointments_booked
        
        return {
            "calls": calls,
            "leads": leads,
            "appointments": appointments
        }
    
    async def process_payment(
        self,
        invoice_id: str,
        payment_method: str,
        payment_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process payment for an invoice
        In production, integrate with Razorpay/Stripe
        """
        invoice = self.invoices.get(invoice_id)
        if not invoice:
            return {"success": False, "error": "Invoice not found"}
        
        # Simulate payment processing
        # In production: Razorpay/Stripe API call here
        
        invoice.status = PaymentStatus.COMPLETED
        invoice.paid_at = datetime.now()
        invoice.payment_method = payment_method
        
        # Update subscription
        subscription = self.subscriptions.get(invoice.subscription_id)
        if subscription:
            subscription.last_payment = datetime.now()
            subscription.status = SubscriptionStatus.ACTIVE
            
            # Extend period
            if subscription.billing_cycle == BillingCycle.MONTHLY:
                subscription.current_period_end += timedelta(days=30)
            elif subscription.billing_cycle == BillingCycle.QUARTERLY:
                subscription.current_period_end += timedelta(days=90)
            else:
                subscription.current_period_end += timedelta(days=365)
            
            subscription.next_payment = subscription.current_period_end
            
            # Reset usage counters
            subscription.calls_used = 0
            subscription.leads_generated = 0
            subscription.appointments_booked = 0
        
        logger.info(f"✅ Payment processed for invoice {invoice_id}")
        
        return {
            "success": True,
            "invoice_id": invoice_id,
            "amount_paid": str(invoice.total_amount),
            "next_billing_date": subscription.next_payment.isoformat() if subscription else None
        }
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        reason: str = ""
    ) -> Dict[str, Any]:
        """Cancel a subscription"""
        subscription = self.subscriptions.get(subscription_id)
        if not subscription:
            return {"success": False, "error": "Subscription not found"}
        
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.now()
        
        logger.info(f"❌ Subscription {subscription_id} cancelled. Reason: {reason}")
        
        return {
            "success": True,
            "subscription_id": subscription_id,
            "effective_until": subscription.current_period_end.isoformat()
        }
    
    def get_tenant_billing_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get billing summary for a tenant"""
        subscription = self._get_tenant_subscription(tenant_id)
        if not subscription:
            return {"error": "No active subscription"}
        
        plan = self.get_plan(subscription.plan_id)
        limits = self.check_limits(tenant_id)
        
        # Get recent invoices
        tenant_invoices = [
            inv for inv in self.invoices.values()
            if inv.tenant_id == tenant_id
        ]
        tenant_invoices.sort(key=lambda x: x.created_at, reverse=True)
        
        return {
            "subscription": {
                "id": subscription.id,
                "plan": plan.name,
                "status": subscription.status.value,
                "billing_cycle": subscription.billing_cycle.value,
                "current_period_start": subscription.current_period_start.isoformat(),
                "current_period_end": subscription.current_period_end.isoformat(),
                "next_payment": subscription.next_payment.isoformat() if subscription.next_payment else None
            },
            "usage": {
                "calls_used": subscription.calls_used,
                "calls_limit": limits.get("calls_limit", "Unlimited"),
                "leads_generated": subscription.leads_generated,
                "leads_limit": limits.get("leads_limit", "Unlimited"),
                "appointments": subscription.appointments_booked
            },
            "pricing": {
                "monthly_price": str(plan.monthly_price),
                "per_lead_price": str(plan.price_per_qualified_lead),
                "per_appointment_price": str(plan.price_per_appointment)
            },
            "recent_invoices": [
                {
                    "id": inv.id,
                    "amount": str(inv.total_amount),
                    "status": inv.status.value,
                    "date": inv.created_at.isoformat()
                }
                for inv in tenant_invoices[:5]
            ]
        }


# Global billing manager
billing_manager = BillingManager()


# =============================================================================
# API ENDPOINTS (FastAPI routes)
# =============================================================================

"""
# Add these routes to your FastAPI app

from fastapi import APIRouter, HTTPException
from app.billing.subscription import billing_manager, PRICING_PLANS

router = APIRouter(prefix="/billing", tags=["Billing"])

@router.get("/plans")
async def get_pricing_plans():
    return {
        "plans": [
            {
                "id": plan.id,
                "name": plan.name,
                "pricing_model": plan.pricing_model.value,
                "monthly_price": str(plan.monthly_price),
                "calls_per_month": plan.calls_per_month or "Unlimited",
                "leads_per_month": plan.leads_per_month or "Unlimited",
                "features": plan.features,
                "pricing": billing_manager.calculate_price(plan.id)
            }
            for plan in PRICING_PLANS.values()
        ]
    }

@router.post("/subscribe")
async def create_subscription(
    tenant_id: str,
    plan_id: str,
    billing_cycle: str = "monthly"
):
    cycle = BillingCycle(billing_cycle)
    subscription = await billing_manager.create_subscription(
        tenant_id=tenant_id,
        plan_id=plan_id,
        billing_cycle=cycle
    )
    return {"subscription": subscription}

@router.get("/usage/{tenant_id}")
async def get_usage(tenant_id: str):
    return billing_manager.check_limits(tenant_id)

@router.get("/summary/{tenant_id}")
async def get_billing_summary(tenant_id: str):
    return billing_manager.get_tenant_billing_summary(tenant_id)
"""
