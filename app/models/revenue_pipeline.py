"""
Revenue Pipeline SQLAlchemy Models — Phase 2 Production Authority
====================================================================
Declarative database models for revenue pipeline lead records and immutable audit logs.
"""

from __future__ import annotations

import time
from sqlalchemy import Column, String, Integer, Float, Text, JSON, DateTime
from app.models.base import Base


class RevenueLeadModel(Base):
    """SQLAlchemy model for persistent revenue lead records."""

    __tablename__ = "revenue_lead_records"

    lead_id = Column(String(64), primary_key=True, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(64), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    domain = Column(String(255), nullable=False, index=True)
    niche = Column(String(128), nullable=False, index=True)
    score = Column(Integer, default=0)
    kanban_state = Column(String(64), nullable=False, default="DISCOVERED", index=True)
    outreach_channel = Column(String(64), default="email")
    outreach_draft = Column(Text, nullable=True)
    provider_action_id = Column(String(128), nullable=True, index=True)
    provider_response_payload = Column(JSON, nullable=True)
    payment_evidence = Column(JSON, nullable=True)
    suppression_status = Column(String(64), default="CLEARED", index=True)
    task_id = Column(String(128), nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)


class RevenueAuditLogModel(Base):
    """SQLAlchemy model for immutable revenue pipeline audit trail."""

    __tablename__ = "revenue_audit_logs"

    audit_id = Column(String(64), primary_key=True, index=True)
    lead_id = Column(String(64), nullable=False, index=True)
    actor_bot = Column(String(64), nullable=False, index=True)
    previous_state = Column(String(64), nullable=False)
    next_state = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    task_id = Column(String(128), nullable=True)
    evidence_id = Column(String(128), nullable=True)
    timestamp = Column(Float, default=time.time, index=True)
