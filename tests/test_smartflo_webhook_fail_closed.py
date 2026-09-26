"""Tests for P0 fail-closed webhook receiver in app.telephony.smartflo_webhooks.

P0 finding: previously accepted requests WITHOUT authentication when
SMARTFLO_WEBHOOK_SECRET env var was unset, regardless of environment.
This let any third party spoof CDR events, trigger fraudulent billing
metering, and poison lead status.

After fix:
  - production (default) + secret unset → 503 + critical log
  - production + secret set + missing header → 401
  - production + secret set + wrong header → 401
  - production + secret set + correct header → pass
  - non-production + secret unset + ALLOW_UNAUTH_WEBHOOK=true → pass
  - non-production + secret unset + ALLOW_UNAUTH_WEBHOOK unset → 503
  - production + ALLOW_UNAUTH_WEBHOOK=true (flag ignored) → still 503
"""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture
def webhook_module(monkeypatch):
    """Reload the webhook module fresh per-test to pick up env changes."""
    def _load(**env):
        for k in ("SMARTFLO_WEBHOOK_SECRET", "ENV", "ALLOW_UNAUTH_WEBHOOK"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import app.telephony.smartflo_webhooks as mod
        importlib.reload(mod)
        return mod
    yield _load


@pytest.fixture
def client_for(webhook_module):
    """Build a fresh FastAPI TestClient wrapping the smartflo_webhooks router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def _make(**env):
        mod = webhook_module(**env)
        app = FastAPI()
        app.include_router(mod.router)
        return TestClient(app)
    yield _make


def test_webhook_secret_unset_in_production_returns_503(client_for):
    client = client_for(ENV="production")
    resp = client.post("/tata-smartflo", json={"call_id": "x"})
    assert resp.status_code == 503
    assert resp.json() == {"error": "webhook_auth_not_configured"}


def test_webhook_secret_unset_in_staging_returns_503(client_for):
    """Staging is not 'dev' or 'test' — production-grade behavior applies."""
    client = client_for(ENV="staging")
    resp = client.post("/tata-smartflo", json={"call_id": "x"})
    assert resp.status_code == 503


def test_webhook_secret_unset_in_dev_with_flag_accepts(client_for):
    client = client_for(ENV="dev", ALLOW_UNAUTH_WEBHOOK="true")
    resp = client.post("/tata-smartflo", json={
        "$call_id": "test-001",
        "$call_status": "completed",
        "$duration": "30",
        "$customer_number": "+91xxxxxxxxxx",
    })
    assert resp.status_code == 200


def test_webhook_secret_unset_in_dev_without_flag_returns_503(client_for):
    client = client_for(ENV="dev")
    resp = client.post("/tata-smartflo", json={"call_id": "x"})
    assert resp.status_code == 503


def test_webhook_secret_set_missing_header_returns_401(client_for):
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    resp = client.post("/tata-smartflo", json={"call_id": "x"})
    assert resp.status_code == 401


def test_webhook_secret_set_wrong_header_returns_401(client_for):
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    resp = client.post(
        "/tata-smartflo",
        json={"call_id": "x"},
        headers={"X-Smartflo-Secret": "yyyyyyyyyyyyyyyyyyyyyyyy"},
    )
    assert resp.status_code == 401


def test_webhook_secret_set_correct_header_passes(client_for):
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    resp = client.post(
        "/tata-smartflo",
        json={
            "$call_id": "CA-prod-001",
            "$call_status": "completed",
            "$duration": "42",
            "$customer_number": "+91xxxxxxxxxx",
        },
        headers={"X-Smartflo-Secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
    )
    assert resp.status_code == 200


def test_webhook_secret_test_env_with_flag_accepts(client_for):
    client = client_for(ENV="test", ALLOW_UNAUTH_WEBHOOK="1")
    resp = client.post("/tata-smartflo", json={"call_id": "x"})
    assert resp.status_code == 200


def test_webhook_secret_production_never_bypassed_even_with_flag(client_for):
    """Even if ALLOW_UNAUTH_WEBHOOK=true is set in prod, auth is required."""
    client = client_for(ENV="production", ALLOW_UNAUTH_WEBHOOK="true")
    resp = client.post("/tata-smartflo", json={"call_id": "x"})
    # Still 503 because production is production; flag is ignored.
    assert resp.status_code == 503


# ----- Body-injected secret (per Tata Smartflo docs 2026-09-25) -------------
# Per official docs, the portal "Headers" section injects key/value into the
# REQUEST BODY, not into HTTP headers. So the receiver must look up the
# configured secret in the parsed JSON body.


def test_webhook_secret_in_body_passes(client_for):
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="matching-secret-32chars-min",
    )
    resp = client.post(
        "/tata-smartflo",
        json={
            "$call_id": "CA-body-001",
            "$call_status": "completed",
            "$duration": "30",
            "$customer_number": "+91xxxxxxxxxx",
            "X-Smartflo-Secret": "matching-secret-32chars-min",
        },
    )
    assert resp.status_code == 200


def test_webhook_secret_in_body_wrong_value_returns_401(client_for):
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="matching-secret-32chars-min",
    )
    resp = client.post(
        "/tata-smartflo",
        json={
            "$call_id": "CA-body-002",
            "$call_status": "completed",
            "X-Smartflo-Secret": "wrong-secret",
        },
    )
    assert resp.status_code == 401


def test_webhook_secret_in_body_normalized_dollar_prefix(client_for):
    """Body may carry ``$X-Smartflo-Secret`` (Tata docs use ``$`` sigil)."""
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="matching-secret-32chars-min",
    )
    resp = client.post(
        "/tata-smartflo",
        json={
            "$call_id": "CA-body-003",
            "X-Smartflo-Secret": "matching-secret-32chars-min",
        },
    )
    assert resp.status_code == 200


def test_webhook_secret_body_overrides_header(client_for):
    """If both body and header carry the secret, body wins (Tata-doc mechanism)."""
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="matching-secret-32chars-min",
    )
    resp = client.post(
        "/tata-smartflo",
        json={
            "$call_id": "CA-body-004",
            "X-Smartflo-Secret": "matching-secret-32chars-min",  # body has correct
        },
        headers={"X-Smartflo-Secret": "wrong-secret"},  # header has wrong
    )
    assert resp.status_code == 200


def test_webhook_secret_header_only_when_body_missing(client_for):
    """HTTP header is fallback when body has no secret field."""
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="matching-secret-32chars-min",
    )
    resp = client.post(
        "/tata-smartflo",
        json={"$call_id": "CA-body-005"},
        headers={"X-Smartflo-Secret": "matching-secret-32chars-min"},
    )
    assert resp.status_code == 200


def test_webhook_secret_custom_body_key(client_for):
    """Operator can rename the body key via SMARTFLO_WEBHOOK_SECRET_BODY_KEY."""
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="matching-secret-32chars-min",
        SMARTFLO_WEBHOOK_SECRET_BODY_KEY="MySecret",
    )
    resp = client.post(
        "/tata-smartflo",
        json={
            "$call_id": "CA-body-006",
            "MySecret": "matching-secret-32chars-min",
        },
    )
    assert resp.status_code == 200


def test_webhook_secret_custom_body_key_wrong_returns_401(client_for):
    client = client_for(
        ENV="production",
        SMARTFLO_WEBHOOK_SECRET="matching-secret-32chars-min",
        SMARTFLO_WEBHOOK_SECRET_BODY_KEY="MySecret",
    )
    resp = client.post(
        "/tata-smartflo",
        json={"$call_id": "x", "MySecret": "wrong-secret"},
    )
    assert resp.status_code == 401
