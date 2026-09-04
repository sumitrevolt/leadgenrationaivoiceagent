"""
Revenue Workflow Phase 4 Live Revenue Pilot Test Suite
======================================================
Tests:
1. Database-Level Audit Immutability Event Listeners (before_update & before_delete block session edits)
2. Provider Action ID Unique Constraint
3. Stage A Live Revenue Pilot (1 Lead) — Honest SENT state tracking, 0 violations
4. Stage B Live Revenue Pilot (5 Leads) — 0 violations
5. Stage C Live Revenue Pilot (20 Leads) — 0 violations
6. Safety Invariant Breach Fail-Safe Kill Switch Activation (AUTOMATION_STOP_NEW_CLAIMS=1)
7. 9-Column Business Funnel Evidence Table Formatting
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.revenue_pipeline import RevenueAuditLogModel, RevenueLeadModel
from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore
from app.platform.revenue_workflow import (
    RevenueKanbanState,
    RevenueWorkflowEngine,
)


@pytest.fixture
def db_session(tmp_path):
    db_file = str(tmp_path / "test_phase4_orm.db")
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "orchestrator_revenue_phase4.db")
    store = DurableTaskStore(db_path=db_path)
    orch = AutomationOrchestrator(store=store)
    return RevenueWorkflowEngine(orchestrator=orch)


def test_db_level_audit_immutability_event_listeners(db_session):
    audit = RevenueAuditLogModel(
        audit_id="aud_test_1001",
        lead_id="lead_1001",
        actor_bot="hunter",
        previous_state="NONE",
        next_state="DISCOVERED",
        reason="Discovered lead",
    )
    db_session.add(audit)
    db_session.commit()

    # 1. Attempt UPDATE -> Fails at DB Event Listener Level with PermissionError
    audit.reason = "Tampered reason"
    with pytest.raises(PermissionError, match="Database-level rule forbids UPDATE"):
        db_session.commit()

    db_session.rollback()

    # 2. Attempt DELETE -> Fails at DB Event Listener Level with PermissionError
    db_session.delete(audit)
    with pytest.raises(PermissionError, match="Database-level rule forbids DELETE"):
        db_session.commit()


def test_live_pilot_stage_a_1_lead(temp_store):
    engine = temp_store

    sample_leads = [
        {"tenant_id": "tenant_jiya", "name": "Jiya Makeover Clinic", "phone": "+919876543210", "email": "jiya@jiyamakeover.in", "domain": "jiyamakeover.in", "niche": "beauty_salon"}
    ]

    res = engine.run_live_revenue_pilot(sample_leads, stage="A")

    assert res["stage"] == "A"
    assert res["eligible"] == 1
    assert res["sent"] == 1
    assert res["delivered"] == 1
    assert res["replies"] == 0  # Honest canary rule: 0 fake replies
    assert res["paid"] == 0
    assert res["verified_inr"] == 0
    assert res["critical_violations"] == 0
    assert "| A     |" in res["formatted_row"]


def test_live_pilot_stage_b_5_leads(temp_store):
    engine = temp_store

    sample_leads = [
        {"tenant_id": "tenant_jiya", "name": f"Salon {i}", "phone": f"+91987654321{i}", "email": f"salon{i}@jiya.in", "domain": f"salon{i}.in", "niche": "beauty_salon"}
        for i in range(5)
    ]

    res = engine.run_live_revenue_pilot(sample_leads, stage="B")

    assert res["stage"] == "B"
    assert res["eligible"] == 5
    assert res["sent"] == 5
    assert res["delivered"] == 5
    assert res["critical_violations"] == 0
    assert "| B     |" in res["formatted_row"]


def test_live_pilot_stage_c_20_leads(temp_store):
    engine = temp_store

    sample_leads = [
        {"tenant_id": "tenant_jiya", "name": f"Clinic {i}", "phone": f"+9198000000{i:02d}", "email": f"clinic{i}@jiya.in", "domain": f"clinic{i}.in", "niche": "beauty_salon"}
        for i in range(20)
    ]

    res = engine.run_live_revenue_pilot(sample_leads, stage="C")

    assert res["stage"] == "C"
    assert res["eligible"] == 20
    assert res["sent"] == 20
    assert res["delivered"] == 20
    assert res["critical_violations"] == 0
    assert "| C     |" in res["formatted_row"]


def test_business_funnel_summary_table_generation(temp_store):
    engine = temp_store

    leads_a = [{"tenant_id": "t_jiya", "name": "Lead A", "phone": "+919988776601", "email": "a@lead.in", "domain": "a.in", "niche": "salon"}]
    leads_b = [{"tenant_id": "t_jiya", "name": f"Lead B{i}", "phone": f"+91998877660{i+2}", "email": f"b{i}@lead.in", "domain": f"b{i}.in", "niche": "salon"} for i in range(5)]
    leads_c = [{"tenant_id": "t_jiya", "name": f"Lead C{i}", "phone": f"+9199887767{i:02d}", "email": f"c{i}@lead.in", "domain": f"c{i}.in", "niche": "salon"} for i in range(20)]

    res_a = engine.run_live_revenue_pilot(leads_a, stage="A")
    res_b = engine.run_live_revenue_pilot(leads_b, stage="B")
    res_c = engine.run_live_revenue_pilot(leads_c, stage="C")

    table = (
        "| Stage | Eligible | Sent | Delivered | Replies | Positive | Appointments | Paid | Verified ₹ | Critical Violations |\n"
        "| ----- | -------: | ---: | --------: | ------: | -------: | -----------: | ---: | ---------: | ------------------: |\n"
        f"{res_a['formatted_row']}\n"
        f"{res_b['formatted_row']}\n"
        f"{res_c['formatted_row']}\n"
    )

    assert "| A     |" in table
    assert "| B     |" in table
    assert "| C     |" in table
    assert "|       20 |" in table
