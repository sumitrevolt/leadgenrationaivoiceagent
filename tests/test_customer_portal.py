"""P2 Customer login portal tests — hashing, credential store, JWT role gate, routes."""

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
    from fastapi import HTTPException

    from app.api.admin import create_access_token, decode_token

    tok = create_access_token("client42", "a@b.com", "customer")
    p = decode_token(tok)
    assert p["role"] == "customer" and p["sub"] == "client42"

    class _Cust:
        credentials = tok

    assert CA.require_customer(_Cust()) == "client42"

    class _Admin:
        credentials = create_access_token("u1", "x@y.com", "admin")

    try:
        CA.require_customer(_Admin())
        raise AssertionError("admin token must be rejected")
    except HTTPException as e:
        assert e.status_code == 403


def test_routes_mounted():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/customer/auth/login" in paths
    assert "/api/customer/auth/set-password" in paths
    assert "/api/customer/auth/portal/dashboard" in paths
    assert "/app/login" in paths
