# tests/test_lead_pipeline_models.py
"""Model-shape tests for the lead-gen pipeline batch tracking tables
(2026-07-08 pipeline-automation vertical slice)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.lead_pipeline import (
    LeadPipelineBatch,
    LeadPipelineQualityIssue,
    LeadPipelineStageRun,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_batch_defaults_and_roundtrip():
    db = _session()
    batch = LeadPipelineBatch(id="b1", source="prospector", niche="dentist", city="pune")
    db.add(batch)
    db.commit()
    row = db.get(LeadPipelineBatch, "b1")
    assert row.status == "pending"
    assert row.total_raw == 0
    assert row.source == "prospector"


def test_stage_run_links_to_batch():
    db = _session()
    db.add(LeadPipelineBatch(id="b2", source="prospector"))
    db.commit()
    db.add(
        LeadPipelineStageRun(
            id="s1", batch_id="b2", stage_name="ingestion", status="passed", output_count=5
        )
    )
    db.commit()
    row = db.get(LeadPipelineStageRun, "s1")
    assert row.batch_id == "b2"
    assert row.output_count == 5


def test_quality_issue_defaults_unresolved():
    db = _session()
    db.add(LeadPipelineBatch(id="b3", source="prospector"))
    db.commit()
    db.add(
        LeadPipelineQualityIssue(
            id="q1",
            batch_id="b3",
            stage_name="ingestion",
            issue_type="zero_output",
            severity="warning",
            message="0 raw leads",
        )
    )
    db.commit()
    row = db.get(LeadPipelineQualityIssue, "q1")
    assert row.resolved is False
    assert row.severity == "warning"


def test_lead_has_score_reason_and_source_batch_id_columns():
    db = _session()
    lead = Lead(
        id="l1",
        company_name="Test Co",
        phone="9198765432 10".replace(" ", ""),
        status=LeadStatus.NEW,
        source=LeadSource.GOOGLE_MAPS,
        score_reason="niche_fit+recency",
        source_batch_id="b1",
    )
    db.add(lead)
    db.commit()
    row = db.get(Lead, "l1")
    assert row.score_reason == "niche_fit+recency"
    assert row.source_batch_id == "b1"


def test_update_score_uses_centralized_threshold_and_persists_reason(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "lead_hot_threshold", 65)
    lead = Lead(
        id="l2",
        company_name="X",
        phone="9198765432 11".replace(" ", ""),
        status=LeadStatus.NEW,
        source=LeadSource.MANUAL,
    )
    lead.update_score(70, reason="high intent")
    assert lead.is_hot_lead is True
    assert lead.score_reason == "high intent"
    lead.update_score(60, reason="lower intent")
    assert lead.is_hot_lead is False
    assert lead.score_reason == "lower intent"
