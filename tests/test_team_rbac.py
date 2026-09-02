"""Tests — RBAC module grants (rbac.py) + require_admin module enforcement.
Hermetic: fake user objects, no DB/network.
"""

from __future__ import annotations

import asyncio
import json


class _FakeUser:
    def __init__(self, role="manager", preferences=None, is_admin=False):
        self.role = role
        self.preferences = json.dumps(preferences) if isinstance(preferences, dict) else preferences
        self._is_admin = is_admin

    def can_access_admin(self):
        return self._is_admin


def test_module_for_path_longest_prefix():
    from app.platform import rbac

    assert rbac.module_for_path("/api/marketing/generate-post") == "marketing"
    assert rbac.module_for_path("/api/growth/leads/hot") == "growth"
    assert rbac.module_for_path("/api/billing/plans") == "billing"
    # unmapped admin surface = None (fail-closed for members)
    assert rbac.module_for_path("/api/admin/users") is None
    assert rbac.module_for_path("/api/team-access/members") is None
    assert rbac.module_for_path("/health") is None


def test_grants_roundtrip_and_validation():
    from app.platform import rbac

    u = _FakeUser(preferences=None)
    assert rbac.get_user_modules(u) == []
    granted = rbac.set_user_modules(u, ["marketing", "nonsense", "billing"])
    assert granted == ["marketing", "billing"]
    assert rbac.get_user_modules(u) == ["marketing", "billing"]
    # must_change flag coexist in same JSON
    rbac.set_must_change_password(u, True)
    assert rbac.must_change_password(u) is True
    assert rbac.get_user_modules(u) == ["marketing", "billing"]
    rbac.set_must_change_password(u, False)
    assert rbac.must_change_password(u) is False


def test_member_can_access():
    from app.platform import rbac

    u = _FakeUser(preferences={"modules": ["marketing"]})
    assert rbac.member_can_access(u, "/api/marketing/hashtags") is True
    assert rbac.member_can_access(u, "/api/billing/plans") is False
    assert rbac.member_can_access(u, "/api/admin/users") is False  # unmapped = closed
    # corrupt preferences = fail-closed, no raise
    bad = _FakeUser(preferences="not-json{{")
    assert rbac.member_can_access(bad, "/api/marketing/x") is False


def test_require_admin_module_enforcement():
    """require_admin: admin pass; member sirf granted module path pe pass."""
    from starlette.requests import Request

    from app.api import auth_deps

    def _req(path):
        return Request(
            {"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""}
        )

    admin = _FakeUser(is_admin=True)
    member = _FakeUser(preferences={"modules": ["marketing"]})

    assert asyncio.run(auth_deps.require_admin(_req("/api/billing/x"), admin)) is admin
    assert asyncio.run(auth_deps.require_admin(_req("/api/marketing/x"), member)) is member
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        asyncio.run(auth_deps.require_admin(_req("/api/billing/x"), member))
    with pytest.raises(HTTPException):
        asyncio.run(auth_deps.require_admin(_req("/api/admin/users"), member))


def test_router_importable():
    from app.api import team_access

    paths = {r.path for r in team_access.router.routes}
    assert "/team-access/members" in paths and "/team-access/auth/change-password" in paths
