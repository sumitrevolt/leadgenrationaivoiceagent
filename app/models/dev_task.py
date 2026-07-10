"""Canonical Claude-managed engineering task ledger (Phase 1)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text

from app.models.base import Base


class DevTask(Base):
    __tablename__ = "dev_tasks"

    id = Column(String(36), primary_key=True)
    idempotency_key = Column(String(180), nullable=False, unique=True)
    parent_objective = Column(String(4000), nullable=False)
    customer_id = Column(String(36), nullable=True, index=True)
    priority = Column(Integer, nullable=False, default=50, index=True)
    state = Column(String(40), nullable=False, default="proposed", index=True)
    selected_provider = Column(String(60), nullable=True)
    selected_model = Column(String(180), nullable=True)
    fallback_models = Column(Text, nullable=True)
    estimated_cost_usd = Column(Numeric(12, 6), nullable=True)
    actual_cost_usd = Column(Numeric(12, 6), nullable=True)
    estimated_input_tokens = Column(Integer, nullable=True)
    estimated_output_tokens = Column(Integer, nullable=True)
    actual_input_tokens = Column(Integer, nullable=True)
    actual_output_tokens = Column(Integer, nullable=True)
    worktree_path = Column(String(500), nullable=True)
    branch_name = Column(String(180), nullable=True)
    file_ownership = Column(Text, nullable=True)
    dependencies = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String(120), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    test_evidence = Column(Text, nullable=True)
    deployment_evidence = Column(Text, nullable=True)
    delivery_evidence = Column(Text, nullable=True)
    worker_report = Column(Text, nullable=True)
    blocked_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
