"""Offline tests for the WhatsApp Cloud API auto-sender + campaign runner.

All Cloud API HTTP is mocked — NO live calls. We assert the ban-safe contract:
  - without flag/creds -> 1-click links, never an auto-send,
  - suppressed numbers are skipped,
  - daily cap + spacing are honoured,
  - template store register/list/status works,
  - the webhook signature verifier + opt-out path behave.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from app.marketing import wa_campaign_runner as runner
from app.marketing import whatsapp_campaign as wac


@pytest.fixture(autouse=True)
def _isolate_data(monkeypatch, tmp_path):
    """Isolate every jsonl/state file under a fresh temp cwd + clear env each test.

    record_failure() writes data/wa_failures.jsonl at a fixed relative path, so we
    chdir into tmp_path and point all stores at data/ under it -> full per-test isolation
    (incl. the daily-cap counter, so the cap test isn't polluted by prior sends).
    """
    monkeypatch.chdir(tmp_path)
    os.makedirs("data", exist_ok=True)
    monkeypatch.setattr(runner, "_TEMPLATES_FILE", os.path.join("data", "wa_templates.jsonl"))
    # Suppression resolves through a function now, not a constant: a path frozen
    # at import cannot be redirected by a fixture that runs later.
    monkeypatch.setattr(
        runner, "_suppression_path", lambda: os.path.join("data", "wa_suppression.jsonl")
    )
    monkeypatch.setattr(runner, "_CAMPAIGN_FILE", os.path.join("data", "wa_campaigns.jsonl"))
    monkeypatch.setattr(wac, "_CAP_FILE", os.path.join("data", "counter.json"))
    for k in (
        "WHATSAPP_AUTO_SEND",
        "WHATSAPP_DAILY_CAP",
        "WHATSAPP_SEND_DELAY_S",
        "WHATSAPP_PROVIDER",
        "WAHA_BASE_URL",
        "WAHA_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    from app.config import settings

    monkeypatch.setattr(settings, "whatsapp_provider", "cloud", raising=False)
    monkeypatch.setattr(settings, "waha_base_url", "", raising=False)
    yield


# --------------------------------------------------------------------------- #
# Ban-safe default: no flag -> links, never sends
# --------------------------------------------------------------------------- #
def test_default_is_links_not_sends(monkeypatch):
    monkeypatch.delenv("WHATSAPP_AUTO_SEND", raising=False)
    assert wac.auto_send_enabled() is False
    res = asyncio.run(wac.send_campaign([{"phone": "9876543210", "message": "hi"}]))
    assert res["auto"] is False
    assert res["sent"] == 0
    assert res["links"] == 1
    assert res["items"][0]["mode"] == "link"
    assert res["items"][0]["link"].startswith("https://wa.me/")


def test_flag_on_but_no_creds_stays_links(monkeypatch):
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setattr(wac, "creds_present", lambda: False)
    assert wac.auto_send_enabled() is True
    assert wac.auto_ready() is False  # flag on but creds missing
    res = asyncio.run(wac.send_one("9876543210", "hi"))
    assert res["sent"] is False
    assert res["mode"] == "link_no_creds"


# --------------------------------------------------------------------------- #
# Auto-send live (mocked HTTP) — happy path + spacing + cap
# --------------------------------------------------------------------------- #
class _FakeWA:
    sent: list = []

    def __init__(self):
        pass

    async def send_text_message(self, phone, message):
        _FakeWA.sent.append(("text", phone, message))
        return {"messages": [{"id": "wamid.TEST"}]}

    async def send_template_message(self, phone, template_name, params, language="en"):
        _FakeWA.sent.append(("tmpl", phone, template_name, tuple(params), language))
        return {"messages": [{"id": "wamid.TPL"}]}


def _enable_live(monkeypatch, sleeps):
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setattr(wac, "creds_present", lambda: True)
    monkeypatch.setattr("app.integrations.whatsapp.WhatsAppIntegration", _FakeWA)
    # Force cloud provider so selfhost backend is not selected (netguard blocks waha in tests)
    monkeypatch.setattr("app.integrations.whatsapp_selfhost.is_active_provider", lambda: False)

    async def _no_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(wac.asyncio, "sleep", _no_sleep)
    _FakeWA.sent = []


def test_auto_send_sends_and_spaces(monkeypatch):
    sleeps: list = []
    _enable_live(monkeypatch, sleeps)
    items = [{"phone": "9876543210", "message": "a"}, {"phone": "9123456780", "message": "b"}]
    res = asyncio.run(wac.send_campaign(items, delay_s=2.0))
    assert res["live"] is True
    assert res["sent"] == 2
    assert res["links"] == 0
    assert len(_FakeWA.sent) == 2
    # spacing applied exactly once (between the two sends)
    assert sleeps == [2.0]


def test_daily_cap_enforced(monkeypatch):
    sleeps: list = []
    _enable_live(monkeypatch, sleeps)
    monkeypatch.setenv("WHATSAPP_DAILY_CAP", "1")
    items = [{"phone": "9000000001", "message": "a"}, {"phone": "9000000002", "message": "b"}]
    res = asyncio.run(wac.send_campaign(items))
    assert res["sent"] == 1
    assert res["skipped"] == 1  # second one hits the cap
    assert any(i.get("mode") == "daily_cap" for i in res["items"])


def test_suppressed_number_skipped(monkeypatch):
    sleeps: list = []
    _enable_live(monkeypatch, sleeps)
    runner.suppress("9876543210", "opt_out")
    res = asyncio.run(wac.send_one("9876543210", "hi"))
    assert res["sent"] is False
    assert res["mode"] == "suppressed"
    assert len(_FakeWA.sent) == 0


# --------------------------------------------------------------------------- #
# Template store
# --------------------------------------------------------------------------- #
def test_template_register_list_status():
    rec = runner.register_template("festival_offer_v1", body="Namaste {{1}}", status="pending")
    assert rec["name"] == "festival_offer_v1"
    assert rec["status"] == "pending"
    assert runner.template_is_approved("festival_offer_v1") is False
    assert runner.update_template_status("festival_offer_v1", "approved") is True
    assert runner.template_is_approved("festival_offer_v1") is True
    names = [t["name"] for t in runner.list_templates()]
    assert "festival_offer_v1" in names
    # upsert (same name+lang) does not duplicate
    runner.register_template("festival_offer_v1", body="changed", status="approved")
    assert len([t for t in runner.list_templates() if t["name"] == "festival_offer_v1"]) == 1


# --------------------------------------------------------------------------- #
# Suppression / failure auto-suppress (bounce protection)
# --------------------------------------------------------------------------- #
def test_repeated_failures_auto_suppress():
    phone = "9555000111"
    assert runner.is_suppressed(phone) is False
    for _ in range(runner._FAIL_SUPPRESS_THRESHOLD):
        runner.record_failure(phone, "delivery_failed")
    assert runner.is_suppressed(phone) is True


def test_unsuppress():
    runner.suppress("9555000222", "opt_out")
    assert runner.is_suppressed("9555000222") is True
    assert runner.unsuppress("9555000222") is True
    assert runner.is_suppressed("9555000222") is False


# --------------------------------------------------------------------------- #
# Campaign runner: run_due only auto-sends APPROVED templates
# --------------------------------------------------------------------------- #
def test_run_due_skips_unapproved_template(monkeypatch):
    sleeps: list = []
    _enable_live(monkeypatch, sleeps)
    # template NOT approved -> recipients skipped, nothing sent
    runner.register_template("promo_x", status="pending")
    runner.schedule_campaign(
        "drip", "promo_x", recipients=[{"phone": "9876500000", "name": "A"}], date_iso="2000-01-01"
    )
    res = asyncio.run(runner.run_due())
    assert res["due"] == 1
    assert res["sent"] == 0
    assert len(_FakeWA.sent) == 0


def test_run_due_sends_approved_template(monkeypatch):
    sleeps: list = []
    _enable_live(monkeypatch, sleeps)
    runner.register_template("promo_ok", status="approved")
    runner.schedule_campaign(
        "reactivation",
        "promo_ok",
        recipients=[{"phone": "9876511111", "name": "Ravi"}],
        date_iso="2000-01-01",
    )
    res = asyncio.run(runner.run_due())
    assert res["due"] == 1
    assert res["sent"] == 1
    assert _FakeWA.sent[0][0] == "tmpl"
    assert _FakeWA.sent[0][2] == "promo_ok"


def test_run_due_without_flag_prepares_links(monkeypatch):
    monkeypatch.delenv("WHATSAPP_AUTO_SEND", raising=False)
    runner.register_template("promo_links", status="approved")
    runner.schedule_campaign(
        "drip", "promo_links", recipients=[{"phone": "9876522222"}], date_iso="2000-01-01"
    )
    res = asyncio.run(runner.run_due())
    assert res["due"] == 1
    assert res["sent"] == 0
    assert res["links"] == 1  # 1-click link, not an auto-send
    # campaign marked 'ready' (not 'sent') in ban-safe mode
    camps = runner.list_campaigns()
    assert camps[0]["status"] == "ready"


# --------------------------------------------------------------------------- #
# Webhook signature verifier
# --------------------------------------------------------------------------- #
def test_signature_verify(monkeypatch):
    import hashlib
    import hmac

    from app.integrations import whatsapp as wi

    monkeypatch.setenv("WHATSAPP_APP_SECRET", "topsecret")
    body = b'{"hello":"world"}'
    good = "sha256=" + hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert wi.verify_meta_signature(body, good) is True
    assert wi.verify_meta_signature(body, "sha256=deadbeef") is False


def test_signature_unconfigured_allows(monkeypatch):
    from app.integrations import whatsapp as wi

    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    # no secret + no settings secret -> permissive (dev), never raises
    monkeypatch.setattr(wi.settings, "whatsapp_app_secret", "", raising=False)
    assert wi.verify_meta_signature(b"x", None) is True
