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

        # Real initial-status contract (see initialize_deliverables_for_client):
        # ONLY `invoice` defaults to DELIVERED; `onboarding_profile` waits on the
        # customer; every other row starts NOT_STARTED. (Earlier draft of this test
        # assumed onboarding+brand-kit+invoice all auto-complete = 30% — the code
        # defaults only invoice, and the customer-facing % is jsonl-derived below.)
        by_type = {r.deliverable_type: r for r in rows}
        assert by_type["invoice"].status == DeliverableStatus.DELIVERED
        assert by_type["onboarding_profile"].status == DeliverableStatus.WAITING_CUSTOMER

        # 2. customer_delivery_status() is the CUSTOMER-FACING source of truth and is
        # jsonl-derived, NOT computed from the DB rows above (those are a best-effort
        # side-effect record whose taxonomy is deliberately not yet reconciled with the
        # returned `deliverables` — see the comment in customer_delivery_status()).
        fake_client = {
            "id": client_id,
            "business_name": "Test Client",
            "city": "Mumbai",
            "phone": "917498797259",
            "status": "active",
            "plan": "starter",
            "product": "marketing",
            "whatsapp_phone": "917498797259",
            "onboarding": {"complete": True},
        }
        monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: fake_client, raising=False)
        monkeypatch.setattr("app.marketing.delivery_ledger.timeline", lambda cid, **kwargs: [], raising=False)

        status_res = customer_delivery_status(client_id)
        assert status_res["ok"] is True
        assert "deliverables" in status_res
        # Honest %: business details present but no generated content yet → only the
        # business-profile deliverable is "done" (10%). Deliberately NOT inflated to
        # count the DB-defaulted invoice row — showing a paid customer a higher
        # completion% than was actually delivered would break the no-fabricated-claims
        # invariant this project holds for the one real paying customer.
        pct = status_res["deliverable_completion_pct"]
        assert isinstance(pct, int) and 0 <= pct <= 100
        assert pct == 10

        # DEFERRED (not yet built): DB-row status sync from generated content
        # (poster→DELIVERED etc.). customer_delivery_status() only *initializes* the
        # DB rows as a side effect; it does not update their status. Re-add a
        # DB-status-sync assertion here once the DB deliverable taxonomy is reconciled
        # with the semantic ids the frontend/admin key on.
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
