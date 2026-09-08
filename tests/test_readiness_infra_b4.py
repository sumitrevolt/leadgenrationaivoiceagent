"""B4 - customer inline lead-status edit (override store + PATCH)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ALLOWED = {"Hot", "Warm", "Cold", "Won", "Lost", "Follow-up"}


def test_override_roundtrip(tmp_path, monkeypatch):
    from app.platform import lead_overrides as lo

    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    assert lo.set_status("lead1", "c1", "Won") is True
    lo.set_status("lead1", "c1", "Lost")  # latest wins
    ovr = lo.read_overrides()
    assert ovr["lead1"]["status"] == "Lost"
    assert ovr["lead1"]["client_id"] == "c1"


def test_set_status_rejects_bad_value(tmp_path, monkeypatch):
    from app.platform import lead_overrides as lo

    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    assert lo.set_status("lead1", "c1", "Nonsense") is False
    assert lo.read_overrides() == {}


def test_patch_requires_auth():
    # no customer token → rejected before any mutation
    r = client.patch("/api/customer/leads/x", json={"status": "Won"})
    assert r.status_code in (401, 403, 422)


def test_patch_records_under_authed_client_only(tmp_path, monkeypatch):
    """IDOR guard: override is recorded under the JWT-resolved client_id, never
    a body/query value — so client A can never write under client B's id."""
    from app.api import customer_dashboard as cd
    from app.api.customer_auth import require_customer
    from app.platform import lead_overrides as lo

    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    # ownership gate has its own suite (test_lead_override_ownership.py);
    # stub it owned=True so this test keeps proving the JWT-client_id contract
    monkeypatch.setattr(cd, "_client_owns_lead", lambda c, l: (True, False))
    app.dependency_overrides[require_customer] = lambda: "client_AUTH"
    try:
        r = client.patch("/api/customer/leads/lead9", json={"status": "Won"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        ovr = lo.read_overrides()
        assert ovr["lead9"]["client_id"] == "client_AUTH"
    finally:
        app.dependency_overrides.pop(require_customer, None)
