"""
Call Log Model
Database model for call logs
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable so the DB stores .value not .name — VARCHAR-backed
    (native_enum=False), matching app/models/payment.py (production audit
    2026-07-01, F-DB4)."""
    return [member.value for member in enum_cls]


class CallOutcome(enum.Enum):
    """Call outcome enum"""

    APPOINTMENT = "appointment"
    CALLBACK = "callback"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    WRONG_NUMBER = "wrong_number"
    DND = "dnd"
    FAILED = "failed"
    DROPPED = "dropped"


class CallDirection(enum.Enum):
    """Call direction enum"""

    OUTBOUND = "outbound"
    INBOUND = "inbound"


class CallLog(Base):
    """Call log database model"""

    __tablename__ = "call_logs"
    __table_args__ = (
        Index("ix_call_logs_client_initiated", "client_id", "initiated_at"),
        Index("ix_call_logs_status_outcome", "status", "outcome"),
    )

    id = Column(String(36), primary_key=True)

    # Call identification
    call_sid = Column(String(100), index=True)  # Twilio/Exotel call ID
    provider = Column(String(20))  # twilio, exotel
    direction = Column(
        Enum(CallDirection, native_enum=False, values_callable=_enum_values),
        default=CallDirection.OUTBOUND,
    )

    # Associations
    lead_id = Column(String(36), ForeignKey("leads.id"), index=True)
    campaign_id = Column(String(36), ForeignKey("campaigns.id"), index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), index=True)

    # Phone numbers
    from_number = Column(String(20))
    to_number = Column(String(20), nullable=False)

    # Timing
    initiated_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime)
    ended_at = Column(DateTime)
    duration_seconds = Column(Integer, default=0)
    ring_duration = Column(Integer, default=0)
    talk_duration = Column(Integer, default=0)

    # Status and outcome
    status = Column(String(20))  # initiated, ringing, answered, completed, failed
    outcome = Column(Enum(CallOutcome, native_enum=False, values_callable=_enum_values), index=True)

    # Lead scoring
    lead_score = Column(Integer, default=0)
    is_hot_lead = Column(Boolean, default=False)

    # Qualification data (JSON)
    qualification_data = Column(Text)
    detected_intent = Column(String(50))

    # Recording
    recording_url = Column(String(500))
    recording_duration = Column(Integer)

    # Transcription
    transcription = Column(Text)
    summary = Column(Text)

    # AI analysis
    sentiment = Column(String(20))  # positive, neutral, negative
    conversation_quality = Column(Integer)  # 0-100
    objections_faced = Column(Text)  # JSON array

    # Appointment details
    appointment_scheduled = Column(Boolean, default=False)
    appointment_date = Column(DateTime)
    appointment_notes = Column(Text)

    # Callback details
    callback_scheduled = Column(Boolean, default=False)
    callback_date = Column(DateTime)
    callback_notes = Column(Text)

    # Cost tracking
    call_cost = Column(Integer, default=0)  # In paise

    # Error handling
    error_code = Column(String(20))
    error_message = Column(Text)

    # Retry information
    retry_count = Column(Integer, default=0)
    is_retry = Column(Boolean, default=False)
    original_call_id = Column(String(36))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    lead = relationship("Lead", back_populates="call_logs")
    campaign = relationship("Campaign", back_populates="call_logs")

    def __repr__(self):
        return f"<CallLog {self.id} ({self.outcome.value if self.outcome else 'pending'})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "call_sid": self.call_sid,
            "lead_id": self.lead_id,
            "campaign_id": self.campaign_id,
            "to_number": self.to_number,
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome.value if self.outcome else None,
            "lead_score": self.lead_score,
            "is_hot_lead": self.is_hot_lead,
            "recording_url": self.recording_url,
            "initiated_at": self.initiated_at.isoformat() if self.initiated_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }

    def calculate_duration(self):
        """Calculate call duration"""
        if self.answered_at and self.ended_at:
            delta = self.ended_at - self.answered_at
            self.talk_duration = int(delta.total_seconds())

        if self.initiated_at and self.ended_at:
            delta = self.ended_at - self.initiated_at
            self.duration_seconds = int(delta.total_seconds())

    def mark_answered(self):
        """Mark call as answered"""
        self.answered_at = datetime.utcnow()
        self.status = "answered"

    def mark_completed(self, outcome: CallOutcome, lead_score: int = 0):
        """Mark call as completed"""
        self.ended_at = datetime.utcnow()
        self.status = "completed"
        self.outcome = outcome
        self.lead_score = lead_score
        self.is_hot_lead = lead_score >= 70
        self.calculate_duration()
