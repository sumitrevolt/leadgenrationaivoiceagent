"""Contact model — person at an account (enterprise flywheel)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String

from app.models.base import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_client_phone", "client_id", "phone_e164"),
        Index("ix_contacts_account", "account_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), index=True, default="")
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=True, index=True)
    name = Column(String(255))
    phone_e164 = Column(String(20), index=True)
    email = Column(String(255), index=True)
    role = Column(String(100))
    lead_id = Column(String(36), index=True)  # link to flat Lead row if exists
    enriched_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
