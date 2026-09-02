"""
Campaign Model
Database model for campaigns
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import relationship

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable so the DB stores .value not .name — VARCHAR-backed
    (native_enum=False), matching app/models/payment.py (production audit
    2026-07-01, F-DB4)."""
    return [member.value for member in enum_cls]


class CampaignStatus(enum.Enum):
    """Campaign status enum"""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignType(enum.Enum):
    """Campaign type enum"""

    COLD_OUTREACH = "cold_outreach"
    FOLLOW_UP = "follow_up"
    CALLBACK = "callback"
    RE_ENGAGEMENT = "re_engagement"


class Campaign(Base):
    """Campaign database model"""

    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Type and status
    type = Column(
        Enum(CampaignType, native_enum=False, values_callable=_enum_values),
        default=CampaignType.COLD_OUTREACH,
    )
    status = Column(
        Enum(CampaignStatus, native_enum=False, values_callable=_enum_values),
        default=CampaignStatus.DRAFT,
        index=True,
    )

    # Client association
    client_id = Column(String(36), ForeignKey("clients.id"))
    client_name = Column(String(255))
    client_service = Column(String(255))

    # Target configuration
    niche = Column(String(50), nullable=False)
    target_cities = Column(Text)  # JSON array
    target_lead_count = Column(Integer, default=500)

    # Script configuration
    script_name = Column(String(100))
    script_language = Column(String(20), default="hinglish")

    # Schedule
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    daily_call_limit = Column(Integer, default=100)
    working_hours_start = Column(Time)
    working_hours_end = Column(Time)
    working_days = Column(String(50), default="mon,tue,wed,thu,fri,sat")

    # Pacing
    calls_per_hour = Column(Integer, default=20)
    max_concurrent_calls = Column(Integer, default=5)

    # Notifications
    notify_whatsapp = Column(Text)  # JSON array of numbers
    notify_email = Column(Text)  # JSON array of emails
    hot_lead_threshold = Column(Integer, default=70)

    # CRM sync settings
    sync_to_sheets = Column(Boolean, default=True)
    spreadsheet_id = Column(String(255))
    sync_to_hubspot = Column(Boolean, default=False)
    hubspot_pipeline_id = Column(String(100))
    sync_to_zoho = Column(Boolean, default=False)

    # Statistics
    leads_scraped = Column(Integer, default=0)
    leads_called = Column(Integer, default=0)
    leads_connected = Column(Integer, default=0)
    leads_qualified = Column(Integer, default=0)
    appointments_booked = Column(Integer, default=0)
    callbacks_scheduled = Column(Integer, default=0)

    # Calculated metrics
    connection_rate = Column(Integer, default=0)  # Stored as percentage * 100
    qualification_rate = Column(Integer, default=0)
    conversion_rate = Column(Integer, default=0)

    # Cost tracking
    total_call_cost = Column(Integer, default=0)  # In paise
    cost_per_lead = Column(Integer, default=0)
    cost_per_appointment = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    leads = relationship("Lead", back_populates="campaign")
    call_logs = relationship("CallLog", back_populates="campaign")
    client = relationship("Client", back_populates="campaigns")

    def __repr__(self):
        return f"<Campaign {self.name} ({self.status.value})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value if self.type else None,
            "status": self.status.value if self.status else None,
            "niche": self.niche,
            "client_name": self.client_name,
            "leads_scraped": self.leads_scraped,
            "leads_called": self.leads_called,
            "leads_qualified": self.leads_qualified,
            "appointments_booked": self.appointments_booked,
            "progress": self.leads_called / self.leads_scraped if self.leads_scraped > 0 else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def update_stats(self):
        """Recalculate statistics"""
        if self.leads_scraped > 0:
            self.connection_rate = int((self.leads_connected / self.leads_scraped) * 10000)

        if self.leads_connected > 0:
            self.qualification_rate = int((self.leads_qualified / self.leads_connected) * 10000)

        if self.leads_qualified > 0:
            self.conversion_rate = int((self.appointments_booked / self.leads_qualified) * 10000)

        self.updated_at = datetime.utcnow()

    def mark_started(self):
        """Mark campaign as started"""
        self.status = CampaignStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_completed(self):
        """Mark campaign as completed"""
        self.status = CampaignStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.update_stats()
