from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


def test_whatsapp_cloud_not_configured_records_failure(monkeypatch):
    from app.config import settings
    from app.integrations.whatsapp import WhatsAppIntegration
    from app.platform import integration_health

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "whatsapp_business_token", "", raising=False)
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "", raising=False)
    monkeypatch.setattr(
        integration_health,
        "record_failure",
        lambda name, note="": calls.append((name, note)),
        raising=False,
    )

    out = asyncio.run(WhatsAppIntegration().send_text_message("9876543210", "hi"))

    assert out["error"] == "whatsapp_not_configured"
    assert calls == [("whatsapp", "cloud_not_configured")]


def test_whatsapp_selfhost_success_records_success(monkeypatch):
    from app.integrations import whatsapp_selfhost as wahost
    from app.platform import integration_health

    calls: list[str] = []
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setattr(integration_health, "record_success", lambda name: calls.append(name), raising=False)

    class _Resp:
        status_code = 200
        content = b"{}"
        text = ""

        def json(self):
            return {"id": "wamid.TEST"}

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(wahost.httpx, "AsyncClient", _Client)

    out = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("9876543210", "hi"))

    assert (out.get("messages") or [{}])[0].get("id") == "wamid.TEST"
    assert calls == ["whatsapp"]


def test_stripe_customer_success_records_success(monkeypatch):
    from app.billing.payment_gateway import StripeGateway
    from app.platform import integration_health

    calls: list[str] = []
    monkeypatch.setattr(integration_health, "record_success", lambda name: calls.append(name), raising=False)

    class _Customer:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(id="cus_123", email=kwargs["email"])

    gw = StripeGateway()
    gw._client = SimpleNamespace(Customer=_Customer)

    out = asyncio.run(gw.create_customer("a@example.com", "A"))

    assert out["customer_id"] == "cus_123"
    assert calls == ["stripe"]


def test_stripe_customer_failure_records_failure(monkeypatch):
    from app.billing.payment_gateway import StripeGateway
    from app.platform import integration_health

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        integration_health,
        "record_failure",
        lambda name, note="": calls.append((name, note)),
        raising=False,
    )

    class _Customer:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("stripe down")

    gw = StripeGateway()
    gw._client = SimpleNamespace(Customer=_Customer)

    with pytest.raises(RuntimeError):
        asyncio.run(gw.create_customer("a@example.com", "A"))

    assert calls == [("stripe", "create_customer")]

