"""Campaign variant model — champion/challenger A/B for scripts and outreach."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text

from app.models.base import Base


class CampaignVariant(Base):
    __tablename__ = "campaign_variants"
    __table_args__ = (Index("ix_cv_script_status", "script_id", "status"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), index=True, default="")
    script_id = Column(String(100), nullable=False, index=True)  # e.g. niche:solar:opening
    variant_key = Column(String(50), nullable=False)  # champion|challenger_a|...
    niche = Column(String(100), index=True)
    channel = Column(String(30), default="email")  # email|voice|whatsapp
    content = Column(Text)
    impressions = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    meetings = Column(Integer, default=0)
    meeting_rate = Column(Float, default=0.0)
    status = Column(String(20), default="challenger")  # champion|challenger|retired
    created_at = Column(DateTime, default=datetime.utcnow)
    promoted_at = Column(DateTime)
