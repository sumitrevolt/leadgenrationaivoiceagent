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


# --------------------------------------------------------------- Hot Queue read-path
def test_noise_row_detection(monkeypatch):
    monkeypatch.delenv("REPLY_SENDER_BLOCKLIST", raising=False)
    assert reply_agent._is_noise_row({"from": "status", "text": "wa status"})
    assert reply_agent._is_noise_row({"from": "false_status@broadcast_x", "text": "yo"})
    assert reply_agent._is_noise_row(
        {"from": "care@adityabirla.com", "subject": "Thank you for your interest"}
    )
    assert not reply_agent._is_noise_row({"from": "owner@localbiz.in", "subject": "Re: pricing"})
    assert reply_agent._is_noise_row(None) in (True, False)


# ------------------------------------------- legacy-noise retro-hide (2026-08-11)
def test_noise_row_dmarc_sender():
    # DMARC aggregate/forensic reports (64 prod rows) — structural noise.
    assert reply_agent._is_noise_row(
        {"from": "noreply-dmarc-support@google.com", "subject": "DMARC report"}
    )


def test_noise_row_closure_body_in_draft_field():
    # 2026-07-25 se pehle saved adityabirla ticketing rows: body `draft` key me
    # hai, intent=interested — read-path pe fake-hot dikhna band hona chahiye.
    assert reply_agent._is_noise_row(
        {
            "from": "opuscare@adityabirla.com",
            "intent": "interested",
            "subject": "Re: AI marketing enquiry",
            "draft": "Not related to Birla Opus. Hence, closed.",
        }
    )
    assert reply_agent._is_noise_row(
        {
            "from": "opuscare@adityabirla.com",
            "intent": "interested",
            "subject": "Re: enquiry",
            "draft": "We regret to inform you that we are not interested.",
        }
    )


def test_noise_row_closure_in_subject_only():
    assert reply_agent._is_noise_row(
        {
            "from": "opuscare@adityabirla.com",
            "intent": "interested",
            "subject": "Your case is closed",
        }
    )


def test_noise_row_genuine_draft_field_passes(monkeypatch):
    # `draft` key wali GENUINE reply noise nahi hai.
    monkeypatch.delenv("REPLY_SENDER_BLOCKLIST", raising=False)
    assert not reply_agent._is_noise_row(
        {
            "from": "owner@localbiz.in",
            "intent": "interested",
            "draft": "Haan demo chahiye, kab milega?",
        }
    )


def test_hot_queue_drops_historic_noise_and_blocklist(tmp_path, monkeypatch):
    import json as _json

    monkeypatch.setenv("REPLY_SENDER_BLOCKLIST", "blocked.example")
    f = tmp_path / "drafts.jsonl"
    rows = [
        {
            "from": "status",
            "intent": "interested",
            "text": "wa status",
            "at": "2026-07-07T10:00:00+00:00",
            "channel": "whatsapp",
        },
        {
            "from": "ack@blocked.example",
            "intent": "interested",
            "subject": "real-ish but operator-blocked",
            "at": "2026-07-07T10:01:00+00:00",
        },
        {
            "from": "ack@example.com",
            "intent": "interested",
            "subject": "Thank you for your interest in Example",
            "at": "2026-07-07T10:02:00+00:00",
        },
        {
            "from": "919876543210",
            "intent": "interested",
            "text": "haan demo chahiye",
            "at": "2026-07-07T10:03:00+00:00",
            "channel": "whatsapp",
        },
        {
            "from": "owner@localbiz.in",
            "intent": "question",
            "subject": "Re: pricing?",
            "at": "2026-07-07T10:04:00+00:00",
        },
    ]
    f.write_text("\n".join(_json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(reply_agent, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        reply_agent,
        "_full_prospect_map",
        lambda: {
            "ack@blocked.example": {"emailed_at": "2026-07-01T10:00:00Z"},
            "ack@example.com": {"emailed_at": "2026-07-01T10:00:00Z"},
            "owner@localbiz.in": {"emailed_at": "2026-07-01T10:00:00Z"},
        },
    )

    senders = {r.get("from") for r in reply_agent.hot_queue(limit=50)}
    assert senders == {"919876543210", "owner@localbiz.in"}


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
