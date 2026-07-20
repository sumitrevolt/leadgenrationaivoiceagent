"""Tests for the 4 production-readiness tracks (2026-06-09):

  Track 1 — self-serve signup + unified billing webhook + usage provisioning
  Track 2 — WhatsApp inbound webhook -> reply_agent Hinglish drafts
  Track 3 — social auto-poster (Meta Graph API + mock fallback)
  Track 4 — Alembic: new-model registration, migration 005, graceful startup migrations

Every feature is fail-open/defensive; these assert BOTH the happy path AND that the safe
fallbacks (mock mode, bad-signature reject, never-raise) behave correctly.

NOTE: we use a *lifespan-free* TestClient (``TestClient(app)`` WITHOUT the ``with`` block)
so the app's startup events — team scheduler thread + per-test alembic — do NOT run for
every request (those background threads contend on the SQLite file and make the suite
flaky). The conftest dependency overrides (auth + async DB) are module-level, so they're
active regardless. Async helpers are driven via ``asyncio.run`` (no pytest-asyncio needed).
File stores are isolated with ``monkeypatch.chdir(tmp_path)``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os

import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def c(monkeypatch):
    """A TestClient that does NOT run lifespan (no team-scheduler thread per test)."""
    from app.cache import RateLimiter

    # ASYNC patch zaroori: callers `await limiter.is_allowed(ip)` karte hain — purana
    # SYNC lambda await pe TypeError deta → RateLimitMiddleware apne IN-MEMORY
    # fallback counter pe girta → CI full-suite burst me yahi 429s de raha tha.
    # (Class-level dispatch patch kaam nahi karta — BaseHTTPMiddleware dispatch_func
    # ko __init__ me bind karta hai.)
    async def _allow(self, ident):
        return True, 9999

    monkeypatch.setattr(RateLimiter, "is_allowed", _allow)

    # CI me RateLimiter INIT hi fail hota (redis absent) → middleware ka INLINE
    # in-memory fallback poore suite ka traffic count karta → yahan tak aate-aate
    # minute-window full → 429. Fallback inline hai (koi helper method nahi) aur
    # dispatch_func __init__-bound hai — isliye INSTANCE patch: stack force-build
    # (skip-path /health = kabhi 429 nahi) → chain walk → ceiling raise + counter clear.
    client = TestClient(app)
    client.get("/health")
    from app.middleware import RateLimitMiddleware

    node = app.middleware_stack
    while node is not None:
        if isinstance(node, RateLimitMiddleware):
            monkeypatch.setattr(node, "requests_per_minute", 10_000_000)
            node._fallback_counts.clear()
        node = getattr(node, "app", None)

    # TEESRI layer: public_signup INLINE per-IP throttle is `_rate_check`
    # (module-level `_RL` / `_RL_AUDIT`). Stale tests patched removed
    # `_rate_limited` — that AttributeError left signup unprotected from
    # cross-test 429 pollution. Canonical seam = async `_rate_check` no-op.
    from app.api import public_site as ps

    async def _no_rate(_ip: str, bucket: str = "inquiry") -> None:
        return None

    monkeypatch.setattr(ps, "_rate_check", _no_rate)
    if isinstance(getattr(ps, "_RL", None), dict):
        ps._RL.clear()
    if isinstance(getattr(ps, "_RL_AUDIT", None), dict):
        ps._RL_AUDIT.clear()
    return client


# =============================================================================
# Track 1 — self-serve signup
# =============================================================================


def test_signup_creates_client_and_returns_token(c, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = {
        "business_name": "Sharma Solar",
        "email": "owner@sharmasolar.in",
        "password": "secret123",  # pragma: allowlist secret — synthetic fixture
        "phone": "9876543210",
        "niche": "solar",
        "city": "Pune",
        "plan": "growth",
    }
    r = c.post("/api/customer/auth/signup", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"]
    assert data["client_id"]
    assert data["plan"] == "growth"
    assert data["business_name"] == "Sharma Solar"

    # Credential persisted -> the new account can log in with the same password.
    login = c.post(
        "/api/customer/auth/login",
        json={
            "email": "owner@sharmasolar.in",
            "password": "secret123",  # pragma: allowlist secret — synthetic fixture
        },
    )
    assert login.status_code == 200, login.text
    assert login.json()["client_id"] == data["client_id"]


def test_signup_duplicate_email_returns_409(c, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = {
        "business_name": "Dup Biz",
        "email": "dup@example.com",
        "password": "secret123",  # pragma: allowlist secret — synthetic fixture
    }
    assert c.post("/api/customer/auth/signup", json=body).status_code == 200
    again = c.post("/api/customer/auth/signup", json=body)
    assert again.status_code == 409


def test_signup_invalid_email_returns_422(c, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    r = c.post(
        "/api/customer/auth/signup",
        json={
            "business_name": "No Email",
            "email": "notanemail",
            "password": "secret123",  # pragma: allowlist secret — synthetic fixture
        },
    )
    assert r.status_code == 422


def test_signup_unknown_plan_defaults_to_starter(c, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    r = c.post(
        "/api/customer/auth/signup",
        json={
            "business_name": "Plan Test",
            "email": "plan@example.com",
            "password": "secret123",  # pragma: allowlist secret — synthetic fixture
            "plan": "enterprise-ultra",  # not a real plan
        },
    )
    assert r.status_code == 200
    assert r.json()["plan"] == "starter"


# =============================================================================
# Track 1 — usage provisioning is fail-open (guards the truncated/stale usage.py)
# =============================================================================


def test_usage_has_provisioning_helpers():
    from app.billing import usage

    assert callable(usage.activate_plan)
    assert callable(usage.reset_usage_period)
    assert usage.plan_minutes("advanced") == 500
    assert usage.plan_minutes("starter") == 0


def test_usage_provisioning_safe_for_unknown_client():
    from app.billing import usage

    assert usage.activate_plan("nonexistent-client", "growth") is False
    assert usage.reset_usage_period("nonexistent-client") is False


# =============================================================================
# Track 1 — unified billing webhook (/api/billing/webhook)
# =============================================================================


def test_billing_webhook_unrecognized_provider_400(c):
    r = c.post("/api/billing/webhook", json={"foo": "bar"})
    assert r.status_code == 400


def test_billing_webhook_razorpay_header_rejected_after_removal(c):
    """Razorpay gateway removed 2026-06-18 (manual UPI only). An X-Razorpay-Signature
    webhook is no longer a recognized provider, so the unified route rejects it with
    400 — guarding against razorpay being silently re-accepted/re-wired later."""
    r = c.post(
        "/api/billing/webhook",
        headers={"X-Razorpay-Signature": "deadbeef"},
        content=b'{"event":"subscription.paused"}',
    )
    assert r.status_code == 400


def test_billing_webhook_stripe_signature_rejected_after_removal(c, monkeypatch):
    """Stripe gateway removed 2026-07-10 (manual UPI only). A Stripe-Signature
    header must not be accepted as a live payment webhook — unified route is 400."""
    monkeypatch.setattr(settings, "stripe_webhook_secret", "", raising=False)
    r = c.post(
        "/api/billing/webhook",
        headers={"Stripe-Signature": "t=1,v1=abc"},
        content=b"{}",
    )
    assert r.status_code == 400
    from tests._api_helpers import api_error_message

    assert "upi" in api_error_message(r).lower() or "webhook" in api_error_message(r).lower()


# =============================================================================
# Track 2 — WhatsApp webhook -> reply_agent drafts
# =============================================================================


def _wa_text_payload(from_number: str, text: str) -> bytes:
    return json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": from_number,
                                        "id": "wamid.TEST",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()


def test_whatsapp_verify_handshake(c, monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "tok123")
    ok = c.get(
        "/api/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "tok123", "hub.challenge": "999"},
    )
    assert ok.status_code == 200
    assert ok.text == "999"

    bad = c.get(
        "/api/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "WRONG", "hub.challenge": "999"},
    )
    assert bad.status_code == 403


def test_whatsapp_inbound_creates_draft(c, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.integrations import whatsapp as wa_int
    from app.platform import reply_agent

    async def fake_classify(subject, body, history=""):
        return "interested"

    async def fake_draft(biz, subject, body, intent, history_msgs=None):
        return "Namaste! Free demo set karein?"

    monkeypatch.setattr(reply_agent, "_classify", fake_classify)
    monkeypatch.setattr(reply_agent, "_draft", fake_draft)
    monkeypatch.setattr(wa_int, "verify_meta_signature", lambda raw, sig: True)

    r = c.post(
        "/api/webhooks/whatsapp",
        headers={"Content-Type": "application/json"},
        content=_wa_text_payload("919876543210", "Mujhe interest hai, price batao"),
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["messages"] == 1
    assert res["drafted"] == 1

    drafts_file = os.path.join("data", "reply_drafts.jsonl")
    assert os.path.exists(drafts_file)
    rows = [json.loads(ln) for ln in open(drafts_file, encoding="utf-8") if ln.strip()]
    assert any(d.get("channel") == "whatsapp" and d.get("intent") == "interested" for d in rows)


def test_whatsapp_optout_suppresses_no_draft(c, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.integrations import whatsapp as wa_int

    monkeypatch.setattr(wa_int, "verify_meta_signature", lambda raw, sig: True)

    r = c.post(
        "/api/webhooks/whatsapp",
        headers={"Content-Type": "application/json"},
        content=_wa_text_payload("919999999999", "STOP"),
    )
    assert r.status_code == 200
    res = r.json()
    assert res["suppressed"] == 1
    assert res["drafted"] == 0


def test_whatsapp_reply_helper_writes_draft(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.platform import reply_agent

    async def fake_classify(subject, body, history=""):
        return "question"

    async def fake_draft(biz, subject, body, intent, history_msgs=None):
        return "Ji, batayein."

    monkeypatch.setattr(reply_agent, "_classify", fake_classify)
    monkeypatch.setattr(reply_agent, "_draft", fake_draft)

    rec = asyncio.run(reply_agent.whatsapp_reply("9111", "kitna charge hai?"))
    assert rec["channel"] == "whatsapp"
    assert rec["intent"] == "question"
    assert rec["draft"]
    assert asyncio.run(reply_agent.whatsapp_reply("9111", "   ")) == {}


# =============================================================================
# Track 3 — social auto-poster (Meta Graph + mock fallback)
# =============================================================================


def _ready_item(client_id="c1", channel="facebook"):
    return {
        "id": "itm1",
        "business_name": "Test Biz",
        "niche": "solar",
        "date": "2020-01-01",
        "occasion": "Sale",
        "channel": channel,
        "client_id": client_id,
        "status": "ready",
        "content": {"caption": "Big sale!", "hashtags": ["#sale", "#solar"], "image_idea": "panel"},
    }


def test_meta_publish_post_mock_when_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOCIAL_AUTOPOST", raising=False)
    monkeypatch.setattr(settings, "social_autopost", False, raising=False)
    monkeypatch.setattr(settings, "meta_page_access_token", "", raising=False)
    from app.integrations import meta_graph

    out = meta_graph.publish_post(_ready_item())
    assert out["status"] == "mock"
    assert "would_post" in out


def test_meta_connect_and_get_connection(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.integrations import meta_graph

    assert meta_graph.has_connection("c-new") is False
    meta_graph.connect("c-new", page_id="P1", page_access_token="TOK", instagram_account_id="IG1")
    conn = meta_graph.get_connection("c-new")
    assert conn and conn["page_access_token"] == "TOK"
    assert meta_graph.has_connection("c-new") is True


def test_meta_global_fallback_connection(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "meta_page_access_token", "GLOBALTOK", raising=False)
    monkeypatch.setattr(settings, "meta_facebook_page_id", "GP", raising=False)
    from app.integrations import meta_graph

    conn = meta_graph.get_connection("client-without-own-conn")
    assert conn and conn.get("_global") is True
    assert conn["page_access_token"] == "GLOBALTOK"


def test_run_social_autopost_mock_keeps_item_ready(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOCIAL_AUTOPOST", raising=False)
    monkeypatch.setattr(settings, "social_autopost", False, raising=False)
    monkeypatch.setattr(settings, "meta_page_access_token", "", raising=False)
    from app.marketing import content_schedule
    from app.tasks.reporting import run_social_autopost

    content_schedule._write_all([_ready_item()])
    res = asyncio.run(run_social_autopost())
    assert res["ready"] == 1
    assert res["mock"] == 1
    assert res["posted"] == 0
    assert content_schedule.list_scheduled(status="ready")[0]["status"] == "ready"


def test_run_social_autopost_real_marks_posted(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.integrations import meta_graph
    from app.marketing import content_schedule
    from app.tasks import reporting

    content_schedule._write_all([_ready_item()])
    monkeypatch.setattr(meta_graph, "publish_post", lambda item, image_url="": {"status": "posted"})

    res = asyncio.run(reporting.run_social_autopost())
    assert res["posted"] == 1
    assert content_schedule.list_scheduled(status="ready") == []
    assert content_schedule.list_scheduled(status="posted")[0]["id"] == "itm1"


def test_meta_instagram_requires_image():
    from app.integrations import meta_graph

    out = meta_graph.publish_instagram("IG", "TOK", "caption", "")
    assert out["ok"] is False
    assert out["error"] == "instagram_requires_image_url"


# =============================================================================
# Track 4 — Alembic
# =============================================================================


def test_billing_records_registered_in_metadata():
    import app.models  # noqa: F401
    from app.models.base import Base

    assert "billing_records" in Base.metadata.tables


def test_migration_005_revision_chain():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "alembic",
        "versions",
        "005_add_billing_records.py",
    )
    assert os.path.exists(path)
    spec = importlib.util.spec_from_file_location("mig005", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "005_add_billing_records"
    assert mod.down_revision == "004_add_data_credits"
    assert callable(mod.upgrade) and callable(mod.downgrade)


def test_startup_migrations_skip_flag(monkeypatch):
    monkeypatch.setenv("SKIP_DB_MIGRATIONS", "1")
    from app.models.migrations import run_startup_migrations

    assert run_startup_migrations().get("skipped") == "SKIP_DB_MIGRATIONS"


def test_startup_migrations_stamps_existing_schema(monkeypatch, tmp_path):
    """create_all-built DB (tables, no alembic_version) -> stamps head, never raises."""
    monkeypatch.delenv("SKIP_DB_MIGRATIONS", raising=False)
    db_path = tmp_path / "startup.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    monkeypatch.setenv("DATABASE_URL", url)

    from sqlalchemy import create_engine

    import app.models  # noqa: F401
    from app.models.base import Base

    eng = create_engine(url)
    Base.metadata.create_all(bind=eng)
    eng.dispose()

    from app.models.migrations import run_startup_migrations

    result = run_startup_migrations()
    assert "error" not in result, result
    assert result.get("action") in ("stamped_head", "upgraded", "upgraded_from_empty")
