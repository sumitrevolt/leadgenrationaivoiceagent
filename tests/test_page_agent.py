"""Tests for the Page-Agent admin copilot (app/api/page_agent.py).

Risk surface = flag gate (503 default) + key-safety (server-side inject, model
enforce) + boot.js serving. Conftest already overrides require_admin (mock
super-admin), test_control_center.py style — self-contained override bhi set.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.page_agent as pa


def _client() -> TestClient:
    from app.api import auth_deps
    from app.main import app

    app.dependency_overrides[auth_deps.require_admin] = lambda: type("U", (), {"email": "t@t"})()
    return TestClient(app)


def test_import_safe():
    assert pa.router is not None
    assert pa.router.prefix == "/page-agent"


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PAGE_AGENT", raising=False)
    assert pa._flag_on() is False
    monkeypatch.setenv("PAGE_AGENT", "1")
    assert pa._flag_on() is True
    monkeypatch.setenv("PAGE_AGENT", "false")
    assert pa._flag_on() is False


def test_flag_in_registry():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "PAGE_AGENT" in AUTOMATION_FLAGS


def test_config_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PAGE_AGENT", raising=False)
    r = _client().get("/api/page-agent/config")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_config_enabled_prefers_vendored_script(monkeypatch):
    """Vendor file repo me hai → self-hosted URL (ISP-block-proof), SRI unneeded."""
    monkeypatch.setenv("PAGE_AGENT", "1")
    monkeypatch.delenv("PAGE_AGENT_SCRIPT_URL", raising=False)
    assert pa._VENDOR_FILE.exists()  # committed vendored bundle
    body = _client().get("/api/page-agent/config").json()
    assert body["enabled"] is True
    assert body["script_url"] == "/api/page-agent/vendor.js?autoInit=false"
    assert body["integrity"] == ""  # same-origin = SRI zaroori nahi
    assert body["model"]


def test_config_cdn_fallback_when_vendor_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("PAGE_AGENT", "1")
    monkeypatch.delenv("PAGE_AGENT_SCRIPT_URL", raising=False)
    monkeypatch.setattr(pa, "_VENDOR_FILE", tmp_path / "nahi-hai.js")
    body = _client().get("/api/page-agent/config").json()
    assert body["script_url"].startswith("https://cdn.jsdelivr.net/npm/page-agent@")
    assert "autoInit=false" in body["script_url"]  # demo LLM auto-init kabhi nahi
    assert body["integrity"].startswith("sha256-")


def test_vendor_js_served_publicly():
    r = _client().get("/api/page-agent/vendor.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert len(r.content) > 100_000  # 208KB pinned bundle


def test_config_custom_script_url_skips_sri(monkeypatch):
    monkeypatch.setenv("PAGE_AGENT", "1")
    monkeypatch.setenv("PAGE_AGENT_SCRIPT_URL", "/static/vendor/page-agent.js")
    body = _client().get("/api/page-agent/config").json()
    assert body["script_url"] == "/static/vendor/page-agent.js"
    assert body["integrity"] == ""  # override pe pinned hash match nahi karega


def test_chat_503_when_flag_off(monkeypatch):
    monkeypatch.delenv("PAGE_AGENT", raising=False)
    r = _client().post("/api/page-agent/v1/chat/completions", json={"messages": []})
    assert r.status_code == 503


def test_chat_502_when_no_provider_keys(monkeypatch):
    monkeypatch.setenv("PAGE_AGENT", "1")
    monkeypatch.setattr(pa, "_key", lambda attr: "")
    r = _client().post(
        "/api/page-agent/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 502


def test_chat_400_on_invalid_json(monkeypatch):
    monkeypatch.setenv("PAGE_AGENT", "1")
    r = _client().post(
        "/api/page-agent/v1/chat/completions",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_chat_413_on_oversize_body(monkeypatch):
    monkeypatch.setenv("PAGE_AGENT", "1")
    big = b'{"messages": "' + b"x" * (pa._MAX_BODY_BYTES + 10) + b'"}'
    r = _client().post(
        "/api/page-agent/v1/chat/completions",
        content=big,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413


def test_model_enforced_server_side(monkeypatch):
    """Client jo bhi model bheje — env PAGE_AGENT_MODEL / provider default hi jaata."""
    monkeypatch.delenv("PAGE_AGENT_MODEL", raising=False)
    assert pa._model_for("mistral-small-latest") == "mistral-small-latest"
    monkeypatch.setenv("PAGE_AGENT_MODEL", "mistral-large-latest")
    assert pa._model_for("mistral-small-latest") == "mistral-large-latest"


def test_boot_js_served_publicly():
    r = _client().get("/api/page-agent/boot.js")
    assert r.status_code == 200
    assert "PageAgent" in r.text
    assert "javascript" in r.headers["content-type"]
    # key-safety: boot loader me koi provider key/secret pattern nahi
    assert "sk_" not in r.text and "API_KEY" not in r.text
