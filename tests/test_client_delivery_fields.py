"""Tests for client delivery field sync + delivery cockpit revenue fix (ADR-064)."""

import pytest


def test_client_model_has_delivery_fields():
    """Client model includes all 13 delivery tracking fields."""
    from app.models.client import Client

    fields = [
        "delivery_stage",
        "onboarding_status",
        "social_setup_status",
        "content_generation_status",
        "approval_status",
        "posting_status",
        "report_status",
        "last_delivery_at",
        "next_action",
        "blocking_reason",
        "assigned_agent",
        "automation_health",
        "setup_completed_at",
    ]
    for f in fields:
        assert hasattr(Client, f), f"Client model missing field: {f}"


def test_delivery_cockpit_has_revenue(monkeypatch):
    """delivery_cockpit() returns revenue block with mrr_total."""
    from app.marketing import product_one_delivery

    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status="active": [],
    )
    result = product_one_delivery.delivery_cockpit()
    assert result["ok"]
    assert "revenue" in result
    assert "mrr_total" in result["revenue"]
    assert "paying_customers" in result["revenue"]
    assert "by_plan" in result["revenue"]


def test_delivery_cockpit_revenue_from_clients(monkeypatch):
    """delivery_cockpit computes MRR from active paying clients."""
    from app.marketing import product_one_delivery

    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status="active": [
            {"id": "c1", "business_name": "Biz1", "plan": "starter", "status": "active"},
            {"id": "c2", "business_name": "Biz2", "plan": "trial", "status": "trial"},
        ],
    )

    # Mock _client_mrr to return known values
    def _mock_mrr(c):
        plan = c.get("plan", "")
        return 1999 if plan == "starter" else 0

    monkeypatch.setattr(
        "app.api.admin_dashboard_builders._client_mrr",
        _mock_mrr,
    )
    result = product_one_delivery.delivery_cockpit()
    assert result["revenue"]["mrr_total"] == 1999
    assert result["revenue"]["paying_customers"] == 1
    assert result["revenue"]["by_plan"]["Starter"] == {"count": 1, "mrr": 1999}
    assert result["revenue"]["by_plan"]["Trial"] == {"count": 1, "mrr": 0}


def test_delivery_ledger_has_social_setup_event():
    """delivery_ledger LABELS includes social_setup_completed."""
    from app.marketing.delivery_ledger import LABELS

    assert "social_setup_completed" in LABELS
    _, msg, _, _ = LABELS["social_setup_completed"]
    assert "social" in msg.lower()


def test_automation_log_model_exists():
    """AutomationLog model is importable."""
    from app.models.automation_log import AutomationLog

    assert AutomationLog.__tablename__ == "automation_logs"
    assert hasattr(AutomationLog, "job_type")
    assert hasattr(AutomationLog, "client_id")


def test_approvals_has_schedule_and_publish(monkeypatch, tmp_path):
    """content_approval persists scheduled/published/failed states and ledger proof."""
    from app.marketing import content_approval, delivery_ledger

    assert hasattr(content_approval, "schedule")
    assert hasattr(content_approval, "mark_published")
    assert hasattr(content_approval, "mark_failed")

    approvals_file = tmp_path / "content_approvals.jsonl"
    ledger_dir = tmp_path / "delivery_ledger"
    monkeypatch.setattr(content_approval, "_FILE", lambda: str(approvals_file))
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(ledger_dir))
    monkeypatch.setattr(
        "app.marketing.auto_content.enqueue_approved",
        lambda client_id, content, approval_id="": True,
    )

    # schedule should fail for non-existent approval
    result = content_approval.schedule("nonexistent_id", "2026-07-15")
    assert result["ok"] is False
    assert "approval nahi mila" in str(result.get("error", ""))

    submitted = content_approval.submit(
        "client_delivery", {"title": "July Offer", "caption": "Book now"}
    )
    assert submitted["ok"] is True
    approved = content_approval.approve(submitted["approval"]["token"])
    assert approved["ok"] is True
    approval_id = approved["approval"]["id"]

    scheduled = content_approval.schedule(approval_id, "2026-07-15")
    assert scheduled == {"ok": True, "id": approval_id, "status": "scheduled"}
    latest = content_approval.list_all("client_delivery")[0]
    assert latest["status"] == "scheduled"
    assert latest["scheduled_date"] == "2026-07-15"

    published = content_approval.mark_published(
        approval_id, channel="instagram", evidence_url="https://example.com/post"
    )
    assert published == {"ok": True, "id": approval_id, "status": "published"}
    latest = content_approval.list_all("client_delivery")[0]
    assert latest["status"] == "published"
    assert latest["publish_channel"] == "instagram"
    assert latest["evidence_url"] == "https://example.com/post"

    events = delivery_ledger.timeline("client_delivery", customer_only=True)
    event_names = [e["event"] for e in events]
    assert "post_approved" in event_names
    assert "post_published" in event_names

    failed = content_approval.mark_failed(approval_id, "Meta token expired")
    assert failed == {"ok": True, "id": approval_id, "status": "failed"}
    latest = content_approval.list_all("client_delivery")[0]
    assert latest["status"] == "failed"
    assert latest["error_message"] == "Meta token expired"
    event_names = [
        e["event"] for e in delivery_ledger.timeline("client_delivery", customer_only=True)
    ]
    assert "post_failed" in event_names
