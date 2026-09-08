"""Focused tests for Swara enterprise conversation upgrade (STT/sticky/opener/QA)."""

from __future__ import annotations

import pytest

from app.voice_agent.call_session_state import CallSessionState
from app.voice_agent.conversation_context import build_context, mask_phones
from app.voice_agent.postcall_qa import analyze_transcript, propose_training_correction
from app.voice_agent.response_contract import parse_and_validate
from app.voice_agent.stt_understanding_gate import (
    CLARIFY_LINE,
    SttClass,
    SttGateMetrics,
    apply_metrics,
    classify,
    should_failure_close,
    strip_junk_phrases,
)
from app.voice_agent.telecaller_brain import TelecallerBrain
from app.voice_agent.voice_sticky_route import (
    ROUTE_LIVE_PRIMARY,
    select_at_call_start,
    try_fallback,
)


def test_stt_gate_aam_shabd_is_noise():
    r = classify("Aam shabd, Aam Shabd, Aam shabd, Aam Shabd")
    assert r.cls == SttClass.NOISE
    assert r.allow_llm is False
    assert r.clarify is True


def test_stt_gate_mixed_junk_with_phone_strips_and_allows_llm():
    raw = "Aam shabd, A4 590 12607 mera mobile number hai"
    r = classify(raw)
    assert r.cls == SttClass.VALID_MEANINGFUL
    assert r.allow_llm is True
    assert "aam shabd" not in r.text.lower()
    assert "12607" in r.text or "590" in r.text


def test_stt_gate_mixed_junk_only_triggers_clarify():
    r = classify("Aam shabd, thank you for watching, subscribe")
    assert r.allow_llm is False
    assert r.clarify is True
    assert r.cls in (SttClass.NOISE, SttClass.LOW_CONFIDENCE)


def test_stt_gate_mixed_junk_metrics():
    m = SttGateMetrics()
    g = classify("Aam shabd, thank you for watching")
    apply_metrics(m, g)
    assert m.stt_noise_count >= 1 or m.stt_low_confidence_count >= 1
    assert m.stt_clarification_count >= 1


def test_strip_junk_phrases_preserves_phone_content():
    cleaned, ratio, had = strip_junk_phrases("Aam shabd, 8459012607 par WhatsApp bhej do")
    assert had is True
    assert "8459012607" in cleaned
    assert "aam shabd" not in cleaned.lower()


def test_close_setup_reply_confirms_number_same_turn():
    b = TelecallerBrain(niche="ai_marketing", client_name="Test Co")
    b.caller_phone = ""
    b.close_signal_fired = False
    out = b._close_setup_reply("haan start karo 9876543210 par")
    assert "9876543210" in out.replace(" ", "")
    assert b.caller_phone == "9876543210"


def test_close_setup_reply_without_number_asks_confirm():
    b = TelecallerBrain(niche="ai_marketing", client_name="Test Co")
    out = b._close_setup_reply("aaj hi trial start kar do")
    assert "whatsapp number confirm" in out.lower()


def test_audit_loop_pivot_after_repeated_audit_offers():
    b = TelecallerBrain(niche="ai_marketing", client_name="Test Co")
    history = [
        {"role": "assistant", "content": "FREE Google audit bhej doon?"},
        {"role": "assistant", "content": "Tab tak FREE audit karwa doon?"},
    ]
    pivot = b._apply_audit_loop_guard(
        "Toh FREE Google audit abhi bhej doon? Saath me 7-din trial — aaj set kar doon?",
        history,
    )
    assert "whatsapp number confirm" in pivot.lower()
    assert "audit" not in pivot.lower()


def test_fast_path_soch_ke_pivots_after_audit_loop():
    b = TelecallerBrain(niche="ai_marketing", client_name="Test Co")
    history = [
        {"role": "assistant", "content": "FREE Google audit bhej doon?"},
        {"role": "assistant", "content": "Tab tak FREE audit karwa doon?"},
    ]
    ans = TelecallerBrain._fast_path_reply(b, history, "soch ke batata hoon")
    assert ans
    assert "whatsapp number confirm" in ans.lower()
    assert "audit" not in ans.lower()


def test_discovery_skipped_after_interest_confirmed():
    b = TelecallerBrain(niche="ai_marketing", client_name="Test Co")
    b._interest_confirmed = True
    history = [{"role": "assistant", "content": "Marketing khud karte ho?"}]
    nxt = b._next_discovery_line(history)
    assert "marketing khud" not in nxt.lower()


def test_stt_gate_opt_out_with_junk_not_stripped():
    r = classify("Aam shabd call mat karna number hata do")
    assert r.cls == SttClass.VALID_OPT_OUT
    assert r.allow_llm is False


def test_stt_gate_pricing_mixed_junk_strips_and_allows():
    r = classify("Aam shabd marketing plan kitne ka hai")
    assert r.cls == SttClass.VALID_MEANINGFUL
    assert r.allow_llm is True
    assert "aam shabd" not in r.text.lower()
    assert "plan" in r.text.lower() or "marketing" in r.text.lower()


def test_semantic_loop_guard_pivots_on_repeat():
    b = TelecallerBrain(niche="ai_marketing", client_name="Test Co")
    history = [
        {"role": "assistant", "content": "Plan Main package 1999 rupaye mahine ka hai."},
    ]
    repeat = "Plan Main package 1999 rupaye mahine ka hai."
    out = b._guard_semantic_loop(repeat, history)
    assert out != repeat
    assert getattr(b, "_semantic_loop_detected", False) is True


def test_stt_gate_meaningful_hindi():
    r = classify("Haan ji, marketing plan kitne ka hai?")
    assert r.cls == SttClass.VALID_MEANINGFUL
    assert r.allow_llm is True
    assert r.advance_sales is True


def test_stt_gate_short_confirm():
    r = classify("Haan")
    assert r.cls == SttClass.VALID_SHORT_CONFIRMATION


def test_stt_gate_opt_out():
    r = classify("Call mat karna, number hata do")
    assert r.cls == SttClass.VALID_OPT_OUT
    assert r.allow_llm is False


def test_stt_gate_duplicate():
    r = classify("hello", last_user="hello")
    assert r.cls == SttClass.DUPLICATE


def test_stt_clarify_then_failure_close():
    m = SttGateMetrics()
    for _ in range(3):
        g = classify("Aam shabd Aam shabd Aam shabd Aam shabd")
        apply_metrics(m, g)
    assert m.stt_clarification_count >= 1
    assert should_failure_close(m) is True
    assert "phir bolenge" in CLARIFY_LINE.lower() or "clear nahi" in CLARIFY_LINE.lower()


def test_opener_guard_on_tools_path_logic():
    """_looks_like_greeting must detect Swara opener for tools-path block."""
    opener = (
        "Namaste, main Swara bol rahi hoon, LeadsGen AI ki taraf se — "
        "ek AI assistant. Do minute baat kar sakti hoon?"
    )
    assert TelecallerBrain._looks_like_greeting(opener) is True
    assert TelecallerBrain._looks_like_greeting("Plan Main 1999 rupaye mahine ka hai.") is False


def test_session_blocks_opener_repeat():
    s = CallSessionState(call_id="c1")
    s.mark_greeting_spoken()
    assert s.greeting_completed is True
    s.block_opener_repeat()
    assert s.opener_blocked_count == 1


def test_sticky_pin_and_fallback_limit():
    route = select_at_call_start()
    assert route.route_id == ROUTE_LIVE_PRIMARY
    assert route.provider
    assert route.model
    r1 = try_fallback(route, error="timeout")
    assert r1 is not None
    r2 = try_fallback(r1, error="429")
    assert r2 is not None
    r3 = try_fallback(r2, error="again")
    assert r3 is None  # max 2 mid-call fallbacks


def test_conversation_context_masks_phone_and_blocks_model_pricing():
    assert "***2607" in mask_phones("mera number 8459012607 hai")
    ctx = build_context(tenant_id="t1", business_name="Test Co", niche="ai_marketing")
    ctx.set_fact("price", "999", server_owned=False)
    assert "price" not in ctx.facts
    ctx.set_fact("price_main", "1999", server_owned=True)
    assert ctx.facts.get("price_main") == "1999"
    block = ctx.prompt_block()
    assert "APPROVED_PRICING" in block or "1999" in block or "pricing" in block.lower()


def test_response_contract_strips_markdown_and_extra_questions():
    c = parse_and_validate("**Namaste** Plan kya hai? Aur features? Aur price?")
    assert "**" not in c.spoken_response
    assert c.spoken_response.count("?") <= 1


def test_response_contract_json():
    raw = '{"spoken_response": "Plan Main 1999 ka hai.", "detected_intent": "pricing", "confidence": 0.9}'
    c = parse_and_validate(raw)
    assert "1999" in c.spoken_response
    assert c.detected_intent == "pricing"


def test_postcall_qa_detects_opener_repeat():
    hist = [
        {
            "role": "assistant",
            "content": "Namaste main Swara, AI assistant. Do minute baat kar sakti hoon?",
        },
        {"role": "user", "content": "Haan"},
        {
            "role": "assistant",
            "content": "Namaste main Swara, AI assistant. Do minute baat kar sakti hoon?",
        },
    ]
    qa = analyze_transcript(hist)
    assert qa.opener_repeat is True
    assert qa.score < 1.0


def test_training_proposal_forbids_pricing_fine_tune(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    p = propose_training_correction(
        batch_count=30,
        qa_summary={"opener_repeat": True},
        allowed_surfaces=["prompt", "pricing", "fine_tune", "stt_filters"],
    )
    assert "pricing" not in p["allowed_surfaces"]
    assert "fine_tune" not in p["allowed_surfaces"]
    assert p["auto_fine_tune"] is False
    assert "stt_filters" in p["allowed_surfaces"]


def test_customer_provide_question_gets_full_answer():
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    out = b._customer_qa_reply("तो क्या provide कर रहे हो तुम?")
    assert out
    assert "marketing" in out.lower() or "post" in out.lower()
    assert "?" not in out or out.count("?") <= 1


def test_customer_plan_question_gets_pricing_not_discovery():
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    assert b._looks_like_question("वाला plan?")
    out = b._customer_qa_reply("वाला plan?")
    assert out
    assert "1999" in out or "5,999" in out or "5999" in out


def test_platform_pitch_caps_discovery_after_one_question():
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    hist = [
        {"role": "assistant", "content": "Marketing abhi khud karte ho, staff se, ya agency?"},
        {"role": "user", "content": "khud karta hoon"},
    ]
    assert b._platform_pitch_discovery_cap_reached(hist) is True
    nxt = b._next_discovery_line(hist)
    assert "marketing abhi khud" not in (nxt or "").lower()
    assert "google pe" not in (nxt or "").lower() or "?" not in (nxt or "")


def test_question_discipline_strips_extra_q_when_customer_silent():
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    hist = [
        {"role": "assistant", "content": "Marketing abhi khud karte ho, staff se, ya agency?"},
        {"role": "user", "content": "khud karta hoon"},
    ]
    raw = "Roz posts automatic hain — social pe time milta hai kya?"
    out = b._apply_question_discipline(raw, "khud karta hoon", hist)
    assert "?" not in out


def test_question_discipline_preserves_pricing_after_customer_question():
    """Rhetorical double-? must not cut pricing/setup detail after the 2nd ?."""
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    hist = [{"role": "user", "content": "price kya hai aapka?"}]
    raw = "Interested hain? Budget kitna? Basic plan 1999 se start hota hai — setup free hai."
    out = b._apply_question_discipline(raw, "price kya hai aapka?", hist)
    assert "1999" in out
    assert "setup free" in out.lower()
    assert out.count("?") <= 1


def test_greeting_on_platform_pitch_skips_discovery_barrage():
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    out = b._fast_path_reply([], "Hello")
    assert out
    assert "post" in out.lower() or "automatic" in out.lower() or "trial" in out.lower()
    assert "marketing abhi khud" not in out.lower()
