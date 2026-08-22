"""Ops MCP tools (/api/ops/*) — contract + auth tests.

conftest.py globally require_admin ko mock-user se override karta hai; auth
proof ke liye hum override POP karte hain (test_blueprint_api_auth pattern).
"""

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import get_current_user, require_admin
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _pop_auth():
    # conftest dono ko override karta hai (get_current_user = mock-admin);
    # dono pop karne se REAL auth chain chalti hai -> bina token = 401.
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------- auth gate
def test_hotqueue_requires_admin(client):
    _pop_auth()
    try:
        r = client.get("/api/ops/hotqueue")
        assert r.status_code in (401, 403), r.text
    finally:
        pass


def test_revenue_summary_requires_admin(client):
    _pop_auth()
    try:
        r = client.get("/api/ops/revenue-summary")
        assert r.status_code in (401, 403), r.text
    finally:
        pass


# ---------------------------------------------------------------- hot queue
def test_ops_hot_queue_shape(client, monkeypatch):
    from app.platform import reply_agent

    monkeypatch.setattr(
        reply_agent,
        "hot_queue",
        lambda limit=50, scope="boss": [{"hq_id": "x:1", "text": "interested"}],
    )
    monkeypatch.setattr(
        reply_agent,
        "hot_queue_summary",
        lambda rows, scope="boss": {"pending": len(rows)},
    )
    r = client.get("/api/ops/hotqueue?limit=10&scope=boss")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["count"] == 1
    assert body["items"][0]["hq_id"] == "x:1"
    assert body["summary"]["pending"] == 1


def test_ops_hot_queue_bad_scope_defaults_boss(client, monkeypatch):
    from app.platform import reply_agent

    seen = {}

    def fake_hq(limit=50, scope="boss"):
        seen["scope"] = scope
        return []

    monkeypatch.setattr(reply_agent, "hot_queue", fake_hq)
    monkeypatch.setattr(reply_agent, "hot_queue_summary", lambda rows, scope="boss": {})
    r = client.get("/api/ops/hotqueue?scope=nonsense")
    assert r.status_code == 200
    assert seen["scope"] == "boss"


# ---------------------------------------------------------------- action
def test_ops_action_done_ok(client, monkeypatch):
    from app.platform import reply_agent

    monkeypatch.setattr(reply_agent, "mark_handled", lambda hq_id: True)
    r = client.post("/api/ops/hotqueue/action", json={"action": "done", "hq_id": "x:9"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "hq_id": "x:9", "action": "done"}


def test_ops_action_park_with_note(client, monkeypatch):
    from app.platform import reply_agent

    captured = {}
    monkeypatch.setattr(
        reply_agent,
        "park_for_admin",
        lambda hq_id, note="": captured.update({"id": hq_id, "note": note}) or True,
    )
    r = client.post(
        "/api/ops/hotqueue/action",
        json={"action": "park", "hq_id": "y:2", "note": "wait for owner"},
    )
    assert r.status_code == 200
    assert captured == {"id": "y:2", "note": "wait for owner"}


def test_ops_action_invalid_action_422(client):
    r = client.post("/api/ops/hotqueue/action", json={"action": "send", "hq_id": "z:1"})
    assert r.status_code == 422


def test_ops_action_unknown_id_404(client, monkeypatch):
    from app.platform import reply_agent

    monkeypatch.setattr(reply_agent, "mark_handled", lambda hq_id: False)
    r = client.post("/api/ops/hotqueue/action", json={"action": "done", "hq_id": "nope"})
    assert r.status_code == 404


# ---------------------------------------------------------------- revenue
def test_ops_revenue_summary_shape(client, monkeypatch):
    from app.billing import gst_invoice

    monkeypatch.setattr(
        gst_invoice,
        "stats",
        lambda: {
            "total": 3,
            "fy": "2026-27",
            "fy_count": 3,
            "fy_gross_inr": 5997.0,
            "fy_voided_count": 0,
            "fy_voided_gross_inr": 0.0,
            "registered_mode": False,
            "send_enabled": False,
        },
    )
    monkeypatch.setattr(
        gst_invoice,
        "list_invoices",
        lambda limit=10: [
            {
                "number": "INV/2026-27/0001",
                "client_id": "jiya-makeover",
                "plan": "starter",
                "gross_inr": 1999,
                "voided": False,
                "date": "2026-07-05",
            }
        ],
    )
    r = client.get("/api/ops/revenue-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["stats"]["fy_gross_inr"] == 5997.0
    assert body["recent"][0]["number"] == "INV/2026-27/0001"
