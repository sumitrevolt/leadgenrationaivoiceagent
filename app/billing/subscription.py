"""
Billing & Subscription Module
Handles recurring subscriptions and per-lead pricing

Pricing Models:
1. Subscription-based (Monthly plans)
2. Per-lead pricing (Pay per qualified lead)
3. Hybrid (Base subscription + per-lead charges)
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

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
    features: list[str] = field(default_factory=list)
    feature_groups: list = field(default_factory=list)  # grouped view for collapsible pricing UI

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
            "Email Support",
        ],
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
            "1 Industry Script",
        ],
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
            "Custom Voice Training",
        ],
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
            "24/7 Phone Support",
        ],
    ),
    # NOTE (ADR-009, 2026-06-11): legacy "per_lead" (₹25/lead) + "hybrid_starter"
    # (per-lead overage) plans REMOVED — per-lead pricing system retired.
    # Voice product plans ab _sync_voice_plans() se aate hain (flat-monthly per niche-band model, updated 2026-06-12).
    # =============================================================================
    # B2B INTELLIGENCE PLATFORM - CREDIT-BASED PLANS
    # =============================================================================
    "data_starter": PricingPlan(
        id="data_starter",
        name="Data Starter",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("5000"),  # ₹5,000/month
        leads_per_month=1000,  # 1000 credits
        concurrent_campaigns=1,
        features=[
            "1,000 Data Credits/month",
            "Company Search API",
            "Data Enrichment (2 credits/company)",
            "CSV Export",
            "1 API Key",
            "Email Support",
        ],
    ),
    "data_growth": PricingPlan(
        id="data_growth",
        name="Data Growth",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("15000"),  # ₹15,000/month
        leads_per_month=5000,  # 5000 credits
        concurrent_campaigns=3,
        features=[
            "5,000 Data Credits/month",
            "Everything in Starter",
            "Market Reports (Basic)",
            "CRM Integration",
            "5 API Keys",
            "Priority Support",
        ],
    ),
    "data_pro": PricingPlan(
        id="data_pro",
        name="Data Pro",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("35000"),  # ₹35,000/month
        leads_per_month=15000,  # 15000 credits
        concurrent_campaigns=10,
        features=[
            "15,000 Data Credits/month",
            "Everything in Growth",
            "Market Reports (Detailed)",
            "Webhook Notifications",
            "Unlimited API Keys",
            "Dedicated Support",
        ],
    ),
    "data_enterprise": PricingPlan(
        id="data_enterprise",
        name="Data Enterprise",
        pricing_model=PricingModel.SUBSCRIPTION,
        monthly_price=Decimal("75000"),  # ₹75,000/month
        leads_per_month=0,  # Unlimited
        concurrent_campaigns=0,  # Unlimited
        features=[
            "Unlimited Data Credits",
            "Everything in Pro",
            "Custom Reports",
            "White-Label API",
            "SLA Guarantee",
            "Dedicated Account Manager",
        ],
    ),
    "data_payg": PricingPlan(
        id="data_payg",
        name="Pay As You Go",
        pricing_model=PricingModel.PER_LEAD,
        price_per_qualified_lead=Decimal("5"),  # ₹5 per credit
        features=[
            "No Monthly Commitment",
            "Buy Credits as Needed",
            "All Features Included",
            "Minimum ₹2,500 Top-up (500 credits)",
        ],
    ),
}


def _sync_plans_from_packages() -> None:
    """PUBLIC pricing truth = app/marketing/packages.py — yahan ke legacy Cloud-Run-era
    prices (₹15k/25k/50k) ko LIVE marketing prices (999/2499/5999) se OVERRIDE karo aur
    missing 'advanced' plan add karo. (BUG FIX 2026-06-10: /pricing page ₹999 dikhata
    tha par checkout billing_manager se ₹15,000+GST charge karta; 'advanced' checkout
    404 deta.) Yearly discount = 1/6 => 12mo*(5/6) = 10mo = packages price_inr_year
    ("2 mahine free"). Defensive: packages import fail => legacy as-is (kabhi raise nahi).
    """
    try:
        from app.marketing.packages import PACKAGES

        for pkg in PACKAGES:
            key = str(pkg.get("key") or "").strip().lower()
            price = Decimal(str(pkg.get("price_inr_month") or 0))
            if not key or price <= 0:
                continue
            feats = list(pkg.get("features") or [])
            fgroups = list(pkg.get("feature_groups") or [])
            existing = PRICING_PLANS.get(key)
            if existing is not None:
                existing.monthly_price = price
                existing.name = str(pkg.get("name") or existing.name)
                existing.features = feats or existing.features
                existing.feature_groups = fgroups or existing.feature_groups
                existing.yearly_discount = float(Decimal(1) / Decimal(6))
            else:
                PRICING_PLANS[key] = PricingPlan(
                    id=key,
                    name=str(pkg.get("name") or key.title()),
                    pricing_model=PricingModel.SUBSCRIPTION,
                    monthly_price=price,
                    calls_per_month=500 if key == "advanced" else 0,
                    leads_per_month=0,
                    concurrent_campaigns=1,
                    features=feats,
                    feature_groups=fgroups,
                    yearly_discount=float(Decimal(1) / Decimal(6)),
                )
    except Exception:  # pragma: no cover - defensive (legacy prices se chalta rahe)
        pass


def _sync_voice_plans() -> None:
    """AI Voice Calling Agent (Product 2) plans — voice_packages.py truth.

    Flat monthly model (2026-06-12): 7 plan IDs
      voice_a_monthly, voice_b_monthly, voice_c_monthly
      voice_a_annual,  voice_b_annual,  voice_c_annual
      voice_pilot  (free 7-day trial)
    Unlimited calls — lead_usage.py has_lead_quota UNLIMITED_QUOTA gate karta hai.
    Defensive — kabhi raise nahi.
    """
    try:
        from app.marketing.voice_packages import BANDS, PILOT_CALL_CAP, UNLIMITED_QUOTA

        for band, info in BANDS.items():
            # Monthly plan
            pid_m = info["plan_monthly"]
            PRICING_PLANS[pid_m] = PricingPlan(
                id=pid_m,
                name=f"Voice {band} — Monthly",
                pricing_model=PricingModel.SUBSCRIPTION,
                monthly_price=Decimal(str(info["price_month"])),
                calls_per_month=UNLIMITED_QUOTA,
                leads_per_month=UNLIMITED_QUOTA,
                concurrent_campaigns=3,
                features=[f"Band {band} niche — flat monthly, unlimited calls"],
                yearly_discount=0.0,
            )
            # Annual plan
            pid_a = info["plan_annual"]
            PRICING_PLANS[pid_a] = PricingPlan(
                id=pid_a,
                name=f"Voice {band} — Annual",
                pricing_model=PricingModel.SUBSCRIPTION,
                monthly_price=Decimal(str(info["price_month"])),
                calls_per_month=UNLIMITED_QUOTA,
                leads_per_month=UNLIMITED_QUOTA,
                concurrent_campaigns=3,
                features=[f"Band {band} niche — annual, 2 mahine free"],
                yearly_discount=1 / 6,  # 2 of 12 months free
            )

        # Free pilot plan
        PRICING_PLANS["voice_pilot"] = PricingPlan(
            id="voice_pilot",
            name="Voice Pilot — 7 din free",
            pricing_model=PricingModel.SUBSCRIPTION,
            monthly_price=Decimal("0"),
            calls_per_month=PILOT_CALL_CAP,
            leads_per_month=PILOT_CALL_CAP,
            concurrent_campaigns=1,
            features=["7-day free pilot, 50 calls cap"],
            yearly_discount=0.0,
        )
    except Exception:  # pragma: no cover - defensive
        pass


def _sync_combo_plans() -> None:
    """AI Growth Suite (Product 3) plans — combo_packages.py truth.

    Flat monthly model: 7 plan IDs
      combo_starter_monthly, combo_growth_monthly, combo_pro_monthly
      combo_starter_annual,  combo_growth_annual,  combo_pro_annual
      combo_pilot  (free 7-day trial)
    Unlimited calls — lead_usage.py has_lead_quota UNLIMITED_QUOTA gate karta hai.
    Defensive — kabhi raise nahi.
    """
    try:
        from app.marketing.combo_packages import COMBO_TIERS, PILOT_CALL_CAP, UNLIMITED_QUOTA

        for tier_key, t in COMBO_TIERS.items():
            pid_m = t["plan_monthly"]
            PRICING_PLANS[pid_m] = PricingPlan(
                id=pid_m,
                name=f"{t['name']} — Monthly",
                pricing_model=PricingModel.SUBSCRIPTION,
                monthly_price=Decimal(str(t["price_month"])),
                calls_per_month=UNLIMITED_QUOTA,
                leads_per_month=UNLIMITED_QUOTA,
                concurrent_campaigns=5,
                features=[
                    f"Combo {tier_key} — Marketing + Voice {t['voice_band']} band, flat monthly"
                ],
                yearly_discount=0.0,
            )
            pid_a = t["plan_annual"]
            PRICING_PLANS[pid_a] = PricingPlan(
                id=pid_a,
                name=f"{t['name']} — Annual",
                pricing_model=PricingModel.SUBSCRIPTION,
                monthly_price=Decimal(str(t["price_month"])),
                calls_per_month=UNLIMITED_QUOTA,
                leads_per_month=UNLIMITED_QUOTA,
                concurrent_campaigns=5,
                features=[f"Combo {tier_key} — Annual, 2 mahine free"],
                yearly_discount=1 / 6,
            )

        PRICING_PLANS["combo_pilot"] = PricingPlan(
            id="combo_pilot",
            name="Combo Pilot — 7 din free",
            pricing_model=PricingModel.SUBSCRIPTION,
            monthly_price=Decimal("0"),
            calls_per_month=PILOT_CALL_CAP,
            leads_per_month=PILOT_CALL_CAP,
            concurrent_campaigns=1,
            features=["7-day free pilot — marketing + voice dono"],
            yearly_discount=0.0,
        )
    except Exception:  # pragma: no cover - defensive
        pass


_sync_plans_from_packages()
_sync_voice_plans()
_sync_combo_plans()


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
    usage_breakdown: dict[str, Any] = field(default_factory=dict)

    # Status
    status: PaymentStatus = PaymentStatus.PENDING
    payment_due_date: datetime = None
    paid_at: datetime | None = None
    payment_method: str | None = None

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
    trial_ends_at: datetime | None = None
    current_period_start: datetime = None
    current_period_end: datetime = None
    cancelled_at: datetime | None = None

    # Usage
    calls_used: int = 0
    leads_generated: int = 0
    appointments_booked: int = 0

    # Payment
    last_payment: datetime | None = None
    next_payment: datetime | None = None
    payment_method: str | None = None

    # Balance (for per-lead model)
    balance: Decimal = Decimal("0")


class BillingManager:
    """
    Manages billing and subscriptions
    """

    def __init__(self):
        self.subscriptions: dict[str, Subscription] = {}
        self.invoices: dict[str, Invoice] = {}
        self.usage_records: list[UsageRecord] = []

        self.plans = PRICING_PLANS
        self.tax_rate = Decimal("0.18")  # 18% GST

        logger.info("💰 Billing Manager initialized")

    def get_plan(self, plan_id: str) -> PricingPlan | None:
        """Get pricing plan by ID"""
        return self.plans.get(plan_id)

    def calculate_price(
        self, plan_id: str, billing_cycle: BillingCycle = BillingCycle.MONTHLY
    ) -> dict[str, Decimal]:
        """
        Calculate price with discounts
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return {}

        # Suffix-locked plans (voice_*/combo_*) encode their cycle in the id.
        # The annual variant's price is stored as monthly_price + yearly_discount,
        # so it MUST be costed on the YEARLY path — otherwise a checkout that sends
        # billing_cycle="monthly" (the default) for an *_annual plan would charge 1×
        # the monthly figure instead of 10× (a 10× undercharge). Force the cycle to
        # match the plan id so every caller (checkout/pricing/renew) is correct.
        if plan_id.endswith("_annual"):
            billing_cycle = BillingCycle.YEARLY
        elif plan_id.endswith("_monthly"):
            billing_cycle = BillingCycle.MONTHLY

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
        # GST sirf REGISTERED hone par (GST_GSTIN env set). Unregistered (<₹20L services
        # turnover) GST collect karna ILLEGAL hai — tab advertised price hi total hai.
        # (BUG FIX 2026-06-10: pehle hamesha +18% lagta tha.)
        import os as _os

        tax_rate = self.tax_rate if (_os.environ.get("GST_GSTIN", "").strip()) else Decimal("0")
        tax = taxable * tax_rate
        total = taxable + tax

        return {
            "subtotal": subtotal,
            "discount": discount,
            "discount_percentage": discount_rate * 100,
            "taxable": taxable,
            "tax": tax,
            "tax_rate": tax_rate * 100,
            "total": total,
            "per_month": total / months,
        }

    async def create_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        billing_cycle: BillingCycle = BillingCycle.MONTHLY,
        start_with_trial: bool = True,
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
            next_payment=period_end if status == SubscriptionStatus.ACTIVE else trial_ends,
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
        call_minutes: float = 0,
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
            call_minutes=call_minutes,
        )
        self.usage_records.append(record)

        # Update subscription counters
        for sub in self.subscriptions.values():
            if sub.tenant_id == tenant_id:
                sub.calls_used += calls
                sub.leads_generated += qualified_leads
                sub.appointments_booked += appointments

    def check_limits(self, tenant_id: str) -> dict[str, Any]:
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
        calls_limit = plan.calls_per_month if plan.calls_per_month > 0 else float("inf")
        leads_limit = plan.leads_per_month if plan.leads_per_month > 0 else float("inf")

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
            "status": subscription.status.value,
        }

    def _get_tenant_subscription(self, tenant_id: str) -> Subscription | None:
        """Get active subscription for tenant"""
        for sub in self.subscriptions.values():
            if sub.tenant_id == tenant_id and sub.status in [
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.ACTIVE,
            ]:
                return sub
        return None

    async def generate_invoice(self, tenant_id: str, subscription_id: str) -> Invoice:
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
                tenant_id, subscription.current_period_start, subscription.current_period_end
            )

            # Calculate excess usage for hybrid
            if plan.pricing_model == PricingModel.HYBRID:
                excess_leads = max(0, period_usage["leads"] - plan.leads_per_month)
                excess_appointments = max(
                    0, period_usage["appointments"] - 0
                )  # No included appointments

                usage_amount = (
                    Decimal(str(excess_leads)) * plan.price_per_qualified_lead
                    + Decimal(str(excess_appointments)) * plan.price_per_appointment
                )

                usage_breakdown = {
                    "excess_leads": excess_leads,
                    "lead_charge": str(plan.price_per_qualified_lead),
                    "excess_appointments": excess_appointments,
                    "appointment_charge": str(plan.price_per_appointment),
                }

            # Pure per-lead model
            else:
                usage_amount = (
                    Decimal(str(period_usage["calls"])) * plan.price_per_call
                    + Decimal(str(period_usage["leads"])) * plan.price_per_qualified_lead
                    + Decimal(str(period_usage["appointments"])) * plan.price_per_appointment
                )

                usage_breakdown = {
                    "calls": period_usage["calls"],
                    "call_charge": str(plan.price_per_call),
                    "leads": period_usage["leads"],
                    "lead_charge": str(plan.price_per_qualified_lead),
                    "appointments": period_usage["appointments"],
                    "appointment_charge": str(plan.price_per_appointment),
                }

        # Calculate totals
        base_amount = pricing.get("subtotal", Decimal("0"))
        discount = pricing.get("discount", Decimal("0"))
        taxable = base_amount - discount + usage_amount
        # GST sirf REGISTERED hone par (GST_GSTIN set) — same gate as calculate_price.
        # Unregistered (<₹20L) pe 18% collect karna ILLEGAL hai; pehle yahan hamesha
        # +18% lagta tha (calculate_price already fixed tha, yeh method chhoot gaya tha).
        import os as _os

        _gst_rate = self.tax_rate if _os.environ.get("GST_GSTIN", "").strip() else Decimal("0")
        tax = taxable * _gst_rate
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
            payment_due_date=subscription.current_period_end + timedelta(days=7),
        )

        self.invoices[invoice.id] = invoice
        logger.info(f"📄 Generated invoice {invoice.id}: ₹{total}")

        return invoice

    def _get_period_usage(self, tenant_id: str, start: datetime, end: datetime) -> dict[str, int]:
        """Get usage for a billing period"""
        calls = 0
        leads = 0
        appointments = 0

        for record in self.usage_records:
            if record.tenant_id == tenant_id and start <= record.date <= end:
                calls += record.calls_made
                leads += record.qualified_leads
                appointments += record.appointments_booked

        return {"calls": calls, "leads": leads, "appointments": appointments}

    async def process_payment(
        self, invoice_id: str, payment_method: str, payment_details: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Process payment for an invoice
        In production, integrate with Razorpay/Stripe
        """
        invoice = self.invoices.get(invoice_id)
        if not invoice:
            return {"success": False, "error": "Invoice not found"}

        # SAFETY (2026-06-25 audit): this legacy in-memory manager is NOT the live
        # billing path (real payments = UPI manual-verify / Stripe via app/billing
        # + DB). It must NEVER fake a gateway success — marking an invoice paid with
        # NO money received is a financial foot-gun. Refuse honestly; the real flow
        # (admin UPI verify / Stripe webhook) performs the actual activation.
        logger.warning(
            f"process_payment() called on the legacy in-memory SubscriptionManager "
            f"for invoice {invoice_id} — no real gateway wired here; refusing to fake "
            f"a paid status. Use the UPI/Stripe billing path."
        )
        return {
            "success": False,
            "status": "not_configured",
            "invoice_id": invoice_id,
            "error": (
                "No payment gateway is wired in this code path. Real payments go "
                "through UPI (admin verification) or Stripe in app/billing."
            ),
        }

    async def cancel_subscription(self, subscription_id: str, reason: str = "") -> dict[str, Any]:
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
            "effective_until": subscription.current_period_end.isoformat(),
        }

    def get_tenant_billing_summary(self, tenant_id: str) -> dict[str, Any]:
        """Get billing summary for a tenant"""
        subscription = self._get_tenant_subscription(tenant_id)
        if not subscription:
            return {"error": "No active subscription"}

        plan = self.get_plan(subscription.plan_id)
        limits = self.check_limits(tenant_id)

        # Get recent invoices
        tenant_invoices = [inv for inv in self.invoices.values() if inv.tenant_id == tenant_id]
        tenant_invoices.sort(key=lambda x: x.created_at, reverse=True)

        return {
            "subscription": {
                "id": subscription.id,
                "plan": plan.name,
                "status": subscription.status.value,
                "billing_cycle": subscription.billing_cycle.value,
                "current_period_start": subscription.current_period_start.isoformat(),
                "current_period_end": subscription.current_period_end.isoformat(),
                "next_payment": (
                    subscription.next_payment.isoformat() if subscription.next_payment else None
                ),
            },
            "usage": {
                "calls_used": subscription.calls_used,
                "calls_limit": limits.get("calls_limit", "Unlimited"),
                "leads_generated": subscription.leads_generated,
                "leads_limit": limits.get("leads_limit", "Unlimited"),
                "appointments": subscription.appointments_booked,
            },
            "pricing": {
                "monthly_price": str(plan.monthly_price),
                "per_lead_price": str(plan.price_per_qualified_lead),
                "per_appointment_price": str(plan.price_per_appointment),
            },
            "recent_invoices": [
                {
                    "id": inv.id,
                    "amount": str(inv.total_amount),
                    "status": inv.status.value,
                    "date": inv.created_at.isoformat(),
                }
                for inv in tenant_invoices[:5]
            ],
        }


# Global billing manager
billing_manager = BillingManager()
