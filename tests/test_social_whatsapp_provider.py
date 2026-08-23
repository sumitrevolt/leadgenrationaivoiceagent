"""social_engine WhatsApp provider — 1-to-1 owner delivery of approved posts.

Bars (delivering promised "1-click publish to WhatsApp" to per-client customers like jiya):
- WhatsAppProvider.publish sends caption (+ media url) via the ACTIVE WA sender to the
  client's OWN phone (single recipient) and reports the message id.
- configured() inert without a WA backend, inert without a recipient phone.
- Engine registers "whatsapp" as a DEFAULT channel candidate for a client with a phone
  (empty-socials client like jiya still gets delivery-ready posts).
- Zero channel + no phone -> "koi channel connected nahi" SURFACED (empty list, not silent).
- Bulk impossible: recipient is always ONE number — a comma/semicolon list collapses to
  the first, and the sender is called with exactly one recipient string (never a list).

Everything mocked; provider/engine logic only — no network, no real WhatsApp.
"""

from __future__ import annotations

import asyncio

import pytest

from app.social_engine import engine, providers, store, vault
from app.social_engine.base import PublishRequest
from app.social_engine.providers import WhatsAppProvider


# --------------------------------------------------------------------------- #
# Fake WhatsApp sender — records EXACTLY what it was asked to send.
# --------------------------------------------------------------------------- #
class _FakeSender:
    def __init__(self, err: str = ""):
        self.err = err
        self.calls: list[tuple] = []  # (to_number, message)

    async def send_text_message(self, to_number, message):
        # A ban-safe 1-to-1 sender takes a single string recipient — NOT a list.
        assert isinstance(to_number, str), "recipient must be a single number, never a list"
        self.calls.append((to_number, message))
        if self.err:
            return {"error": self.err}
        return {"messages": [{"id": "wamid.TEST123"}]}


@pytest.fixture
def wa_on(monkeypatch):
    """A configured WA backend (self-host active) + a fake sender."""
    sender = _FakeSender()
    monkeypatch.setattr(WhatsAppProvider, "_sender_configured", staticmethod(lambda: True))
    import app.integrations.whatsapp as wa_mod

    monkeypatch.setattr(wa_mod, "get_whatsapp_sender", lambda: sender)
    return sender


# --------------------------------------------------------------------------- #
# Provider-level
# --------------------------------------------------------------------------- #
def test_publish_sends_to_single_recipient(wa_on):
    prov = WhatsAppProvider()
    req = PublishRequest(
        client_id="c1",
        caption="Diwali offer 20% off",
        platform="whatsapp",
        account_ref="8712928847",
        media_type="image",
    )
    res = asyncio.run(prov.publish(req, {}))
    assert res.ok is True
    assert res.post_id == "wamid.TEST123"
    # EXACTLY one send, one recipient, caption delivered.
    assert len(wa_on.calls) == 1
    to, msg = wa_on.calls[0]
    assert to == "8712928847"
    assert "Diwali offer" in msg


def test_publish_appends_media_url(wa_on):
    prov = WhatsAppProvider()
    req = PublishRequest(
        client_id="c1",
        caption="New look",
        platform="whatsapp",
        account_ref="8712928847",
        media_url="https://cdn.x/y.jpg",
    )
    res = asyncio.run(prov.publish(req, {}))
    assert res.ok is True
    _, msg = wa_on.calls[0]
    assert "New look" in msg and "https://cdn.x/y.jpg" in msg


def test_publish_records_sender_error(wa_on, monkeypatch):
    bad = _FakeSender(err="selfhost_not_configured")
    import app.integrations.whatsapp as wa_mod

    monkeypatch.setattr(wa_mod, "get_whatsapp_sender", lambda: bad)
    prov = WhatsAppProvider()
    req = PublishRequest(
        client_id="c1", caption="hi", platform="whatsapp", account_ref="8712928847"
    )
    res = asyncio.run(prov.publish(req, {}))
    assert res.ok is False
    assert "selfhost_not_configured" in res.error


def test_publish_no_recipient_clean_fail(wa_on):
    prov = WhatsAppProvider()
    req = PublishRequest(client_id="c1", caption="hi", platform="whatsapp", account_ref="")
    res = asyncio.run(prov.publish(req, {}))
    assert res.ok is False and "recipient" in res.error
    assert wa_on.calls == []  # never touched the sender


def test_configured_needs_backend_and_recipient(monkeypatch):
    prov = WhatsAppProvider()
    # No backend -> inert even with a phone.
    monkeypatch.setattr(WhatsAppProvider, "_sender_configured", staticmethod(lambda: False))
    assert prov.configured({"account_ref": "8712928847"}) is False
    # Backend but no recipient -> inert.
    monkeypatch.setattr(WhatsAppProvider, "_sender_configured", staticmethod(lambda: True))
    assert prov.configured({}) is False
    assert prov.configured(None) is False
    # Backend + recipient -> configured.
    assert prov.configured({"account_ref": "8712928847"}) is True


def test_bulk_recipient_collapses_to_single(wa_on):
    """A comma/semicolon list must NEVER fan out — only the first number is used."""
    prov = WhatsAppProvider()
    req = PublishRequest(
        client_id="c1",
        caption="hi",
        platform="whatsapp",
        account_ref="8712928847, 9000000000; 9111111111",
    )
    res = asyncio.run(prov.publish(req, {}))
    assert res.ok is True
    assert len(wa_on.calls) == 1  # one send only
    to, _ = wa_on.calls[0]
    assert to == "8712928847"
    assert "," not in to and ";" not in to


# --------------------------------------------------------------------------- #
# Engine wiring — default channel candidate + no-channel surfacing
# --------------------------------------------------------------------------- #
@pytest.fixture
def iso(monkeypatch, tmp_path):
    """Hermetic engine: real registry (so whatsapp provider present), isolated store/vault."""
    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "tokens.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)
    monkeypatch.setattr(engine, "_REGISTRY", providers.default_providers())
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.delenv("SOCIAL_TOKEN_KEY", raising=False)


def test_whatsapp_is_default_candidate_for_client_with_phone(iso, monkeypatch, wa_on):
    monkeypatch.setattr(engine, "_client_phone", lambda cid: "8712928847")
    plats = engine._default_platforms("jiya")
    assert "whatsapp" in plats


def test_whatsapp_not_candidate_without_backend(iso, monkeypatch):
    monkeypatch.setattr(engine, "_client_phone", lambda cid: "8712928847")
    monkeypatch.setattr(WhatsAppProvider, "_sender_configured", staticmethod(lambda: False))
    plats = engine._default_platforms("jiya")
    assert "whatsapp" not in plats


def test_resolve_account_uses_client_phone(iso, monkeypatch):
    monkeypatch.setattr(engine, "_client_phone", lambda cid: "8712928847")
    acct = engine._resolve_account("jiya", "whatsapp", "")
    assert acct.get("account_ref") == "8712928847"


def test_enqueue_delivers_to_whatsapp_end_to_end(iso, monkeypatch, wa_on):
    monkeypatch.setattr(engine, "_client_phone", lambda cid: "8712928847")
    ids = engine.enqueue_publish("jiya", caption="Approved post", media_type="image")
    assert ids  # queued for whatsapp
    out = asyncio.run(engine.process_queue())
    assert out["published"] == 1
    assert len(wa_on.calls) == 1
    to, msg = wa_on.calls[0]
    assert to == "8712928847" and "Approved post" in msg


def test_no_channel_surfaced_not_silent(iso, monkeypatch):
    """Client with NO socials and NO phone -> empty list + surfaced warning (not silent)."""
    monkeypatch.setattr(engine, "_client_phone", lambda cid: "")  # jiya-with-no-phone case
    events: list[tuple] = []

    class _Team:
        @staticmethod
        def log_event(who, kind, detail, status="ok"):
            events.append((who, kind, detail, status))

    import app.platform.team as team_mod

    monkeypatch.setattr(team_mod, "log_event", _Team.log_event)
    ids = engine.enqueue_publish("empty-client", caption="hi", media_type="image")
    assert ids == []  # nothing queued
    assert events, "no-channel must surface a team event (not silent)"
    who, kind, detail, status = events[0]
    assert kind == "social_no_channel" and status == "warn"
    assert "koi channel connected nahi" in detail
