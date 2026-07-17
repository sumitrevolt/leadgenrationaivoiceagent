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
