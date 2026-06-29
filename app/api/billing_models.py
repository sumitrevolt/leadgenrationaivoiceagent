"""
Billing API request/response Pydantic models.

Extracted verbatim from app/api/billing.py (behaviour-preserving refactor).
Re-exported by app.api.billing so existing imports keep working.
"""

from pydantic import BaseModel, Field


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
    feature_groups: list[dict] = Field(default_factory=list)  # grouped view for collapsible UI
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
