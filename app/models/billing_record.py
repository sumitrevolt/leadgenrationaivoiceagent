"""
Billing Record Model
Per-period billing line items for clients (MRR, telephony cost, lead delivery).
Powers admin dashboard revenue/cost aggregates and per-client MRR.
"""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable so the DB stores .value not .name — VARCHAR-backed
    (native_enum=False), matching app/models/payment.py (production audit
    2026-07-01, F-DB4)."""
    return [member.value for member in enum_cls]


class BillingRecordType(enum.Enum):
    """Type of billing record"""

    SUBSCRIPTION = "subscription"  # monthly plan MRR
    PER_LEAD = "per_lead"  # per-qualified-lead charge
    TELEPHONY = "telephony"  # PSTN / telephony cost (a cost, not revenue)
    OVERAGE = "overage"  # usage above plan limits
    ADJUSTMENT = "adjustment"  # manual credit/debit


class BillingRecordStatus(enum.Enum):
    """Status of a billing record"""

    PENDING = "pending"
    INVOICED = "invoiced"
    PAID = "paid"
    FAILED = "failed"
    WAIVED = "waived"


class BillingRecord(Base):
    """Billing record / ledger line for a client over a billing period"""

    __tablename__ = "billing_records"

    __table_args__ = (
        Index("ix_billing_client", "client_id"),
        Index("ix_billing_period", "period_year", "period_month"),
        Index("ix_billing_type_status", "record_type", "status"),
    )

    id = Column(String(36), primary_key=True)

    # Association
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    client_name = Column(String(255))
    campaign_id = Column(String(36), ForeignKey("campaigns.id"))

    # Classification
    record_type = Column(
        Enum(BillingRecordType, native_enum=False, values_callable=_enum_values),
        default=BillingRecordType.SUBSCRIPTION,
        index=True,
    )
    status = Column(
        Enum(BillingRecordStatus, native_enum=False, values_callable=_enum_values),
        default=BillingRecordStatus.PENDING,
        index=True,
    )

    # Billing period
    period_year = Column(Integer, index=True)
    period_month = Column(Integer, index=True)  # 1-12

    # Amounts (stored in paise to match Client.monthly_amount convention)
    amount = Column(Integer, default=0)  # revenue (positive) in paise
    cost = Column(Integer, default=0)  # cost in paise (telephony etc.)
    quantity = Column(Integer, default=1)  # e.g. number of leads
    currency = Column(String(10), default="INR")

    # Description / reference
    description = Column(String(500))
    reference_id = Column(String(100))  # invoice id, payment id, etc.

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    billed_at = Column(DateTime)
    paid_at = Column(DateTime)

    def __repr__(self):
        return f"<BillingRecord {self.client_name} {self.record_type.value if self.record_type else '?'} Rs.{(self.amount or 0) / 100:.0f}>"

    @property
    def amount_inr(self) -> float:
        """Revenue amount in rupees"""
        return (self.amount or 0) / 100.0

    @property
    def cost_inr(self) -> float:
        """Cost amount in rupees"""
        return (self.cost or 0) / 100.0

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "record_type": self.record_type.value if self.record_type else None,
            "status": self.status.value if self.status else None,
            "period_year": self.period_year,
            "period_month": self.period_month,
            "amount_inr": self.amount_inr,
            "cost_inr": self.cost_inr,
            "quantity": self.quantity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def mark_paid(self) -> None:
        """Mark this billing record as paid"""
        self.status = BillingRecordStatus.PAID
        self.paid_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
