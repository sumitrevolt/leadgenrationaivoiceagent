"""Tests for Customer Delivery OS: paid customer dashboard, setup wizard data, Day-1 value,
admin command center visibility, social errors, and navigation cleanup.
"""

from fastapi.testclient import TestClient
import pytest
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import require_admin
from app.api.customer_auth import require_customer
from app.main import app


def test_customer_dashboard_active_view_payload(monkeypatch):
    """1. Verify paid customer sees onboarding checklist, setup fields in portal response."""
    app.dependency_overrides[require_customer] = lambda: "jiya-makeover"

    fake_client = {
        "id": "jiya-makeover",
        "business_name": "Jiya Makeover",
        "city": "Mumbai",
        "phone": "917498797259",
        "status": "active",
        "plan": "starter",
        "product": "marketing",
        "setup_done": False,
        "services": "Bridal makeup, hair design",
        "target_area": "Andheri West",
        "whatsapp_phone": "917498797259",
        "approval_preference": "manual",
        "social_error": "Instagram connection timeout",
    }

    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: fake_client, raising=False
    )
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients", lambda status=None: [fake_client], raising=False
    )

    with TestClient(app) as client:
        resp = client.get("/api/customer/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_id"] == "jiya-makeover"
    assert data["social_error"] == "Instagram connection timeout"

    # Checklist verification
    onb = data.get("onboarding")
    assert onb is not None
    steps = onb["steps"]
    assert any(step["id"] == "wizard_details" and step["done"] is True for step in steps)
    assert any(step["id"] == "whatsapp" and step["done"] is True for step in steps)

    app.dependency_overrides.clear()


def test_starter_plan_day1_value_generation(monkeypatch):
    """2. Verify ₹1,999 (marketing starter) plan creates a Day-1 value content packet."""
    cid = f"test-mkt-{uuid.uuid4().hex[:6]}"
    fake_client = {
        "id": cid,
        "business_name": "Jiya Makeover",
        "city": "Mumbai",
        "phone": "917498797259",
        "status": "active",
        "plan": "starter",
        "product": "marketing",
        "slug": f"slug-{cid}",
    }

    submitted_drafts = []
    logged_events = []

    async def fake_generate_for_client(client, day=None):
        d_str = str(day) if day else "2026-07-01"
        return [
            {
                "date": d_str,
                "type": "post",
                "title": "Beauty post",
                "caption": "Beauty post description",
            }
        ]

    async def fake_broadcast_pack(business_name, niche, occasion="", offer=""):
        return {"broadcast": ["Special WhatsApp promo draft!"]}

    def fake_submit(cid, draft):
        submitted_drafts.append(draft)
        return True

    def fake_log_event(cid, event, detail="", actor="system", meta=None):
        logged_events.append((cid, event, detail))

    monkeypatch.setattr(
        "app.marketing.auto_content.generate_for_client", fake_generate_for_client, raising=False
    )
    monkeypatch.setattr(
        "app.marketing.whatsapp_pack.broadcast_pack", fake_broadcast_pack, raising=False
    )
    monkeypatch.setattr("app.marketing.content_approval.submit", fake_submit, raising=False)
    monkeypatch.setattr("app.marketing.delivery_ledger.log_event", fake_log_event, raising=False)

    import asyncio

    from app.marketing import auto_content

    result = asyncio.run(auto_content.seed_client_content(fake_client))

    assert result >= 9  # 7 days posts + 1 whatsapp promo + 1 suggestion
    assert len(submitted_drafts) >= 9
    assert any("WhatsApp Promo Message" in d.get("title", "") for d in submitted_drafts)
    assert any("Local Offer Campaign Suggestion" in d.get("title", "") for d in submitted_drafts)

    # Ledger verification
    assert any(ev[1] == "marketing_calendar_generated" for ev in logged_events)
    assert any(ev[1] == "post_draft_created" for ev in logged_events)


def test_admin_sees_customer_delivery_status(monkeypatch):
    """3. Verify admin sees customer delivery status, setup done, and failures."""
    app.dependency_overrides[require_admin] = lambda: "admin-user"

    fake_client = {
        "id": "jiya-makeover",
        "business_name": "Jiya Makeover",
        "city": "Mumbai",
        "phone": "917498797259",
        "status": "active",
        "plan": "starter",
        "product": "marketing",
        "setup_done": True,
        "delivery_state": "delivered",
    }

    def fake_summary(cid):
        return {"value_delivered": True, "automation_failures": 0}

    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients", lambda status=None: [fake_client], raising=False
    )
    monkeypatch.setattr(
        "app.delivery_ledger.summary"
        if hasattr(fake_client, "none")
        else "app.marketing.delivery_ledger.summary",
        fake_summary,
        raising=False,
    )

    with TestClient(app) as client:
        resp = client.get("/api/admin/command-center")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["summary"]["receiving_value"] == 1
    assert data["summary"]["stuck_in_setup"] == 0
    assert data["per_customer"][0]["value_delivered"] is True

    app.dependency_overrides.clear()


def test_failed_social_connection_blocked_state(monkeypatch):
    """4. Verify failed social connection maps to blocked/error state."""
    app.dependency_overrides[require_customer] = lambda: "jiya-makeover"

    fake_client = {
        "id": "jiya-makeover",
        "business_name": "Jiya Makeover",
        "city": "Mumbai",
        "phone": "917498797259",
        "status": "active",
        "plan": "starter",
        "product": "marketing",
        "social_error": "Connection refused by Meta OAuth API (403)",
        "blocked_reason": "Failed to authenticate Instagram account.",
    }

    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: fake_client, raising=False
    )

    with TestClient(app) as client:
        resp = client.get("/api/customer/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["social_error"] == "Connection refused by Meta OAuth API (403)"

    app.dependency_overrides.clear()


def test_command_center_navigation_cleanup():
    """5. Verify duplicate/confusing command-center page returns 307 redirect."""
    with TestClient(app) as client:
        resp = client.get("/app/command-center", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/app/control-center"


def test_delivery_ledger_records_automation_events():
    """6. Verify delivery ledger records automation events correctly."""
    from app.marketing import delivery_ledger

    cid = "test-client-ledger"
    delivery_ledger.log_event(cid, "post_published", detail="Instagram post id: 12987")

    events = delivery_ledger.timeline(cid, limit=5, customer_only=False)
    assert len(events) >= 1
    assert events[0]["event"] == "post_published"
    assert "Instagram post id" in events[0]["detail"]
