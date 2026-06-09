"""Offline unit tests for the payment-gateway automation (Stripe + Razorpay).

NO live API calls and NO real DB: the gateways' verify_webhook is monkeypatched,
the AsyncSession is a tiny fake, and the route coroutines are driven directly with
asyncio (matching the repo's pytest-asyncio-free style). Covers:

  * config-gating helpers (503 when keys empty)
  * Razorpay webhook HMAC-SHA256 verification (bad sig -> 400, good sig -> handled)
  * Stripe webhook event handling -> Subscription activated + usage provisioned
  * usage.activate_plan / reset_usage_period are best-effort (never raise)
  * the new routes are mounted on the real app

Self-contained; skips the FastAPI-dependent parts gracefully if fastapi is absent.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import pytest

# These two import without fastapi/sqlalchemy heavy deps where possible; if the
# whole stack is missing the module-level import will skip the file.
billing = pytest.importorskip("app.api.billing")
from app.billing import usage as usage_mod  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #
class FakeRequest:
    """Minimal stand-in for starlette Request (body + headers)."""

    def __init__(self, body: bytes, headers: dict[str, str]):
        self._body = body
        self.headers = headers

    async def body(self) -> bytes:
        return self._body


class FakeResult:
    def __init__(self, obj=None):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeDB:
    """Async session stub: execute() returns a configurable row; commit/add no-op."""

    def __init__(self, row=None):
        self._row = row
        self.committed = 0
        self.added = []

    async def execute(self, *_a, **_k):
        return FakeResult(self._row)

    async def commit(self):
        self.committed += 1

    def add(self, obj):
        self.added.append(obj)


# --------------------------------------------------------------------------- #
# config-gating helpers                                                        #
# --------------------------------------------------------------------------- #
def test_gateway_config_helpers(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "", raising=False)
    monkeypatch.setattr(billing.settings, "stripe_webhook_secret", "", raising=False)
    monkeypatch.setattr(billing.settings, "razorpay_key_id", "", raising=False)
    monkeypatch.setattr(billing.settings, "razorpay_key_secret", "", raising=False)
    monkeypatch.setattr(billing.settings, "razorpay_webhook_secret", "", raising=False)
    assert billing._stripe_configured() is False
    assert billing._stripe_webhook_configured() is False
    assert billing._razorpay_configured() is False
    assert billing._razorpay_webhook_configured() is False

    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test_x", raising=False)
    monkeypatch.setattr(billing.settings, "razorpay_key_id", "rzp_id", raising=False)
    monkeypatch.setattr(billing.settings, "razorpay_key_secret", "rzp_secret", raising=False)
    assert billing._stripe_configured() is True
    assert billing._razorpay_configured() is True


def test_client_email_fallback_for_unknown_client():
    # No record + no auth row -> safe fallback (never the fake example.com).
    email = billing._client_email("definitely-not-a-real-client-id")
    assert "@" in email
    assert "example.com" not in email
    assert email == billing._FALLBACK_EMAIL


# --------------------------------------------------------------------------- #
# webhooks: 503 when not configured                                            #
# --------------------------------------------------------------------------- #
def test_stripe_webhook_503_when_unconfigured(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(billing, "_stripe_configured", lambda: False)
    monkeypatch.setattr(billing, "_stripe_webhook_configured", lambda: False)
    req = FakeRequest(b"{}", {"Stripe-Signature": "x"})
    with pytest.raises(HTTPException) as ei:
        _run(billing.stripe_webhook(req, db=FakeDB()))
    assert ei.value.status_code == 503


def test_razorpay_webhook_503_when_unconfigured(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(billing, "_razorpay_configured", lambda: False)
    monkeypatch.setattr(billing, "_razorpay_webhook_configured", lambda: False)
    req = FakeRequest(b"{}", {"X-Razorpay-Signature": "x"})
    with pytest.raises(HTTPException) as ei:
        _run(billing.razorpay_webhook(req, db=FakeDB()))
    assert ei.value.status_code == 503


# --------------------------------------------------------------------------- #
# Razorpay HMAC verification (no SDK needed — pure stdlib hmac)                 #
# --------------------------------------------------------------------------- #
def test_razorpay_webhook_bad_signature_400(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(billing, "_razorpay_configured", lambda: True)
    monkeypatch.setattr(billing, "_razorpay_webhook_configured", lambda: True)
    monkeypatch.setattr(billing.settings, "razorpay_webhook_secret", "whsec", raising=False)
    body = json.dumps({"event": "subscription.charged", "payload": {}}).encode()
    req = FakeRequest(body, {"X-Razorpay-Signature": "deadbeef"})  # wrong sig
    with pytest.raises(HTTPException) as ei:
        _run(billing.razorpay_webhook(req, db=FakeDB()))
    assert ei.value.status_code == 400


def test_razorpay_webhook_valid_signature_provisions(monkeypatch):
    monkeypatch.setattr(billing, "_razorpay_configured", lambda: True)
    monkeypatch.setattr(billing, "_razorpay_webhook_configured", lambda: True)
    secret = "whsec"
    monkeypatch.setattr(billing.settings, "razorpay_webhook_secret", secret, raising=False)

    captured = {}

    def fake_provision(client_id, plan_id, period_end, sub_id, reset=True):
        captured.update(
            client_id=client_id, plan_id=plan_id, sub_id=sub_id, reset=reset
        )

    async def fake_activate(db, **kw):
        captured["activated"] = kw
        return None  # no row -> exercises the None-safe provisioning path

    monkeypatch.setattr(billing, "_provision_usage", fake_provision)
    monkeypatch.setattr(billing, "_activate_subscription_row", fake_activate)

    event = {
        "event": "subscription.charged",
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_rzp_123",
                    "customer_id": "cust_9",
                    "current_start": 1_700_000_000,
                    "current_end": 1_702_592_000,
                    "notes": {"client_id": "acme-123", "plan_id": "advanced"},
                }
            }
        },
    }
    body = json.dumps(event).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    req = FakeRequest(body, {"X-Razorpay-Signature": sig})

    out = _run(billing.razorpay_webhook(req, db=FakeDB()))
    assert out["received"] is True
    assert out["event"] == "subscription.charged"
    assert captured["client_id"] == "acme-123"
    assert captured["plan_id"] == "advanced"
    assert captured["sub_id"] == "sub_rzp_123"
    assert captured["reset"] is True
    assert captured["activated"]["razorpay_subscription_id"] == "sub_rzp_123"


# --------------------------------------------------------------------------- #
# Stripe webhook: mocked verify_webhook -> activation + provisioning           #
# --------------------------------------------------------------------------- #
def test_stripe_webhook_checkout_completed_provisions(monkeypatch):
    monkeypatch.setattr(billing, "_stripe_configured", lambda: True)
    monkeypatch.setattr(billing, "_stripe_webhook_configured", lambda: True)

    fake_event = {
        "event_id": "evt_1",
        "event_type": "checkout.session.completed",
        "data": {
            "mode": "subscription",
            "subscription": "sub_stripe_1",
            "customer": "cus_1",
            "metadata": {"client_id": "acme-9", "plan_id": "advanced"},
        },
    }

    class FakeStripeGW:
        async def verify_webhook(self, payload, signature):
            return fake_event

    monkeypatch.setattr(
        "app.billing.payment_gateway.get_stripe_gateway", lambda: FakeStripeGW()
    )

    captured = {}

    def fake_provision(client_id, plan_id, period_end, sub_id, reset=True):
        captured.update(client_id=client_id, plan_id=plan_id, sub_id=sub_id)

    class FakeSub:
        client_id = "acme-9"
        plan_id = "advanced"
        current_period_end = None

    async def fake_activate(db, **kw):
        captured["activated"] = kw
        return FakeSub()

    monkeypatch.setattr(billing, "_provision_usage", fake_provision)
    monkeypatch.setattr(billing, "_activate_subscription_row", fake_activate)

    req = FakeRequest(b"{}", {"Stripe-Signature": "t=1,v1=abc"})
    out = _run(billing.stripe_webhook(req, db=FakeDB()))
    assert out["event"] == "checkout.session.completed"
    assert captured["client_id"] == "acme-9"
    assert captured["sub_id"] == "sub_stripe_1"
    assert captured["activated"]["stripe_subscription_id"] == "sub_stripe_1"


def test_stripe_webhook_invalid_signature_400(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(billing, "_stripe_configured", lambda: True)
    monkeypatch.setattr(billing, "_stripe_webhook_configured", lambda: True)

    class FakeStripeGW:
        async def verify_webhook(self, payload, signature):
            raise ValueError("bad sig")

    monkeypatch.setattr(
        "app.billing.payment_gateway.get_stripe_gateway", lambda: FakeStripeGW()
    )
    req = FakeRequest(b"{}", {"Stripe-Signature": "bad"})
    with pytest.raises(HTTPException) as ei:
        _run(billing.stripe_webhook(req, db=FakeDB()))
    assert ei.value.status_code == 400


# --------------------------------------------------------------------------- #
# usage provisioning is best-effort (never raises)                             #
# --------------------------------------------------------------------------- #
def test_usage_activate_and_reset_are_safe_without_data():
    # No client id -> False, no exception.
    assert usage_mod.activate_plan("", "advanced") is False
    assert usage_mod.activate_plan("x", "") is False
    assert usage_mod.reset_usage_period("") is False
    # Unknown client (no clients_store record, no DB row) -> False but no raise.
    assert usage_mod.activate_plan("no-such-client", "advanced") in (True, False)
    assert usage_mod.reset_usage_period("no-such-client") in (True, False)


def test_usage_period_start_safe_without_db():
    # Never raises; returns None when there's no subscription row / DB.
    assert usage_mod._usage_period_start("") is None
    assert usage_mod._usage_period_start("no-such-client") is None


def test_provision_usage_swallows_errors(monkeypatch):
    # If the underlying usage module blows up, _provision_usage must not raise.
    import app.billing.usage as u

    monkeypatch.setattr(u, "activate_plan", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    billing._provision_usage("c", "advanced", None, "sub_x")  # should not raise


# --------------------------------------------------------------------------- #
# routes mounted on the real app                                              #
# --------------------------------------------------------------------------- #
def test_new_billing_routes_mounted():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/billing/webhooks/stripe" in paths
    assert "/api/billing/webhooks/razorpay" in paths
    assert "/api/billing/portal" in paths
    assert "/api/billing/subscription/pause" in paths
    assert "/api/billing/subscription/resume" in paths
