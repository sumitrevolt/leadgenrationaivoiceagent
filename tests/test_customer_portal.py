"""P2 Customer login portal tests — hashing, credential store, JWT role gate, routes."""

from fastapi.testclient import TestClient

from app.api import customer_auth as CA


def test_hash_verify_roundtrip():
    h = CA._hash("secret123")
    assert CA._verify("secret123", h) is True
    assert CA._verify("wrong", h) is False
    assert CA._verify("x", "bad$format") is False


def test_credential_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(CA, "_STORE", str(tmp_path / "cust.jsonl"))
    CA._write_all([{"email": "a@b.com", "client_id": "c1", "password_hash": CA._hash("pw123456")}])
    rec = CA._find("A@B.com")  # case-insensitive
    assert rec and rec["client_id"] == "c1"
    assert CA._verify("pw123456", rec["password_hash"]) is True


def test_require_customer_enforces_role():
    import asyncio

    from fastapi import HTTPException

    from app.api.admin import create_access_token, decode_token

    tok = create_access_token("client42", "a@b.com", "customer")
    p = decode_token(tok)
    assert p["role"] == "customer" and p["sub"] == "client42"

    class _Cust:
        credentials = tok

    # require_customer is async (Redis blacklist check since ADR logout revoke)
    assert asyncio.run(CA.require_customer(_Cust())) == "client42"

    class _Admin:
        credentials = create_access_token("u1", "x@y.com", "admin")

    try:
        asyncio.run(CA.require_customer(_Admin()))
        raise AssertionError("admin token must be rejected")
    except HTTPException as e:
        assert e.status_code == 403


def test_routes_mounted():
    from app.main import app
    from app.utils.route_inspection import iter_effective_routes

    paths = {getattr(r, "path", "") for r in iter_effective_routes(app.routes)}
    assert "/api/customer/auth/login" in paths
    assert "/api/customer/auth/set-password" in paths
    assert "/api/customer/auth/portal/dashboard" in paths
    assert "/api/customer/dashboard" in paths
    assert "/api/customer/dashboard/send-to-crm" in paths
    assert "/api/customer/speed-to-lead" in paths
    assert "/api/customer/branded-feed" in paths
    assert "/api/customer/approvals/pending" in paths
    assert "/api/customer/routing" in paths
    assert "/app/login" in paths


def test_customer_dashboard_requires_auth():
    from app.main import app

    c = TestClient(app)
    r = c.get("/api/customer/dashboard")
    assert r.status_code in (401, 403)


def test_customer_dashboard_accepts_customer_token():
    from app.api.admin import create_access_token
    from app.main import app

    c = TestClient(app)
    tok = create_access_token("client42", "c42@example.com", "customer")
    r = c.get("/api/customer/dashboard", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert "kpis" in data and "leads" in data and "calls" in data
    assert "onboarding" in data
    ob = data["onboarding"]
    assert ob and isinstance(ob.get("steps"), list) and ob.get("total", 0) >= 4


def test_speed_to_lead_requires_auth():
    from app.main import app

    c = TestClient(app)
    r = c.get("/api/customer/speed-to-lead")
    assert r.status_code in (401, 403)


def test_speed_to_lead_accepts_customer_token():
    from app.api.admin import create_access_token
    from app.main import app

    c = TestClient(app)
    tok = create_access_token("client42", "c42@example.com", "customer")
    r = c.get("/api/customer/speed-to-lead", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "under_2min_pct" in data


def test_onboarding_checklist_builder():
    from app.api.customer_dashboard import _build_onboarding_checklist

    ob = _build_onboarding_checklist("test-client", None, leads_count=0, content_count=0)
    assert ob.total == 7
    assert ob.done == 0
    assert ob.complete is False
    assert len(ob.steps) == 7


def test_send_to_crm_requires_auth():
    from app.main import app

    c = TestClient(app)
    r = c.post("/api/customer/dashboard/send-to-crm")
    assert r.status_code in (401, 403)


def test_branded_feed_requires_auth():
    from app.main import app

    c = TestClient(app)
    r = c.get("/api/customer/branded-feed")
    assert r.status_code in (401, 403)


def test_customer_routing_requires_auth():
    from app.main import app

    c = TestClient(app)
    assert c.get("/api/customer/routing").status_code in (401, 403)
    assert c.post("/api/customer/routing", json={"members": []}).status_code in (401, 403)
