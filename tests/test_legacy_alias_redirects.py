"""Regression guard for legacy top-level page aliases (ISSUE-09, 2026-08-02).

People type/bookmark `/admin`, `/voice`, `/dashboard`, `/app/dashboard` straight
from a browser and got a hard 404 (the canonical pages are /app/admin,
/voice-agent, /app/customer). Static GET-only 307s now point to the canonical
pages — mirrors the /app/customer/{view} hash-view aliases (test
test_customer_dashboard_product_routing.py). These paths are ALSO API router
prefixes (/api/admin/*, /api/voice/*), so the exact top-level path ownership
must stay exclusive to avoid first-route-wins shadowing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_LEGACY_ALIASES = {
    "/admin": "/app/admin",
    "/voice": "/voice-agent",
    "/dashboard": "/app/customer",
    "/app/dashboard": "/app/customer",
}


def test_legacy_aliases_307_redirect_to_canonical_pages():
    from app.main import app

    client = TestClient(app)
    for src, dst in _LEGACY_ALIASES.items():
        r = client.get(src, follow_redirects=False)
        assert r.status_code == 307, f"{src} -> {r.status_code} (expected 307)"
        assert r.headers["location"] == dst, f"{src} location={r.headers.get('location')}"


def test_aliases_are_get_only_not_write_bypass():
    from app.main import app

    client = TestClient(app)
    for src in _LEGACY_ALIASES:
        r = client.post(src, follow_redirects=False)
        assert r.status_code in (405, 307), f"POST {src} -> {r.status_code}"
        assert r.headers.get("location") is None, (
            f"POST {src} must NOT redirect (write surface is not aliased)"
        )


def test_aliases_do_not_shadow_the_real_api_routes():
    """First-route-wins safety: the alias targets live on /app/* and the API
    prefixes sit under /api/* — neither must be swallowed by these aliases."""
    from app.main import app

    client = TestClient(app)
    for path in ("/app/admin", "/voice-agent", "/app/customer", "/api/admin/auth/login"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (
            200,
            401,
            404,
        ), f"{path} -> {r.status_code} (alias must not shadow the real surface)"
