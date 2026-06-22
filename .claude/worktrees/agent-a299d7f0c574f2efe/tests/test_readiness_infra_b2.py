"""B2 - per-client activity timeline endpoint + pure aggregator."""

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import require_admin
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _admin_auth():
    app.dependency_overrides[require_admin] = lambda: {"id": "admin", "role": "super_admin"}
    yield
    app.dependency_overrides.pop(require_admin, None)


def test_timeline_flag_off(monkeypatch):
    monkeypatch.delenv("CLIENT_TIMELINE", raising=False)
    r = client.get("/api/admin/clients/abc/timeline")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_timeline_aggregator_merges_and_sorts():
    from app.api.admin_dashboard import _build_client_timeline

    events = _build_client_timeline(
        client_id="c1",
        agent_events=[
            {
                "at": "2026-06-20T10:00:00",
                "member": "neha",
                "action": "rescore",
                "detail": "",
                "meta": {"client_id": "c1"},
            }
        ],
        inquiries=[
            {"id": "i1", "client_id": "c1", "name": "Ravi", "at": "2026-06-20T09:00:00"}
        ],  # real inquiries use "at"
        audit=[
            {
                "created_at": "2026-06-20T11:00:00",
                "action": "impersonate.start",
                "resource_id": "c1",
            }
        ],
        limit=50,
    )
    # newest first
    assert [e["ts"][:16] for e in events] == [
        "2026-06-20T11:00",
        "2026-06-20T10:00",
        "2026-06-20T09:00",
    ]
    assert {e["source"] for e in events} == {"audit", "agent", "lead"}


def test_timeline_filters_other_clients():
    from app.api.admin_dashboard import _build_client_timeline

    events = _build_client_timeline(
        client_id="c1",
        agent_events=[
            {
                "at": "2026-06-20T10:00:00",
                "member": "x",
                "action": "a",
                "meta": {"client_id": "other"},
            }
        ],
        inquiries=[],
        audit=[],
        limit=50,
    )
    assert events == []
