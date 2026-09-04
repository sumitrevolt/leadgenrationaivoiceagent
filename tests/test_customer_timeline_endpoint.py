"""GET /api/customer/timeline — customer-facing 'AI ne aapke liye kya kiya'.
Must be scoped to the caller's OWN client_id only (require_customer, same
IDOR-safe pattern as every other /api/customer/* route)."""

from fastapi.testclient import TestClient


def test_customer_timeline_returns_own_events_only(monkeypatch):
    from app.api.customer_auth import require_customer
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "client_A"

    def _fake_timeline(client_id, limit=30, customer_only=False):
        assert client_id == "client_A"  # never leaks another client's id
        assert customer_only is True
        return [
            {
                "at": "2026-07-06T09:00:00",
                "event": "plan_activated",
                "label": "Aapka plan activate ho gaya",
                "icon": "✅",
                "detail": "",
                "actor": "system",
                "customer_visible": True,
                "meta": {},
            }
        ]

    monkeypatch.setattr("app.marketing.delivery_ledger.timeline", _fake_timeline, raising=False)

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


def test_customer_timeline_backfills_pre_ledger_customer(monkeypatch):
    """Existing (pre-ledger) customers like jiya makeover ka historical timeline
    tabhi bharega jab endpoint read se PEHLE ensure_backfilled() bulaaye. Ye wire
    pehle missing tha (function exported par zero callers) — regression guard."""
    from app.api.customer_auth import require_customer
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "client_A"
    called = {"backfill_cid": None, "order": []}

    def _fake_backfill(cid):
        called["backfill_cid"] = cid
        called["order"].append("backfill")

    def _fake_timeline(client_id, limit=30, customer_only=False):
        called["order"].append("timeline")
        return []

    monkeypatch.setattr(
        "app.marketing.delivery_ledger.ensure_backfilled", _fake_backfill, raising=False
    )
    monkeypatch.setattr("app.marketing.delivery_ledger.timeline", _fake_timeline, raising=False)

    with TestClient(app) as c:
        resp = c.get("/api/customer/timeline")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert called["backfill_cid"] == "client_A"  # backfilled the caller's OWN id
    assert called["order"] == ["backfill", "timeline"]  # backfill BEFORE read
    app.dependency_overrides.clear()


def test_customer_timeline_empty_state_is_graceful(monkeypatch):
    from app.api.customer_auth import require_customer
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "client_B"
    monkeypatch.setattr("app.marketing.delivery_ledger.timeline", lambda *a, **k: [], raising=False)

    with TestClient(app) as c:
        resp = c.get("/api/customer/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["events"] == []
    app.dependency_overrides.clear()
