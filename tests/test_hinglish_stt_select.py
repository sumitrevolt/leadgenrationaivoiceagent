"""
Unit tests for the free self-host Hinglish STT model selection in
vobiz_stream._get_stt() (Sarvam-Saaras ka 100%-free alternative).

Locks in:
  1. Flag OFF / dir absent  -> current weak whisper-base (zero behaviour change).
  2. HINGLISH_STT=1 + baked dir present -> Hinglish CT2 model loaded.
  3. HINGLISH_STT=1 but dir MISSING -> safe fall back to whisper-base.
  4. Hinglish model load RAISES -> ALWAYS falls back to whisper-base (a bad/
     corrupt Hinglish dir can never make the call deaf).

WhisperModel is faked (injected into sys.modules) so no heavy model ever loads.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.telephony import vobiz_stream as vs


def _install_fake_whisper(monkeypatch, calls, fail_on=None):
    """Inject a fake `faster_whisper` module whose WhisperModel records the
    model_size it was constructed with (and optionally raises for one size)."""

    class _FakeWhisperModel:
        def __init__(self, model_size, device="cpu", compute_type="int8"):
            if fail_on is not None and model_size == fail_on:
                raise RuntimeError(f"simulated load failure for {model_size}")
            self.model_size = model_size
            calls.append(model_size)

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = _FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)


@pytest.fixture(autouse=True)
def _reset_stt(monkeypatch):
    """Force the local-whisper path on, reset the load-once cache, and clear the
    relevant env so each test starts clean."""
    monkeypatch.setattr(vs, "_VOSK_OK", False, raising=False)
    monkeypatch.setattr(vs, "_FWHISPER_OK", True, raising=False)
    monkeypatch.setattr(vs, "_STT_ENGINE", None, raising=False)
    monkeypatch.setattr(vs, "_STT_INIT", False, raising=False)
    for k in ("HINGLISH_STT", "HINGLISH_WHISPER_DIR", "FWHISPER_MODEL", "VOSK_MODEL_PATH"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_flag_off_uses_whisper_base(monkeypatch):
    calls: list[str] = []
    _install_fake_whisper(monkeypatch, calls)
    engine = vs._get_stt()
    assert engine is not None
    assert engine[0] == "whisper"
    assert calls == ["base"]


def test_flag_on_with_dir_uses_hinglish(monkeypatch, tmp_path):
    calls: list[str] = []
    _install_fake_whisper(monkeypatch, calls)
    d = tmp_path / "hinglish_whisper"
    d.mkdir()
    monkeypatch.setenv("HINGLISH_STT", "1")
    monkeypatch.setenv("HINGLISH_WHISPER_DIR", str(d))
    engine = vs._get_stt()
    assert engine is not None and engine[0] == "whisper"
    assert calls == [str(d)]  # baked Hinglish model, not "base"


def test_flag_on_dir_missing_falls_back_to_base(monkeypatch, tmp_path):
    calls: list[str] = []
    _install_fake_whisper(monkeypatch, calls)
    monkeypatch.setenv("HINGLISH_STT", "1")
    monkeypatch.setenv("HINGLISH_WHISPER_DIR", str(tmp_path / "does_not_exist"))
    engine = vs._get_stt()
    assert engine is not None and engine[0] == "whisper"
    assert calls == ["base"]  # missing dir -> safe base fallback


def test_hinglish_load_failure_falls_back_to_base(monkeypatch, tmp_path):
    d = tmp_path / "hinglish_whisper"
    d.mkdir()
    calls: list[str] = []
    # Fail specifically when constructed with the Hinglish dir; base must still load.
    _install_fake_whisper(monkeypatch, calls, fail_on=str(d))
    monkeypatch.setenv("HINGLISH_STT", "1")
    monkeypatch.setenv("HINGLISH_WHISPER_DIR", str(d))
    engine = vs._get_stt()
    assert engine is not None and engine[0] == "whisper"
    assert calls == ["base"]  # hinglish raised -> base loaded


# --- web-call local fallback (Phase 2) -------------------------------------- #


def test_web_local_stt_disabled_returns_empty(monkeypatch):
    """HINGLISH_STT off -> web-call local fallback is a no-op (current behaviour)."""
    import asyncio

    from app.api import web_call

    monkeypatch.delenv("HINGLISH_STT", raising=False)
    assert asyncio.run(web_call._local_whisper_transcribe(b"\x00\x01")) == ""


def test_web_local_stt_enabled_uses_model(monkeypatch):
    """HINGLISH_STT=1 -> reuses the phone path's cached whisper model on web audio."""
    import asyncio

    from app.api import web_call

    monkeypatch.setenv("HINGLISH_STT", "1")

    class _Seg:
        def __init__(self, t: str) -> None:
            self.text = t

    class _FakeModel:
        def transcribe(self, audio, **kw):
            return ([_Seg("haan ji"), _Seg("boliye")], {})

    monkeypatch.setattr(vs, "_get_stt", lambda: ("whisper", _FakeModel()))
    out = asyncio.run(web_call._local_whisper_transcribe(b"\x00\x01"))
    assert out == "haan ji boliye"


def test_web_local_first_short_circuits_cloud(monkeypatch):
    """WEBCALL_STT_LOCAL_FIRST=1 -> local Hinglish runs PRIMARY, cloud skipped."""
    import asyncio
    import base64

    from app.api import web_call

    monkeypatch.setenv("WEBCALL_STT_LOCAL_FIRST", "1")
    monkeypatch.setenv("HINGLISH_STT", "1")

    async def _fake_local(audio):
        return "namaste ji"

    monkeypatch.setattr(web_call, "_local_whisper_transcribe", _fake_local)
    audio_b64 = base64.b64encode(b"\x00\x01\x02\x03").decode()
    out = asyncio.run(web_call._transcribe_audio(None, None, audio_b64))
    assert out == "namaste ji"
