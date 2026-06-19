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
