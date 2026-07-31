"""§5 ban-safety: WHATSAPP_AUTO_SEND is enforced at the SENDER boundary.

REGRESSION THIS LOCKS DOWN (2026-07-31)
---------------------------------------
``WHATSAPP_AUTO_SEND`` was only ever consulted by campaign-level modules
(``whatsapp_campaign`` / ``review_engine`` / ``product_one_delivery``). Every OTHER
caller sent for real with nothing gating it. The live proof was the hourly ``onboard``
scheduler job::

    onboarding._send_whatsapp (app/marketing/onboarding.py:207)
      -> get_whatsapp_sender().send_text_message()
        -> POST http://waha:3000/api/sendText          # no flag anywhere in this chain

Production logs showed that POST firing 4x per run, hourly, against every active
client's ``contact_phone`` — the paying customer included. The ONLY thing stopping real
delivery was a WAHA session stuck in FAILED. The moment the owner scanned the QR it
would have become real automatic bulk WhatsApp — exactly the §5 invariant
("WhatsApp bulk auto-send = number ban; 1-click human send only; auto gated OFF").

So these tests assert the gate at the boundary, NOT in onboarding — a per-caller fix
would leave the next caller to remember it, which is how this happened.

NO live HTTP anywhere: httpx is faked and every request is recorded, so "no POST" is
asserted as **no HTTP call at all** (``_recipient_check`` does a GET).
"""

from __future__ import annotations

import asyncio

import pytest

from app.integrations import whatsapp as wa
from app.integrations import whatsapp_selfhost as wahost


# --------------------------------------------------------------------------- #
# Recording fake httpx — every call lands in `calls`, so a silent GET can't hide
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, json_data, status=200, content=b"{}"):
        self._json = json_data
        self.status_code = status
        self.content = content
        self.headers = {}
        self.text = ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)


class _Recorder:
    """Records ('GET'|'POST', url) for every request. Recipient-check says the
    number EXISTS so the happy path is not blocked for an unrelated reason."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        self.calls.append(("GET", url))
        if "/contacts/check-exists" in url:
            return _Resp(
                {"numberExists": True, "chatId": "919876543210@c.us"},
                content=b'{"numberExists":true}',
            )
        return _Resp({"status": "WORKING"}, content=b'{"status":"WORKING"}')

    async def post(self, url, **k):
        self.calls.append(("POST", url))
        return _Resp({"id": "wamid.GATE"})

    @property
    def posts(self) -> list[str]:
        return [u for m, u in self.calls if m == "POST"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Neutralise env AND settings so the gate — not a stray .env value — is what decides."""
    for k in (
        "WHATSAPP_AUTO_SEND",
        "WAHA_BASE_URL",
        "WAHA_API_KEY",
        "WAHA_SESSION",
        "WHATSAPP_PROVIDER",
        "WHATSAPP_BUSINESS_NUMBER",
        "WHATSAPP_ENFORCE_BUSINESS_NUMBER",
        "WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN",
        "WHATSAPP_BUSINESS_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
    ):
        monkeypatch.delenv(k, raising=False)
    from app.config import settings

    monkeypatch.setattr(settings, "waha_base_url", "", raising=False)
    monkeypatch.setattr(settings, "whatsapp_provider", "cloud", raising=False)
    monkeypatch.setattr(settings, "whatsapp_business_token", "", raising=False)
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "", raising=False)
    monkeypatch.setattr(settings, "whatsapp_business_number", "", raising=False)
    # The linked-number probe is cached module-wide for 5 min — stale state would
    # leak the business-number guard's verdict between tests.
    wahost._LINKED_CACHE["digits"] = None
    wahost._LINKED_CACHE["at"] = 0.0
    # auto_send_enabled() short-circuits on the Owner-OS kill switch BEFORE it reads
    # the env var, and that switch lives in an on-disk store this fixture would
    # otherwise leave ambient. Pin it OFF so the flag is provably the deciding input:
    # if someone engaged the kill locally or in CI, every "flag ON" test below would
    # go red and read as "the gate is broken" when nothing is. The kill switch's own
    # behaviour is asserted separately in test_owner_kill_switch_blocks_even_when_flag_on.
    from app.platform import owner_os

    monkeypatch.setattr(owner_os, "kill_engaged", lambda _name: False, raising=False)
    yield


def _arm_selfhost(monkeypatch, rec: _Recorder, auto_send: bool) -> None:
    """Point the dual-engine selector at a faked, reachable WAHA stack."""
    monkeypatch.setattr(wahost.httpx, "AsyncClient", rec)
    monkeypatch.setenv("WAHA_BASE_URL", "http://waha:3000")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "waha")
    monkeypatch.setenv("WHATSAPP_ENFORCE_BUSINESS_NUMBER", "0")
    if auto_send:
        monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")


# --------------------------------------------------------------------------- #
# (a) THE LIVE DEFECT — the onboard job must make NO HTTP call when the flag is off
# --------------------------------------------------------------------------- #
def test_onboarding_send_makes_no_http_call_when_flag_unset(monkeypatch):
    from app.marketing import onboarding

    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=False)

    ok = asyncio.run(onboarding._send_whatsapp("919876543210", "Namaste!"))

    assert ok is False, "gated-off send must not be reported as delivered"
    # Not just "no POST": _recipient_check would otherwise still GET check-exists
    # once per active client, hourly, forever.
    assert rec.calls == []


def test_onboarding_renudge_message_is_also_gated(monkeypatch):
    """_renudge_awaiting_interviews re-nudges up to 25 clients through the SAME
    helper — the repetition is what turns one leak into a bulk-send."""
    from app.marketing import onboarding

    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=False)

    msg = onboarding._interview_message("Jiya Makeover", renudge=True)
    for _ in range(3):
        assert asyncio.run(onboarding._send_whatsapp("919876543210", msg)) is False
    assert rec.calls == []


# --------------------------------------------------------------------------- #
# (b) With the flag ON + a WORKING session, the send really happens
# --------------------------------------------------------------------------- #
def test_onboarding_send_posts_when_flag_on(monkeypatch):
    from app.marketing import onboarding

    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=True)

    ok = asyncio.run(onboarding._send_whatsapp("919876543210", "Namaste!"))

    assert ok is True
    assert any("/api/sendText" in u for u in rec.posts), rec.calls


# --------------------------------------------------------------------------- #
# (c) The recipient check must not fail OPEN into a send
# --------------------------------------------------------------------------- #
class _CheckExplodes(_Recorder):
    async def get(self, url, **k):
        self.calls.append(("GET", url))
        if "/contacts/check-exists" in url:
            raise RuntimeError("waha unreachable")
        return _Resp({"status": "WORKING"}, content=b'{"status":"WORKING"}')


class _CheckHttp500(_Recorder):
    async def get(self, url, **k):
        self.calls.append(("GET", url))
        if "/contacts/check-exists" in url:
            return _Resp({}, status=500)
        return _Resp({"status": "WORKING"}, content=b'{"status":"WORKING"}')


@pytest.mark.parametrize("client_cls", [_CheckExplodes, _CheckHttp500])
def test_recipient_check_failure_blocks_the_send(monkeypatch, client_cls):
    """Transport/HTTP failure of the check = unverifiable recipient = NO send."""
    rec = client_cls()
    _arm_selfhost(monkeypatch, rec, auto_send=True)

    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("919876543210", "hi"))

    assert res["error"] == "recipient_check_failed"
    assert res["status"] == "blocked"
    assert rec.posts == [], "an unverifiable recipient must never be POSTed to"


def test_recipient_check_fail_open_kill_switch(monkeypatch):
    """Ops escape hatch restores the old behaviour deliberately, never by accident."""
    rec = _CheckExplodes()
    _arm_selfhost(monkeypatch, rec, auto_send=True)
    monkeypatch.setenv("WHATSAPP_RECIPIENT_CHECK_FAIL_OPEN", "1")

    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("919876543210", "hi"))

    assert res.get("delivery_status") == "accepted"
    assert any("/api/sendText" in u for u in rec.posts)


def test_unreadable_check_shape_still_proceeds(monkeypatch):
    """Backward-compat, asserted on purpose: an OLDER WAHA that answers WITHOUT
    `numberExists` is not a transport failure — it answered, we just can't read it.
    Tightening this would break real deployments, so make it a deliberate change."""

    class _NoField(_Recorder):
        async def get(self, url, **k):
            self.calls.append(("GET", url))
            return _Resp({"status": "WORKING"}, content=b'{"status":"WORKING"}')

    rec = _NoField()
    _arm_selfhost(monkeypatch, rec, auto_send=True)

    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("919876543210", "hi"))
    assert res.get("delivery_status") == "accepted"


# --------------------------------------------------------------------------- #
# Boundary coverage — the point of the fix is that NO caller has to remember
# --------------------------------------------------------------------------- #
def test_blocked_result_carries_an_error_key_and_a_1click_link():
    """Every caller in this repo detects success with
    ``bool(res) and not res.get("error")`` (onboarding:215, reply_agent:1493,
    whatsapp_campaign:162). A blocked result WITHOUT `error` would be logged as a
    successful send — a silent lie in a paying customer's delivery ledger."""
    res = wa.auto_send_blocked("9876543210", "hello")

    assert res["error"] == "auto_send_disabled"
    assert res["would_send"] is True
    assert res["mode"] == "link"
    assert res["link"].startswith("https://wa.me/919876543210?text=")
    assert not (bool(res) and not res.get("error"))


def test_owner_kill_switch_blocks_even_when_flag_on(monkeypatch):
    """The boundary gate delegates to whatsapp_campaign.auto_send_enabled(), which
    short-circuits on the Owner-OS `owner_whatsapp_outbound` kill BEFORE reading the
    env var. Assert the delegation really carries that authority through — otherwise
    the owner's kill switch would stop campaigns but not the boundary."""
    from app.platform import owner_os

    monkeypatch.setattr(owner_os, "kill_engaged", lambda name: name == "owner_whatsapp_outbound")
    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=True)  # flag explicitly ON

    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("919876543210", "hi"))

    assert res["error"] == "auto_send_disabled"
    assert rec.calls == []


def test_gate_fails_closed_when_unreadable(monkeypatch):
    """Compliance gate, not a billing meter: an exception means DENY, never allow."""
    import app.marketing.whatsapp_campaign as wac

    def _boom():
        raise RuntimeError("flag store down")

    monkeypatch.setattr(wac, "auto_send_enabled", _boom)
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")  # even with the flag ON
    assert wa.auto_send_allowed() is False


def test_direct_selfhost_instantiation_is_gated(monkeypatch):
    """Three call sites bypass get_whatsapp_sender() entirely — api/whatsapp.py:470,
    video_production/review_whatsapp.py:173, marketing/whatsapp_flows.py:83. Gating
    the SELECTOR would have missed all three; gating the METHOD catches them."""
    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=False)

    res = asyncio.run(wahost.SelfHostWhatsApp().send_text_message("919876543210", "hi"))

    assert res["error"] == "auto_send_disabled"
    assert rec.calls == []


def test_selfhost_template_send_is_gated(monkeypatch):
    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=False)

    res = asyncio.run(
        wahost.SelfHostWhatsApp().send_template_message("919876543210", "welcome", [])
    )

    assert res["error"] == "auto_send_disabled"
    assert rec.calls == []


def test_selfhost_post_backstop_is_gated(monkeypatch):
    """Egress backstop: even a caller that reaches _post directly cannot send."""
    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=False)

    res = asyncio.run(
        wahost.SelfHostWhatsApp()._post(
            "/api/sendText", {"session": "default", "chatId": "919876543210@c.us", "text": "hi"}
        )
    )

    assert res["error"] == "auto_send_disabled"
    assert rec.posts == []


def test_mixin_notification_helpers_are_gated(monkeypatch):
    """send_lead_alert / send_daily_report / appointment / callback all funnel into
    send_text_message, so the boundary gate covers them for free — assert it, because
    they are the helpers most likely to be wired up by a future caller."""
    rec = _Recorder()
    _arm_selfhost(monkeypatch, rec, auto_send=False)
    sh = wahost.SelfHostWhatsApp()

    alert = asyncio.run(sh.send_lead_alert("919999999999", {"company_name": "Acme"}))
    report = asyncio.run(sh.send_daily_report("919999999999", {"calls_made": 3}))

    assert alert["error"] == "auto_send_disabled"
    assert report["error"] == "auto_send_disabled"
    assert rec.calls == []


# --------------------------------------------------------------------------- #
# Cloud (Meta) engine — inert today without a token, but must not be the next hole
# --------------------------------------------------------------------------- #
def _cloud_client(monkeypatch, rec: _Recorder):
    monkeypatch.setattr(wa.httpx, "AsyncClient", rec)
    client = wa.WhatsAppIntegration()
    client.token = "TEST_TOKEN"  # simulate configured creds
    client.phone_number_id = "123"
    client.base_url = "https://graph.facebook.com/v18.0/123"
    return client


def test_cloud_text_send_is_gated(monkeypatch):
    rec = _Recorder()
    client = _cloud_client(monkeypatch, rec)

    res = asyncio.run(client.send_text_message("919876543210", "hi"))

    assert res["error"] == "auto_send_disabled"
    assert rec.calls == []


def test_cloud_template_send_is_gated(monkeypatch):
    """Templates build their own payload and call _send_message directly — gating
    send_text_message alone would have left this path wide open."""
    rec = _Recorder()
    client = _cloud_client(monkeypatch, rec)

    res = asyncio.run(client.send_template_message("919876543210", "welcome", ["Ramesh"]))

    assert res["error"] == "auto_send_disabled"
    assert rec.calls == []


def test_cloud_send_message_backstop_is_gated(monkeypatch):
    rec = _Recorder()
    client = _cloud_client(monkeypatch, rec)

    res = asyncio.run(client._send_message({"to": "919876543210", "type": "text"}))

    assert res["error"] == "auto_send_disabled"
    assert rec.posts == []


def test_cloud_send_works_when_flag_on(monkeypatch):
    rec = _Recorder()
    client = _cloud_client(monkeypatch, rec)
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")

    res = asyncio.run(client.send_text_message("919876543210", "hi"))

    assert res.get("id") == "wamid.GATE"
    assert any("graph.facebook.com" in u for u in rec.posts)
