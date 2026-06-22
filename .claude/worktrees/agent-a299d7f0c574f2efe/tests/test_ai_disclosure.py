"""TRAI up-front AI-disclosure gate — niche_scripts.ensure_ai_disclosure.

Legal gate (TCCCPR): AI promotional calls MUST disclose up-front that the caller
is an AI. This guards the shared helper used by BOTH live opener paths
(vobiz_stream._opening_line + phone_stream._greeting).
"""

from __future__ import annotations

from app.voice_agent.niche_scripts import ensure_ai_disclosure


def test_injects_disclosure_into_main_swara_opener():
    line = "Namaste, main Swara bol rahi hoon Acme ki taraf se. Kya main do minute le sakti hoon?"
    out = ensure_ai_disclosure(line)
    assert "ai assistant" in out.lower()
    # injected right after "main Swara", before "bol rahi hoon"
    assert out.lower().index("ai assistant") < out.lower().index("bol rahi hoon")


def test_idempotent_when_already_disclosed():
    line = "Namaste, main Swara, ek AI assistant, bol rahi hoon."
    assert ensure_ai_disclosure(line) == line  # no double-injection


def test_recognizes_alternate_disclosure_tokens():
    line = "Hello, this is an automated call from Acme."
    assert ensure_ai_disclosure(line) == line  # 'automated' already discloses


def test_prepends_when_no_name_anchor():
    line = "Namaste! LeadGen AI ki taraf se baat. Do minute baat kar sakti hoon?"
    out = ensure_ai_disclosure(line)
    # 'AI' substring present already? 'LeadGen AI' contains 'ai ' -> not an AI token,
    # so a disclosure must be added.
    assert "ai assistant" in out.lower()
    assert out.startswith("Main ek AI assistant hoon.")


def test_empty_is_safe():
    assert ensure_ai_disclosure("") == ""
    assert ensure_ai_disclosure(None) == ""  # type: ignore[arg-type]
