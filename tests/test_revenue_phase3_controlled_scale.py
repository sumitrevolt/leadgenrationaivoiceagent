"""
Revenue Workflow Phase 3 Controlled Scale Test Suite
=====================================================
Tests:
1. Alembic Migration 025 (revision 025, down_revision 024)
2. HMAC Signed Webhook Authentication & Replay Protection
3. Global Transaction UTR Uniqueness & Partial Payment Rejection
4. Audit Log Immutability & Sensitive Field Redaction
5. Scale Ladder Execution (Stages A: 1 lead, B: 5 leads, C: 20 leads with 0 violations)
6. Business & Financial Metrics Pipeline Calculation
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore
from app.platform.revenue_workflow import (
    RevenueKanbanState,
    RevenueWorkflowEngine,
    redact_sensitive_payload,
    verify_webhook_signature,
)


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_revenue_phase3.db")
    store = DurableTaskStore(db_path=db_path)
    orch = AutomationOrchestrator(store=store)
    return RevenueWorkflowEngine(orchestrator=orch)


def test_alembic_migration_025_up_down():
    import importlib.util
    spec = importlib.util.spec_from_file_location("m025", "alembic/versions/025_add_revenue_pipeline_tables.py")
    m025 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m025)

    assert m025.revision == "025"
    assert m025.down_revision == "024"
    assert callable(m025.upgrade)
    assert callable(m025.downgrade)


def test_webhook_hmac_signature_and_replay_protection(temp_store):
    engine = temp_store
    secret = "super_webhook_secret_key"  # nosecret
    ts = time.time()

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Webhook Test Salon",
        phone="+919876543001",
        email="webhook@salon.in",
        domain="salon.in",
        niche="salon",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="email")
    engine.guardian_pre_send_check(lead.lead_id)
    engine.dispatch_outreach(lead.lead_id)

    reply_payload = {"lead_id": lead.lead_id, "reply_text": "I am interested"}
    payload_str = json.dumps(reply_payload, sort_keys=True)
    valid_sig = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.{payload_str}".encode(),
        hashlib.sha256,
    ).hexdigest()

    # 1. Valid Signature -> Succeeds
    engine.record_inbound_reply_webhook(
        lead_id=lead.lead_id,
        provider_event_id="evt_valid_101",
        reply_text="I am interested",
        signature=valid_sig,
        secret=secret,
        timestamp=ts,
    )
    assert lead.kanban_state == RevenueKanbanState.REPLIED

    # 2. Invalid Signature -> Fails
    with pytest.raises(PermissionError, match="Webhook Authentication Failed"):
        engine.record_inbound_reply_webhook(
            lead_id=lead.lead_id,
            provider_event_id="evt_invalid_102",
            reply_text="Attack payload",
            signature="bad_signature_hash",
            secret=secret,
            timestamp=ts,
        )

    # 3. Duplicate Webhook Event ID Replay -> Rejection metric incremented, 0 second state transition!
    engine.record_inbound_reply_webhook(
        lead_id=lead.lead_id,
        provider_event_id="evt_valid_101",  # Same event ID!
        reply_text="Duplicate replay attack",
    )
    assert engine.metrics["duplicate_webhook_rejections"] == 1


def test_payment_utr_uniqueness_and_partial_rejection(temp_store):
    engine = temp_store

    lead1, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Lead One",
        phone="+919876543002",
        email="one@salon.in",
        domain="one.in",
        niche="salon",
    )
    lead2, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Lead Two",
        phone="+919876543003",
        email="two@salon.in",
        domain="two.in",
        niche="salon",
    )

    pay_lead1 = {
        "payment_verification_method": "owner_confirmed_upi",
        "transaction_id": "UPI/20260831/UNIQUE123",
        "amount_inr": 1999,
        "customer_phone": "+919876543002",
    }
    engine.mark_won_with_payment(lead1.lead_id, pay_lead1)
    assert lead1.kanban_state == RevenueKanbanState.WON

    # 1. Duplicate UTR Reuse for Lead Two -> Raises ValueError (UTR Collision)
    pay_lead2_dup_utr = {
        "payment_verification_method": "owner_confirmed_upi",
        "transaction_id": "UPI/20260831/UNIQUE123",  # Same UTR!
        "amount_inr": 1999,
        "customer_phone": "+919876543003",
    }
    with pytest.raises(ValueError, match="UTR Collision"):
        engine.mark_won_with_payment(lead2.lead_id, pay_lead2_dup_utr)
    assert engine.metrics["utr_collisions"] == 1

    # 2. Partial Payment Rejection (amount_inr = 500 < 1999)
    pay_lead2_partial = {
        "payment_verification_method": "owner_confirmed_upi",
        "transaction_id": "UPI/20260831/NEW456",
        "amount_inr": 500,  # Partial payment!
        "customer_phone": "+919876543003",
    }
    with pytest.raises(ValueError, match="Partial Payment Rejected"):
        engine.mark_won_with_payment(lead2.lead_id, pay_lead2_partial)
    assert engine.metrics["partial_payment_rejections"] == 1


def test_audit_log_immutability_and_redaction(temp_store):
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Audit Redact Lead",
        phone="+919876543004",
        email="redact@salon.in",
        domain="redact.in",
        niche="salon",
    )

    # 1. Audit Immutability Guard
    with pytest.raises(PermissionError, match="Audit Immutability Violation"):
        engine.update_audit_log(lead.lead_id)

    with pytest.raises(PermissionError, match="Audit Immutability Violation"):
        engine.delete_audit_log(lead.lead_id)

    assert engine.metrics["audit_tamper_attempts"] == 2

    # 2. Sensitive Field Redaction Test
    raw_payload = {
        "user": "admin",
        "api_key": "sk_live_secret123",
        "password": "my_secret_pass",
        "nested": {"token": "bearer_abc_456", "public_info": "safe"},
    }
    redacted = redact_sensitive_payload(raw_payload)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["public_info"] == "safe"


def test_scale_ladder_stage_a_b_c(temp_store):
    engine = temp_store

    sample_leads = [
        {"tenant_id": "t1", "name": f"Lead {i}", "phone": f"+9198000000{i:02d}", "email": f"lead{i}@scale.in", "domain": f"scale{i}.in", "niche": "salon"}
        for i in range(25)
    ]

    # Stage A: 1 lead
    stage_a = engine.execute_scale_ladder(sample_leads, stage="A")
    assert stage_a["requested_count"] == 1
    assert stage_a["processed_count"] == 1
    assert stage_a["guardrails_pass"] is True

    # Stage B: 5 leads
    stage_b = engine.execute_scale_ladder(sample_leads, stage="B")
    assert stage_b["requested_count"] == 5
    assert stage_b["processed_count"] == 5
    assert stage_b["guardrails_pass"] is True

    # Stage C: 20 leads
    stage_c = engine.execute_scale_ladder(sample_leads, stage="C")
    assert stage_c["requested_count"] == 20
    assert stage_c["processed_count"] == 20
    assert stage_c["guardrails_pass"] is True


def test_business_financial_metrics_pipeline(temp_store):
    engine = temp_store

    lead, _ = engine.ingest_and_dedup_lead(
        tenant_id="tenant_jiya",
        name="Financial Test Lead",
        phone="+919876543005",
        email="fin@salon.in",
        domain="fin.in",
        niche="salon",
    )
    engine.qualify_lead(lead.lead_id)
    engine.draft_outreach(lead.lead_id, channel="email")
    engine.guardian_pre_send_check(lead.lead_id)
    engine.dispatch_outreach(lead.lead_id)  # ₹0.50 cost added
    engine.record_inbound_reply_webhook(lead.lead_id, "evt_fin_202", "Interested")
    engine.record_genuine_appointment(lead.lead_id, "meet_cal_202", "2026-09-02 12:00 IST")

    pay_proof = {
        "payment_verification_method": "owner_confirmed_upi",
        "transaction_id": "UPI/20260831/FIN999",
        "amount_inr": 1999,
        "customer_phone": "+919876543005",
    }
    engine.mark_won_with_payment(lead.lead_id, pay_proof)

    metrics = engine.get_financial_and_funnel_metrics()
    assert metrics["funnel"]["won"] == 1
    assert metrics["financials"]["total_sent_cost_inr"] == 0.50
    assert metrics["financials"]["collected_revenue_inr"] == 1999
    assert metrics["financials"]["net_profit_inr"] == 1998.50
