"""Voice close-signal side-effects — root-cause fix for "customer haan bolta hai
to onboard nahi hota": the deterministic close-intent trigger used to be pure
dialogue (promised WhatsApp send + setup, did neither). Now it deterministically
(1) writes a sales_pipeline deal and (2) fires a real WhatsApp send (gated
WHATSAPP_AUTO_SEND) to the number the call was placed to/from.
"""

from __future__ import annotations

import asyncio

import pytest

from app.voice_agent.telecaller_brain import TelecallerBrain


def test_set_caller_phone_strips_non_digits():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("+91 98765-43210")
    assert brain.caller_phone == "919876543210"


def test_set_caller_phone_ignores_empty():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("")
    assert brain.caller_phone == ""


def test_on_close_signal_writes_sales_pipeline_deal(monkeypatch):
    from app.marketing import sales_pipeline

    calls = []
    monkeypatch.setattr(
        sales_pipeline, "upsert_deal", lambda lead, stage="interested": calls.append((lead, stage))
    )
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    brain._on_close_signal()
    assert len(calls) == 1
    lead, stage = calls[0]
    assert lead["phone"] == "9876543210"
    assert lead["niche"] == "ai_marketing"
    assert stage == "negotiating"


def test_on_close_signal_deal_write_never_raises(monkeypatch):
    from app.marketing import sales_pipeline

    def _boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(sales_pipeline, "upsert_deal", _boom)
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    brain._on_close_signal()  # must not raise


def test_on_close_signal_no_whatsapp_task_without_phone(monkeypatch):
    """No caller_phone (e.g. web-test call) -> no background task spawned."""
    from app.marketing import sales_pipeline

    monkeypatch.setattr(sales_pipeline, "upsert_deal", lambda *a, **k: None)
    spawned = []
    orig_create_task = asyncio.create_task
    monkeypatch.setattr(asyncio, "create_task", lambda coro: spawned.append(coro) or orig_create_task(coro))
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    assert brain.caller_phone == ""
    brain._on_close_signal()
    assert spawned == []


@pytest.mark.asyncio
async def test_send_close_whatsapp_inert_when_flag_off(monkeypatch):
    """Neither flag set -> inert (default OFF, safe)."""
    from app.integrations import whatsapp as wa

    monkeypatch.delenv("WHATSAPP_AUTO_SEND", raising=False)
    monkeypatch.delenv("VOICE_CLOSE_WHATSAPP", raising=False)
    sent = []
    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: sent.append("called"))
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    await brain._send_close_whatsapp()
    assert sent == []


@pytest.mark.asyncio
async def test_send_close_whatsapp_inert_with_only_global_flag(monkeypatch):
    """WHATSAPP_AUTO_SEND=1 alone (already ON for unrelated campaign sends on
    VPS) must NOT activate this feature — dedicated VOICE_CLOSE_WHATSAPP opt-in
    required so an existing flag can't silently turn on new AI-judged outbound."""
    from app.integrations import whatsapp as wa

    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.delenv("VOICE_CLOSE_WHATSAPP", raising=False)
    sent = []
    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: sent.append("called"))
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    await brain._send_close_whatsapp()
    assert sent == []


@pytest.mark.asyncio
async def test_send_close_whatsapp_sends_when_both_flags_enabled(monkeypatch):
    from app.integrations import whatsapp as wa

    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setenv("VOICE_CLOSE_WHATSAPP", "1")

    sent = {}

    class FakeSender:
        async def send_text_message(self, to_number, message):
            sent["to"] = to_number
            sent["message"] = message
            return {"ok": True}

    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: FakeSender())
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    await brain._send_close_whatsapp()
    assert sent["to"] == "9876543210"
    assert "leadsgenai.in/start" in sent["message"]


@pytest.mark.asyncio
async def test_close_intent_reply_triggers_close_signal(monkeypatch):
    """Full reply() path: a close-intent utterance must call _on_close_signal
    exactly once and return the setup-confirm line (pre-LLM, deterministic)."""
    monkeypatch.setenv("CLOSE_DETECT", "1")
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    triggered = []
    monkeypatch.setattr(brain, "_on_close_signal", lambda: triggered.append(True))
    reply = await brain.reply([], "trial start karwa do")
    assert triggered == [True]
    assert "whatsapp" in reply.lower() or "व्हाट्सएप" in reply.lower() or "WhatsApp" in reply


@pytest.mark.asyncio
async def test_bare_haan_does_not_trigger_close_signal(monkeypatch):
    """A plain 'haan' (no proceed verb) must NOT fire the close side-effects —
    guards against false-positive CRM writes / WhatsApp spam on every yes."""
    monkeypatch.setenv("CLOSE_DETECT", "1")
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    triggered = []
    monkeypatch.setattr(brain, "_on_close_signal", lambda: triggered.append(True))
    # Bare "haan" alone; reply() may still call the LLM downstream but that's
    # unrelated to this assertion — we only check the close-signal did not fire.
    from app.voice_agent.telecaller_brain import _is_close_intent

    assert _is_close_intent("haan") is False
    assert triggered == []


@pytest.mark.asyncio
async def test_web_call_learns_phone_from_post_close_reply(monkeypatch):
    """Web-test call (no dialed number, e.g. /app/test-call — the same page real
    prospects get as a demo link): the close-signal turn alone must stay a
    no-op (no caller_phone yet), but once the caller SPEAKS a WhatsApp number
    on the very next turn, the brain must learn it and fire the same durable
    actions (deal write + real WhatsApp send) a phone call gets immediately."""
    from app.integrations import whatsapp as wa
    from app.marketing import sales_pipeline

    deals = []
    monkeypatch.setattr(
        sales_pipeline, "upsert_deal", lambda lead, stage="interested": deals.append((lead, stage))
    )
    monkeypatch.setenv("CLOSE_DETECT", "1")
    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setenv("VOICE_CLOSE_WHATSAPP", "1")

    sent = {}

    class FakeSender:
        async def send_text_message(self, to_number, message):
            sent["to"] = to_number
            return {"ok": True}

    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: FakeSender())

    spawned = []
    orig_create_task = asyncio.create_task
    monkeypatch.setattr(
        asyncio, "create_task", lambda coro: spawned.append(coro) or orig_create_task(coro)
    )

    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    assert brain.caller_phone == ""  # web call: nothing dialed

    # Turn 1: close-intent -> setup-confirm asked; no phone yet -> clean no-op.
    reply1 = await brain.reply([], "trial start karwa do")
    assert brain.caller_phone == ""
    assert deals == []
    assert spawned == []

    # Turn 2: caller states their WhatsApp number.
    history = [{"role": "assistant", "content": reply1}]
    reply2 = await brain.reply(history, "9876543210")

    assert brain.caller_phone == "9876543210"
    assert len(deals) == 1
    lead, stage = deals[0]
    assert lead["phone"] == "9876543210"
    assert stage == "negotiating"
    assert "9876543210" in reply2 or "9 8 7 6 5 4 3 2 1 0" in reply2

    assert len(spawned) == 1
    await spawned[0]
    assert sent.get("to") == "9876543210"
