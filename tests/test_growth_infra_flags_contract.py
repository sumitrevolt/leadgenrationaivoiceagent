"""Admin /infra/flags — typed manifest fields stay backward compatible."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_infra_flags_includes_kind_governance_and_boolean_on(monkeypatch):
    from app.api.auth_deps import require_admin
    from app.main import app

    async def _admin():
        return {"role": "admin", "sub": "test"}

    app.dependency_overrides[require_admin] = _admin
    try:
        monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
        monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "100")
        monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test-not-real")
        client = TestClient(app)
        r = client.get("/api/growth/infra/flags")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "on_count" in body
        assert "boolean_on_count" in body
        assert "by_kind" in body
        assert "by_lifecycle" in body
        flags = body["flags"]
        assert flags["PLATFORM_DIAL_DAILY"]["kind"] == "boolean"
        assert flags["PLATFORM_DIAL_DAILY"]["switch_on"] is True
        assert flags["PLATFORM_DIAL_LIMIT"]["kind"] == "capacity_limit"
        assert flags["PLATFORM_DIAL_LIMIT"]["switch_on"] is None
        assert flags["LITELLM_MASTER_KEY"]["value"] == "***"
        assert flags["LITELLM_MASTER_KEY"]["secret"] is True
    finally:
        app.dependency_overrides.pop(require_admin, None)
