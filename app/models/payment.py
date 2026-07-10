"""
Payment & Billing Models
Database models for payments, subscriptions, and invoices
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable for SQLAlchemy Enum columns so the DB stores the enum's
    .value (e.g. "active") not its .name (e.g. "ACTIVE"). Keeps existing VARCHAR
    data valid and avoids a Postgres native-ENUM type (native_enum=False)."""
    return [member.value for member in enum_cls]


class PaymentGateway(enum.Enum):
    """Supported payment gateways"""

    # STRIPE removed 2026-07-10 — project me Stripe use nahi hota.
    RAZORPAY = "razorpay"  # Legacy: Razorpay also removed 2026-06-18


class SubscriptionStatus(enum.Enum):
    """Subscription status"""

    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    EXPIRED = "expired"


class PaymentStatus(enum.Enum):
    """Payment transaction status"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"


class InvoiceStatus(enum.Enum):
    """Invoice status"""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class BillingCycle(enum.Enum):
    """Billing cycle options"""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class PricingPlanModel(enum.Enum):
    """Pricing model types"""

    SUBSCRIPTION = "subscription"
    PER_LEAD = "per_lead"
    HYBRID = "hybrid"


class Subscription(Base):
    """
    Database-backed subscription model
    Linked to Stripe/Razorpay subscription IDs
    """

    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Tenant/Client association
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Plan details
    plan_id = Column(String(50), nullable=False, index=True)
    plan_name = Column(String(100), nullable=False)
    pricing_model = Column(String(20), default="subscription")

    # Status — Enum(native_enum=False) renders as VARCHAR (Postgres-compatible,
    # no native ENUM type / no migration) while letting all callers use enum
    # semantics (assign SubscriptionStatus.X, read .status.value, filter .in_([...])).
    status = Column(
        Enum(SubscriptionStatus, native_enum=False, values_callable=_enum_values),
        default=SubscriptionStatus.TRIAL,
        nullable=False,
        index=True,
    )
    billing_cycle = Column(
        Enum(BillingCycle, native_enum=False, values_callable=_enum_values),
        default=BillingCycle.MONTHLY,
    )

    # External gateway references
    payment_gateway = Column(String(20), nullable=True)
    stripe_subscription_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    razorpay_subscription_id = Column(String(255), unique=True, nullable=True, index=True)
    razorpay_customer_id = Column(String(255), nullable=True)

    # Pricing (stored at subscription time for historical reference)
    base_price = Column(Numeric(12, 2), default=0)
    currency = Column(String(3), default="INR")

    # Dates
    started_at = Column(DateTime, default=datetime.utcnow)
    trial_ends_at = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    # Usage tracking (for current period)
    calls_used = Column(Integer, default=0)
    calls_limit = Column(Integer, default=0)  # 0 = unlimited
    leads_generated = Column(Integer, default=0)
    leads_limit = Column(Integer, default=0)
    appointments_booked = Column(Integer, default=0)

    # Balance for per-lead/prepaid models
    balance = Column(Numeric(12, 2), default=0)

    # Extra data (metadata)
    extra_data = Column(JSON, default=dict)
    cancel_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    payments = relationship("Payment", back_populates="subscription", lazy="dynamic")
    invoices = relationship("Invoice", back_populates="subscription", lazy="dynamic")

    def is_active(self) -> bool:
        """Check if subscription is active"""
        return self.status in [SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE]

    def is_trial(self) -> bool:
        """Check if in trial period"""
        return self.status == SubscriptionStatus.TRIAL

    def has_exceeded_limits(self) -> bool:
        """Check if usage limits are exceeded"""
        if self.calls_limit > 0 and self.calls_used >= self.calls_limit:
            return True
        if self.leads_limit > 0 and self.leads_generated >= self.leads_limit:
            return True
        return False

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "status": self.status.value if self.status else None,
            "billing_cycle": self.billing_cycle.value if self.billing_cycle else None,
            "payment_gateway": self.payment_gateway,
            "base_price": float(self.base_price) if self.base_price else 0,
            "currency": self.currency,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            "current_period_start": (
                self.current_period_start.isoformat() if self.current_period_start else None
            ),
            "current_period_end": (
                self.current_period_end.isoformat() if self.current_period_end else None
            ),
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "usage": {
                "calls_used": self.calls_used,
                "calls_limit": self.calls_limit or "unlimited",
                "leads_generated": self.leads_generated,
                "leads_limit": self.leads_limit or "unlimited",
                "appointments_booked": self.appointments_booked,
            },
            "balance": float(self.balance) if self.balance else 0,
        }


class Payment(Base):
    """
    Payment transaction records
    Stores all payment transactions from Stripe/Razorpay
    """

    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Associations
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=True, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id"), nullable=True)

    # Payment gateway info (using String for PostgreSQL compatibility)
    payment_gateway = Column(String(20), nullable=False)
    gateway_payment_id = Column(String(255), unique=True, nullable=False, index=True)
    gateway_order_id = Column(String(255), nullable=True)  # Razorpay order ID

    # Amount details
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="INR")
    amount_refunded = Column(Numeric(12, 2), default=0)

    # Status — see Subscription.status note (Enum, VARCHAR-backed, no migration).
    status = Column(
        Enum(PaymentStatus, native_enum=False, values_callable=_enum_values),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Payment method details (masked for security)
    payment_method_type = Column(String(50))  # card, upi, netbanking, wallet
    payment_method_last4 = Column(String(4), nullable=True)
    payment_method_brand = Column(String(50), nullable=True)  # visa, mastercard, etc.

    # Description
    description = Column(String(500), nullable=True)

    # Error handling
    failure_code = Column(String(100), nullable=True)
    failure_message = Column(Text, nullable=True)

    # Data from gateway
    gateway_response = Column(JSON, default=dict)
    extra_data = Column(JSON, default=dict)

    # Receipt
    receipt_url = Column(String(500), nullable=True)
    receipt_number = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)

    # Relationships
    subscription = relationship("Subscription", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payment")

    def is_successful(self) -> bool:
        """Check if payment was successful"""
        return self.status == PaymentStatus.COMPLETED

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "subscription_id": self.subscription_id,
            "invoice_id": self.invoice_id,
            "payment_gateway": self.payment_gateway,
            "gateway_payment_id": self.gateway_payment_id,
            "amount": float(self.amount) if self.amount else 0,
            "currency": self.currency,
            "amount_refunded": float(self.amount_refunded) if self.amount_refunded else 0,
            "status": self.status.value if self.status else None,
            "payment_method": {
                "type": self.payment_method_type,
                "last4": self.payment_method_last4,
                "brand": self.payment_method_brand,
            },
            "description": self.description,
            "receipt_url": self.receipt_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class Invoice(Base):
    """
    Invoice records with PDF storage
    """

    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Associations
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=True, index=True)

    # Invoice number (human readable)
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)

    # External references
    stripe_invoice_id = Column(String(255), unique=True, nullable=True)
    razorpay_invoice_id = Column(String(255), unique=True, nullable=True)

    # Status — see Subscription.status note (Enum, VARCHAR-backed, no migration).
    status = Column(
        Enum(InvoiceStatus, native_enum=False, values_callable=_enum_values),
        default=InvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # Billing period
    billing_period_start = Column(DateTime, nullable=True)
    billing_period_end = Column(DateTime, nullable=True)

    # Amounts (all in minor units, e.g., paisa for INR)
    subtotal = Column(Numeric(12, 2), default=0)
    discount_amount = Column(Numeric(12, 2), default=0)
    discount_percentage = Column(Numeric(5, 2), default=0)
    tax_amount = Column(Numeric(12, 2), default=0)
    tax_rate = Column(Numeric(5, 2), default=18)  # GST 18%
    total = Column(Numeric(12, 2), default=0)
    amount_paid = Column(Numeric(12, 2), default=0)
    amount_due = Column(Numeric(12, 2), default=0)
    currency = Column(String(3), default="INR")

    # Line items (JSON array)
    line_items = Column(JSON, default=list)

    # Usage breakdown (for hybrid/per-lead models)
    usage_summary = Column(JSON, default=dict)

    # PDF storage
    pdf_url = Column(String(500), nullable=True)
    hosted_invoice_url = Column(String(500), nullable=True)  # Stripe/Razorpay hosted URL

    # Customer details (snapshot at invoice time)
    customer_name = Column(String(255), nullable=True)
    customer_email = Column(String(255), nullable=True)
    customer_address = Column(JSON, default=dict)
    customer_gstin = Column(String(20), nullable=True)  # For Indian GST

    # Dates
    invoice_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    voided_at = Column(DateTime, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)
    footer = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscription = relationship("Subscription", back_populates="invoices")
    payment = relationship("Payment", back_populates="invoice", uselist=False)

    def is_paid(self) -> bool:
        """Check if invoice is fully paid"""
        return self.status == InvoiceStatus.PAID

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "invoice_number": self.invoice_number,
            "client_id": self.client_id,
            "subscription_id": self.subscription_id,
            "status": self.status.value if self.status else None,
            "billing_period": {
                "start": (
                    self.billing_period_start.isoformat() if self.billing_period_start else None
                ),
                "end": self.billing_period_end.isoformat() if self.billing_period_end else None,
            },
            "amounts": {
                "subtotal": float(self.subtotal) if self.subtotal else 0,
                "discount": float(self.discount_amount) if self.discount_amount else 0,
                "tax": float(self.tax_amount) if self.tax_amount else 0,
                "total": float(self.total) if self.total else 0,
                "paid": float(self.amount_paid) if self.amount_paid else 0,
                "due": float(self.amount_due) if self.amount_due else 0,
            },
            "currency": self.currency,
            "line_items": self.line_items or [],
            "usage_summary": self.usage_summary or {},
            "pdf_url": self.pdf_url,
            "hosted_invoice_url": self.hosted_invoice_url,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
        }


class PaymentMethod(Base):
    """
    Stored payment methods for recurring payments
    Only stores non-sensitive references
    """

    __tablename__ = "payment_methods"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Associations
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)

    # Gateway references (using String for PostgreSQL compatibility)
    payment_gateway = Column(String(20), nullable=False)
    gateway_payment_method_id = Column(String(255), unique=True, nullable=False)
    stripe_customer_id = Column(String(255), nullable=True)
    razorpay_customer_id = Column(String(255), nullable=True)

    # Method type
    type = Column(String(50), nullable=False)  # card, upi, netbanking, wallet

    # Card details (masked)
    card_brand = Column(String(50), nullable=True)  # visa, mastercard, rupay
    card_last4 = Column(String(4), nullable=True)
    card_exp_month = Column(Integer, nullable=True)
    card_exp_year = Column(Integer, nullable=True)
    card_funding = Column(String(20), nullable=True)  # credit, debit, prepaid

    # UPI details (masked)
    upi_id_masked = Column(String(100), nullable=True)  # x***@upi

    # Netbanking
    bank_name = Column(String(100), nullable=True)

    # Status
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Billing address
    billing_name = Column(String(255), nullable=True)
    billing_address = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary (safe for frontend)"""
        result = {
            "id": self.id,
            "payment_gateway": self.payment_gateway,
            "type": self.type,
            "is_default": self.is_default,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

        if self.type == "card":
            result["card"] = {
                "brand": self.card_brand,
                "last4": self.card_last4,
                "exp_month": self.card_exp_month,
                "exp_year": self.card_exp_year,
                "funding": self.card_funding,
            }
        elif self.type == "upi":
            result["upi"] = {"id_masked": self.upi_id_masked}
        elif self.type == "netbanking":
            result["bank"] = {"name": self.bank_name}

        return result


class UsageRecord(Base):
    """
    Usage tracking for billing calculations
    """

    __tablename__ = "usage_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Associations
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=True, index=True)

    # Usage date (for aggregation)
    usage_date = Column(DateTime, nullable=False, index=True)

    # Usage metrics
    calls_made = Column(Integer, default=0)
    calls_connected = Column(Integer, default=0)
    call_duration_seconds = Column(Integer, default=0)
    qualified_leads = Column(Integer, default=0)
    appointments_booked = Column(Integer, default=0)

    # For per-lead billing
    billable_amount = Column(Numeric(12, 2), default=0)
    billed = Column(Boolean, default=False)
    billed_at = Column(DateTime, nullable=True)
    invoice_id = Column(String(36), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "usage_date": self.usage_date.isoformat() if self.usage_date else None,
            "calls_made": self.calls_made,
            "calls_connected": self.calls_connected,
            "call_duration_seconds": self.call_duration_seconds,
            "qualified_leads": self.qualified_leads,
            "appointments_booked": self.appointments_booked,
            "billable_amount": float(self.billable_amount) if self.billable_amount else 0,
            "billed": self.billed,
        }
