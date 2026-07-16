"""Contract: GET /api/platform/office/agent-os-status (ADR-109 admin surface)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_agent_os_status_requires_admin():
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/platform/office/agent-os-status")
    assert r.status_code in (401, 403)


def test_agent_os_status_shape_for_admin(monkeypatch):
    from app.api import auth_deps
    from app.main import app

    async def _admin():
        return {"sub": "admin-test", "role": "admin"}

    app.dependency_overrides[auth_deps.require_admin] = _admin
    monkeypatch.delenv("OMNIROUTE_ENABLED", raising=False)
    monkeypatch.delenv("OMNIROUTE_AGENTS", raising=False)
    try:
        client = TestClient(app)
        r = client.get("/api/platform/office/agent-os-status")
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert body.get("staff_count") == 31
        assert isinstance(body.get("agents"), list)
        assert len(body["agents"]) == 31
        omni = body.get("omniroute") or {}
        assert omni.get("enabled_flag") is False
        assert omni.get("agents_hook_armed") is False
        assert "api_key_present" in omni
        assert "leadgen.agent_ops" in (omni.get("task_routes") or [])
        # No secret leakage
        dumped = str(body)
        assert "sk-" not in dumped.lower()
        assert "Bearer" not in dumped
        swara = next(a for a in body["agents"] if a["key"] == "swara")
        assert swara["omniroute_eligible"] is False
        zara = next(a for a in body["agents"] if a["key"] == "zara")
        assert zara["omniroute_eligible"] is True
        assert zara["requires_human_approval_before_publish"] is True
    finally:
        app.dependency_overrides.pop(auth_deps.require_admin, None)
