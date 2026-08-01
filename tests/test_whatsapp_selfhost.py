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
from app.marketing import wa_campaign_runner as _runner_mod
from app.marketing import whatsapp_campaign as wac

# Captured BEFORE the autouse fixture pins it — the one test that genuinely exercises
# suppression restores this real implementation.
_REAL_IS_SUPPRESSED = _runner_mod.is_suppressed


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
    for k in (
        "WAHA_BASE_URL",
        "WAHA_API_KEY",
        "WAHA_SESSION",
        "WHATSAPP_PROVIDER",
        "WHATSAPP_AUTO_SEND",
        "WHATSAPP_SEND_ALLOWLIST",
        "WHATSAPP_BUSINESS_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
    ):
        monkeypatch.delenv(k, raising=False)
    # The boundary gate consults the opt-out ledger + local suppression store, both of
    # which resolve REAL relative data/ paths. Pin them so these wire-format tests are
    # deterministic and never let live customer data decide a test outcome.
    from app.marketing import wa_campaign_runner as _wcr
    from app.telephony import consent_ledger as _cl

    monkeypatch.setattr(_cl, "is_suppressed", lambda _p: False, raising=False)
    monkeypatch.setattr(_wcr, "is_suppressed", lambda _p: False, raising=False)
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
    # 2026-07-31: sends are gated at the sender boundary by the §5 WHATSAPP_AUTO_SEND
    # gate. This test covers WIRE FORMAT, so arm the flag explicitly. The gate's own
    # behaviour lives in tests/test_whatsapp_auto_send_gate.py.
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    # Canary allowlist is a SECOND gate; these tests cover wire format, so graduate it.
    monkeypatch.setenv("WHATSAPP_SEND_ALLOWLIST", "*")
    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("9876543210", "hello"))
    assert (res.get("messages") or [{}])[0].get("id") == "wamid.SELFHOST"
    assert res.get("delivery_status") == "accepted"


class _RecipientMissingClient(_FakeClient):
    sends = 0

    async def get(self, url, **k):
        if "/contacts/check-exists" in url:
            return _FakeResp({"numberExists": False}, content=b'{"numberExists":false}')
        return await super().get(url, **k)

    async def post(self, url, **k):
        if "/api/sendText" in url:
            self.sends += 1
        return await super().post(url, **k)


def test_unregistered_recipient_is_blocked_before_send(monkeypatch):
    client = _RecipientMissingClient()
    monkeypatch.setattr(wahost.httpx, "AsyncClient", lambda *a, **k: client)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    # Canary allowlist is a SECOND gate; these tests cover wire format, so graduate it.
    monkeypatch.setenv("WHATSAPP_SEND_ALLOWLIST", "*")  # §5 boundary gate — see happy-path note
    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("9876543210", "hello"))
    assert res["error"] == "recipient_not_on_whatsapp"
    assert res["status"] == "blocked"
    assert client.sends == 0


def test_chat_id_adds_india_cc():
    assert wahost._chat_id("9876543210") == "919876543210@c.us"
    assert wahost._chat_id("+91 98765 43210") == "919876543210@c.us"
    assert wahost._chat_id("918261030181") == "918261030181@c.us"


def test_template_renders_placeholders():
    assert (
        wahost._render("Namaste {{1}}, offer {{2}}", ["Ramesh", "20%"])
        == "Namaste Ramesh, offer 20%"
    )


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
    # Canary allowlist is a SECOND gate; these tests cover wire format, so graduate it.
    monkeypatch.setenv("WHATSAPP_SEND_ALLOWLIST", "*")
    res = asyncio.run(wac.send_one("9876543210", "hi"))
    assert res["sent"] is True
    assert res["mode"] == "selfhost"


def test_suppressed_number_skipped_on_selfhost(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    from app.marketing import wa_campaign_runner as runner

    # Resolver function, not a constant — the constant is gone so that the path
    # can follow a cutover instead of being frozen at import time.
    monkeypatch.setattr(runner, "_suppression_path", lambda: os.path.join("data", "supp.jsonl"))
    # This is THE test that exercises suppression for real — undo the fixture's pin.
    monkeypatch.setattr(runner, "is_suppressed", _REAL_IS_SUPPRESSED)
    runner.suppress("9876543210", "opt_out")
    monkeypatch.setattr(wahost.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "waha")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    # Canary allowlist is a SECOND gate; these tests cover wire format, so graduate it.
    monkeypatch.setenv("WHATSAPP_SEND_ALLOWLIST", "*")
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
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    # Canary allowlist is a SECOND gate; these tests cover wire format, so graduate it.
    monkeypatch.setenv("WHATSAPP_SEND_ALLOWLIST", "*")  # §5 boundary gate — see happy-path note
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


# --------------------------------------------------------------------------- #
# start_session() idempotency + self-healing (2026-07-04 dashboard-441 bug)
#
# Before: start_session() always POSTed the deprecated singular
# /api/sessions/start. If the session was ALREADY running (linked directly
# via the WAHA API, or a second dashboard click), WAHA replies 422 "Session
# 'default' is already started" and the admin dashboard showed a scary
# "Start failed". Now it checks current status first and behaves per-state.
# --------------------------------------------------------------------------- #
class _RecordingClient:
    """Fake httpx.AsyncClient that records (method, path) calls and returns a
    configurable status for the initial GET (session_status) probe."""

    def __init__(self, status_for_get="STOPPED"):
        self.calls: list[tuple[str, str]] = []
        self._status_for_get = status_for_get

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        self.calls.append(("get", url))
        return _FakeResp(
            {"status": self._status_for_get},
            content=b'{"status":"' + self._status_for_get.encode() + b'"}',
        )

    async def post(self, url, **k):
        self.calls.append(("post", url))
        return _FakeResp({"ok": True}, status=201)

    async def delete(self, url, **k):
        self.calls.append(("delete", url))
        return _FakeResp({"ok": True}, status=200)


def _paths(calls):
    return [c[1].rsplit("/", 1)[-1] if "start" in c[1] or "logout" in c[1] else c[1] for c in calls]


def test_start_session_noop_when_already_scan_qr_code(monkeypatch):
    """Already SCAN_QR_CODE -> success no-op, must NOT call create/start again
    (that extra call is exactly what produced the 422 'already started')."""
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    client = _RecordingClient(status_for_get="SCAN_QR_CODE")
    monkeypatch.setattr(wahost.httpx, "AsyncClient", client)

    out = asyncio.run(wahost.start_session())
    assert out["ok"] is True
    assert out["status"] == "SCAN_QR_CODE"
    assert out["already_running"] is True
    # only the status-check GET happened — no POST at all
    assert all(m == "get" for m, _ in client.calls)


def test_start_session_noop_when_already_working(monkeypatch):
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    client = _RecordingClient(status_for_get="WORKING")
    monkeypatch.setattr(wahost.httpx, "AsyncClient", client)

    out = asyncio.run(wahost.start_session())
    assert out["ok"] is True
    assert out["already_running"] is True
    assert all(m == "get" for m, _ in client.calls)


def test_start_session_creates_when_not_created(monkeypatch):
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    client = _RecordingClient(status_for_get="NOT_CREATED")
    monkeypatch.setattr(wahost.httpx, "AsyncClient", client)

    out = asyncio.run(wahost.start_session())
    assert out["ok"] is True
    methods = [m for m, _ in client.calls]
    assert methods == ["get", "post", "post"]  # status check, create, start
    assert client.calls[1][1].endswith("/api/sessions")  # create (no session-name suffix)
    assert client.calls[2][1].endswith("/start")


def test_start_session_starts_directly_when_stopped(monkeypatch):
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    client = _RecordingClient(status_for_get="STOPPED")
    monkeypatch.setattr(wahost.httpx, "AsyncClient", client)

    out = asyncio.run(wahost.start_session())
    assert out["ok"] is True
    methods = [m for m, _ in client.calls]
    assert methods == ["get", "post"]  # status check, start (no create — already exists)
    assert client.calls[1][1].endswith("/start")


def test_start_session_logout_delete_recreate_when_failed(monkeypatch):
    """WAHA's own guidance: 'restart, if that doesn't help logout + start
    again' -- FAILED must self-heal via logout+delete+recreate, not just retry
    start (which is what got stuck looping 422s in production)."""
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    client = _RecordingClient(status_for_get="FAILED")
    monkeypatch.setattr(wahost.httpx, "AsyncClient", client)

    out = asyncio.run(wahost.start_session())
    assert out["ok"] is True
    methods = [m for m, _ in client.calls]
    assert methods == ["get", "post", "delete", "post", "post"]
    assert client.calls[1][1].endswith("/logout")
    assert client.calls[2][1].endswith("/default") or client.calls[2][1].endswith("default")
    assert client.calls[3][1].endswith("/api/sessions")  # recreate
    assert client.calls[4][1].endswith("/start")


def test_default_config_includes_webhook_token(monkeypatch):
    monkeypatch.setenv("WAHA_WEBHOOK_TOKEN", "tok123")
    cfg = wahost._default_config()
    assert cfg["webhooks"][0]["url"].endswith("token=tok123")
    assert cfg["webhooks"][0]["events"] == ["message"]


def test_recipient_not_on_whatsapp_is_not_an_integration_failure(monkeypatch):
    """A recipient with no WhatsApp account is a RECIPIENT outcome, not an
    integration fault — WAHA answered correctly.

    Regression: counting it as an integration failure let synthetic/test numbers
    drive whatsapp to fail_rate 0.973 and write a DAILY false
    "WhatsApp integration failing" into a real paying customer's delivery ledger
    while WhatsApp was working (live snapshot: fail=72 ok=2
    last_error=recipient_not_on_whatsapp).
    """
    recorded: list[str] = []
    monkeypatch.setattr(wahost, "_record_whatsapp_failure", lambda note="": recorded.append(note))
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_ENFORCE_BUSINESS_NUMBER", "0")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    # Canary allowlist is a SECOND gate; these tests cover wire format, so graduate it.
    monkeypatch.setenv("WHATSAPP_SEND_ALLOWLIST", "*")  # §5 boundary gate — see happy-path note

    async def _fake_check(_self, _to):
        return {"known": True, "exists": False, "reason": "recipient_not_on_whatsapp"}

    monkeypatch.setattr(wahost.SelfHostWhatsApp, "_recipient_check", _fake_check)

    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("919123456780", "hi"))

    # Caller still learns the send was blocked...
    assert res.get("error") == "recipient_not_on_whatsapp"
    assert res.get("status") == "blocked"
    # ...but integration health is NOT poisoned by it.
    assert recorded == []


def test_real_integration_faults_are_still_recorded(monkeypatch):
    """Guard the fix's blast radius: genuine config faults must STILL be recorded."""
    recorded: list[str] = []
    monkeypatch.setattr(wahost, "_record_whatsapp_failure", lambda note="": recorded.append(note))
    monkeypatch.delenv("WAHA_BASE_URL", raising=False)

    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("919999999999", "hi"))

    assert res.get("error") == "selfhost_not_configured"
    assert recorded == ["selfhost_not_configured"]
