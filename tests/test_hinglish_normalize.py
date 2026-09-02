"""2026-07-03 — close/proceed-intent Devanagari words were missing from the
STT gate-vocabulary map (hinglish_normalize.to_roman), so a caller saying
"प्री प्लान एक्टिवेट करो" (a real utterance from a live test call) never
matched telecaller_brain's roman-only _CLOSE_HARD_RE — the close-signal /
WhatsApp-handoff path silently never fired even though the caller clearly
signalled "activate it now"."""

from __future__ import annotations

from app.voice_agent.hinglish_normalize import to_roman
from app.voice_agent.telecaller_brain import _is_close_intent


def test_activate_karo_now_romanizes():
    assert to_roman("एक्टिवेट करो") == "activate karo"


def test_real_call_utterance_now_triggers_close_intent():
    # Verbatim from a real 2026-07-03 test call transcript.
    assert _is_close_intent("प्री प्लान एक्टिवेट करो।") is True


def test_start_shuru_chalu_setup_sign_confirm_fix_romanize():
    assert to_roman("स्टार्ट") == "start"
    assert to_roman("शुरू") == "shuru"
    assert to_roman("चालू") == "chalu"
    assert to_roman("सेटअप") == "setup"
    assert to_roman("साइन") == "sign"
    assert to_roman("कन्फर्म") == "confirm"
    assert to_roman("फिक्स") == "fix"


def test_pure_roman_text_is_unaffected():
    s = "haan activate karo abhi"
    assert to_roman(s) == s
