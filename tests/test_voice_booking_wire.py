"""P2 (2026-06-28): wire REAL booking (calendar_booking) into live calls without
regressing the P1 answer-first fix.

- _is_booking_intent gates the agentic tool-path to booking turns only.
- reply_with_tools (the VOICE_TOOLS path) must STILL answer a product question via
  the deterministic fast-path (no dodge), only routing booking-intent to the tool-LLM.
"""

from __future__ import annotations

import asyncio

from app.api.web_call import _is_booking_intent
from app.voice_agent.telecaller_brain import TelecallerBrain


def test_booking_intent_detection():
    for yes in (
        "Book karoge appointment mein",
        "abhi karo book",
        "meeting fix karo",
        "kal visit karna hai",
        "slot kya hai",
        "बुक कर दो",
    ):
        assert _is_booking_intent(yes) is True, yes
    for no in ("kya kya features hain?", "mera bill zyada aata hai", "price kitna", "haan ji", ""):
        assert _is_booking_intent(no) is False, no


def test_reply_with_tools_still_answers_question_no_dodge():
    # Under the VOICE_TOOLS path, a feature question must hit the deterministic
    # fast-path answer (call is None, content enumerates) — NOT the tool-LLM that
    # would re-introduce the dodge.
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    hist = [{"role": "assistant", "content": "interested hain?"}]
    spoken, call = asyncio.run(b.reply_with_tools(hist, "kya kya features hain?", object()))
    assert call is None
    low = (spoken or "").lower()
    assert "char" in low or "feature" in low or "post" in low
