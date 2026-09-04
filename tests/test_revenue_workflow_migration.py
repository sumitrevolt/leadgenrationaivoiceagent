"""
Revenue Workflow Migration Phase 1 & 2 Test Suite
=================================================
Tests:
1. End-to-End Canary Run: board -> hunter -> neha -> sales -> guardian -> operations -> reply -> appointment -> payment WON
2. Phone/Email/Domain Deduplication
3. Pre-Send Guardian DND Suppression Gate
4. Voice Outbound HARD_OFF Safety Gate Enforcement
5. Provider Action ID Persistence & Idempotency
6. Payment-Verified WON State Rejection of Unverified Claims
7. Kanban Pipeline Sync
"""

from __future__ import annotations

import pytest

from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore
from app.platform.revenue_workflow import (
    RevenueKanbanState,
    RevenueWorkflowEngine,
)


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_revenue.db")
    store = DurableTaskStore(db_path=db_path)
    orch = AutomationOrchestrator(store=store)
    return RevenueWorkflowEngine(orchestrator=orch)


def test_end_to_end_revenue_canary_flow(temp_store):
    engine = temp_store

    # 1. Hunter Discovery
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

    # 2. Neha Qualification
    qualified_lead = engine.qualify_lead(lead.lead_id)
    assert qualified_lead.kanban_state == RevenueKanbanState.QUALIFIED
    assert qualified_lead.score == 85

    # 3. Sales Outreach Draft
    drafted_lead = engine.draft_outreach(lead.lead_id, channel="email")
    assert drafted_lead.kanban_state == RevenueKanbanState.DRAFTED
    assert "grow your beauty_salon revenue" in drafted_lead.outreach_draft

    # 4. Guardian Pre-Send Suppression Gate
    approved_lead, ok = engine.guardian_pre_send_check(lead.lead_id)
    assert ok is True
    assert approved_lead.kanban_state == RevenueKanbanState.APPROVED

    # 5. Operations Dispatch & Action ID Persistence
    sent_lead = engine.dispatch_outreach(lead.lead_id)
    assert sent_lead.kanban_state == RevenueKanbanState.SENT
    assert sent_lead.provider_action_id.startswith("act_email_")

    # 6. Success Webhook Reply Classification
    replied_lead = engine.record_inbound_reply_webhook(
        lead_id=lead.lead_id,
        provider_event_id="evt_inbound_998877",
        reply_text="Interested in your AI marketing package!",
    )
    assert replied_lead.kanban_state == RevenueKanbanState.REPLIED

    # 7. Success Appointment Booking
    app_lead = engine.record_genuine_appointment(
        lead_id=lead.lead_id,
        meeting_provider_id="meet_cal_554433",
        appointment_timestamp="2026-09-02 11:00 IST",
    )
    assert app_lead.kanban_state == RevenueKanbanState.APPOINTMENT

    # 8. Payment Verified WON State
    payment_proof = {
        "payment_verification_method": "owner_confirmed_upi",
        "transaction_id": "UPI/20260831/998877",
        "amount_inr": 1999,
        "customer_phone": "+919876543210",
        "customer_email": "jiya@jiyamakeover.in",
    }
    won_lead = engine.mark_won_with_payment(lead.lead_id, payment_proof)
    assert won_lead.kanban_state == RevenueKanbanState.WON
    assert won_lead.payment_evidence["transaction_id"] == "UPI/20260831/998877"


def test_lead_deduplication(temp_store):
    engine = temp_store

    lead1, is_new1 = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Salon Alpha",
        phone="+919999900000",
        email="contact@salonalpha.in",
        domain="salonalpha.in",
        niche="salon",
    )
    assert is_new1 is True

    # Duplicate submission with same phone number
    lead2, is_new2 = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Salon Alpha Duplicate",
        phone="+919999900000",
        email="other@salonalpha.in",
        domain="otherdomain.in",
        niche="salon",
    )
    assert is_new2 is False
    assert lead2.lead_id == lead1.lead_id


def test_guardian_pre_send_dnd_suppression_gate(temp_store):
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="DND Customer",
        phone="+919876543211",
        email="dnd_user@optout.com",
        domain="optout.com",
        niche="retail",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="email")

    # Guardian Pre-Send Check immediately before send -> Suppresses lead
    suppressed_lead, ok = engine.guardian_pre_send_check(lead.lead_id)
    assert ok is False
    assert suppressed_lead.kanban_state == RevenueKanbanState.LOST
    assert suppressed_lead.suppression_status == "SUPPRESSED"

    # Attempting dispatch MUST raise ValueError due to permanent immunity
    with pytest.raises(ValueError, match="Permanent Immunity Violation"):
        engine.dispatch_outreach(lead.lead_id)


def test_outbound_voice_safety_gate_enforcement(temp_store):
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Voice Call Prospect",
        phone="+919876543212",
        email="prospect@voice.com",
        domain="voice.com",
        niche="healthcare",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="voice")  # Attempt voice channel

    # Guardian Pre-Send Check -> Blocks voice channel
    blocked_lead, ok = engine.guardian_pre_send_check(lead.lead_id)
    assert ok is False
    assert blocked_lead.kanban_state == RevenueKanbanState.LOST
    assert blocked_lead.suppression_status == "SUPPRESSED"


def test_unverified_payment_won_rejection(temp_store):
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Text Only Claim",
        phone="+919876543213",
        email="text@claim.com",
        domain="claim.com",
        niche="clinic",
    )

    # Attempt text-only / unverified WON state -> Must raise ValueError
    unverified_proof = {
        "payment_verification_method": "provider_verified_stripe",  # Disallowed / removed provider
        "transaction_id": "fake_tx_123",
    }
    with pytest.raises(ValueError, match="Payment Evidence Verification Failed"):
        engine.mark_won_with_payment(lead.lead_id, unverified_proof)


def test_kanban_pipeline_state_sync(temp_store):
    engine = temp_store

    engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Kanban Test Lead",
        phone="+919876543214",
        email="kanban@test.com",
        domain="test.com",
        niche="spa",
    )

    pipeline = engine.get_kanban_pipeline()
    assert "DISCOVERED" in pipeline
    assert len(pipeline["DISCOVERED"]) == 1
    assert pipeline["DISCOVERED"][0]["name"] == "Kanban Test Lead"
