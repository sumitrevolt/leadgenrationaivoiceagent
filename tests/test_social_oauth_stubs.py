"""Social OAuth — Meta + LinkedIn + YouTube wired; X/GBP stubs; Telegram bot_ready.

Contract:
- GET /state → per-platform readiness + telegram bot_ready (non-OAuth).
- Meta/LI/YT oauth_ready only when APPROVED + client creds present.
- X/GBP stay manual_paste even if APPROVED (unwired).
- Telegram: oauth_ready=false, bot_ready when TELEGRAM_BOT_TOKEN+CHAT_ID.
- Callback exchange mocked (no live provider in CI).
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
        "FACEBOOK_APP_ID",
        "FACEBOOK_APP_SECRET",
        "LINKEDIN_CLIENT_ID",
        "LINKEDIN_CLIENT_SECRET",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
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
    assert "telegram" in plats
    assert plats["telegram"]["oauth_ready"] is False
    assert plats["telegram"]["bot_ready"] is False
    assert plats["telegram"]["fallback"] == "bot_token"


def test_telegram_bot_ready_helper_and_state(client, monkeypatch):
    from app.api import social_oauth as so

    assert so._telegram_bot_ready() is False
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001")
    assert so._telegram_bot_ready() is True

    r = client.get("/api/social/oauth/state")
    plats = {p["platform"]: p for p in r.json()["platforms"]}
    assert plats["telegram"]["bot_ready"] is True
    assert plats["telegram"]["oauth_ready"] is False
    assert plats["telegram"]["fallback"] == "bot_token"


def test_telegram_start_is_bot_not_oauth(client, monkeypatch):
    r = client.get("/api/social/oauth/telegram/start")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body["oauth_ready"] is False
    assert body["bot_ready"] is False

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001")
    r2 = client.get("/api/social/oauth/telegram/start")
    body2 = r2.json()
    assert body2.get("ok") is True
    assert body2["status"] == "bot_ready"
    assert body2["bot_ready"] is True
    assert body2["oauth_ready"] is False
    assert not body2.get("authorize_url")


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


def test_linkedin_stays_unwired_without_creds(client, monkeypatch):
    monkeypatch.setenv("LINKEDIN_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/linkedin/start")
    body = r.json()
    assert body.get("ok") is False
    assert body["status"] == "activation_pending"
    assert body["reason"] == "linkedin_client_credentials_missing"
    assert not body.get("authorize_url")


def test_linkedin_authorize_url_when_wired(client, monkeypatch):
    monkeypatch.setenv("LINKEDIN_OAUTH_APPROVED", "1")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "li-client-test")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "li-secret-test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://leadsgenai.in")
    r = client.get("/api/social/oauth/linkedin/start?return_to=/app/office")
    body = r.json()
    assert body.get("ok") is True
    assert body["status"] == "ready"
    import urllib.parse

    url = body.get("authorize_url") or ""
    assert "linkedin.com/oauth/v2/authorization" in url
    assert "client_id=li-client-test" in url
    decoded = urllib.parse.unquote(url)
    assert "leadsgenai.in/api/social/oauth/linkedin/callback" in decoded
    assert "w_member_social" in decoded or "w_organization_social" in decoded


def test_youtube_authorize_url_when_wired(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_APPROVED", "1")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "yt-client-test")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "yt-secret-test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://leadsgenai.in")
    r = client.get("/api/social/oauth/youtube/start")
    body = r.json()
    assert body.get("ok") is True
    url = body.get("authorize_url") or ""
    assert "accounts.google.com" in url
    assert "youtube.upload" in url
    import urllib.parse

    decoded = urllib.parse.unquote(url)
    assert "leadsgenai.in/api/social/oauth/youtube/callback" in decoded


def test_youtube_accepts_google_client_aliases(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_APPROVED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-alias-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-alias-secret")
    r = client.get("/api/social/oauth/youtube/start")
    body = r.json()
    assert body.get("ok") is True
    assert "client_id=google-alias-id" in (body.get("authorize_url") or "")


def test_x_stays_unwired_even_if_approved(client, monkeypatch):
    monkeypatch.setenv("X_OAUTH_APPROVED", "1")
    r = client.get("/api/social/oauth/x/start")
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


def test_linkedin_callback_mocked_stores_vault(client, monkeypatch, tmp_path):
    monkeypatch.setenv("LINKEDIN_OAUTH_APPROVED", "1")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "li-client-test")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "li-secret-test")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-for-oauth-state")

    from app.api import social_oauth as so
    from app.social_engine import vault

    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "social_tokens.jsonl"))
    state = so._sign_state(client_id="c_oauth_test", platform="linkedin", return_to="/app/office")

    def fake_li(code: str):
        assert code == "li-code"
        return {
            "ok": True,
            "token": "LI_TOKEN_FAKE",
            "account_ref": "urn:li:person:abc",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "meta": {"source": "linkedin_oauth"},
        }

    monkeypatch.setattr(so, "_exchange_linkedin_code", fake_li)
    r = client.get(f"/api/social/oauth/linkedin/callback?code=li-code&state={state}")
    assert r.status_code == 200
    assert r.json()["status"] == "connected"
    stored = vault.get("c_oauth_test", "linkedin", "urn:li:person:abc")
    assert stored and stored.get("token") == "LI_TOKEN_FAKE"


def test_youtube_callback_mocked_stores_vault(client, monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_OAUTH_APPROVED", "1")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "yt-client-test")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "yt-secret-test")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-for-oauth-state")

    from app.api import social_oauth as so
    from app.social_engine import vault

    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "social_tokens.jsonl"))
    state = so._sign_state(client_id="c_oauth_test", platform="youtube", return_to="/app/office")

    def fake_yt(code: str):
        return {
            "ok": True,
            "token": "YT_REFRESH_FAKE",
            "account_ref": "UC_test_channel",
            "expires_at": "",
            "meta": {"source": "youtube_oauth", "has_refresh": True},
        }

    monkeypatch.setattr(so, "_exchange_youtube_code", fake_yt)
    r = client.get(f"/api/social/oauth/youtube/callback?code=yt-code&state={state}")
    assert r.status_code == 200
    stored = vault.get("c_oauth_test", "youtube", "UC_test_channel")
    assert stored and stored.get("token") == "YT_REFRESH_FAKE"


def test_callback_rejects_tampered_state(client, monkeypatch):
    monkeypatch.setenv("META_OAUTH_APPROVED", "1")
    monkeypatch.setenv("META_APP_ID", "1278868110768460")
    monkeypatch.setenv("META_APP_SECRET", "test-secret-not-real")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-for-oauth-state")
    r = client.get("/api/social/oauth/facebook/callback?code=abc&state=notavalid.signature")
    assert r.status_code == 400


def test_telegram_not_in_default_providers():
    from app.social_engine.providers import default_providers

    assert "telegram" not in default_providers()
