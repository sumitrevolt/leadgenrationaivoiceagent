"""Tests for Customer Deliverable DB initialization, lazy-syncing, and querying."""
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.api.customer_auth import require_customer
from app.models.customer_deliverable import CustomerDeliverable, DeliverableStatus, DeliverableChannel
from app.marketing.product_one_delivery import initialize_deliverables_for_client, customer_delivery_status

def _iso_db(monkeypatch):
    """Wire app.models.base to a fresh in-memory SQLite so get_db_session() uses it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.models.base as base_mod

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Session = sessionmaker(bind=engine)
    base_mod.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(base_mod, "_engine", engine)
    monkeypatch.setattr(base_mod, "_SessionLocal", Session)
    return Session

def test_initialize_and_sync_deliverables(monkeypatch):
    Session = _iso_db(monkeypatch)
    
    # 1. Initialize deliverables for a client
    client_id = "test-client-123"
    
    session = Session()
    try:
        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")
        session.commit()

        rows = session.query(CustomerDeliverable).filter(CustomerDeliverable.client_id == client_id).all()
        assert len(rows) > 0
        assert any(r.channel == DeliverableChannel.DASHBOARD for r in rows)
        assert any(r.channel == DeliverableChannel.POSTER for r in rows)
        assert any(r.channel == DeliverableChannel.REPORT for r in rows)
        
        # 2. Sync / query deliverables status on-read
        fake_client = {
            "id": client_id,
            "business_name": "Test Client",
            "city": "Mumbai",
            "phone": "917498797259",
            "status": "active",
            "plan": "starter",
            "product": "marketing",
            "whatsapp_phone": "917498797259",
            "onboarding": {"complete": True}
        }
        monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: fake_client, raising=False)
        monkeypatch.setattr("app.marketing.delivery_ledger.timeline", lambda cid, **kwargs: [], raising=False)
        
        status_res = customer_delivery_status(client_id)
        assert status_res["ok"] is True
        assert "deliverables" in status_res
        assert status_res["deliverable_completion_pct"] == 30 # Onboarding, Brand Kit, and Invoice default to complete
        
        # Now mock items (e.g. 4 posters) to trigger the sync of posters to DELIVERED
        fake_items = [
            {"type": "poster", "status": "approved"},
            {"type": "poster", "status": "approved"},
            {"type": "poster", "status": "approved"},
            {"type": "poster", "status": "approved"},
        ]
        monkeypatch.setattr("app.marketing.product_one_delivery._content_items", lambda cid: fake_items, raising=False)
        
        status_res_updated = customer_delivery_status(client_id)
        assert status_res_updated["deliverable_completion_pct"] > 30
        
        # Force reload from DB to clear session cache
        session.expire_all()
        
        # Verify that the DB row status is updated to DELIVERED
        db_deliv = session.query(CustomerDeliverable).filter(
            CustomerDeliverable.client_id == client_id,
            CustomerDeliverable.deliverable_type == "branded_poster"
        ).first()
        assert db_deliv.status == DeliverableStatus.DELIVERED
    finally:
        session.close()

def test_api_customer_delivery_proof_endpoint(monkeypatch):
    Session = _iso_db(monkeypatch)
    client_id = "jiya-makeover"
    
    session = Session()
    try:
        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")
        session.commit()
    finally:
        session.close()
    
    app.dependency_overrides[require_customer] = lambda: client_id
    
    fake_client = {
        "id": client_id,
        "business_name": "Jiya Makeover",
        "city": "Mumbai",
        "phone": "917498797259",
        "status": "active",
        "plan": "starter",
        "product": "marketing",
    }
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: fake_client, raising=False)
    monkeypatch.setattr("app.marketing.delivery_ledger.timeline", lambda cid, **kwargs: [], raising=False)

    with TestClient(app) as client:
        resp = client.get("/api/customer/delivery-proof")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "deliverables" in data
    
    app.dependency_overrides.clear()
