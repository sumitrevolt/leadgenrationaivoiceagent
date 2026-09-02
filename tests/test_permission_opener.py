"""
Tests for D-9 (permission opener, ensure_permission_ask) + D-12 (KB threshold).
Pure functions; no network.
"""

from app.voice_agent.niche_scripts import ensure_ai_disclosure, ensure_permission_ask


def test_permission_appended_when_missing(monkeypatch):
    monkeypatch.setenv("PERMISSION_OPENER", "1")
    out = ensure_permission_ask("Namaste, main Swara ek AI assistant hoon")
    assert "do minute" in out.lower()
    assert out.lower().rstrip().endswith("busy hain?")


def test_permission_not_doubled_when_present(monkeypatch):
    monkeypatch.setenv("PERMISSION_OPENER", "1")
    base = "Namaste — do minute baat kar sakti hoon ya busy hain?"
    assert ensure_permission_ask(base) == base


def test_permission_gated_off(monkeypatch):
    monkeypatch.setenv("PERMISSION_OPENER", "0")
    base = "Namaste, main Swara hoon"
    assert ensure_permission_ask(base) == base


def test_permission_empty_safe():
    assert ensure_permission_ask("") == ""
    assert ensure_permission_ask(None) == ""  # type: ignore[arg-type]


def test_disclosure_plus_permission_compose(monkeypatch):
    """Opener through both gates -> discloses AI AND asks permission (the D-9
    target). Verified against the same check qa_checks.check_missing_permission."""
    monkeypatch.setenv("PERMISSION_OPENER", "1")
    from app.voice_agent.qa_checks import check_missing_permission

    raw = "Namaste, main Swara bol rahi hoon LeadGen se"
    opener = ensure_permission_ask(ensure_ai_disclosure(raw))
    low = opener.lower()
    assert "ai assistant" in low or "ai agent" in low  # disclosure present
    assert "do minute" in low  # permission present
    # the QA check should see permission in the opener turn
    assert check_missing_permission([{"role": "assistant", "content": opener}]) is None


def test_kb_min_score_default():
    """D-12: KB score gate default raised 0.05 -> 0.35 (regression guard)."""
    from app.voice_agent import telecaller_brain as tb

    assert tb._KB_MIN_SCORE == 0.35


def test_stt_keyterms_biases_on_entities(monkeypatch):
    """D-11: STT bias string carries client + niche + Hinglish register."""
    monkeypatch.setenv("STT_BIAS", "1")
    from app.voice_agent.niche_scripts import stt_keyterms

    out = stt_keyterms("solar", "Acme Solar")
    assert "Acme Solar" in out
    assert "solar" in out.lower()
    assert "hinglish" in out.lower()


def test_stt_keyterms_excludes_demo_and_general(monkeypatch):
    monkeypatch.setenv("STT_BIAS", "1")
    from app.voice_agent.niche_scripts import stt_keyterms

    out = stt_keyterms("general", "Demo Co")
    assert "Demo Co" not in out
    assert "general" not in out.lower()
    assert out  # still returns the Hinglish hint


def test_stt_keyterms_gated_off(monkeypatch):
    monkeypatch.setenv("STT_BIAS", "0")
    from app.voice_agent.niche_scripts import stt_keyterms

    assert stt_keyterms("solar", "Acme") == ""


def test_web_call_opener_discloses_ai(monkeypatch):
    """D-14: the web-call opener (brain.opening_line wrapped, as web_call does) must
    disclose AI + carry permission — parity with the phone opener."""
    monkeypatch.setenv("PERMISSION_OPENER", "1")
    from app.voice_agent.niche_scripts import ensure_ai_disclosure, ensure_permission_ask
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain = TelecallerBrain(niche="solar", client_name="Acme")
    opener = ensure_permission_ask(ensure_ai_disclosure(brain.opening_line()))
    low = opener.lower()
    assert "ai assistant" in low or "ai agent" in low  # AI disclosure injected
    assert ("minute" in low) or ("busy" in low)  # permission/timing present
