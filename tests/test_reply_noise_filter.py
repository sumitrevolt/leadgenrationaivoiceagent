"""Reply noise-filter tests (2026-07-07 deliverability audit fixes).

Background: reply_drafts.jsonl 1803 rows me sirf ~9 genuine the — 312 rows ek
adityabirla.com auto-responder loop se ("Thank you for your interest..." mails
LLM se "interested" classify ho rahi thi), WhatsApp status/broadcast bhi
"interested" tak class ho raha tha. Fix: auto-ack guard (known-prospect pe bhi),
per-sender flood cap, operator blocklist, WA status/broadcast guard.
"""

import asyncio
import email.message

from app.platform import reply_agent


def _msg(headers: dict[str, str] | None = None) -> email.message.Message:
    m = email.message.Message()
    for k, v in (headers or {}).items():
        m[k] = v
    return m


# --------------------------------------------------------------- auto-ack guard
def test_auto_ack_subjects():
    assert reply_agent._is_auto_ack(_msg(), "Thank you for your interest in Vikram Solar.")
    assert reply_agent._is_auto_ack(_msg(), "Thanks for contacting Aditya Birla Capital")
    assert reply_agent._is_auto_ack(_msg(), "We have received your enquiry")
    assert reply_agent._is_auto_ack(_msg(), "Automatic reply: out of office")
    assert reply_agent._is_auto_ack(_msg(), "Auto-Reply: ticket #123 created")


def test_auto_ack_header():
    assert reply_agent._is_auto_ack(_msg({"Auto-Submitted": "auto-replied"}), "hello")
    assert not reply_agent._is_auto_ack(_msg({"Auto-Submitted": "no"}), "hello")


def test_auto_ack_real_replies_pass():
    # Genuine human replies must NOT be swallowed by the guard.
    assert not reply_agent._is_auto_ack(_msg(), "Re: quick question — pricing?")
    assert not reply_agent._is_auto_ack(_msg(), "haan interested hoon, demo kab?")
    assert not reply_agent._is_auto_ack(_msg(), "Tattoo ki services dete h")


def test_auto_ack_never_raises():
    assert reply_agent._is_auto_ack(None, "") in (True, False)


# --------------------------------------------------------------- flood cap
def test_flood_cap_default_and_disable(monkeypatch):
    monkeypatch.delenv("REPLY_SENDER_FLOOD_CAP", raising=False)
    assert reply_agent._flood_cap() == 6
    monkeypatch.setenv("REPLY_SENDER_FLOOD_CAP", "0")
    assert reply_agent._flood_cap() == 0
    monkeypatch.setenv("REPLY_SENDER_FLOOD_CAP", "garbage")
    assert reply_agent._flood_cap() == 6


def test_sender_counts():
    rows = [
        {"from": "Loop@AdityaBirla.com"},
        {"from": "loop@adityabirla.com"},
        {"from": "real@smb.in"},
        {"from": ""},
        None,
    ]
    counts = reply_agent._sender_counts(rows)
    assert counts["loop@adityabirla.com"] == 2
    assert counts["real@smb.in"] == 1
    assert "" not in counts


# --------------------------------------------------------------- blocklist
def test_blocklist_domain_and_address(monkeypatch):
    monkeypatch.setenv("REPLY_SENDER_BLOCKLIST", "adityabirla.com, noisy@vendor.in")
    assert reply_agent._is_blocklisted("anything@adityabirla.com")
    assert reply_agent._is_blocklisted("noisy@vendor.in")
    assert not reply_agent._is_blocklisted("owner@localbiz.in")


def test_blocklist_unset_blocks_nothing(monkeypatch):
    monkeypatch.delenv("REPLY_SENDER_BLOCKLIST", raising=False)
    assert not reply_agent._is_blocklisted("anything@adityabirla.com")


# --------------------------------------------------------------- WhatsApp guards
def test_wa_status_and_broadcast_skipped(monkeypatch):
    # Guard must fire BEFORE any LLM classify — fail loudly if classify is reached.
    async def _boom(*a, **k):  # pragma: no cover - must not run
        raise AssertionError("classify should not be called for status/broadcast")

    monkeypatch.setattr(reply_agent, "_classify", _boom)
    assert asyncio.run(reply_agent.whatsapp_reply("status", "some status text")) == {}
    assert asyncio.run(reply_agent.whatsapp_reply("status@broadcast", "yo")) == {}
    assert asyncio.run(reply_agent.whatsapp_reply("false_status@BROADCAST_x", "yo")) == {}


def test_wa_blocklisted_number_skipped(monkeypatch):
    monkeypatch.setenv("REPLY_SENDER_BLOCKLIST", "120363174051639404")

    async def _boom(*a, **k):  # pragma: no cover - must not run
        raise AssertionError("classify should not be called for blocklisted sender")

    monkeypatch.setattr(reply_agent, "_classify", _boom)
    assert asyncio.run(reply_agent.whatsapp_reply("120363174051639404", "spam")) == {}


def test_wa_real_number_still_processed(tmp_path, monkeypatch):
    # Over-filtering guard: a genuine 1-1 WhatsApp message must still flow.
    monkeypatch.delenv("REPLY_SENDER_BLOCKLIST", raising=False)
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(tmp_path / "drafts.jsonl"))

    async def _fake_classify(subject, body, history=""):
        return "interested"

    async def _fake_draft(*a, **k):
        return "namaste! demo?"

    monkeypatch.setattr(reply_agent, "_classify", _fake_classify)
    monkeypatch.setattr(reply_agent, "_draft", _fake_draft)
    rec = asyncio.run(reply_agent.whatsapp_reply("919876543210", "haan interested hoon"))
    assert rec.get("intent") == "interested"
    assert rec.get("channel") == "whatsapp"
