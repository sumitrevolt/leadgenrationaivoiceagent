"""GET /api/admin/clients/{id}/timeline must merge delivery-ledger events
alongside the existing agent_events/inquiries/audit sources."""

from fastapi.testclient import TestClient


def test_client_timeline_includes_ledger_events(monkeypatch):
    from app.main import app
    from app.api.auth_deps import require_admin

    app.dependency_overrides[require_admin] = lambda: {"username": "test"}
    monkeypatch.setenv("CLIENT_TIMELINE", "1")

    monkeypatch.setattr("app.platform.team.recent_events", lambda limit=200: [], raising=False)
    monkeypatch.setattr("app.api.admin_dashboard._read_inquiries", lambda: [], raising=False)
    monkeypatch.setattr(
        "app.api.admin_dashboard._fetch_client_audit",
        lambda client_id, limit=100: [],
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.timeline",
        lambda client_id, limit=100, customer_only=False: [
            {
                "at": "2026-07-06T09:00:00",
                "event": "plan_activated",
                "label": "Plan activated",
                "icon": "✅",
                "detail": "starter",
                "actor": "system",
                "customer_visible": True,
                "meta": {},
            }
        ],
        raising=False,
    )

    with TestClient(app) as c:
        resp = c.get("/api/admin/clients/c1/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    kinds = [e["kind"] for e in body["events"]]
    assert "delivery" in kinds
    app.dependency_overrides.clear()
