"""Enterprise-grade CORS + trusted-host hardening regression tests.

Loop: enterprise-grade hardening (CORS lockdown + TrustedHostMiddleware).
Goal: prove the owner-admin surface is never wildcard+credentials, that the
main app's trusted-host enforcement is fail-safe by default, and that list
settings accept owner-friendly comma/space env values.

NOTE: app.main cannot be imported in this sandbox (missing `jose`), so the
main-app TrustedHost *wiring* is covered by source review + a behavioral test
of the exact starlette contract it relies on. owner_admin is imported for real.
"""

import os

import pytest

starlette_testclient = pytest.importorskip("starlette.testclient")

from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402
from starlette.applications import Starlette  # noqa: E402


# --------------------------------------------------------------------------- #
# Settings layer
# --------------------------------------------------------------------------- #
def test_settings_owner_admin_cors_default_not_wildcard():
    from app.config import Settings

    s = Settings()
    assert s.owner_admin_cors_origins, "default must be non-empty"
    assert "*" not in s.owner_admin_cors_origins, "never wildcard"
    assert "https://leadsgenai.in" in s.owner_admin_cors_origins


def test_settings_trusted_hosts_default_empty_failsafe():
    from app.config import Settings

    s = Settings()
    # Empty = disabled. main.py only adds TrustedHostMiddleware when non-empty,
    # so prod behavior is unchanged until the owner explicitly sets TRUSTED_HOSTS.
    assert s.trusted_hosts == []


def test_settings_csv_coercion_owner_admin_cors(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("OWNER_ADMIN_CORS_ORIGINS", "https://a.example https://b.example")
    s = Settings()
    assert s.owner_admin_cors_origins == ["https://a.example", "https://b.example"]


def test_settings_csv_coercion_trusted_hosts(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("TRUSTED_HOSTS", "leadsgenai.in, www.leadsgenai.in")
    s = Settings()
    assert s.trusted_hosts == ["leadsgenai.in", "www.leadsgenai.in"]


# --------------------------------------------------------------------------- #
# Owner-admin surface — real import + TestClient
# --------------------------------------------------------------------------- #
@pytest.fixture
def owner_client():
    os.environ.setdefault("APP_ENV", "development")
    from app.platform import owner_admin

    return starlette_testclient.TestClient(owner_admin.app)


def test_owner_admin_cors_rejects_disallowed_origin(owner_client):
    # A disallowed origin must NOT be echoed back (and never "*").
    resp = owner_client.options(
        "/",
        headers={
            "Origin": "https://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    allowed = resp.headers.get("access-control-allow-origin")
    assert allowed != "*", "wildcard CORS must never be returned"
    assert allowed != "https://evil.com", "disallowed origin must not be echoed"


def test_owner_admin_cors_allows_production_domain(owner_client):
    resp = owner_client.options(
        "/",
        headers={
            "Origin": "https://leadsgenai.in",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "https://leadsgenai.in"
    # Credentials are safe because origins are explicit (never "*").
    assert resp.headers.get("access-control-allow-credentials") == "true"


# --------------------------------------------------------------------------- #
# Trusted-host mechanism (the exact starlette contract main.py relies on)
# --------------------------------------------------------------------------- #
def test_trusted_host_blocks_bad_host_allows_good():
    app = Starlette()
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["leadsgenai.in", "www.leadsgenai.in", "localhost", "127.0.0.1", "testserver"],
    )

    from starlette.responses import PlainTextResponse

    async def _ok(request):
        return PlainTextResponse("ok")

    app.router.add_route("/", _ok)

    client = starlette_testclient.TestClient(app)
    # Good host → 200
    assert client.get("/", headers={"Host": "leadsgenai.in"}).status_code == 200
    # Bad host → 400 (host-header attack blocked)
    assert client.get("/", headers={"Host": "evil.attacker.com"}).status_code == 400
