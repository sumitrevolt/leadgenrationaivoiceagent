"""Optional turn-taking upgrades on top of the energy-RMS VAD in
``app/telephony/vobiz_stream.py``.

Why: the call loop currently decides "user spoke" from raw PCM16 RMS
(``VOBIZ_VAD_RMS``) and ends a turn after ``VOBIZ_SILENCE_MS`` of trailing
silence. That crude gate false-triggers on line noise/echo and clips callers
who pause mid-sentence. Two free, CPU-only, open-source models fix this:

  * **Silero VAD** (snakers4/silero-vad, MIT) — robust speech/non-speech gate.
    2MB ONNX, <1ms per 32ms frame on CPU. Implemented here.
  * **Smart Turn v3** (pipecat-ai/smart-turn-v3, open weights) — *semantic*
    end-of-turn detection (knows the caller actually FINISHED vs just paused),
    8MB int8 ONNX, ~12ms CPU, Hindi supported. Recommended next step via the
    existing pipecat skeleton — see ``get_smart_turn()`` below and
    ``docs/Efficiency_Repos_Integration.md``.

Design rules (match the rest of the voice agent):
  * OFF by default. Enable per detector via env once installed + tested on the
    FREE web-call (``leadsgenai.in/app/test-call``) — never first on a paid call.
  * Never raise. Any missing dep / load error / inference error disables the
    detector permanently and returns ``None`` so the caller falls back to the
    existing energy + silence-timer logic. Zero behaviour change unless enabled.

Env flags:
  USE_SILERO_VAD=1        # turn on the Silero speech gate
  SILERO_VAD_THRESHOLD    # speech probability threshold (default 0.5)
  USE_SMART_TURN=1        # turn on Smart Turn v3 end-of-turn (needs pipecat)
  SMART_TURN_MODEL_PATH   # optional path to a local smart-turn ONNX model
  SMART_TURN_THRESHOLD    # endpoint probability >= this == "turn complete" (default 0.55)

Shared turn-taking knobs (read by the stream files + pipeline so a single env
controls every audio path; sane defaults keep prod identical until set):
  TURN_SILENCE_MS         # trailing silence that ends a turn (default 700 ms)
  TURN_VAD_RMS            # PCM16 RMS speech gate (default 300)
  TURN_BARGE_MIN_MS       # speech-over-bot before barge-in fires (default 100 ms)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """float(env[name]) with a safe fallback — a bad value never breaks import
    or a call. Shared by every voice path so one env tunes turn-taking globally."""
    try:
        raw = os.getenv(name, "")
        return float(raw) if raw.strip() != "" else float(default)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        raw = os.getenv(name, "")
        return int(float(raw)) if raw.strip() != "" else int(default)
    except Exception:
        return int(default)


def _pcm16_to_float32(pcm16: bytes):
    """PCM16 little-endian bytes -> mono float32 numpy in [-1, 1]. None on failure."""
    try:
        import numpy as np

        if not pcm16:
            return None
        arr = np.frombuffer(pcm16, dtype="<i2").astype("float32") / 32768.0
        return arr
    except Exception:  # numpy missing / odd buffer length
        return None


class SileroSpeechGate:
    """Robust speech/non-speech gate using Silero VAD.

    Drop-in companion to the RMS gate: ``is_speech(pcm16_16k)`` returns True/False
    when active, or ``None`` when disabled/unavailable (caller uses RMS instead).
    """

    def __init__(self) -> None:
        self._enabled = _flag("USE_SILERO_VAD")
        self._loaded = False
        self._broken = False
        self._model = None
        self._get_ts = None
        try:
            self._threshold = float(os.getenv("SILERO_VAD_THRESHOLD", "0.5"))
        except Exception:
            self._threshold = 0.5

    def _ensure(self) -> bool:
        if not self._enabled or self._broken:
            return False
        if self._loaded:
            return self._model is not None
        self._loaded = True
        try:
            from silero_vad import load_silero_vad, get_speech_timestamps

            # onnx=True keeps it light; silero-vad pulls torch as a dependency.
            self._model = load_silero_vad(onnx=True)
            self._get_ts = get_speech_timestamps
            logger.info("SileroSpeechGate: model loaded (threshold=%.2f)", self._threshold)
            return True
        except Exception as exc:  # dep missing or load failure -> disable forever
            self._broken = True
            self._model = None
            logger.info("SileroSpeechGate disabled (load failed: %s)", exc)
            return False

    @property
    def active(self) -> bool:
        return self._ensure()

    def is_speech(self, pcm16: bytes, sample_rate: int = 16000) -> Optional[bool]:
        """True/False if active; None if disabled/unavailable/error (use RMS)."""
        if not self._ensure():
            return None
        try:
            import torch

            audio = _pcm16_to_float32(pcm16)
            if audio is None or len(audio) < 512:
                return None
            ts = self._get_ts(
                torch.from_numpy(audio),
                self._model,
                sampling_rate=sample_rate,
                threshold=self._threshold,
            )
            return len(ts) > 0
        except Exception as exc:
            # one bad frame shouldn't kill the call; degrade to RMS for this turn
            logger.debug("SileroSpeechGate.is_speech error: %s", exc)
            return None


class SmartTurnDetector:
    """Semantic end-of-turn detector (pipecat-ai smart-turn-v3).

    EXPERIMENTAL / opt-in. Loads pipecat's ``LocalSmartTurnAnalyzerV3`` (bundled
    ``smart-turn-v3.2-cpu`` ONNX) when pipecat is installed AND ``USE_SMART_TURN=1``.
    Disabled (or any load/inference failure) -> ``is_endpoint`` returns ``None`` so
    the silence-timer decides. The standalone call binds the model's private
    ``_predict_endpoint`` (ONNX sigmoid head) — pipecat normally drives it inside
    its pipeline, but the head itself is a pure ``float32 -> probability`` fn.
    """

    def __init__(self) -> None:
        self._enabled = _flag("USE_SMART_TURN")
        self._loaded = False
        self._broken = False
        self._analyzer = None
        self._predict = None  # bound standalone inference fn (set on load)
        # Endpoint probability at/above which we trust "turn complete". 0.55 is
        # deliberately a touch above 0.5 so a borderline pause keeps listening.
        self._threshold = _env_float("SMART_TURN_THRESHOLD", 0.55)

    def _ensure(self) -> bool:
        if not self._enabled or self._broken:
            return False
        if self._loaded:
            return self._analyzer is not None
        self._loaded = True
        try:
            from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
                LocalSmartTurnAnalyzerV3,
            )

            path = os.getenv("SMART_TURN_MODEL_PATH") or None
            self._analyzer = LocalSmartTurnAnalyzerV3(smart_turn_model_path=path)
            # smart-turn-v3 exposes a private ``_predict_endpoint(np_float32_16k)``
            # that runs the ONNX session directly and returns a dict with a
            # sigmoid ``probability`` — perfect for our standalone (no-pipeline)
            # call. Bind it if present; otherwise stay conservative (predict=None
            # -> is_endpoint returns None -> silence-timer decides).
            self._predict = getattr(self._analyzer, "_predict_endpoint", None)
            logger.info(
                "SmartTurnDetector: analyzer loaded (threshold=%.2f, predict=%s)",
                self._threshold,
                self._predict is not None,
            )
            return True
        except Exception as exc:
            self._broken = True
            self._analyzer = None
            logger.info("SmartTurnDetector disabled (load failed: %s)", exc)
            return False

    @property
    def active(self) -> bool:
        return self._ensure()

    def is_endpoint(self, pcm16: bytes, sample_rate: int = 16000) -> Optional[bool]:
        """True if the caller's turn looks complete, False if they only paused
        mid-sentence, None when disabled/unavailable/uncertain (silence-timer decides).

        Runs smart-turn-v3's ONNX endpoint head on the trailing audio. The model
        wants mono float32 @ 16 kHz; 8 kHz phone audio is upsampled (cheap). ANY
        failure degrades to None so a bad frame can never end/hold a turn wrongly.
        """
        if not self._ensure() or self._predict is None:
            return None
        try:
            import numpy as np

            audio = _pcm16_to_float32(pcm16)
            if audio is None or len(audio) < 1600:  # <100 ms @16k — too little to judge
                return None
            if sample_rate and sample_rate != 16000:
                # linear-interp resample to 16k (feature extractor's rate). Crude
                # but adequate — the model classifies prosody, not exact samples.
                ratio = 16000.0 / float(sample_rate)
                n_out = int(len(audio) * ratio)
                if n_out < 1600:
                    return None
                xp = np.arange(len(audio), dtype="float32")
                x = np.linspace(0.0, len(audio) - 1, n_out, dtype="float32")
                audio = np.interp(x, xp, audio).astype("float32")
            res = self._predict(audio)
            prob = None
            if isinstance(res, dict):
                prob = res.get("probability")
                if prob is None and "prediction" in res:
                    # some builds return only a 0/1 prediction
                    return bool(res.get("prediction"))
            if prob is None:
                return None
            return float(prob) >= self._threshold
        except Exception as exc:
            logger.debug("SmartTurnDetector.is_endpoint error: %s", exc)
            return None


_speech_gate: Optional[SileroSpeechGate] = None
_smart_turn: Optional[SmartTurnDetector] = None


def get_speech_gate() -> SileroSpeechGate:
    """Process-wide Silero speech gate (lazy singleton)."""
    global _speech_gate
    if _speech_gate is None:
        _speech_gate = SileroSpeechGate()
    return _speech_gate


def get_smart_turn() -> SmartTurnDetector:
    """Process-wide Smart Turn detector (lazy singleton)."""
    global _smart_turn
    if _smart_turn is None:
        _smart_turn = SmartTurnDetector()
    return _smart_turn


def confirm_end_of_turn(silence_ended: bool, pcm16: bytes = b"", sample_rate: int = 16000) -> bool:
    """Combine the silence-timer end-of-turn with the Smart Turn v3 semantic check.

    ``silence_ended=False`` -> caller still talking, return False. ``silence_ended=True``
    -> Smart Turn (USE_SMART_TURN=1) se poochho: agar woh kahe turn ABHI complete nahi
    (caller ne sochne ko pause liya) to False (sun-te raho, beech me mat toko); complete
    ya uncertain/disabled (None) to silence-timer honor karo -> True. Never raises.
    """
    if not silence_ended:
        return False
    try:
        ep = get_smart_turn().is_endpoint(pcm16, sample_rate=sample_rate)
        if ep is False:
            return False  # semantic: mid-sentence pause -> keep listening
    except Exception:
        pass
    return True


# --------------------------------------------------------------------------- #
# Shared turn-taking knobs — ONE place every audio path reads, so a single env
# tunes end-of-turn snappiness across vobiz_stream (16k), phone_stream (8k) and
# the text/web pipeline. Defaults reproduce the previous hard-coded behaviour
# (silence 700 ms, RMS 300, barge-in ~100 ms), so prod is unchanged until set.
# --------------------------------------------------------------------------- #
def turn_silence_ms(default: float = 700.0) -> float:
    """Trailing silence (ms) that ends a user turn. Env: TURN_SILENCE_MS.
    Lower = snappier (risk: clip a slow talker); higher = safer but laggier.
    ~500-800 ms is the human-feeling sweet spot."""
    return _env_float("TURN_SILENCE_MS", default)


def turn_vad_rms(default: int = 300) -> int:
    """PCM16 RMS above which a frame counts as speech. Env: TURN_VAD_RMS.
    Higher on a noisy line (ignore hum); lower in a quiet studio."""
    return _env_int("TURN_VAD_RMS", default)


def barge_in_ms(default: float = 100.0) -> float:
    """How long the caller must talk over the bot before barge-in fires (ms).
    Env: TURN_BARGE_MIN_MS. Lower = more eager cut-in (risk: own echo stops the
    bot); higher = bot less interruptible."""
    return _env_float("TURN_BARGE_MIN_MS", default)


def barge_in_frames(frame_ms: float, default_ms: float = 100.0) -> int:
    """barge_in_ms() converted to a count of ``frame_ms``-long frames (min 1).
    Callers tick per inbound frame, so they want a frame count not a duration."""
    ms = barge_in_ms(default_ms)
    try:
        return max(1, int(round(ms / float(frame_ms)))) if frame_ms > 0 else 1
    except Exception:
        return max(1, int(default_ms / 20.0))


__all__ = [
    "SileroSpeechGate",
    "SmartTurnDetector",
    "get_speech_gate",
    "get_smart_turn",
    "confirm_end_of_turn",
    "turn_silence_ms",
    "turn_vad_rms",
    "barge_in_ms",
    "barge_in_frames",
]
