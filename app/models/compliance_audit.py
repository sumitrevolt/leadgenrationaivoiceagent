"""
Compliance Audit Model
Database model for TRAI/DPDP compliance audit trail
CRITICAL: Required for regulatory compliance proof
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, String, Text

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable: DB stores .value not .name (VARCHAR-backed, native_enum=False)"""
    return [member.value for member in enum_cls]


class ComplianceDecision(enum.Enum):
    """Compliance gate decision"""

    ALLOWED = "allowed"
    BLOCKED_DND = "blocked_dnd"
    BLOCKED_WINDOW = "blocked_window"
    BLOCKED_CONSENT = "blocked_consent"
    BLOCKED_OTHER = "blocked_other"


class ComplianceAuditLog(Base):
    """
    TRAI/DPDP Compliance Audit Log

    Required by TRAI for 90-day proof of DND checks, calling window compliance,
    and consent verification. This is a PERMANENT audit trail — never delete entries
    within the 90-day retention window.

    CRITICAL: This table is accessed for compliance defense. Queries must be fast.
    Index on (created_at, decision) for date-range queries.
    """

    __tablename__ = "compliance_audit_logs"
    __table_args__ = (
        # Index for compliance audit retrieval: "last 90 days of blocked calls"
        Index("ix_compliance_audit_created_decision", "created_at", "decision"),
        # Index for per-phone audits: "all decisions for phone X"
        Index("ix_compliance_audit_phone", "phone_number"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Call/Contact Details
    phone_number = Column(String(20), nullable=False, index=True)  # Normalized phone
    call_type = Column(String(50), nullable=False)  # "promotional", "transactional", "callback"

    # Compliance Decision
    decision = Column(
        Enum(ComplianceDecision, native_enum=False, values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    decision_reason = Column(String(255), nullable=True)  # "DND_VERIFIED", "OUTSIDE_WINDOW", etc.

    # DND Check Details
    dnd_checked = Column(Boolean, default=False)
    dnd_result = Column(String(50), nullable=True)  # "do_not_call", "do_not_sms", "not_registered"
    dnd_timestamp = Column(DateTime, nullable=True)
    dnd_provider = Column(String(100), nullable=True)  # Which DND service responded

    # Calling Window Check
    window_checked = Column(Boolean, default=False)
    window_start_hour = Column(String(5), nullable=True)  # "09:00"
    window_end_hour = Column(String(5), nullable=True)  # "21:00"
    call_time_hour = Column(String(5), nullable=True)  # Actual call hour

    # Consent Check
    consent_checked = Column(Boolean, default=False)
    consent_status = Column(String(50), nullable=True)  # "opted_in", "opted_out", "not_found"

    # Metadata
    client_id = Column(String(36), nullable=True, index=True)
    campaign_id = Column(String(36), nullable=True)
    call_id = Column(String(36), nullable=True)  # Link to actual call_log if applicable

    # Request Context
    request_ip = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(255), nullable=True)
    request_path = Column(String(255), nullable=True)  # Which API endpoint triggered check

    # Audit Trail
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(String(100), nullable=True)  # "compliance_gate", "manual_audit", etc.

    # Notes for auditor
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<ComplianceAuditLog(phone={self.phone_number}, "
            f"decision={self.decision.value}, created={self.created_at})>"
        )
