"""Approval-notification audit + idempotency model.

One row per (client, approval, approval-version, channel) notification attempt.
`idempotency_key` is UNIQUE, so a duplicate send is prevented across task retries,
worker restarts and repeated scheduler runs (DB-backed — survives a Redis flush).
Additive table, created by Base.metadata.create_all (DB_CREATE_ALL). ADR: Phase-1
customer-delivery notifications (2026-07-12).
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.models.base import Base


class ApprovalNotification(Base):
    __tablename__ = "approval_notifications"

    id = Column(String(36), primary_key=True, default=lambda: uuid4().hex)
    client_id = Column(String(64), nullable=True, index=True)
    approval_id = Column(String(64), nullable=False, index=True)
    # Version token derived from the approval's mutable state — a changed approval
    # yields a new version, so a new notification is allowed for it.
    approval_version = Column(String(64), nullable=True)
    channel = Column(String(20), nullable=False, default="email")
    # UNIQUE dedupe key = f"{channel}:{client_id}:{approval_id}:{approval_version}".
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    # attempted -> sent | skipped | failed
    status = Column(String(20), nullable=False, default="attempted", index=True)
    # no_email | no_consent | email_disabled | provider_error | provider_exception | sender_unavailable | ...
    failure_category = Column(String(50), nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    attempts = Column(Integer, default=1)
    attempted_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    meta_json = Column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ApprovalNotification {self.approval_id} {self.status} {self.channel}>"
