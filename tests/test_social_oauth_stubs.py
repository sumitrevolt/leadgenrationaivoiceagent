"""Loop-social-13 (2026-07-11): OAuth callback route stubs.

Contract:
- GET /state → per-platform readiness map. Nothing approved by default.
- GET /{platform}/start → not_available (external-blocker) until env flag flips.
- GET /{platform}/callback → 403 until env flag flips; 400 on missing state/code.
- Env-flag flip changes readiness WITHOUT any code redeploy (activation-day
  swap-in path).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _override_customer_auth(monkeypatch):
    from app.api.customer_auth import require_customer
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "c_oauth_test"
    for var in ("META_OAUTH_APPROVED", "GBP_OAUTH_APPROVED", "LINKEDIN_OAUTH_APPROVED",
                "X_OAUTH_APPROVED", "GOOGLE_OAUTH_APPROVED"):
        monkeypatch.delenv(var, raising=False)
    yield
    app.dependency_overrides.pop(require_customer, None)


def test_state_endpoint_all_platforms_default_pending(client):
    r = client.get("/api/social/oauth/state")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    plats = {p["platform"]: p for p in body["platforms"]}
    for p in ("facebook", "instagram", "gbp", "linkedin", "x", "youtube"):
        assert plats[p]["oauth_ready"] is False
        assert plats[p]["fallback"] == "manual_paste"
        assert plats[p]["scopes_required"]


def test_state_stays_not_ready_when_env_approved_but_authorize_unwired(client, monkeypatch):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/state")
    body = r.json()
    plats = {p["platform"]: p for p in body["platforms"]}
    assert plats["facebook"]["env_approved"] is True
    assert plats["facebook"]["oauth_ready"] is False
    assert plats["facebook"]["fallback"] == "manual_paste"
    assert plats["facebook"]["external_blocker"] == "oauth_authorize_url_not_wired"


def test_start_returns_not_available_by_default(client):
    r = client.get("/api/social/oauth/facebook/start")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_available"
    assert body["reason"] == "provider_review_pending"
    assert body["fallback"] == "manual_paste"
    assert body["fallback_endpoint"] == "/api/customer/social/accounts/connect"


def test_start_rejects_unknown_platform(client):
    r = client.get("/api/social/oauth/myspace/start")
    assert r.status_code == 400


def test_callback_403_when_not_approved(client):
    r = client.get("/api/social/oauth/facebook/callback?code=abc&state=xyz")
    assert r.status_code == 403


def test_callback_400_on_missing_state_when_approved(client, monkeypatch):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/facebook/callback?code=abc")
    assert r.status_code == 400


def test_oauth_approval_flags_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS

    for f in (
        "META_OAUTH_APPROVED",
        "GBP_OAUTH_APPROVED",
        "LINKEDIN_OAUTH_APPROVED",
        "X_OAUTH_APPROVED",
        "GOOGLE_OAUTH_APPROVED",
    ):
        assert f in AUTOMATION_FLAGS


def test_start_honest_when_approved_but_authorize_not_wired(client, monkeypatch):
    """Env flag ON ≠ OAuth ready — empty authorize_url must never be ok:True."""
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/facebook/start")
    body = r.json()
    assert r.status_code == 200
    assert body.get("ok") is False
    assert body["status"] == "activation_pending"
    assert body["reason"] == "oauth_authorize_url_not_wired"
    assert body["fallback"] == "manual_paste"
    assert body["platform"] == "facebook"
    assert not body.get("authorize_url")
