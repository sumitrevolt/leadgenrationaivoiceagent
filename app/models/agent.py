"""
Agent (Worker) Model
Database model for AI voice agents / workers in the agent pool.
Powers the admin dashboard "agents" panel (live worker status + stats).
"""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable so the DB stores .value not .name — VARCHAR-backed
    (native_enum=False), matching app/models/payment.py (production audit
    2026-07-01, F-DB4)."""
    return [member.value for member in enum_cls]


class AgentStatus(enum.Enum):
    """Agent / worker live status enum"""

    IDLE = "idle"
    CALLING = "calling"
    SCRAPING = "scraping"
    PAUSED = "paused"
    ERROR = "error"
    OFFLINE = "offline"


class Agent(Base):
    """AI voice agent / worker database model"""

    __tablename__ = "agents"

    __table_args__ = (
        Index("ix_agents_status", "status"),
        Index("ix_agents_client", "current_client_id"),
    )

    id = Column(String(36), primary_key=True)

    # Identity
    name = Column(String(100), nullable=False)
    agent_code = Column(String(20), index=True)  # e.g. "AG-01"

    # Current assignment
    current_client_id = Column(String(36), ForeignKey("clients.id"))
    current_client_name = Column(String(255))
    current_campaign_id = Column(String(36), ForeignKey("campaigns.id"))

    # Live status (index defined explicitly in __table_args__ as ix_agents_status)
    status = Column(
        Enum(AgentStatus, native_enum=False, values_callable=_enum_values),
        default=AgentStatus.IDLE,
    )

    # Capabilities / config
    # role: "data" (client business data/KB) | "leads" (end-customer calling)
    role = Column(String(20), default="leads", index=True)
    niche = Column(String(50))  # specialization niche, if any
    voice = Column(String(50), default="EdgeTTS")
    language = Column(String(20), default="hinglish")
    max_concurrent_calls = Column(Integer, default=1)

    # Statistics (lifetime / current period)
    calls_made = Column(Integer, default=0)
    leads_found = Column(Integer, default=0)
    appointments_booked = Column(Integer, default=0)
    talk_time_seconds = Column(Integer, default=0)

    # Error tracking
    last_error = Column(Text)
    error_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at = Column(DateTime)

    def __repr__(self):
        return f"<Agent {self.agent_code} {self.name} ({self.status.value if self.status else 'unknown'})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "agent_code": self.agent_code,
            "current_client": self.current_client_name,
            "status": self.status.value if self.status else None,
            "calls_made": self.calls_made,
            "leads_found": self.leads_found,
            "appointments_booked": self.appointments_booked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def mark_calling(self) -> None:
        """Mark agent as actively calling"""
        self.status = AgentStatus.CALLING
        self.last_active_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_idle(self) -> None:
        """Mark agent as idle"""
        self.status = AgentStatus.IDLE
        self.updated_at = datetime.utcnow()

    def record_call(self, talk_seconds: int = 0) -> None:
        """Record a completed call against this agent"""
        self.calls_made += 1
        self.talk_time_seconds += max(0, talk_seconds)
        self.last_active_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def record_error(self, message: str) -> None:
        """Record an error and flip status to ERROR"""
        self.status = AgentStatus.ERROR
        self.last_error = message
        self.error_count += 1
        self.updated_at = datetime.utcnow()
