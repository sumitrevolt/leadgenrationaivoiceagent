"""Loop-social-13 (2026-07-11): OAuth callback routes — Meta wired, others stubs.

Contract:
- GET /state → per-platform readiness map. Nothing approved by default.
- Meta oauth_ready only when META_OAUTH_APPROVED + META_APP_ID + META_APP_SECRET.
- Other platforms stay manual_paste even if their APPROVED flag flips (unwired).
- Callback exchange mocked (no live Meta in CI).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _override_customer_auth(monkeypatch):
    from app.api.customer_auth import require_customer
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "c_oauth_test"
    for var in (
        "META_OAUTH_APPROVED",
        "GBP_OAUTH_APPROVED",
        "LINKEDIN_OAUTH_APPROVED",
        "X_OAUTH_APPROVED",
        "GOOGLE_OAUTH_APPROVED",
        "META_APP_ID",
        "META_APP_SECRET",
    ):
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


def test_state_stays_not_ready_when_env_approved_but_creds_missing(client, monkeypatch):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/state")
    body = r.json()
    plats = {p["platform"]: p for p in body["platforms"]}
    assert plats["facebook"]["env_approved"] is True
    assert plats["facebook"]["oauth_ready"] is False
    assert plats["facebook"]["fallback"] == "manual_paste"
    assert plats["facebook"]["external_blocker"] == "meta_app_credentials_missing"


def test_state_meta_ready_when_approved_and_creds(client, monkeypatch):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    monkeypatch.setenv("META_APP_ID", "1278868110768460")
    monkeypatch.setenv("META_APP_SECRET", "test-secret-not-real")
    r = client.get("/api/social/oauth/state")
    body = r.json()
    plats = {p["platform"]: p for p in body["platforms"]}
    assert plats["facebook"]["oauth_ready"] is True
    assert plats["instagram"]["oauth_ready"] is True
    assert plats["facebook"]["fallback"] == "oauth_v1"
    # Non-Meta stay honest even if we somehow set their flags later
    assert plats["gbp"]["oauth_ready"] is False
    assert plats["linkedin"]["oauth_ready"] is False
    assert plats["x"]["oauth_ready"] is False
    assert plats["youtube"]["oauth_ready"] is False


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
    monkeypatch.setenv("META_APP_ID", "1278868110768460")
    monkeypatch.setenv("META_APP_SECRET", "test-secret-not-real")
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


def test_start_honest_when_approved_but_creds_missing(client, monkeypatch):
    """Env flag ON ≠ OAuth ready — missing App ID/Secret must never be ok:True."""
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/facebook/start")
    body = r.json()
    assert r.status_code == 200
    assert body.get("ok") is False
    assert body["status"] == "activation_pending"
    assert body["reason"] == "meta_app_credentials_missing"
    assert body["fallback"] == "manual_paste"
    assert body["platform"] == "facebook"
    assert not body.get("authorize_url")


def test_start_returns_authorize_url_when_meta_wired(client, monkeypatch):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    monkeypatch.setenv("META_APP_ID", "1278868110768460")
    monkeypatch.setenv("META_APP_SECRET", "test-secret-not-real")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://leadsgenai.in")
    r = client.get("/api/social/oauth/facebook/start?return_to=/app/office")
    body = r.json()
    assert r.status_code == 200
    assert body.get("ok") is True
    assert body["status"] == "ready"
    import urllib.parse

    url = body.get("authorize_url") or ""
    assert "facebook.com" in url
    assert "client_id=1278868110768460" in url
    assert "redirect_uri=" in url
    decoded = urllib.parse.unquote(url)
    assert "leadsgenai.in/api/social/oauth/facebook/callback" in decoded
    assert "state=" in url
    assert "pages_manage_posts" in url


def test_linkedin_stays_unwired_even_if_approved(client, monkeypatch):
    monkeypatch.setenv("LINKEDIN_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/linkedin/start")
    body = r.json()
    assert body.get("ok") is False
    assert body["status"] == "activation_pending"
    assert body["reason"] == "oauth_authorize_url_not_wired"
    assert not body.get("authorize_url")


def test_callback_exchange_mocked_stores_vault(client, monkeypatch, tmp_path):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    monkeypatch.setenv("META_APP_ID", "1278868110768460")
    monkeypatch.setenv("META_APP_SECRET", "test-secret-not-real")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-for-oauth-state")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://leadsgenai.in")

    from app.api import social_oauth as so
    from app.social_engine import vault

    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "social_tokens.jsonl"))

    state = so._sign_state(
        client_id="c_oauth_test",
        platform="facebook",
        return_to="/app/office",
    )

    def fake_exchange(platform: str, code: str):
        assert platform == "facebook"
        assert code == "fake-code"
        return {
            "ok": True,
            "token": "PAGE_TOKEN_FAKE",
            "account_ref": "page_123",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "meta": {
                "page_id": "page_123",
                "page_name": "Test Page",
                "instagram_account_id": "",
                "token_kind": "page_access_token",
                "source": "meta_oauth",
            },
        }

    monkeypatch.setattr(so, "_exchange_meta_code", fake_exchange)

    r = client.get(f"/api/social/oauth/facebook/callback?code=fake-code&state={state}")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body["status"] == "connected"
    assert body["account_ref"] == "page_123"

    stored = vault.get("c_oauth_test", "facebook", "page_123")
    assert stored is not None
    assert stored.get("token") == "PAGE_TOKEN_FAKE"


def test_callback_rejects_tampered_state(client, monkeypatch):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    monkeypatch.setenv("META_APP_ID", "1278868110768460")
    monkeypatch.setenv("META_APP_SECRET", "test-secret-not-real")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-for-oauth-state")
    r = client.get("/api/social/oauth/facebook/callback?code=abc&state=notavalid.signature")
    assert r.status_code == 400
