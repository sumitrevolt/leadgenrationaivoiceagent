"""Offline tests for the self-hosted WhatsApp stack (WAHA Core) provider.

NO live HTTP — httpx is faked. Asserts the integration contract:
  - inert without WAHA_BASE_URL (never raises, returns error dict),
  - provider selection flips to "waha" only when selected + configured,
  - cloud_creds_present() stays truthful (not lied to by the self-host path),
  - happy-path text send normalises chatId + returns a message id,
  - the WAHA webhook dedupes on message id and isolates from the Meta parser,
  - all ban-safety guards (suppression) still wrap the self-host sender.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from app.integrations import whatsapp_selfhost as wahost
from app.marketing import whatsapp_campaign as wac


# --------------------------------------------------------------------------- #
# Fake httpx (no network)
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, json_data, status=200, content=b"{}", headers=None):
        self._json = json_data
        self.status_code = status
        self.content = content
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **k):
        return _FakeResp({"id": "wamid.SELFHOST"})

    async def get(self, url, **k):
        return _FakeResp({"status": "WORKING"}, content=b'{"status":"WORKING"}')


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in ("WAHA_BASE_URL", "WAHA_API_KEY", "WAHA_SESSION", "WHATSAPP_PROVIDER",
              "WHATSAPP_AUTO_SEND", "WHATSAPP_BUSINESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"):
        monkeypatch.delenv(k, raising=False)
    # settings may carry values from a real .env — neutralise for deterministic tests
    from app.config import settings

    monkeypatch.setattr(settings, "waha_base_url", "", raising=False)
    monkeypatch.setattr(settings, "whatsapp_provider", "cloud", raising=False)
    monkeypatch.setattr(settings, "whatsapp_business_token", "", raising=False)
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "", raising=False)
    yield


# --------------------------------------------------------------------------- #
# Inert without config
# --------------------------------------------------------------------------- #
def test_inert_without_base_url():
    assert wahost.is_configured() is False
    assert wahost.is_active_provider() is False
    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("9876543210", "hi"))
    assert res.get("error") == "selfhost_not_configured"


def test_session_helpers_inert():
    assert asyncio.run(wahost.session_status())["status"] == "not_configured"
    assert asyncio.run(wahost.start_session())["ok"] is False
    data, _ctype = asyncio.run(wahost.qr_image())
    assert data is None


# --------------------------------------------------------------------------- #
# Provider selection + truthfulness
# --------------------------------------------------------------------------- #
def test_provider_defaults_to_cloud():
    assert wac.provider() == "cloud"
    assert wac.selfhost_present() is False


def test_provider_flips_to_waha(monkeypatch):
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "waha")
    assert wahost.is_active_provider() is True
    assert wac.provider() == "waha"
    assert wac.selfhost_present() is True
    # creds_present True via self-host, but cloud_creds_present stays honest (False)
    assert wac.creds_present() is True
    assert wac.cloud_creds_present() is False


def test_configured_but_not_selected_stays_cloud(monkeypatch):
    # URL set but provider still "cloud" -> self-host NOT active (no silent takeover)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    assert wahost.is_configured() is True
    assert wahost.is_active_provider() is False
    assert wac.provider() == "cloud"


# --------------------------------------------------------------------------- #
# Happy-path send (faked httpx) + chatId normalisation
# --------------------------------------------------------------------------- #
def test_send_text_happy_path(monkeypatch):
    monkeypatch.setattr(wahost.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("9876543210", "hello"))
    assert (res.get("messages") or [{}])[0].get("id") == "wamid.SELFHOST"


def test_chat_id_adds_india_cc():
    assert wahost._chat_id("9876543210") == "919876543210@c.us"
    assert wahost._chat_id("+91 98765 43210") == "919876543210@c.us"
    assert wahost._chat_id("918261030181") == "918261030181@c.us"


def test_template_renders_placeholders():
    assert wahost._render("Namaste {{1}}, offer {{2}}", ["Ramesh", "20%"]) == "Namaste Ramesh, offer 20%"


# --------------------------------------------------------------------------- #
# Campaign send routes through self-host when selected (guards still apply)
# --------------------------------------------------------------------------- #
def test_campaign_send_uses_selfhost(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # isolate suppression/cap stores (relative data/ paths)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(wahost.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "waha")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    res = asyncio.run(wac.send_one("9876543210", "hi"))
    assert res["sent"] is True
    assert res["mode"] == "selfhost"


def test_suppressed_number_skipped_on_selfhost(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    from app.marketing import wa_campaign_runner as runner

    monkeypatch.setattr(runner, "_SUPPRESSION_FILE", os.path.join("data", "supp.jsonl"))
    runner.suppress("9876543210", "opt_out")
    monkeypatch.setattr(wahost.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "waha")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    res = asyncio.run(wac.send_one("9876543210", "hi"))
    assert res["sent"] is False
    assert res["mode"] == "suppressed"


# --------------------------------------------------------------------------- #
# Dual-engine EVERYWHERE: notification helpers + the shared factory
# --------------------------------------------------------------------------- #
def test_selfhost_inherits_notification_helpers(monkeypatch):
    # Mixin gives the self-host client the same lead-alert/report surface as Cloud API.
    monkeypatch.setattr(wahost.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    sh = wahost.SelfHostWhatsApp()
    assert hasattr(sh, "send_lead_alert") and hasattr(sh, "send_daily_report")
    res = asyncio.run(sh.send_lead_alert("919999999999", {"company_name": "Acme"}))
    assert (res.get("messages") or [{}])[0].get("id") == "wamid.SELFHOST"


def test_factory_returns_selfhost_when_selected(monkeypatch):
    from app.integrations.whatsapp import WhatsAppIntegration, get_whatsapp_sender

    # default -> Cloud API client
    assert isinstance(get_whatsapp_sender(), WhatsAppIntegration)
    # selected + configured -> self-host client (with the same notification surface)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "waha")
    sender = get_whatsapp_sender()
    assert isinstance(sender, wahost.SelfHostWhatsApp)
    assert hasattr(sender, "send_lead_alert")


# --------------------------------------------------------------------------- #
# Webhook dedupe (WAHA/Evolution redeliver)
# --------------------------------------------------------------------------- #
def test_webhook_dedupe(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from app.api import whatsapp as wa_api

    monkeypatch.setattr(wa_api, "_SEEN_FILE", os.path.join("data", "seen.json"))
    assert wa_api._seen_message("msg-1") is False  # first time
    assert wa_api._seen_message("msg-1") is True  # redelivery
    assert wa_api._seen_message("") is False  # empty id never "seen"
