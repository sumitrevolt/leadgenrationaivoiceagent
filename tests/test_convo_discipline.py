"""
Tests for D-9 source-line + D-10 conversation discipline block in the
TelecallerBrain system prompt (gated CONVO_DISCIPLINE).
"""

from app.voice_agent import telecaller_brain as tb


def test_convo_discipline_flag(monkeypatch):
    monkeypatch.delenv("CONVO_DISCIPLINE", raising=False)
    assert tb._convo_discipline_enabled() is True
    monkeypatch.setenv("CONVO_DISCIPLINE", "0")
    assert tb._convo_discipline_enabled() is False


def test_convo_discipline_constant_covers_gaps():
    c = tb._CONVO_DISCIPLINE
    assert "OBJECTION 3-STEP" in c  # D-10 objection structure + incumbent trick
    assert "WHATSAPP-GATE" in c  # D-10 qualify-before-send
    assert "HINGLISH MIRROR" in c  # D-10 mix/formality/tech-noun
    assert "SOURCE" in c  # D-9 source line


def test_brain_prompt_includes_discipline_when_on(monkeypatch):
    monkeypatch.setenv("CONVO_DISCIPLINE", "1")
    monkeypatch.setenv("SOFTNO_DEESCALATE", "1")
    b = tb.TelecallerBrain(niche="solar", client_name="Acme")
    assert "OBJECTION 3-STEP" in b.system_prompt
    assert "HINGLISH MIRROR" in b.system_prompt
    assert "POLITE-NO RULE" in b.system_prompt  # D-8 rule rides along


def test_brain_prompt_excludes_discipline_when_off(monkeypatch):
    monkeypatch.setenv("CONVO_DISCIPLINE", "0")
    b = tb.TelecallerBrain(niche="solar", client_name="Acme")
    assert "OBJECTION 3-STEP" not in b.system_prompt
