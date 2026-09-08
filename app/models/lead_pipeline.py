"""Lead-gen funnel pipeline batch tracking (2026-07-08).

Instruments the already-scheduled prospector.py daily run with first-class
batch/stage/quality-issue records so a broken scraper or a silent
data-quality regression is visible in the admin dashboard instead of only
surfacing weeks later as "0 replies". Deliberately NOT a new parallel
pipeline system — reuses app.models.interaction.Interaction for
per-lead/per-channel events and app.platform.dlq_retry for task-level
retry. See docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.models.base import Base


class LeadPipelineBatch(Base):
    """One row per prospector.py ingestion run: what ran, how many leads
    made it through each phase, whether anything failed."""

    __tablename__ = "lead_pipeline_batches"
    __table_args__ = (
        Index("ix_pipeline_batches_source_time", "source", "created_at"),
        Index("ix_pipeline_batches_status_time", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(30), nullable=False, default="prospector")
    niche = Column(String(50))
    city = Column(String(100))
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending|running|completed|partial_failed|failed
    total_raw = Column(Integer, default=0)
    total_duplicate = Column(Integer, default=0)
    total_invalid = Column(Integer, default=0)
    total_valid = Column(Integer, default=0)
    total_scored = Column(Integer, default=0)
    total_eligible = Column(Integer, default=0)
    total_outreach_created = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LeadPipelineStageRun(Base):
    """Per-stage counts within one batch (ingestion/dedup/validation/scoring)."""

    __tablename__ = "lead_pipeline_stage_runs"
    __table_args__ = (Index("ix_pipeline_stage_runs_batch", "batch_id", "stage_name"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(
        String(36), ForeignKey("lead_pipeline_batches.id"), nullable=False, index=True
    )
    stage_name = Column(String(30), nullable=False)
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending|running|passed|warning|failed
    input_count = Column(Integer, default=0)
    output_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class LeadPipelineQualityIssue(Base):
    """A data-quality signal for a batch — distinct from dlq_retry.py's
    task-level failure queue. e.g. "38% duplicate rate", "scraper returned
    zero leads", "provider disabled". Drives the admin 'Today's Pipeline
    Problems' view."""

    __tablename__ = "lead_pipeline_quality_issues"
    __table_args__ = (
        Index("ix_pipeline_issues_batch", "batch_id", "created_at"),
        Index("ix_pipeline_issues_resolved", "resolved", "severity"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(
        String(36), ForeignKey("lead_pipeline_batches.id"), nullable=False, index=True
    )
    stage_name = Column(String(30), nullable=False)
    issue_type = Column(String(40), nullable=False)
    severity = Column(String(10), nullable=False, default="warning")  # info|warning|critical
    message = Column(Text)
    resolved = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
