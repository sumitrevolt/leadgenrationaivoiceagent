"""Pure-python tests for the zero-dep text/semantic endpoint check in
``app.voice_agent.turn_detector``.

No network / DB / LLM / audio model — the text rule is plain string logic.
Covers: affirmative (terminal punctuation), dangling conjunction, thinking
filler, empty/undecided, and the USE_TEXT_ENDPOINT gating in confirm_end_of_turn.
"""

from app.voice_agent import turn_detector as TD


# --------------------------------------------------------------------------- #
# text_end_of_turn — the standalone rule
# --------------------------------------------------------------------------- #
def test_terminal_punctuation_is_complete():
    assert TD.text_end_of_turn("haan bilkul.") is True
    assert TD.text_end_of_turn("aap kya bechte ho?") is True
    assert TD.text_end_of_turn("zaroor!") is True
    # Hindi danda + double-danda
    assert TD.text_end_of_turn("theek hai।") is True
    assert TD.text_end_of_turn("samajh gaya॥") is True


def test_dangling_conjunction_is_incomplete():
    # Roman Hinglish conjunctions -> caller mid-thought, keep listening.
    assert TD.text_end_of_turn("mujhe website chahiye aur") is False
    assert TD.text_end_of_turn("haan chahiye lekin") is False
    assert TD.text_end_of_turn("nahi le sakta kyunki") is False
    assert TD.text_end_of_turn("voice agent ya") is False
    # Devanagari conjunction tail.
    assert TD.text_end_of_turn("mujhe chahiye और") is False


def test_thinking_filler_is_incomplete():
    assert TD.text_end_of_turn("matlab") is False
    assert TD.text_end_of_turn("haan woh") is False
    assert TD.text_end_of_turn("ek second uh") is False
    assert TD.text_end_of_turn("hmm") is False


def test_trailing_comma_or_dash_is_incomplete():
    assert TD.text_end_of_turn("pehli baat,") is False
    assert TD.text_end_of_turn("dekho -") is False


def test_empty_or_undecided_returns_none():
    assert TD.text_end_of_turn("") is None
    assert TD.text_end_of_turn("   ") is None
    assert TD.text_end_of_turn(None) is None  # type: ignore[arg-type]
    # A plain word with no terminal punct and not a known tail -> undecided.
    assert TD.text_end_of_turn("namaste") is None
    assert TD.text_end_of_turn("mujhe ek website banwani hai") is None


def test_never_raises_on_weird_input():
    # Punctuation-only / odd unicode should never throw.
    assert TD.text_end_of_turn("...") is None or TD.text_end_of_turn("...") in (True, False)
    assert TD.text_end_of_turn("?!") is True  # ends on terminal punct


# --------------------------------------------------------------------------- #
# confirm_end_of_turn — gating behaviour (default OFF = unchanged)
# --------------------------------------------------------------------------- #
def test_confirm_default_off_ignores_text(monkeypatch):
    monkeypatch.delenv("USE_TEXT_ENDPOINT", raising=False)
    # Flag OFF: a dangling conjunction must NOT hold the turn (legacy behaviour).
    assert TD.confirm_end_of_turn(True, b"", text="haan chahiye lekin") is True
    # still-talking short-circuit unchanged
    assert TD.confirm_end_of_turn(False, b"", text="kuch bhi") is False


def test_confirm_text_endpoint_holds_on_dangling(monkeypatch):
    monkeypatch.setenv("USE_TEXT_ENDPOINT", "1")
    # Flag ON + dangling conjunction -> keep listening (False) despite silence.
    assert TD.confirm_end_of_turn(True, b"", text="mujhe chahiye aur") is False
    # Flag ON + complete sentence -> turn ends (True).
    assert TD.confirm_end_of_turn(True, b"", text="haan bilkul.") is True
    # Flag ON + undecided text -> falls through to silence-timer (True; Smart-Turn off).
    assert TD.confirm_end_of_turn(True, b"", text="namaste sir") is True
    # Flag ON + empty text -> no text effect (True).
    assert TD.confirm_end_of_turn(True, b"", text="") is True


def test_text_end_of_turn_exported():
    assert hasattr(TD, "text_end_of_turn")
    assert "text_end_of_turn" in TD.__all__
