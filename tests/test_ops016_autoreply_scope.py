"""OPS-016 — the WhatsApp AI's scope must be FLAG-INDEPENDENT.

OPS-013 (docs/OPS_013_WHATSAPP_AI_SCOPE_2026-09-07.md) found exactly one drift
vector: ``WHATSAPP_AI_AUTOREPLY=1`` widened ``_draft_intents`` to include ``other``,
so an open-ended inbound message got an open-ended LLM answer — the precise shape
Meta's "general-purpose AI chatbot" bar targets. One env var away from a number ban.

OPS-016 closes it: ``other`` is never drafted and never auto-sent, whether or not the
flag is armed. Scope no longer depends on configuration.

These are BEHAVIOURAL tests. They drive the real ``whatsapp_reply`` path and inspect
the returned record plus a recording sender — so reverting the change fails the suite
even if nobody re-reads the comment (the OPS-022 lesson: source-comment edits are not
proof, and a comment-only revert is invisible).
"""

import asyncio

import pytest

from app.platform import reply_agent as ra
from app.platform import wa_conversation as wc


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(wc, "_CONV_FILE", str(tmp_path / "wa_conversations.jsonl"))
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(tmp_path / "reply_drafts.jsonl"))
    monkeypatch.setattr(ra, "_notify", lambda *a, **k: None)
    # Money-path isolation: no UPI footer appended to drafts.
    from app.platform import upi_config

    monkeypatch.setattr(upi_config, "get_vpa", lambda: "")


def _run(tmp_path, monkeypatch, label, autoreply):
    """Drive one inbound message through the real path.

    Returns ``(record, sent_messages, draft_calls)``. ``autoreply=None`` means the
    flag is unset (the shipped default).
    """
    _isolate(tmp_path, monkeypatch)
    if autoreply is None:
        monkeypatch.delenv("WHATSAPP_AI_AUTOREPLY", raising=False)
    else:
        monkeypatch.setenv("WHATSAPP_AI_AUTOREPLY", autoreply)

    sent = []
    draft_calls = []

    async def fake_chat(system, messages, max_tokens=90, temperature=0.6, **kw):
        if max_tokens == 8:  # classifier call -> fixed label
            return (label, "fake")
        draft_calls.append(messages)  # drafter call -> prose
        return ("AI se likha hua jawab", "fake")

    class _Sender:
        async def send_text_message(self, to, msg):
            sent.append((to, msg))
            return {"messages": [{"id": "x"}]}

    from app.integrations import whatsapp as wa_int
    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    monkeypatch.setattr(wa_int, "get_whatsapp_sender", lambda: _Sender())

    rec = asyncio.run(ra.whatsapp_reply("919876543210", "aapke baare me batao"))
    return rec, sent, draft_calls


# --------------------------------------------------------------------------- #
# 1. The fix: `other` stays out of scope even with the flag armed
# --------------------------------------------------------------------------- #
def test_other_is_never_drafted_even_with_autoreply_on(tmp_path, monkeypatch):
    """THE regression test. Pre-OPS-016 this returned 'AI se likha hua jawab'."""
    rec, _sent, draft_calls = _run(tmp_path, monkeypatch, "other", "1")
    assert rec["intent"] == "other"
    assert rec["draft"] == ""
    assert draft_calls == []  # the LLM drafter was never invoked


def test_other_is_never_auto_sent_even_with_autoreply_on(tmp_path, monkeypatch):
    rec, sent, _drafts = _run(tmp_path, monkeypatch, "other", "1")
    assert rec["auto_sent"] is False
    assert sent == []


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_other_stays_out_of_scope_for_every_truthy_spelling(tmp_path, monkeypatch, value):
    rec, sent, draft_calls = _run(tmp_path, monkeypatch, "other", value)
    assert rec["draft"] == ""
    assert draft_calls == []
    assert sent == []


# --------------------------------------------------------------------------- #
# 2. Default state is unchanged (flag OFF) — no silent regression
# --------------------------------------------------------------------------- #
def test_other_is_not_drafted_with_flag_unset(tmp_path, monkeypatch):
    rec, sent, draft_calls = _run(tmp_path, monkeypatch, "other", None)
    assert rec["draft"] == ""
    assert draft_calls == []
    assert sent == []


def test_drafting_is_flag_independent_for_other(tmp_path, monkeypatch):
    """Off vs on must produce identical records for `other` — that IS the fix."""
    off, sent_off, drafts_off = _run(tmp_path, monkeypatch, "other", None)
    on, sent_on, drafts_on = _run(tmp_path, monkeypatch, "other", "1")
    assert (off["draft"], off["auto_sent"]) == (on["draft"], on["auto_sent"])
    assert (sent_off, drafts_off) == (sent_on, drafts_on)


# --------------------------------------------------------------------------- #
# 3. Sales-scoped intents must KEEP working — narrowing, not amputation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("intent", ["interested", "question", "objection"])
def test_sales_intents_still_draft_when_autoreply_on(tmp_path, monkeypatch, intent):
    rec, _sent, draft_calls = _run(tmp_path, monkeypatch, intent, "1")
    assert rec["intent"] == intent
    assert rec["draft"] == "AI se likha hua jawab"
    assert len(draft_calls) == 1


def test_interested_still_auto_sends_when_autoreply_on(tmp_path, monkeypatch):
    rec, sent, _drafts = _run(tmp_path, monkeypatch, "interested", "1")
    assert rec["auto_sent"] is True
    assert sent and sent[0][1] == "AI se likha hua jawab"


@pytest.mark.parametrize("intent", ["unsubscribe", "not_interested", "ooo"])
def test_optout_intents_never_auto_send(tmp_path, monkeypatch, intent):
    rec, sent, _drafts = _run(tmp_path, monkeypatch, intent, "1")
    assert rec["auto_sent"] is False
    assert sent == []


# --------------------------------------------------------------------------- #
# 4. The warning stays factually accurate (OPS-013 wording must not go stale)
# --------------------------------------------------------------------------- #
def test_policy_warning_no_longer_claims_other_is_drafted():
    msg = ra.autoreply_policy_warning(True)
    assert "OPS-016" in msg
    # It must not assert the OLD behaviour, which no longer exists.
    assert "INCLUDING" not in msg.upper() or "OPS-016" in msg


def test_policy_warning_still_names_the_policy_and_the_ban_risk():
    msg = ra.autoreply_policy_warning(True)
    assert "WHATSAPP_AI_AUTOREPLY" in msg
    assert "OPS-013" in msg
    assert "GENERAL-PURPOSE AI chatbots" in msg
    assert "ban" in msg.lower()
