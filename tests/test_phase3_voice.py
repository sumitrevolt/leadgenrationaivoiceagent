"""Phase-3 voice-quality tests: Silero VAD gate + Smart Turn combine (defensive/OFF-default).

Free-stack. silero-vad / pipecat are NOT installed, so the gates must stay inert
(return None) and the wiring must fall back to RMS / silence-timer cleanly.
"""

from app.voice_agent import turn_detector as TD


def test_silero_gate_inert_when_disabled_or_unavailable():
    # USE_SILERO_VAD unset (or dep missing) -> is_speech returns None => RMS fallback.
    g = TD.SileroSpeechGate()
    assert g.is_speech(b"\x00\x01" * 300) is None  # short/disabled -> None


def test_smart_turn_inert_by_default():
    d = TD.SmartTurnDetector()
    assert d.is_endpoint(b"\x00" * 640) is None


def test_confirm_end_of_turn_combines_silence_and_semantic():
    assert TD.confirm_end_of_turn(False) is False  # still talking -> not end
    # silence ended + Smart Turn disabled (None) -> honor silence timer -> end.
    assert TD.confirm_end_of_turn(True) is True
    assert TD.confirm_end_of_turn(True, b"\x00" * 640) is True


def test_singletons_and_exports():
    assert TD.get_speech_gate() is TD.get_speech_gate()
    assert TD.get_smart_turn() is TD.get_smart_turn()
    assert hasattr(TD, "confirm_end_of_turn")


def test_stream_and_pipeline_imports_clean():
    from app.telephony import vobiz_stream  # noqa: F401
    from app.voice_agent import phone_stream, pipeline  # noqa: F401

    assert True
