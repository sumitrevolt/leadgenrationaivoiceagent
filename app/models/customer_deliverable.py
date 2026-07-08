"""
Customer Deliverable Model
Database model for tracking customer deliverables (Product One AI Automated Marketing).
"""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, String, Text

from app.models.base import Base


def _enum_values(enum_cls):
    """VARCHAR-backed Enum values list helper"""
    return [member.value for member in enum_cls]


class DeliverableStatus(enum.Enum):
    """Status options for customer deliverables"""

    NOT_STARTED = "not_started"
    WAITING_CUSTOMER = "waiting_customer"
    READY_TO_GENERATE = "ready_to_generate"
    GENERATING = "generating"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


class DeliverableChannel(enum.Enum):
    """Channel options for deliverable outcomes"""

    DASHBOARD = "dashboard"
    WHATSAPP_MANUAL = "whatsapp_manual"
    EMAIL = "email"
    GBP = "gbp"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    POSTER = "poster"
    REPORT = "report"
    INVOICE = "invoice"
    INTERNAL = "internal"


class CustomerDeliverable(Base):
    """Database model for customer-facing deliverables"""

    __tablename__ = "customer_deliverables"

    __table_args__ = (
        Index("ix_customer_deliverables_client", "client_id"),
        Index("ix_customer_deliverables_status", "status"),
        Index("ix_customer_deliverables_cycle", "client_id", "billing_cycle_month"),
    )

    id = Column(String(36), primary_key=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    plan_code = Column(String(50))
    billing_cycle_month = Column(String(7))  # Format YYYY-MM
    deliverable_type = Column(String(100))
    title = Column(String(255))
    description = Column(Text)

    status = Column(
        Enum(DeliverableStatus, native_enum=False, values_callable=_enum_values),
        default=DeliverableStatus.NOT_STARTED,
        nullable=False,
    )

    channel = Column(
        Enum(DeliverableChannel, native_enum=False, values_callable=_enum_values),
        default=DeliverableChannel.DASHBOARD,
        nullable=False,
    )

    due_date = Column(DateTime)
    delivered_at = Column(DateTime)
    evidence_url = Column(String(500))
    evidence_payload = Column(Text)  # Optional JSON details or text proof

    approval_id = Column(String(36))
    automation_run_id = Column(String(36))
    error_message = Column(Text)
    next_action = Column(Text)
    owner = Column(String(50))  # e.g., system, admin, customer

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
