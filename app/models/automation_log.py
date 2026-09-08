"""Automation Log model — centralized event log for all automation/agent/scheduler jobs.

ADR-064, 2026-07-09.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.models.base import Base


class AutomationLog(Base):
    __tablename__ = "automation_logs"

    id = Column(String(36), primary_key=True)
    client_id = Column(String(36), nullable=True, index=True)
    job_type = Column(String(100), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued", index=True)
    started_at = Column(String(50))
    finished_at = Column(String(50))
    duration_ms = Column(Integer)
    input_summary = Column(Text)
    output_summary = Column(Text)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    next_retry_at = Column(String(50))
    evidence_url = Column(
        String(500)
    )  # ADR-068: proof artifact URL/path (report HTML, published post, etc.)
    triggered_by = Column(String(50), default="system")
    meta_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
