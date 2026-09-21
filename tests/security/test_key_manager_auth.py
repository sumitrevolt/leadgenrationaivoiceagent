"""Key Manager P0 — REAL auth enforcement (tests/security harness).

The package conftest strips the harness mock-admin overrides, so these prove:
- every /api/admin/keys/* mutation is wired to require_super_admin
- every read is wired to require_admin
- anonymous callers are rejected 401 by the real auth chain
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.auth_deps import require_admin, require_super_admin
from app.main import app


def _route(path: str):
    for r in app.routes:
        if getattr(r, "path", "") == path:
            return r
    raise AssertionError(f"route not found on app: {path}")


def _deps(route) -> list:
    return [d.dependency for d in route.dependant.dependencies]


MUTATION_PATHS = (
    "/api/admin/keys/set",
    "/api/admin/keys/rotate",
    "/api/admin/keys/delete/{service}",
    "/api/admin/keys/deploy/{service}",
    "/api/admin/keys/verify/{service}",
    "/api/admin/keys/request-rotation/{service}",
)

READ_PATHS = (
    "/api/admin/keys/status",
    "/api/admin/keys/status/{service}",
    "/api/admin/keys/audit",
    "/api/admin/keys/audit/{service}",
)


def test_mutation_routes_wired_to_super_admin():
    for p in MUTATION_PATHS:
        assert require_super_admin in _deps(_route(p)), f"{p} missing require_super_admin"


def test_read_routes_wired_to_admin():
    for p in READ_PATHS:
        assert require_admin in _deps(_route(p)), f"{p} missing require_admin"


def test_anonymous_requests_rejected_real_auth():
    """No harness override in this package => the 401 comes from real auth."""
    client = TestClient(app)
    assert (
        client.post(
            "/api/admin/keys/set",
            json={"service": "typesafe_a", "key": "x" * 24},
        ).status_code
        == 401
    )
    assert client.get("/api/admin/keys/status").status_code == 401
    assert client.get("/api/admin/keys/audit").status_code == 401
    assert client.get("/api/admin/keys/status/typesafe_a").status_code == 401
