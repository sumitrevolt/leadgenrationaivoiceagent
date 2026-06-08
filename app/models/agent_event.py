"""
AgentEvent Model — AI staff team ka activity log.
Har staff member (Swara/Arjun/Meera/...) ka har kaam yahan record hota hai;
admin Team dashboard isi se "kaun kya kar raha hai" dikhata hai.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text

from app.models.base import Base


class AgentEvent(Base):
    """Ek staff action ka record (call placed, QA run, KB seeded, ...)."""

    __tablename__ = "agent_events"

    __table_args__ = (
        Index("ix_agent_events_member_time", "member", "created_at"),
        Index("ix_agent_events_time", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    member = Column(String(40), nullable=False, default="system")  # STAFF key
    action = Column(String(60), nullable=False, default="event")
    detail = Column(String(500), default="")
    status = Column(String(10), default="ok")  # ok | warn | error
    meta_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
