"""Tests for WorkerBot type-safe execution and parameter validation."""

from __future__ import annotations

from app.agents.workers import (
    LeadGeneratorWorker,
    QualityAssuranceWorker,
    WorkerRole,
    get_workers_manager,
)


def test_worker_parameter_type_validation():
    """Worker task must fail with a clear type error if input does not match expected schema."""
    qa_bot = QualityAssuranceWorker()

    # rules expects 'list', pass a string instead -> must fail cleanly
    task = qa_bot.create_task(
        "validate_content", {"content": "Sample outreach", "rules": "not_a_list"}
    )
    result = qa_bot.execute_task(task)
    assert result.status == "failed"
    assert "expected list/array" in result.error


def test_qa_worker_compliance_check():
    """QA worker evaluates compliance and executes skill logic."""
    qa_bot = QualityAssuranceWorker()

    task = qa_bot.create_task(
        "check_compliance", {"campaign": {"dlt_approved": True, "cold_whatsapp": False}}
    )
    result = qa_bot.execute_task(task)
    assert result.status == "completed"
    assert result.result["compliant"] is True
    assert len(result.result["violations"]) == 0


def test_qa_worker_compliance_catches_violations():
    """QA worker catches DLT and cold WhatsApp violations."""
    qa_bot = QualityAssuranceWorker()

    task = qa_bot.create_task(
        "check_compliance", {"campaign": {"dlt_approved": False, "cold_whatsapp": True}}
    )
    result = qa_bot.execute_task(task)
    assert result.status == "completed"
    assert result.result["compliant"] is False
    assert len(result.result["violations"]) == 2


def test_lead_generator_harvest_and_enrich():
    """Lead generator worker harvests and enriches leads."""
    lead_bot = LeadGeneratorWorker()

    # 1. Harvest prospects
    task1 = lead_bot.create_task(
        "harvest_prospects",
        {
            "source": "google_maps",
            "criteria": {"niche": "salon"},
            "prospects": [{"name": "Salon A"}],
        },
    )
    res1 = lead_bot.execute_task(task1)
    assert res1.status == "completed"
    assert res1.result["count"] == 1

    # 2. Enrich lead
    task2 = lead_bot.create_task(
        "enrich_lead", {"lead": {"name": "Salon A", "phone": "+919876543210"}}
    )
    res2 = lead_bot.execute_task(task2)
    assert res2.status == "completed"
    assert res2.result["enriched_lead"]["verified"] is True
