"""Interaction model — omnichannel timeline (enterprise flywheel)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from app.models.base import Base


class Interaction(Base):
    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interactions_contact_at", "contact_id", "occurred_at"),
        Index("ix_interactions_channel", "channel", "direction"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), index=True, default="")
    contact_id = Column(String(36), ForeignKey("contacts.id"), nullable=True, index=True)
    lead_id = Column(String(36), index=True)
    channel = Column(String(30), nullable=False)  # email|voice|whatsapp|sms|inquiry|cadence
    direction = Column(String(10), default="out")  # in|out|draft
    body_summary = Column(Text)
    outcome = Column(String(50))  # sent|replied|booked|qualified|opt_out|...
    campaign_variant_id = Column(String(36), index=True)
    meta_json = Column(Text)
    occurred_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
