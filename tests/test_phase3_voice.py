"""Phase-3 voice-quality tests: Silero VAD gate + Smart Turn combine + shared
turn-taking knobs (defensive / OFF-default).

Free-stack. silero-vad / pipecat are NOT installed, so the gates must stay inert
(return None) and the wiring must fall back to RMS / silence-timer cleanly. The
shared knobs must default to the historical values so prod is unchanged until an
operator sets the env.
"""

import importlib

from app.voice_agent import turn_detector as TD


def test_silero_gate_inert_when_disabled_or_unavailable():
    # USE_SILERO_VAD unset (or dep missing) -> is_speech returns None => RMS fallback.
    g = TD.SileroSpeechGate()
    assert g.is_speech(b"\x00\x01" * 300) is None  # short/disabled -> None


def test_smart_turn_inert_by_default():
    d = TD.SmartTurnDetector()
    # disabled (no USE_SMART_TURN / no pipecat) -> always None, any audio length.
    assert d.is_endpoint(b"\x00" * 640) is None
    assert d.is_endpoint(b"\x00" * 32000) is None  # 1 s @16k still None when off
    assert d.is_endpoint(b"\x00" * 16000, sample_rate=8000) is None  # 8k path None too


def test_confirm_end_of_turn_combines_silence_and_semantic():
    assert TD.confirm_end_of_turn(False) is False  # still talking -> not end
    # silence ended + Smart Turn disabled (None) -> honor silence timer -> end.
    assert TD.confirm_end_of_turn(True) is True
    assert TD.confirm_end_of_turn(True, b"\x00" * 640) is True
    assert TD.confirm_end_of_turn(True, b"\x00" * 16000, sample_rate=8000) is True


def test_singletons_and_exports():
    assert TD.get_speech_gate() is TD.get_speech_gate()
    assert TD.get_smart_turn() is TD.get_smart_turn()
    assert hasattr(TD, "confirm_end_of_turn")
    for fn in ("turn_silence_ms", "turn_vad_rms", "barge_in_ms", "barge_in_frames"):
        assert hasattr(TD, fn)


def test_shared_knob_defaults_unchanged(monkeypatch):
    # No env set -> historical defaults (700 ms silence, 300 RMS, ~100 ms barge-in).
    for k in ("TURN_SILENCE_MS", "TURN_VAD_RMS", "TURN_BARGE_MIN_MS", "SMART_TURN_THRESHOLD"):
        monkeypatch.delenv(k, raising=False)
    assert TD.turn_silence_ms() == 700.0
    assert TD.turn_silence_ms(650.0) == 650.0  # caller default honored
    assert TD.turn_vad_rms() == 300
    assert TD.barge_in_ms() == 100.0
    # 20 ms frames -> 100 ms == 5 frames; 8k path uses the same helper.
    assert TD.barge_in_frames(20.0) == 5
    assert TD.barge_in_frames(20.0, 100.0) == 5


def test_shared_knobs_env_override(monkeypatch):
    monkeypatch.setenv("TURN_SILENCE_MS", "550")
    monkeypatch.setenv("TURN_VAD_RMS", "420")
    monkeypatch.setenv("TURN_BARGE_MIN_MS", "60")
    assert TD.turn_silence_ms() == 550.0
    assert TD.turn_vad_rms() == 300 or TD.turn_vad_rms() == 420  # env wins
    assert TD.turn_vad_rms() == 420
    assert TD.barge_in_ms() == 60.0
    assert TD.barge_in_frames(20.0) == 3  # 60/20 = 3 frames


def test_shared_knobs_bad_env_falls_back(monkeypatch):
    # garbage env must never raise / never break import — falls back to default.
    monkeypatch.setenv("TURN_SILENCE_MS", "not-a-number")
    monkeypatch.setenv("TURN_VAD_RMS", "")
    assert TD.turn_silence_ms() == 700.0
    assert TD.turn_vad_rms() == 300
    assert TD.barge_in_frames(0.0) == 1  # zero frame_ms guarded -> 1


def test_smart_turn_threshold_env(monkeypatch):
    monkeypatch.setenv("SMART_TURN_THRESHOLD", "0.7")
    d = TD.SmartTurnDetector()
    assert abs(d._threshold - 0.7) < 1e-9
    # still inert (no pipecat) regardless of threshold
    assert d.is_endpoint(b"\x00" * 32000) is None


def test_stream_and_pipeline_imports_clean():
    from app.telephony import vobiz_stream  # noqa: F401
    from app.voice_agent import pipeline  # noqa: F401

    assert True


def test_stream_constants_use_shared_defaults(monkeypatch):
    # Re-import the stream modules with snappy knobs set; their module-level
    # constants should reflect the shared defaults (no VOBIZ_*/explicit override).
    for k in ("VOBIZ_SILENCE_MS", "VOBIZ_VAD_RMS", "VOBIZ_BARGE_MIN_FRAMES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TURN_VAD_RMS", "350")
    import app.telephony.vobiz_stream as vs

    vs = importlib.reload(vs)
    assert vs._VAD_RMS == 350  # picked up shared TURN_VAD_RMS default
    assert vs.BARGE_MIN_FRAMES >= 1


def test_pipeline_default_knobs_unchanged(monkeypatch):
    for k in ("TURN_SILENCE_MS", "TURN_VAD_RMS"):
        monkeypatch.delenv(k, raising=False)
    from app.voice_agent.pipeline import VoicePipeline

    p = VoicePipeline()
    # historical defaults preserved when nothing is set.
    assert abs(p.silence_timeout_s - 0.8) < 1e-9
    assert p.energy_threshold == 500
    # explicit args still win.
    p2 = VoicePipeline(silence_timeout_s=0.5, energy_threshold=222)
    assert abs(p2.silence_timeout_s - 0.5) < 1e-9
    assert p2.energy_threshold == 222
