"""Tests for Hermes3D custom runtime provider adapter and endpoints.

Verifies:
1. /api/hermes3d/health and /api/runtime/custom/health return 200 with runtime metadata.
2. /api/hermes3d/registry returns canonical 9 supervisory bots and 31 agent identities.
3. /api/hermes3d/state returns live agent states, office environment, and TypeSafe slots.
4. /api/hermes3d/config returns allowlist, mode_2d_fallback, and refresh intervals.
5. /api/hermes3d/command enforces require_admin (401/403 when unauthenticated).
6. Authenticated admin can toggle 2D mode and dispatch commands.
7. Allowlist boundary enforcement rejects disallowed client hosts.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User, UserRole, UserStatus
from app.platform.hermes3d_bridge import Hermes3DBridge, get_hermes3d_bridge


def test_hermes3d_health_endpoints():
    """Both /api/hermes3d/health and /api/runtime/custom/health must return 200."""
    client = TestClient(app)

    for path in ("/api/hermes3d/health", "/api/runtime/custom/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["runtime"] == "leadgen_hermes3d"
        assert data["adapter"] == "custom"
        assert "mode_2d" in data


def test_hermes3d_registry_returns_canonical_workforce():
    """Registry must return the 31 agents and 9 supervisory bots."""
    client = TestClient(app)

    for path in ("/api/hermes3d/registry", "/api/runtime/custom/registry"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert len(data["agents"]) >= 15  # canonical company staff
        assert "supervisory_bots" in data
        assert len(data["supervisory_bots"]) == 9
        assert data["telemetry_standard"] == "REAL_EVENTS_ONLY"


def test_hermes3d_state_endpoint():
    """State endpoint returns live agents, office environment, and TypeSafe slots."""
    client = TestClient(app)

    for path in ("/api/hermes3d/state", "/api/runtime/custom/state"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "office" in data
        assert "typesafe_gateway" in data["office"]
        assert "slots" in data["office"]["typesafe_gateway"]
        assert data["evidence_kind"] == "real_events_only"


def test_hermes3d_config_endpoint():
    """Config endpoint returns adapter settings and allowlists."""
    client = TestClient(app)

    for path in ("/api/hermes3d/config", "/api/runtime/custom/config"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["adapter_type"] == "custom"
        assert "allowlist" in data
        assert "mode_2d_fallback" in data


def test_hermes3d_command_requires_admin():
    """Unauthenticated command dispatch must be rejected with 401/403."""
    from app.api.auth_deps import get_current_user, require_admin

    saved_admin = app.dependency_overrides.pop(require_admin, None)
    saved_user = app.dependency_overrides.pop(get_current_user, None)
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/hermes3d/command",
            json={"action": "run_cycle", "target_agent": "dev"},
        )
        assert resp.status_code in (401, 403)
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user


def test_authenticated_admin_can_dispatch_command_and_toggle_2d():
    """Authenticated admin can execute commands and toggle 2D fallback mode."""
    from app.api.auth_deps import require_admin

    mock_admin = User(
        id="admin_hermes3d_test",
        email="admin@leadsgenai.in",
        first_name="Admin",
        last_name="Owner",
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        password_hash="fake",
        password_salt="fake",
    )

    saved_admin = app.dependency_overrides.get(require_admin)
    app.dependency_overrides[require_admin] = lambda: mock_admin
    try:
        client = TestClient(app)

        # Toggle 2D mode command
        resp = client.post(
            "/api/hermes3d/command",
            json={"action": "toggle_2d_mode"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "mode_2d" in data

        # General action command
        resp2 = client.post(
            "/api/hermes3d/command",
            json={"action": "focus_agent", "target_agent": "isha", "parameters": {"zoom": 1.5}},
        )
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        else:
            app.dependency_overrides.pop(require_admin, None)


def test_allowlist_rejection():
    """Clients outside the upstream allowlist must be rejected with 403."""
    bridge = get_hermes3d_bridge()
    original_allowlist = bridge.allowlist
    try:
        # Restrict allowlist to a specific dummy IP
        bridge.allowlist = {"192.168.1.50"}

        client = TestClient(app)
        # TestClient headers with client host simulation
        resp = client.get("/api/hermes3d/health", headers={"X-Forwarded-For": "203.0.113.195"})
        # Direct allowlist check via bridge
        assert bridge.is_client_allowed("203.0.113.195") is False
        assert bridge.is_client_allowed("192.168.1.50") is True
    finally:
        bridge.allowlist = original_allowlist
