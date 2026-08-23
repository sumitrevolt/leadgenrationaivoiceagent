"""Loop-social-1 (2026-07-11): customer-facing per-platform social ACCOUNT connect
CRUD + admin social-delivery cockpit.

Closes audit gaps G1 (no OAuth callback → wizard captures handles, not tokens),
G2 (customer can't self-serve mark platform "connected"), G3 (no per-platform
status in wizard), and G4 (no admin triage for social publish queue).

Contract:
- GET  /api/customer/social/accounts       → list vault accounts (token NEVER
  leaked; only presence + masked account_ref + updated_at + meta.source).
- POST /api/customer/social/accounts/connect → Fernet-encrypt + store a per-client
  per-platform token (interim provider-mediated fallback until FB/IG/LI/GBP OAuth
  app-review completes). IDOR-safe: client_id from JWT, never body.
- DELETE /api/customer/social/accounts/{platform}?account_ref=… → soft-delete via
  vault.delete (append-only latest-wins).
- GET  /api/growth/social/jobs             → admin cockpit; filters + rollup
  counts, read-only over `social_engine.store.list_jobs()`.
- POST /api/growth/social/jobs/{id}/retry  → admin idempotent re-queue.

Never auto-posts. SOCIAL_ENGINE master flag still gates whether ANY dispatch
actually happens.
"""

from __future__ import annotations

import os
import tempfile

import pytest


# =========================================================================== #
# Isolated vault + store fixture — mirrors tests/test_social_engine.py pattern #
# =========================================================================== #
@pytest.fixture()
def iso(monkeypatch):
    """Point vault + job store at a fresh tmp dir; force plaintext (no
    SOCIAL_TOKEN_KEY) so the encrypt roundtrip is deterministic without secrets.
    Also stubs `store._mirror` so Postgres is not touched (hermetic)."""
    from app.social_engine import store as _store
    from app.social_engine import vault as _vault

    td = tempfile.mkdtemp()
    monkeypatch.setattr(_vault, "_PATH", os.path.join(td, "tokens.jsonl"))
    monkeypatch.setattr(_store, "_PATH", os.path.join(td, "jobs.jsonl"))
    monkeypatch.setattr(_store, "_mirror", lambda job: None)
    monkeypatch.delenv("SOCIAL_TOKEN_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET", raising=False)
    return {"dir": td, "vault": _vault, "store": _store}


# =========================================================================== #
# Customer routes — dependency override forces require_customer to return a    #
# known client_id (mirror tests/test_customer_change_password.py pattern).     #
# =========================================================================== #
@pytest.fixture()
def as_customer(monkeypatch):
    """Force the customer routes to see client_id='c_social_test'."""
    from app.api.customer_auth import require_customer
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "c_social_test"
    yield "c_social_test"
    app.dependency_overrides.pop(require_customer, None)


@pytest.fixture()
def as_admin(monkeypatch):
    """Bypass admin auth by overriding `require_admin` on the app."""
    from app.api.auth_deps import require_admin
    from app.main import app

    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    yield
    app.dependency_overrides.pop(require_admin, None)


# --------------------------------------------------------------------------- #
# Customer: GET /social/accounts                                              #
# --------------------------------------------------------------------------- #
def test_accounts_list_empty_returns_all_platforms_not_connected(client, iso, as_customer):
    r = client.get("/api/customer/social/accounts")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    plats = {p["platform"]: p for p in body["platforms"]}
    # 7 platforms exposed by the connect surface.
    assert set(plats.keys()) == {
        "facebook",
        "instagram",
        "gbp",
        "linkedin",
        "x",
        "youtube",
        "postiz",
    }
    # Nothing stored → every direct-API platform is provider_review_pending;
    # postiz alone is not_connected (no review path).
    for p in ("facebook", "instagram", "gbp", "linkedin", "x", "youtube"):
        assert plats[p]["connected"] is False
        assert plats[p]["state"] == "provider_review_pending"
        assert plats[p]["requires_review"] is True
    assert plats["postiz"]["state"] == "not_connected"


def test_accounts_list_after_connect_shows_connected_state(client, iso, as_customer):
    # Seed vault via the connect route (exercises the write path too).
    r = client.post(
        "/api/customer/social/accounts/connect",
        json={
            "platform": "facebook",
            "token": "EAA_test_page_token",
            "account_ref": "1234567890",
            "label": "Test Page",
            "source": "manual_paste",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    r2 = client.get("/api/customer/social/accounts")
    body = r2.json()
    plats = {p["platform"]: p for p in body["platforms"]}
    assert plats["facebook"]["connected"] is True
    assert plats["facebook"]["state"] == "connected"
    assert plats["facebook"]["account_count"] == 1

    # Token MUST NOT leak in the account payload — only presence sentinel.
    row = body["accounts"]["facebook"][0]
    assert "token" not in row
    assert "tok" not in row
    assert row["token_stored"] == "✓ stored"
    assert row["account_ref_masked"].startswith("…")
    assert "1234567890" not in row["account_ref_masked"]


# --------------------------------------------------------------------------- #
# Customer: POST /social/accounts/connect                                     #
# --------------------------------------------------------------------------- #
def _extract_error_code(body: dict) -> str | None:
    """The app has a global exception middleware that wraps HTTPException.detail
    into `{"error": {"code": "HTTP_400", "message": <detail>, "request_id": ...}}`.
    Support both the wrapped shape and the raw FastAPI `{"detail": ...}` shape
    (so tests remain robust if the middleware is disabled during isolated runs)."""
    if not isinstance(body, dict):
        return None
    wrapped = body.get("error")
    if isinstance(wrapped, dict):
        msg = wrapped.get("message")
        if isinstance(msg, dict):
            code = msg.get("error")
            if isinstance(code, str):
                return code
        if isinstance(msg, str):
            return msg
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("error")
    return None


def test_connect_rejects_unknown_platform(client, iso, as_customer):
    r = client.post(
        "/api/customer/social/accounts/connect",
        json={
            "platform": "myspace",
            "token": "abcdefghij",
            "account_ref": "x",
        },
    )
    assert r.status_code == 400
    assert _extract_error_code(r.json()) == "invalid_platform"


def test_connect_rejects_short_token(client, iso, as_customer):
    r = client.post(
        "/api/customer/social/accounts/connect",
        json={
            "platform": "x",
            "token": "abc",  # < 8
        },
    )
    assert r.status_code == 400
    assert _extract_error_code(r.json()) == "invalid_token"


@pytest.mark.parametrize("plat", ["facebook", "instagram", "gbp", "linkedin"])
def test_connect_requires_account_ref_for_direct_api_platforms(client, iso, as_customer, plat):
    r = client.post(
        "/api/customer/social/accounts/connect",
        json={
            "platform": plat,
            "token": "token_at_least_eight",
            # No account_ref
        },
    )
    assert r.status_code == 400
    assert _extract_error_code(r.json()) == "account_ref_required"


def test_connect_stores_token_encrypted_and_retrievable_via_vault(client, iso, as_customer):
    r = client.post(
        "/api/customer/social/accounts/connect",
        json={
            "platform": "instagram",
            "token": "IG_LIVE_TEST_TOKEN_XYZ",
            "account_ref": "17841400000000000",
            "label": "Test IG Business",
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True

    # Vault MUST have the token retrievable for the (real) publish path.
    rec = iso["vault"].get("c_social_test", "instagram")
    assert rec is not None
    assert rec["token"] == "IG_LIVE_TEST_TOKEN_XYZ"
    assert rec["account_ref"] == "17841400000000000"
    assert rec["meta"].get("source") == "manual_paste"


def test_connect_is_idor_safe_uses_jwt_client_id_not_body(client, iso, as_customer):
    """Even if a caller injects `client_id` in the body, the vault key MUST come
    from the JWT (`require_customer` returns 'c_social_test')."""
    r = client.post(
        "/api/customer/social/accounts/connect",
        json={
            "platform": "x",
            "token": "X_BEARER_TOKEN_12345",
            "client_id": "c_ATTACKER",  # extra field — must be ignored
        },
    )
    assert r.status_code == 200

    # Vault has it under the JWT-authoritative client_id, NOT the body one.
    assert iso["vault"].get("c_social_test", "x") is not None
    assert iso["vault"].get("c_ATTACKER", "x") is None


# --------------------------------------------------------------------------- #
# Customer: DELETE /social/accounts/{platform}                                #
# --------------------------------------------------------------------------- #
def test_disconnect_soft_deletes_via_vault(client, iso, as_customer):
    # Seed
    client.post(
        "/api/customer/social/accounts/connect",
        json={
            "platform": "linkedin",
            "token": "LI_TOKEN_XXXX",
            "account_ref": "urn:li:organization:123",
        },
    )
    assert iso["vault"].get("c_social_test", "linkedin") is not None

    r = client.delete("/api/customer/social/accounts/linkedin?account_ref=urn:li:organization:123")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("state") == "disconnected"
    assert iso["vault"].get("c_social_test", "linkedin") is None


def test_disconnect_rejects_unknown_platform(client, iso, as_customer):
    r = client.delete("/api/customer/social/accounts/myspace")
    assert r.status_code == 400


# =========================================================================== #
# Admin cockpit — /api/growth/social/jobs                                     #
# =========================================================================== #
def _seed_job(store, **overrides) -> str:
    """Enqueue a raw social-post job for cockpit tests."""
    base = {
        "client_id": "c_social_test",
        "platform": "facebook",
        "caption": "hello",
        "media_type": "text",
    }
    base.update(overrides)
    return store.enqueue(base)


def test_admin_social_jobs_lists_with_rollup_counts(client, iso, as_admin):
    j1 = _seed_job(iso["store"], platform="facebook")
    j2 = _seed_job(iso["store"], platform="instagram")
    iso["store"].mark(j2, "published", post_id="fb_pub_1")
    _seed_job(iso["store"], platform="x")

    r = client.get("/api/growth/social/jobs?limit=100")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    # Rollup includes queued + published.
    counts = body["counts"]
    assert counts["queued"] >= 2
    assert counts["published"] >= 1
    assert body["count"] >= 3


def test_admin_social_jobs_filters_by_platform_and_status(client, iso, as_admin):
    _seed_job(iso["store"], platform="facebook", client_id="c_A")
    _seed_job(iso["store"], platform="instagram", client_id="c_A")
    _seed_job(iso["store"], platform="facebook", client_id="c_B")

    r = client.get("/api/growth/social/jobs?platform=facebook")
    body = r.json()
    assert all(j["platform"] == "facebook" for j in body["jobs"])
    assert len(body["jobs"]) >= 2

    r2 = client.get("/api/growth/social/jobs?client_id=c_A&platform=facebook")
    body2 = r2.json()
    for j in body2["jobs"]:
        assert j["platform"] == "facebook"
        assert j["client_id"] == "c_A"


def test_admin_retry_requeues_dead_job_and_is_idempotent(client, iso, as_admin):
    jid = _seed_job(iso["store"], platform="facebook")
    # Push to dead state (like the drain loop would after max_attempts).
    iso["store"].mark(jid, "dead", attempts=iso["store"].max_attempts(), last_error="Provider 401")
    assert iso["store"].get(jid)["status"] == "dead"

    r = client.post(f"/api/growth/social/jobs/{jid}/retry")
    body = r.json()
    assert r.status_code == 200
    assert body.get("ok") is True
    assert body.get("previous") == "dead"
    assert body.get("status") == "queued"
    # Idempotent: re-hit on an already-queued job returns no_change:True.
    r2 = client.post(f"/api/growth/social/jobs/{jid}/retry")
    body2 = r2.json()
    assert body2.get("ok") is True
    assert body2.get("no_change") is True
    # last_error was cleared by the retry mark.
    assert iso["store"].get(jid).get("last_error", "") == ""


def test_admin_retry_returns_not_found_gracefully(client, iso, as_admin):
    r = client.post("/api/growth/social/jobs/does_not_exist/retry")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "not_found"
