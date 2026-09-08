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
    monkeypatch.setattr(
        asyncio, "create_task", lambda coro: spawned.append(coro) or orig_create_task(coro)
    )
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    assert brain.caller_phone == ""
    brain._on_close_signal()
    assert spawned == []


def test_on_close_signal_without_running_loop_does_not_construct_coroutine(monkeypatch):
    """Sync callers must not create an awaitable they cannot schedule."""
    from app.marketing import sales_pipeline

    monkeypatch.setattr(sales_pipeline, "upsert_deal", lambda *a, **k: None)
    constructed = []
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    monkeypatch.setattr(brain, "_send_close_whatsapp", lambda: constructed.append(True))

    brain._on_close_signal()

    assert constructed == []


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


def test_close_signal_fired_flag_set_when_phone_known():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    assert brain.close_signal_fired is False
    brain._on_close_signal()
    assert brain.close_signal_fired is True


def test_close_signal_fired_flag_stays_false_without_phone():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    assert brain.caller_phone == ""
    brain._on_close_signal()
    assert brain.close_signal_fired is False


@pytest.mark.asyncio
async def test_close_signal_fired_resets_on_next_turn(monkeypatch):
    """close_signal_fired must reflect ONLY the just-completed reply() turn --
    web_call.py checks it once per turn to decide whether to emit a WS
    close_signal event; a stale True would re-fire the overlay forever."""
    monkeypatch.setenv("CLOSE_DETECT", "1")
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")

    await brain.reply([], "trial start karwa do")
    assert brain.close_signal_fired is True

    await brain.reply(
        [{"role": "assistant", "content": "Bilkul sir! ... WhatsApp number confirm kar dijiye."}],
        "mujhe thoda sochna hai",
    )
    assert brain.close_signal_fired is False


@pytest.mark.asyncio
async def test_send_close_whatsapp_personalizes_link_with_phone_and_niche(monkeypatch):
    from app.integrations import whatsapp as wa

    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setenv("VOICE_CLOSE_WHATSAPP", "1")

    sent = {}

    class FakeSender:
        async def send_text_message(self, to_number, message):
            sent["message"] = message
            return {"ok": True}

    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: FakeSender())
    brain = TelecallerBrain(niche="salon", client_name="Glow Salon")
    brain.set_caller_phone("9876543210")
    await brain._send_close_whatsapp()
    assert "phone=9876543210" in sent["message"]
    assert "biz=Glow%20Salon" in sent["message"]
    assert "niche=salon" in sent["message"]


@pytest.mark.asyncio
async def test_send_close_whatsapp_omits_biz_for_ai_marketing_niche(monkeypatch):
    """ai_marketing persona pitches the platform itself -- client_name holds an
    internal placeholder ("Demo Co"), not the prospect's real business, so the
    personalized link must omit biz= (matches _on_close_signal's existing
    business_name-blank rule for this niche, telecaller_brain.py:807)."""
    from app.integrations import whatsapp as wa

    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setenv("VOICE_CLOSE_WHATSAPP", "1")

    sent = {}

    class FakeSender:
        async def send_text_message(self, to_number, message):
            sent["message"] = message
            return {"ok": True}

    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: FakeSender())
    brain = TelecallerBrain(niche="ai_marketing", client_name="Demo Co")
    brain.set_caller_phone("9876543210")
    await brain._send_close_whatsapp()
    assert "biz=" not in sent["message"]
    assert "phone=9876543210" in sent["message"]
    assert "niche=ai_marketing" in sent["message"]


@pytest.mark.asyncio
async def test_thank_you_after_whatsapp_readback_no_audit(monkeypatch):
    """Proven 7742e06a defect: after Perfect+WhatsApp readback, thank-you must NOT
    resell FREE Google audit."""
    monkeypatch.setenv("CLOSE_DETECT", "1")
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    brain.closing_started = True
    history = [
        {
            "role": "assistant",
            "content": (
                "Perfect! Aapka WhatsApp number 9 8 7 6 5 4 3 2 1 0 — isi par abhi "
                "saari detail aur setup bhej rahi hoon."
            ),
        }
    ]
    reply = await brain.reply(history, "theek hai thank you")
    assert "audit" not in reply.lower()
    assert brain.session_closed is True
    assert "whatsapp" in reply.lower() or "dhanyavaad" in reply.lower()


@pytest.mark.asyncio
async def test_stream_thank_you_after_handoff_blocks_audit(monkeypatch):
    monkeypatch.setenv("CLOSE_DETECT", "1")
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    history = [
        {
            "role": "assistant",
            "content": (
                "Perfect sir! Saari detail aur setup abhi WhatsApp pe bhej rahi "
                "hoon — wahin aaram se baat kar lenge. Dhanyavaad, aapka din shubh ho!"
            ),
        }
    ]
    out: list[str] = []
    async for sent in TelecallerBrain.reply_stream_sentences(brain, history, "ok thanks"):
        out.append(sent)
    text = " ".join(out).lower()
    assert "audit" not in text
    assert brain.session_closed is True


def test_script_fallback_empty_after_closing_started():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.closing_started = True
    history = [
        {"role": "assistant", "content": "FREE Google audit bhej doon?"},
    ]
    assert brain._script_fallback(history) == ""


def test_block_post_close_speech_strips_audit_line():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.closing_started = True
    blocked = brain._block_post_close_speech("Toh FREE Google audit abhi bhej doon?")
    assert "audit" not in blocked.lower()
    assert "whatsapp" in blocked.lower() or "dhanyavaad" in blocked.lower()
