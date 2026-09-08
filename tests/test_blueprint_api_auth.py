"""Auth / fail-closed contract for the Blueprint API (PR #125 hardening).

Internal architecture endpoints must be admin-only; the public contract must
be sanitized. Uses TestClient (imports the app) so it runs in CI's
`prod_check + pytest` job. Kept in its own module so the fast static graph
contract tests stay import-light.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures()


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_full_graph_requires_auth_fail_closed():
    """conftest overrides require_admin→mock-admin for tests; pop it to prove the
    REAL gate is fail-closed (autouse restore_dependency_overrides puts it back)."""
    from app.api.auth_deps import get_current_user, require_admin
    from app.main import app

    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(get_current_user, None)
    c = _client()
    for path in (
        "/api/blueprint/graph",
        "/api/blueprint/validate",
        "/api/blueprint/trace?src=app_fastapi",
    ):
        r = c.get(path)  # no Authorization header
        assert r.status_code in (401, 403), f"{path} not fail-closed: {r.status_code}"


def test_admin_endpoints_pass_with_mock_admin():
    """With conftest's mock-admin override, the full graph is reachable (no
    Explorer/admin regression)."""
    c = _client()
    r = c.get("/api/blueprint/graph")
    assert r.status_code == 200
    body = r.json()
    assert body.get("visibility") == "admin"
    assert body["workforce"]["count"] == 31


def test_public_contract_open_and_sanitized():
    c = _client()
    r = c.get("/api/blueprint/public")
    assert r.status_code == 200
    body = r.json()
    assert body.get("visibility") == "public"
    assert body["nodes"], "public graph empty"
    for n in body["nodes"]:
        assert set(n.keys()) == {"id", "title", "layer", "domain", "state", "disabled"}
    blob = r.text
    for leak_key in ('"files"', '"flags"', '"runtime"', '"tech_refs"', '"desc"'):
        assert leak_key not in blob, f"public leaks field {leak_key}"
    for infra in ("app/", ".py", "127.0.0.1", "8080"):
        assert infra not in blob, f"public leaks infra {infra}"


def test_meta_public_and_minimal():
    c = _client()
    r = c.get("/api/blueprint/meta")
    assert r.status_code == 200
    body = r.json()
    assert "schema_version" in body and "counts" in body
    # counts only — no node/edge detail
    assert "nodes" not in body


def test_admin_endpoints_are_registered():
    """The admin endpoints exist (FastAPI 0.139 keeps included routers lazy, so
    use iter_effective_routes, not app.routes)."""
    from app.main import app
    from app.utils.route_inspection import iter_effective_routes

    paths = {getattr(r, "path", "") for r in iter_effective_routes(app.routes)}
    for p in (
        "/api/blueprint/graph",
        "/api/blueprint/validate",
        "/api/blueprint/trace",
        "/api/blueprint/public",
        "/api/blueprint/meta",
    ):
        assert p in paths, f"{p} not registered ({len(paths)} routes seen)"
