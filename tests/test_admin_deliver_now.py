"""POST /api/admin/clients/{client_id}/deliver-now — human-clicked single-customer
delivery bypass. Never flips AUTO_DELIVER_VALUE; always calls
deliver_client_value(client, force=True), the existing operator bypass."""

from fastapi.testclient import TestClient


def _override_admin(app):
    """Matches the established pattern in tests/test_upi_config.py — overriding
    require_admin replaces the whole dependency, so a plain dict is enough."""
    from app.api.auth_deps import require_admin

    app.dependency_overrides[require_admin] = lambda: {"username": "test"}


def test_deliver_now_success(monkeypatch):
    from app.main import app

    _override_admin(app)
    client = {"id": "c1", "business_name": "Test Biz", "phone": "9812345678", "slug": "s"}
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: client, raising=False)

    async def _fake_deliver(client, force=False):
        assert force is True
        return {"delivered": True, "client_id": "c1"}

    monkeypatch.setattr(
        "app.marketing.customer_delivery.deliver_client_value", _fake_deliver, raising=False
    )

    events = []
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda client_id, event, **kw: events.append((client_id, event)),
    )

    with TestClient(app) as c:
        resp = c.post("/api/admin/clients/c1/deliver-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is True
    assert ("c1", "admin_manual_action") in events
    app.dependency_overrides.clear()


def test_deliver_now_failure_still_logs_reason(monkeypatch):
    from app.main import app

    _override_admin(app)
    client = {"id": "c2", "business_name": "No Phone Biz", "phone": "", "slug": "s2"}
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: client, raising=False)

    async def _fake_deliver(client, force=False):
        return {"delivered": False, "skipped": "no_phone"}

    monkeypatch.setattr(
        "app.marketing.customer_delivery.deliver_client_value", _fake_deliver, raising=False
    )

    events = []
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda client_id, event, **kw: events.append((client_id, event, kw.get("detail"))),
    )

    with TestClient(app) as c:
        resp = c.post("/api/admin/clients/c2/deliver-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["delivered"] is False
    assert body["reason"] == "no_phone"
    assert ("c2", "admin_manual_action", "no_phone") in events
    app.dependency_overrides.clear()


def test_deliver_now_unknown_client_404(monkeypatch):
    from app.main import app

    _override_admin(app)
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: None, raising=False)
    with TestClient(app) as c:
        resp = c.post("/api/admin/clients/does-not-exist/deliver-now")
    assert resp.status_code == 404
    app.dependency_overrides.clear()
