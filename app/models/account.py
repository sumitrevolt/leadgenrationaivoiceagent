"""Account model — company-level entity for enterprise flywheel SSOT."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String

from app.models.base import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_accounts_client_domain", "client_id", "domain"),
        Index("ix_accounts_client_niche", "client_id", "niche"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id = Column(String(36), index=True, default="")  # tenant (SaaS customer)
    company_name = Column(String(255), nullable=False, index=True)
    domain = Column(String(255), index=True)
    industry = Column(String(100))
    employee_band = Column(String(50))
    niche = Column(String(100), index=True)
    city = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
