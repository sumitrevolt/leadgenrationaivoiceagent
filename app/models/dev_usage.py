"""Per-attempt provider usage/cost ledger for the Claude-managed control plane.

Every gateway invocation attempt (success, skip, budget-denial, or provider
error) becomes one immutable row here so FinOps/audit can reconstruct exactly
which provider ran, what it cost, and why a fallback happened. DevTask carries
the rolled-up aggregate; this table carries the itemised evidence. (Phase 2.)
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text

from app.models.base import Base


class DevTaskUsage(Base):
    __tablename__ = "dev_task_usage"

    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), nullable=False, index=True)
    attempt_no = Column(Integer, nullable=False, default=1)
    provider = Column(String(60), nullable=False)
    model = Column(String(180), nullable=True)
    # success | skipped_unconfigured | budget_denied | provider_error | empty_response
    outcome = Column(String(40), nullable=False, index=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Numeric(12, 6), nullable=True)
    estimated = Column(Boolean, nullable=False, default=True)
    scope = Column(String(160), nullable=True)
    detail = Column(Text, nullable=True)  # bounded error/skip reason (never secrets/PII)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
