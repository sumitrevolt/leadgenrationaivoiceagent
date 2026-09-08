"""Pure-python tests for the adaptive-interruption helpers in
``app.voice_agent.turn_detector``: ``is_backchannel`` (pure ack detection) and
the ``barge_guard_*`` frame-window helpers (BARGE_GUARD).

No network / DB / LLM / audio model — all plain logic + env gating. Mirrors the
research from LiveKit "adaptive interruption" + Pipecat semantic turn-taking:
a cough / one-word "haan" must not stop the bot, and a pure ack that still barges
is not a real turn.
"""

from app.voice_agent import turn_detector as TD


# --------------------------------------------------------------------------- #
# is_backchannel — pure acknowledgments
# --------------------------------------------------------------------------- #
def test_pure_backchannels_are_true():
    for t in (
        "haan",
        "hmm",
        "achha",
        "ok",
        "okay",
        "ji",
        "haan ji",
        "ji haan",
        "theek hai",
        "thik hai",
        "sahi hai",
        "bilkul",
        "right",
        "samajh gaya",
        "samajh gayi",
        "yes",
        "go on",
        "carry on",
    ):
        assert TD.is_backchannel(t) is True, t


def test_devanagari_backchannels_are_true():
    assert TD.is_backchannel("हाँ") is True
    assert TD.is_backchannel("अच्छा") is True
    assert TD.is_backchannel("ठीक है") is True  # है is in the set


def test_backchannel_strips_punctuation():
    assert TD.is_backchannel("haan!") is True
    assert TD.is_backchannel("achha...") is True
    assert TD.is_backchannel("ok, ") is True
    assert TD.is_backchannel("hmm?") is True


def test_real_content_is_not_backchannel():
    # Substantive replies / questions must never be swallowed.
    for t in (
        "mujhe website chahiye",
        "kitne ka hai",
        "kitna",  # a real one-word question
        "nahi",  # a negative ANSWER, not an ack
        "nahi chahiye",
        "haan mujhe ek website banwani hai",  # ack + real content (>3 tokens)
        "price kya hai bhai",
        "ek sawaal hai",
        "call me kal",
    ):
        assert TD.is_backchannel(t) is False, t


def test_empty_or_none_is_not_backchannel():
    assert TD.is_backchannel("") is False
    assert TD.is_backchannel("   ") is False
    assert TD.is_backchannel(None) is False  # type: ignore[arg-type]
    assert TD.is_backchannel("...") is False  # punctuation only


def test_backchannel_token_cap():
    # <=3 tokens only; a 4-token all-ack string is treated as content (safety).
    assert TD.is_backchannel("haan ji bilkul") is True  # 3 tokens
    assert TD.is_backchannel("haan ji bilkul sahi") is False  # 4 tokens


def test_backchannel_never_raises():
    for t in ("\x00", "😀😀", "haan\n\n", "  HAAN  ", "Achha Ji"):
        TD.is_backchannel(t)  # must not raise


# --------------------------------------------------------------------------- #
# barge_guard — frame-window helpers + env gating
# --------------------------------------------------------------------------- #
def test_guard_off_matches_snappy_barge(monkeypatch):
    monkeypatch.delenv("BARGE_GUARD", raising=False)
    monkeypatch.delenv("TURN_BARGE_MIN_MS", raising=False)
    assert TD.barge_guard_enabled() is False
    # OFF -> identical to the snappy ~100 ms barge (5 frames @20 ms).
    assert TD.barge_guard_frames(20.0) == TD.barge_in_frames(20.0) == 5


def test_guard_on_requires_sustained_window(monkeypatch):
    monkeypatch.setenv("BARGE_GUARD", "1")
    monkeypatch.delenv("TURN_BARGE_GUARD_MS", raising=False)
    assert TD.barge_guard_enabled() is True
    # ON -> 280 ms / 20 ms = 14 frames (sustained; a cough can't reach it).
    assert TD.barge_guard_frames(20.0, default_ms=280.0) == 14
    # And it is strictly longer than the snappy default.
    assert TD.barge_guard_frames(20.0, default_ms=280.0) > TD.barge_in_frames(20.0)


def test_guard_window_env_override(monkeypatch):
    monkeypatch.setenv("BARGE_GUARD", "on")
    monkeypatch.setenv("TURN_BARGE_GUARD_MS", "400")
    assert TD.barge_guard_ms() == 400.0
    assert TD.barge_guard_frames(20.0) == 20  # 400 / 20


def test_guard_bad_env_is_safe(monkeypatch):
    monkeypatch.setenv("BARGE_GUARD", "1")
    monkeypatch.setenv("TURN_BARGE_GUARD_MS", "not-a-number")
    # Bad value must fall back to the 280 ms default, never raise.
    assert TD.barge_guard_ms() == 280.0
    assert TD.barge_guard_frames(20.0) == 14


def test_new_helpers_exported():
    for name in ("is_backchannel", "barge_guard_enabled", "barge_guard_ms", "barge_guard_frames"):
        assert name in TD.__all__, name
        assert hasattr(TD, name)
