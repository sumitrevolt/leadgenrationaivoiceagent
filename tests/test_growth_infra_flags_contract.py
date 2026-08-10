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
        assert "effective_overrides" in body
        flags = body["flags"]
        assert flags["PLATFORM_DIAL_DAILY"]["kind"] == "boolean"
        assert flags["PLATFORM_DIAL_DAILY"]["switch_on"] is True
        assert flags["PLATFORM_DIAL_LIMIT"]["kind"] == "capacity_limit"
        assert flags["PLATFORM_DIAL_LIMIT"]["switch_on"] is None
        assert flags["LITELLM_MASTER_KEY"]["value"] == "***"
        assert flags["LITELLM_MASTER_KEY"]["secret"] is True
        assert "REPLY_AUTO_SEND" in flags
        assert "effective_on" in flags["REPLY_AUTO_SEND"]
        assert "effective_note" in flags["REPLY_AUTO_SEND"]
    finally:
        app.dependency_overrides.pop(require_admin, None)


def test_infra_flags_reply_auto_send_effective_on_when_env_off(monkeypatch):
    """Env REPLY_AUTO_SEND=0 can still be live via Redis runtime flag."""
    import app.platform.reply_agent as reply_agent
    from app.api.auth_deps import require_admin
    from app.main import app

    async def _admin():
        return {"role": "admin", "sub": "test"}

    async def _eff_true():
        return True

    app.dependency_overrides[require_admin] = _admin
    try:
        monkeypatch.setenv("REPLY_AUTO_SEND", "0")
        monkeypatch.delenv("REPLY_AUTO_SEND_HARD_OFF", raising=False)
        monkeypatch.setattr(reply_agent, "_reply_auto_send_enabled", _eff_true)
        client = TestClient(app)
        r = client.get("/api/growth/infra/flags")
        assert r.status_code == 200, r.text
        body = r.json()
        row = body["flags"]["REPLY_AUTO_SEND"]
        assert row["on"] is False
        assert row["effective_on"] is True
        assert "REPLY_AUTO_SEND" in body["effective_overrides"]
    finally:
        app.dependency_overrides.pop(require_admin, None)
