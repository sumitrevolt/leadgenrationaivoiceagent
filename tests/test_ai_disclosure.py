"""TRAI up-front AI-disclosure gate — niche_scripts.ensure_ai_disclosure.

Legal gate (TCCCPR): AI promotional calls MUST disclose up-front that the caller
is an AI. This guards the shared helper used by BOTH live opener paths
(vobiz_stream._opening_line + phone_stream._greeting).

Note on wording (2026-06-30): opener now uses "AI agent" / "ek AI agent" naturally
(see commit 11a757d "bidirectional AI-agent disclosure" + commit 2802645 buy-signal).
The helper's `_AI_DISCLOSURE_TOKENS` tuple still includes BOTH "ai assistant" AND
"ai agent" so the gate stays satisfied across either wording. Tests assert that
SOME valid disclosure appears (string-level check), not a specific word — keeps
wording flexibility without losing the legal gate.
"""

from __future__ import annotations

from app.voice_agent.niche_scripts import (
    _AI_DISCLOSURE_TOKENS,
    ensure_ai_disclosure,
)


def _has_disclosure(text: str) -> bool:
    """True iff text contains at least one _AI_DISCLOSURE_TOKENS entry."""
    low = text.lower()
    return any(tok in low for tok in _AI_DISCLOSURE_TOKENS)


def test_injects_disclosure_into_main_swara_opener():
    line = "Namaste, main Swara bol rahi hoon Acme ki taraf se. Kya main do minute le sakti hoon?"
    out = ensure_ai_disclosure(line)
    assert _has_disclosure(out), f"no disclosure token in {out!r}"
    # injected right after "main Swara", before "bol rahi hoon"
    assert _has_disclosure(out[: out.lower().index("bol rahi hoon")])


def test_idempotent_when_already_disclosed():
    line = "Namaste, main Swara, ek AI agent, bol rahi hoon."
    assert ensure_ai_disclosure(line) == line  # no double-injection


def test_recognizes_alternate_disclosure_tokens():
    line = "Hello, this is an automated call from Acme."
    assert ensure_ai_disclosure(line) == line  # 'automated' already discloses


def test_prepends_when_no_name_anchor():
    line = "Namaste! LeadGen AI ki taraf se baat. Do minute baat kar sakti hoon?"
    out = ensure_ai_disclosure(line)
    # 'AI' substring present already? 'LeadGen AI' contains 'ai ' -> not an AI token,
    # so a disclosure must be added.
    assert _has_disclosure(out), f"no disclosure token in {out!r}"
    # Prepended format starts with AI self-introduction
    low = out.lower()
    assert low.startswith("main ek ai") or "ai agent hoon" in low or "ai assistant hoon" in low


def test_empty_is_safe():
    assert ensure_ai_disclosure("") == ""
    assert ensure_ai_disclosure(None) == ""  # type: ignore[arg-type]
