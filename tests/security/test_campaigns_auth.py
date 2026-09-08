"""SEC-001: confirm /api/campaigns/* endpoints reject unauthenticated requests.

Workflow audit 2026-06-26 found `app/api/campaigns.py` mounted at /api/campaigns
with ZERO auth on all 9 endpoints — unauthenticated attacker could list /
create / start / pause / resume campaigns. Fix added Depends(require_admin) to
every route; these tests lock the fix so a regression CAN'T silently re-open
the hole."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests._api_helpers import iter_mounted_routes


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_auth_overrides() -> None:
    """Exercise campaign authorization without conftest's authenticated user."""
    from app.api.auth_deps import (
        get_current_user,
        require_admin,
        require_agent,
        require_manager,
        require_super_admin,
    )

    for dependency in (
        get_current_user,
        require_admin,
        require_agent,
        require_manager,
        require_super_admin,
    ):
        app.dependency_overrides.pop(dependency, None)


# All campaign endpoints — full surface coverage so future endpoint adds get caught.
CAMPAIGN_ROUTES_GET: list[str] = [
    "/api/campaigns/",
    "/api/campaigns/some-id",
    "/api/campaigns/some-id/stats",
    "/api/campaigns/niches/available",
    "/api/campaigns/cities/available",
]
CAMPAIGN_ROUTES_POST: list[str] = [
    "/api/campaigns/",
    "/api/campaigns/some-id/start",
    "/api/campaigns/some-id/pause",
    "/api/campaigns/some-id/resume",
]


@pytest.mark.parametrize("path", CAMPAIGN_ROUTES_GET)
def test_campaign_get_rejects_unauthenticated(client: TestClient, path: str) -> None:
    """Every GET endpoint must return 401/403 without an admin token."""
    r = client.get(path)
    assert r.status_code in (401, 403), (
        f"SEC-001 REGRESSION: {path} returned {r.status_code} without auth "
        f"(must be 401/403). Body: {r.text[:200]}"
    )


@pytest.mark.parametrize("path", CAMPAIGN_ROUTES_POST)
def test_campaign_post_rejects_unauthenticated(client: TestClient, path: str) -> None:
    """Every POST endpoint must return 401/403 without an admin token."""
    body = {} if path == "/api/campaigns/" else None
    r = client.post(path, json=body) if body is not None else client.post(path)
    assert r.status_code in (401, 403), (
        f"SEC-001 REGRESSION: {path} returned {r.status_code} without auth "
        f"(must be 401/403). Body: {r.text[:200]}"
    )


def test_campaign_route_count_locked(client: TestClient) -> None:
    """Catch a future endpoint added without auth: count must stay at 9.
    If you add a new /api/campaigns/* route, gate it AND bump this number."""
    paths = [
        r.path
        for r in iter_mounted_routes(app)
        if getattr(r, "path", "").startswith("/api/campaigns")
    ]
    assert len(paths) == 9, (
        f"Campaign route count changed ({len(paths)} found). If you added a "
        f"new endpoint, gate it with Depends(require_admin) and update this "
        f"count. Routes: {sorted(paths)}"
    )
