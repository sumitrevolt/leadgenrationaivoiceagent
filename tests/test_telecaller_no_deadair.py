"""Voice brain: conversation must ALWAYS advance — no dead-air / robotic-repeat
after discovery exhausts. Repros the "2-3 conversation ke baad agent ko aage kya
karna nahi pata" bug: once discovery + value + closing are all covered,
_next_discovery_line returned "" (blank) or the SAME closing again (repeat), so the
agent stalled. Shared TelecallerBrain => guards ALL agents/niches.
"""

from app.voice_agent import telecaller_brain as tb
from app.voice_agent.telecaller_brain import TelecallerBrain


def _brain():
    return TelecallerBrain(niche="general", client_name="Test Co")


def _exhaust(b):
    """History where every scripted line (discovery + value + closing) is already
    asked by the assistant — the exact state after 2-3 real turns."""
    try:
        from app.voice_agent.niche_scripts import get_script

        s = get_script(b.niche) or {}
    except Exception:
        s = {}
    disc = [d for d in (s.get("discovery") or list(getattr(b, "questions", []) or [])) if d]
    vals = [v for v in (s.get("value_lines") or []) if v]
    closing = (s.get("closing") or "").strip()
    asked = list(disc) + list(vals) + ([closing] if closing else [])
    return [{"role": "assistant", "content": x} for x in asked], asked


def test_advances_after_everything_asked():
    b = _brain()
    hist, asked = _exhaust(b)
    line = b._next_discovery_line(hist)
    assert line, (
        "discovery+value+closing exhaust ke baad bhi ek next-step aana chahiye (no dead-air)"
    )
    assert line not in asked, "wahi closing/sawaal repeat na ho — conversation ADVANCE kare"


def test_script_fallback_never_blank_after_exhaust():
    b = _brain()
    hist, _ = _exhaust(b)
    assert b._script_fallback(hist), "script fallback kabhi blank na de (dead-air guard)"


def test_never_blank_even_when_universal_close_also_asked():
    b = _brain()
    hist, asked = _exhaust(b)
    hist += [{"role": "assistant", "content": c} for c in tb._UNIVERSAL_CLOSE]
    assert b._next_discovery_line(hist), "sab kuch asked hone par bhi non-blank last-resort"


def test_universal_close_exists_and_drives_next_step():
    # the safety-net closers must be niche-agnostic next-steps (callback/follow-up),
    # no invented price/number.
    assert isinstance(tb._UNIVERSAL_CLOSE, (list, tuple)) and len(tb._UNIVERSAL_CLOSE) >= 2
    for c in tb._UNIVERSAL_CLOSE:
        assert "?" in c  # each drives to a concrete next-step choice
