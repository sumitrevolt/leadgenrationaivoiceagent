"""GET /api/customer/timeline — customer-facing 'AI ne aapke liye kya kiya'.
Must be scoped to the caller's OWN client_id only (require_customer, same
IDOR-safe pattern as every other /api/customer/* route)."""
from fastapi.testclient import TestClient


def test_customer_timeline_returns_own_events_only(monkeypatch):
    from app.main import app
    from app.api.customer_auth import require_customer

    app.dependency_overrides[require_customer] = lambda: "client_A"

    def _fake_get_timeline(client_id, limit=30, audience="customer"):
        assert client_id == "client_A"  # never leaks another client's id
        assert audience == "customer"
        return [{"ts": "2026-07-06T09:00:00", "event_type": "plan_activated",
                 "label": "Aapka plan activate ho gaya", "icon": "✅", "detail": "", "status": "ok"}]

    monkeypatch.setattr("app.platform.delivery_ledger.get_timeline", _fake_get_timeline, raising=False)

    with TestClient(app) as c:
        resp = c.get("/api/customer/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["events"]) == 1
    assert body["events"][0]["label"] == "Aapka plan activate ho gaya"
    # Technical event_type/detail must not leak to the customer-facing payload's
    # raw form beyond what get_timeline(audience="customer") already redacted.
    app.dependency_overrides.clear()


def test_customer_timeline_empty_state_is_graceful(monkeypatch):
    from app.main import app
    from app.api.customer_auth import require_customer

    app.dependency_overrides[require_customer] = lambda: "client_B"
    monkeypatch.setattr("app.platform.delivery_ledger.get_timeline", lambda *a, **k: [], raising=False)

    with TestClient(app) as c:
        resp = c.get("/api/customer/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["events"] == []
    app.dependency_overrides.clear()
