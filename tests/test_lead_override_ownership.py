"""Cross-tenant lead-override eviction guard (2026-07 audit fix).

PATCH /api/customer/leads/{lead_id} previously recorded an override for ANY
lead_id under the authed client, so client B could PATCH client A's lead_id and
silently EVICT A's own override (read_overrides collapses to one record per
lead_id, latest-write-wins). The fix verifies ownership before recording:
  - owned lead   -> override recorded (200)
  - foreign lead -> 404 (generic, no existence leak) + NO record appended
  - infra error  -> 503 (fail-CLOSED: unverified write refused)
"""

import contextlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import customer_dashboard as cd
from app.api.customer_auth import require_customer
from app.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Unit tests for the ownership resolver (real logic)                           #
# --------------------------------------------------------------------------- #
def _fake_session_returning(row):
    @contextlib.contextmanager
    def _cm():
        class _Q:
            def filter(self, *a, **k):
                return self

            def first(self):
                return row

        class _DB:
            def query(self, *a, **k):
                return _Q()

        yield _DB()

    return _cm


def test_owns_lead_via_inquiry(monkeypatch):
    monkeypatch.setattr(cd, "_client_record", lambda cid: {})
    monkeypatch.setattr(cd, "_inquiries_for_client", lambda cid, rec: [{"id": "L1"}, {"id": "L2"}])
    owned, infra = cd._client_owns_lead("clientA", "L2")
    assert owned is True
    assert infra is False


def test_foreign_lead_clean_not_owned(monkeypatch):
    """Inquiry miss + clean DB miss -> (False, False) => endpoint 404."""
    monkeypatch.setattr(cd, "_client_record", lambda cid: {})
    monkeypatch.setattr(cd, "_inquiries_for_client", lambda cid, rec: [])
    monkeypatch.setattr("app.models.base.get_db_session", _fake_session_returning(None))
    owned, infra = cd._client_owns_lead("clientB", "L2")
    assert owned is False
    assert infra is False


def test_owns_lead_via_db(monkeypatch):
    monkeypatch.setattr(cd, "_client_record", lambda cid: {})
    monkeypatch.setattr(cd, "_inquiries_for_client", lambda cid, rec: [])
    monkeypatch.setattr(
        "app.models.base.get_db_session", _fake_session_returning(SimpleNamespace(id="L9"))
    )
    owned, infra = cd._client_owns_lead("clientA", "L9")
    assert owned is True
    assert infra is False


def test_infra_error_flags_unknown(monkeypatch):
    """Both backends error -> (False, True) => endpoint fails-CLOSED (503)."""

    def _boom_inq(cid, rec):
        raise RuntimeError("inquiry store down")

    def _boom_db():
        raise RuntimeError("db down")

    monkeypatch.setattr(cd, "_client_record", lambda cid: {})
    monkeypatch.setattr(cd, "_inquiries_for_client", _boom_inq)
    monkeypatch.setattr("app.models.base.get_db_session", _boom_db)
    owned, infra = cd._client_owns_lead("clientA", "L2")
    assert owned is False
    assert infra is True


def test_empty_lead_id_not_owned(monkeypatch):
    owned, infra = cd._client_owns_lead("clientA", "")
    assert owned is False
    assert infra is False


# --------------------------------------------------------------------------- #
# Endpoint tests (eviction blocked)                                            #
# --------------------------------------------------------------------------- #
def test_owned_lead_records_override(tmp_path, monkeypatch):
    from app.platform import lead_overrides as lo

    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    monkeypatch.setattr(cd, "_client_owns_lead", lambda cid, lid: (True, False))
    app.dependency_overrides[require_customer] = lambda: "clientA"
    try:
        r = client.patch("/api/customer/leads/leadX", json={"status": "Won"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert lo.read_overrides()["leadX"]["client_id"] == "clientA"
    finally:
        app.dependency_overrides.pop(require_customer, None)


def test_foreign_lead_404_and_no_eviction(tmp_path, monkeypatch):
    """Core fix: client B cannot evict client A's override by PATCHing A's lead."""
    from app.platform import lead_overrides as lo

    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    # Ownership: A owns leadX, B does not.
    monkeypatch.setattr(cd, "_client_owns_lead", lambda cid, lid: (cid == "clientA", False))

    # A records an override on its own lead.
    app.dependency_overrides[require_customer] = lambda: "clientA"
    try:
        r = client.patch("/api/customer/leads/leadX", json={"status": "Won"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(require_customer, None)

    # B tries to overwrite (evict) A's override -> 404, nothing recorded for B.
    app.dependency_overrides[require_customer] = lambda: "clientB"
    try:
        r = client.patch("/api/customer/leads/leadX", json={"status": "Lost"})
        assert r.status_code == 404
        # generic message, no existence leak (global handler wraps detail).
        assert "not found" in r.text.lower()
        assert "own" not in r.text.lower()  # never reveals ownership semantics
    finally:
        app.dependency_overrides.pop(require_customer, None)

    # A's override survived (not evicted).
    ovr = lo.read_overrides()
    assert ovr["leadX"]["client_id"] == "clientA"
    assert ovr["leadX"]["status"] == "Won"


def test_infra_error_refuses_write_503(tmp_path, monkeypatch):
    from app.platform import lead_overrides as lo

    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    monkeypatch.setattr(cd, "_client_owns_lead", lambda cid, lid: (False, True))
    app.dependency_overrides[require_customer] = lambda: "clientA"
    try:
        r = client.patch("/api/customer/leads/leadX", json={"status": "Won"})
        assert r.status_code == 503
        assert lo.read_overrides() == {}  # fail-CLOSED: nothing written
    finally:
        app.dependency_overrides.pop(require_customer, None)


def test_bad_status_still_422(tmp_path, monkeypatch):
    """Invalid status is rejected before any ownership check (422 unchanged)."""
    from app.platform import lead_overrides as lo

    monkeypatch.setattr(lo, "_OVR_FILE", str(tmp_path / "ovr.jsonl"))
    app.dependency_overrides[require_customer] = lambda: "clientA"
    try:
        r = client.patch("/api/customer/leads/leadX", json={"status": "Nonsense"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(require_customer, None)
