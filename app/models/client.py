"""
Client Model
Database model for clients (businesses using the platform)
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable so the DB stores .value not .name — VARCHAR-backed
    (native_enum=False), matching app/models/payment.py (production audit
    2026-07-01, F-DB4)."""
    return [member.value for member in enum_cls]


class SubscriptionPlan(enum.Enum):
    """Subscription plan enum"""

    STARTER = "starter"  # 15,000/month
    GROWTH = "growth"  # 25,000/month
    ENTERPRISE = "enterprise"  # 35,000/month
    CUSTOM = "custom"


class ClientStatus(enum.Enum):
    """Client status enum"""

    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Client(Base):
    """Client database model"""

    __tablename__ = "clients"

    id = Column(String(36), primary_key=True)

    # Business information
    business_name = Column(String(255), nullable=False)
    business_type = Column(String(100))  # agency, sme, enterprise
    industry = Column(String(100))
    website = Column(String(255))

    # Contact information
    contact_name = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=False, unique=True)
    contact_phone = Column(String(20), nullable=False)
    contact_designation = Column(String(100))

    # Location
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100), default="India")
    pincode = Column(String(10))
    gst_number = Column(String(20))

    # Subscription
    plan = Column(
        Enum(SubscriptionPlan, native_enum=False, values_callable=_enum_values),
        default=SubscriptionPlan.STARTER,
    )
    status = Column(
        Enum(ClientStatus, native_enum=False, values_callable=_enum_values),
        default=ClientStatus.TRIAL,
    )

    # Plan limits
    monthly_call_limit = Column(Integer, default=1000)
    monthly_lead_limit = Column(Integer, default=500)
    max_campaigns = Column(Integer, default=3)
    max_users = Column(Integer, default=2)

    # Usage tracking
    calls_this_month = Column(Integer, default=0)
    leads_this_month = Column(Integer, default=0)
    active_campaigns = Column(Integer, default=0)

    # Billing
    billing_cycle_start = Column(DateTime)
    billing_cycle_end = Column(DateTime)
    next_billing_date = Column(DateTime)
    monthly_amount = Column(Integer, default=1500000)  # In paise

    # API credentials
    api_key = Column(String(64), unique=True)
    webhook_url = Column(String(500))

    # Integration settings (JSON)
    twilio_config = Column(Text)  # JSON
    exotel_config = Column(Text)  # JSON
    whatsapp_config = Column(Text)  # JSON
    hubspot_config = Column(Text)  # JSON
    zoho_config = Column(Text)  # JSON
    sheets_config = Column(Text)  # JSON

    # Caller ID settings
    caller_id_number = Column(String(20))
    caller_id_name = Column(String(100))

    # Voice settings
    preferred_voice = Column(String(50), default="ElevenLabs")
    preferred_language = Column(String(20), default="hinglish")

    # Notification settings
    notify_on_hot_lead = Column(Boolean, default=True)
    notify_on_appointment = Column(Boolean, default=True)
    daily_report_enabled = Column(Boolean, default=True)
    weekly_report_enabled = Column(Boolean, default=True)

    # ---- Product One Delivery OS fields (ADR-064, 2026-07-09) ----
    delivery_stage = Column(String(50))
    onboarding_status = Column(String(50))
    social_setup_status = Column(String(50))
    content_generation_status = Column(String(50))
    approval_status = Column(String(50))
    posting_status = Column(String(50))
    report_status = Column(String(50))
    last_delivery_at = Column(String(50))
    next_action = Column(String(255))
    blocking_reason = Column(String(255))
    assigned_agent = Column(String(100))
    automation_health = Column(String(50))
    setup_completed_at = Column(String(50))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    trial_ends_at = Column(DateTime)
    last_active_at = Column(DateTime)

    # Relationships
    campaigns = relationship("Campaign", back_populates="client")

    def __repr__(self):
        return f"<Client {self.business_name} ({self.plan.value})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "business_name": self.business_name,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "plan": self.plan.value if self.plan else None,
            "status": self.status.value if self.status else None,
            "calls_this_month": self.calls_this_month,
            "leads_this_month": self.leads_this_month,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def can_make_calls(self) -> bool:
        """Check if client can make more calls"""
        if self.status not in [ClientStatus.ACTIVE, ClientStatus.TRIAL]:
            return False
        return self.calls_this_month < self.monthly_call_limit

    def can_scrape_leads(self) -> bool:
        """Check if client can scrape more leads"""
        if self.status not in [ClientStatus.ACTIVE, ClientStatus.TRIAL]:
            return False
        return self.leads_this_month < self.monthly_lead_limit

    def increment_calls(self, count: int = 1):
        """Increment call count"""
        self.calls_this_month += count
        self.last_active_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def increment_leads(self, count: int = 1):
        """Increment lead count"""
        self.leads_this_month += count
        self.last_active_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def reset_monthly_usage(self):
        """Reset monthly usage counters"""
        self.calls_this_month = 0
        self.leads_this_month = 0
        self.billing_cycle_start = datetime.utcnow()
        self.updated_at = datetime.utcnow()
