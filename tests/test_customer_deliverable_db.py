"""Tests for Customer Deliverable DB initialization, lazy-syncing, and querying."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.api.customer_auth import require_customer
from app.main import app
from app.marketing.product_one_delivery import (
    DELIVERABLES,
    customer_deliverable_db_audit,
    customer_delivery_status,
    initialize_deliverables_for_client,
    record_manual_action,
    sync_customer_deliverable_status,
)
from app.models.customer_deliverable import (
    CustomerDeliverable,
    DeliverableChannel,
    DeliverableStatus,
)


def _iso_db(monkeypatch):
    """Wire app.models.base to a fresh in-memory SQLite so get_db_session() uses it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models.base as base_mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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

        rows = (
            session.query(CustomerDeliverable)
            .filter(CustomerDeliverable.client_id == client_id)
            .all()
        )
        assert len(rows) == len(DELIVERABLES)
        assert {r.deliverable_type for r in rows} == {d[0] for d in DELIVERABLES}
        assert any(r.channel == DeliverableChannel.DASHBOARD for r in rows)
        assert any(r.channel == DeliverableChannel.POSTER for r in rows)
        assert any(r.channel == DeliverableChannel.REPORT for r in rows)

        # Real initial-status contract: business_profile waits on the customer;
        # every other semantic deliverable starts NOT_STARTED.
        by_type = {r.deliverable_type: r for r in rows}
        assert by_type["business_profile"].status == DeliverableStatus.WAITING_CUSTOMER
        assert all(
            r.status == DeliverableStatus.NOT_STARTED
            for dtype, r in by_type.items()
            if dtype != "business_profile"
        )

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
        monkeypatch.setattr(
            "app.marketing.clients_store.get_client", lambda cid: fake_client, raising=False
        )
        monkeypatch.setattr(
            "app.marketing.delivery_ledger.timeline", lambda cid, **kwargs: [], raising=False
        )

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


def test_initialize_normalizes_legacy_deliverable_types(monkeypatch):
    Session = _iso_db(monkeypatch)
    client_id = "legacy-client-123"

    session = Session()
    try:
        session.add(
            CustomerDeliverable(
                id="legacy-1",
                client_id=client_id,
                plan_code="starter",
                billing_cycle_month="2026-07",
                deliverable_type="onboarding_profile",
                title="Legacy onboarding",
                status=DeliverableStatus.WAITING_CUSTOMER,
                channel=DeliverableChannel.DASHBOARD,
            )
        )
        session.commit()

        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")

        rows = (
            session.query(CustomerDeliverable)
            .filter(CustomerDeliverable.client_id == client_id)
            .all()
        )
        assert any(r.id == "legacy-1" and r.deliverable_type == "business_profile" for r in rows)
        assert {r.deliverable_type for r in rows} == {d[0] for d in DELIVERABLES}
    finally:
        session.close()


def test_sync_customer_deliverable_status_updates_existing_row(monkeypatch):
    Session = _iso_db(monkeypatch)
    client_id = "sync-client-123"

    session = Session()
    try:
        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")
        assert sync_customer_deliverable_status(
            client_id,
            "monthly_report",
            "delivered",
            billing_cycle_month="2026-07",
            evidence_url="/reports/sync-client-123/2026-07",
            evidence_payload={"report": "July"},
            note="July report sent",
            owner="ops-team",
        )

        row = (
            session.query(CustomerDeliverable)
            .filter(
                CustomerDeliverable.client_id == client_id,
                CustomerDeliverable.deliverable_type == "monthly_report",
            )
            .one()
        )
        session.refresh(row)
        assert row.status == DeliverableStatus.DELIVERED
        assert row.delivered_at is not None
        assert row.evidence_url == "/reports/sync-client-123/2026-07"
        payload = json.loads(row.evidence_payload)
        assert payload["report"] == "July"
        assert payload["note"] == "July report sent"
        assert row.owner == "ops-team"
    finally:
        session.close()


def test_record_manual_action_syncs_monthly_report_row(monkeypatch, tmp_path):
    Session = _iso_db(monkeypatch)
    client_id = "manual-sync-client"
    monkeypatch.setattr(
        "app.marketing.product_one_delivery._DELIVERY_DIR",
        str(tmp_path / "product_one_delivery"),
        raising=False,
    )

    session = Session()
    try:
        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")

        async def _fake_report(cid, send=False):
            return {"ok": True, "client_id": cid, "sent": send}

        monkeypatch.setattr(
            "app.marketing.client_report.build_report",
            _fake_report,
            raising=False,
        )

        out = asyncio.run(
            record_manual_action(
                client_id, "monthly_report", note="July report sent", owner="ops-team"
            )
        )
        assert out["ok"] is True

        row = (
            session.query(CustomerDeliverable)
            .filter(
                CustomerDeliverable.client_id == client_id,
                CustomerDeliverable.deliverable_type == "monthly_report",
            )
            .one()
        )
        session.refresh(row)
        assert row.status == DeliverableStatus.DELIVERED
        assert row.delivered_at is not None
        assert "July report sent" in (row.evidence_payload or "")
    finally:
        session.close()


def test_content_mark_item_syncs_social_and_proof_rows(monkeypatch, tmp_path):
    Session = _iso_db(monkeypatch)
    client_id = "content-sync-client"
    monkeypatch.setattr(
        "app.marketing.auto_content._QUEUE_DIR",
        lambda: str(tmp_path / "content_queue"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger._LEDGER_DIR",
        lambda: str(tmp_path / "delivery_ledger"),
        raising=False,
    )

    session = Session()
    try:
        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")

        from app.marketing import auto_content

        assert auto_content._append_items(
            client_id,
            [
                {
                    "id": "item-1",
                    "client_id": client_id,
                    "date": "2026-07-08",
                    "type": "post",
                    "title": "July Offer",
                    "caption": "July offer is live for local customers today.",
                    "status": "draft",
                    "created_at": "2026-07-08T00:00:00+00:00",
                }
            ],
        )
        assert auto_content.mark_item(client_id, "item-1", "approved")
        assert auto_content.mark_item(client_id, "item-1", "posted")

        rows = {
            r.deliverable_type: r
            for r in session.query(CustomerDeliverable)
            .filter(CustomerDeliverable.client_id == client_id)
            .all()
        }
        session.refresh(rows["social_posts"])
        session.refresh(rows["proof"])
        assert rows["social_posts"].status == DeliverableStatus.APPROVED
        assert rows["proof"].status == DeliverableStatus.DELIVERED
        assert rows["proof"].delivered_at is not None
        assert "July Offer" in (rows["proof"].evidence_payload or "")
    finally:
        session.close()


def test_customer_deliverable_db_audit_flags_and_clears_drift(monkeypatch):
    Session = _iso_db(monkeypatch)
    client_id = "audit-client-123"

    session = Session()
    try:
        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")
        cards = [
            {
                "id": client_id,
                "customer_name": "Audit Client",
                "deliverables": [
                    {"id": "business_profile", "status": "done"},
                    {"id": "monthly_report", "status": "pending"},
                ],
            }
        ]

        audit = customer_deliverable_db_audit(cards)
        assert audit["ok"] is True
        assert audit["checked_deliverables"] == 2
        assert audit["stale_db_rows"] == 1
        assert audit["read_path_ready"] is False
        assert audit["mismatches"][0]["kind"] == "db_behind"
        assert audit["mismatches"][0]["deliverable_id"] == "business_profile"

        assert sync_customer_deliverable_status(
            client_id,
            "business_profile",
            "delivered",
            billing_cycle_month="2026-07",
            note="Business profile captured",
        )

        audit = customer_deliverable_db_audit(cards)
        assert audit["read_path_ready"] is True
        assert audit["stale_db_rows"] == 0
        assert audit["mismatches"] == []
    finally:
        session.close()


def test_delivery_cockpit_includes_db_audit(monkeypatch):
    Session = _iso_db(monkeypatch)
    client_id = "cockpit-db-audit"

    session = Session()
    try:
        initialize_deliverables_for_client(session, client_id, "starter", "2026-07")
    finally:
        session.close()

    fake_client = {
        "id": client_id,
        "business_name": "Cockpit Audit",
        "city": "Mumbai",
        "phone": "917498797259",
        "status": "active",
        "plan": "starter",
        "product": "marketing",
        "whatsapp_phone": "917498797259",
        "approval_preference": "manual",
        "brand": {"primary": "#111111", "logo_text": "Audit"},
        "socials": {"instagram": "audit"},
    }
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [fake_client],
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.timeline", lambda cid, **kwargs: [], raising=False
    )
    monkeypatch.setattr("app.marketing.delivery_ledger.summary", lambda cid: {}, raising=False)
    monkeypatch.setattr(
        "app.marketing.product_one_delivery.integration_readiness",
        lambda: {"ok": True, "integrations": [], "scheduler": {}, "affected_customers_total": 0},
        raising=False,
    )

    from app.marketing import product_one_delivery

    cockpit = product_one_delivery.delivery_cockpit()
    assert "db_audit" in cockpit
    assert cockpit["db_audit"]["ok"] is True
    assert cockpit["db_audit"]["checked_customers"] == 1
    assert cockpit["db_audit"]["checked_deliverables"] == len(DELIVERABLES)


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
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: fake_client, raising=False
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.timeline",
        lambda cid, **kwargs: [
            {
                "at": "2026-07-09T10:00:00+00:00",
                "event": "post_published",
                "label": "Post published",
                "detail": "Instagram offer post",
            },
            {
                "at": "2026-07-08T10:00:00+00:00",
                "event": "post_approved",
                "label": "Post approved",
                "detail": "Monsoon makeup post",
            },
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.content_approval.pending",
        lambda cid: [
            {
                "id": "appr123",
                "status": "pending",
                "created_at": "2026-07-09T09:00:00",
                "content": {
                    "title": "Bridal makeup offer",
                    "caption": "Book your bridal look this week.",
                },
            }
        ],
        raising=False,
    )

    with TestClient(app) as client:
        resp = client.get("/api/customer/delivery-proof")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "deliverables" in data
    assert data["approvals_pending"][0]["title"] == "Bridal makeup offer"
    assert data["approvals_pending"][0]["caption_preview"] == "Book your bridal look this week."
    assert [p["status"] for p in data["posts_published"]] == ["published", "approved"]
    assert data["posts_published"][0]["title"] == "Instagram offer post"

    app.dependency_overrides.clear()
