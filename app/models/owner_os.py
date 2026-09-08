"""Owner OS durable tables — commands, kill switches, audit (ADR Owner OS v1)."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from app.models.base import Base


class OwnerCommand(Base):
    __tablename__ = "owner_commands"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_owner_commands_idempotency"),)

    command_id = Column(String(40), primary_key=True)
    actor_id = Column(String(120), nullable=False, default="admin")
    actor_role = Column(String(40), nullable=True)
    original_instruction = Column(Text, nullable=False)
    normalized_intent = Column(String(64), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    assigned_agent_id = Column(String(40), nullable=True, index=True)
    risk_level = Column(String(20), nullable=False, default="low")
    approval_state = Column(String(40), nullable=False, default="none")
    execution_state = Column(String(40), nullable=False, default="DRAFT", index=True)
    idempotency_key = Column(String(80), nullable=False)
    parameters_json = Column(Text, nullable=True)
    publish_allowed = Column(Boolean, nullable=False, default=False)
    customer_notify_allowed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_code = Column(String(64), nullable=True)
    sanitized_error = Column(Text, nullable=True)
    evidence_summary_json = Column(Text, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    preview_summary = Column(Text, nullable=True)


class OwnerKillSwitch(Base):
    __tablename__ = "owner_kill_switches"

    switch_name = Column(String(64), primary_key=True)
    engaged = Column(Boolean, nullable=False, default=False)
    scope = Column(String(40), nullable=False, default="global")
    reason = Column(String(200), nullable=True)
    changed_by = Column(String(120), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow)
    expiry = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)


class OwnerOSAuditEvent(Base):
    __tablename__ = "owner_os_audit_events"

    id = Column(String(36), primary_key=True, default=lambda: uuid4().hex)
    at = Column(DateTime, default=datetime.utcnow, index=True)
    actor = Column(String(120), nullable=False, default="admin")
    action = Column(String(80), nullable=False, index=True)
    target = Column(String(120), nullable=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    before_summary = Column(Text, nullable=True)
    after_summary = Column(Text, nullable=True)
    meta_json = Column(Text, nullable=True)


class OwnerAgentControl(Base):
    __tablename__ = "owner_agent_controls"

    agent_id = Column(String(40), primary_key=True)
    manual_pause = Column(Boolean, nullable=False, default=False)
    scheduled_pause = Column(Boolean, nullable=False, default=False)
    stop_claims = Column(Boolean, nullable=False, default=False)
    drain = Column(Boolean, nullable=False, default=False)
    drain_state = Column(String(20), nullable=False, default="idle")
    reason = Column(String(200), nullable=True)
    changed_by = Column(String(120), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow)
    expiry = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    meta_json = Column(Text, nullable=True)
