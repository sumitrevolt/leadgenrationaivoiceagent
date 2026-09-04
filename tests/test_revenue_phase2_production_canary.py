"""
Revenue Workflow Phase 2 Production Canary Test Suite
=====================================================
Tests:
1. End-to-End Eligible Lead Canary Flow (Real Provider Action ID + Inbound Webhook + Booking Evidence + Payment UTR)
2. Honest Canary Rule (Unanswered lead stays in SENT state without fake WON promotion)
3. Permanent LOST / Suppression Immunity Guard
4. Immutable Audit Trail Logging Across Transitions
5. Production PostgreSQL Database Fail-Closed Guard
6. Kill Switch Behavior During Canary Execution
"""

from __future__ import annotations

import os

import pytest

from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore
from app.platform.revenue_workflow import (
    RevenueKanbanState,
    RevenueWorkflowEngine,
    verify_production_db_guard,
)


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_revenue_phase2.db")
    store = DurableTaskStore(db_path=db_path)
    orch = AutomationOrchestrator(store=store)
    return RevenueWorkflowEngine(orchestrator=orch)


def test_real_eligible_lead_canary_flow(temp_store):
    engine = temp_store

    # 1. DISCOVERED (hunter)
    lead, is_new = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Jiya Makeover Clinic",
        phone="+919876543210",
        email="jiya@jiyamakeover.in",
        domain="jiyamakeover.in",
        niche="beauty_salon",
    )
    assert is_new is True
    assert lead.kanban_state == RevenueKanbanState.DISCOVERED

    # 2. QUALIFIED (neha)
    engine.qualify_lead(lead.lead_id)
    assert lead.kanban_state == RevenueKanbanState.QUALIFIED

    # 3. DRAFTED (sales)
    engine.draft_outreach(lead.lead_id, channel="email")
    assert lead.kanban_state == RevenueKanbanState.DRAFTED

    # 4. APPROVED (guardian)
    _, ok = engine.guardian_pre_send_check(lead.lead_id)
    assert ok is True
    assert lead.kanban_state == RevenueKanbanState.APPROVED

    # 5. SENT (operations)
    engine.dispatch_outreach(lead.lead_id)
    assert lead.kanban_state == RevenueKanbanState.SENT
    assert lead.provider_action_id.startswith("act_email_")
    assert lead.provider_response_payload["status"] == "SENT"

    # 6. REPLIED (success webhook)
    engine.record_inbound_reply_webhook(
        lead_id=lead.lead_id,
        provider_event_id="evt_inbound_998877",
        reply_text="Yes, I want to book a demo for my salon!",
    )
    assert lead.kanban_state == RevenueKanbanState.REPLIED

    # 7. APPOINTMENT (success demo booking)
    engine.record_genuine_appointment(
        lead_id=lead.lead_id,
        meeting_provider_id="meet_cal_554433",
        appointment_timestamp="2026-09-02 11:00 IST",
    )
    assert lead.kanban_state == RevenueKanbanState.APPOINTMENT

    # 8. WON (upi_payments verified UTR proof)
    payment_evidence = {
        "payment_verification_method": "owner_confirmed_upi",
        "transaction_id": "UPI/20260831/998877",
        "amount_inr": 1999,
        "customer_phone": "+919876543210",
        "customer_email": "jiya@jiyamakeover.in",
    }
    engine.mark_won_with_payment(lead.lead_id, payment_evidence)
    assert lead.kanban_state == RevenueKanbanState.WON


def test_honest_canary_unanswered_lead_remains_sent(temp_store):
    """Honest Canary Rule: Unanswered lead stays in SENT state without fake WON promotion."""
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Unanswered Lead Clinic",
        phone="+919876543299",
        email="unanswered@clinic.in",
        domain="clinic.in",
        niche="dental",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="email")
    engine.guardian_pre_send_check(lead.lead_id)
    engine.dispatch_outreach(lead.lead_id)

    # Lead remains SENT!
    assert lead.kanban_state == RevenueKanbanState.SENT
    assert lead.payment_evidence is None

    pipeline = engine.get_kanban_pipeline()
    assert len(pipeline["SENT"]) == 1
    assert len(pipeline["WON"]) == 0


def test_permanent_lost_suppression_immunity(temp_store):
    """Permanent LOST / Suppression Immunity Guard."""
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Opted Out Lead",
        phone="+919876543211",
        email="optout@dnd.in",
        domain="dnd.in",
        niche="retail",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="email")
    engine.guardian_pre_send_check(lead.lead_id)  # DND suppressed -> LOST

    assert lead.kanban_state == RevenueKanbanState.LOST
    assert lead.suppression_status == "SUPPRESSED"

    # Attempting to qualify or draft outreach MUST raise ValueError due to permanent immunity
    with pytest.raises(ValueError, match="Permanent Immunity Violation"):
        engine.qualify_lead(lead.lead_id)

    with pytest.raises(ValueError, match="Permanent Immunity Violation"):
        engine.draft_outreach(lead.lead_id, channel="email")


def test_immutable_audit_trail_logging(temp_store):
    """Immutable Audit Trail Logging Across Transitions."""
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Audit Test Lead",
        phone="+919876543215",
        email="audit@test.com",
        domain="test.com",
        niche="spa",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="email")
    engine.guardian_pre_send_check(lead.lead_id)
    engine.dispatch_outreach(lead.lead_id)

    audit_logs = engine.get_audit_trail(lead_id=lead.lead_id)
    assert len(audit_logs) == 5  # DISCOVERED, QUALIFIED, DRAFTED, APPROVED, SENT

    states = [log["next_state"] for log in audit_logs]
    assert states == ["DISCOVERED", "QUALIFIED", "DRAFTED", "APPROVED", "SENT"]
    actors = [log["actor_bot"] for log in audit_logs]
    assert actors == ["hunter", "neha", "sales", "guardian", "operations"]


def test_production_db_guard(monkeypatch):
    """Production PostgreSQL Database Fail-Closed Guard."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///stale.db")

    with pytest.raises(RuntimeError, match="Production Authority Violation"):
        verify_production_db_guard()


def test_kill_switch_during_canary(temp_store, monkeypatch):
    """Kill switch stops new dispatches during canary."""
    monkeypatch.setenv("AUTOMATION_STOP_NEW_CLAIMS", "1")
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Kill Switch Lead",
        phone="+919876543216",
        email="killswitch@test.com",
        domain="test.com",
        niche="fitness",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="email")
    engine.guardian_pre_send_check(lead.lead_id)

    # Dispatch under kill switch must be BLOCKED
    res = engine.orchestrator.dispatch_task(lead.task_id)
    assert res is False
    task_rec = engine.orchestrator.store.get(lead.task_id)
    assert task_rec.status.value == "BLOCKED"
