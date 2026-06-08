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
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


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
    ``smart-turn-v3.2-cpu`` ONNX) if pipecat is installed. Until the standalone
    inference call is verified against the installed pipecat version (do it while
    wiring the pipecat pipeline + testing on the web-call), this stays disabled
    and returns ``None`` so the silence-timer logic is used. See
    ``docs/Efficiency_Repos_Integration.md`` for the wiring plan.
    """

    def __init__(self) -> None:
        self._enabled = _flag("USE_SMART_TURN")
        self._loaded = False
        self._broken = False
        self._analyzer = None

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
            logger.info("SmartTurnDetector: analyzer loaded")
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
        """True if the caller's turn looks complete; None when disabled/uncertain.

        NOTE: the exact BaseSmartTurn inference call is finalised when pipecat is
        wired (it is designed to run inside pipecat's pipeline). Standalone use is
        intentionally conservative here — returns None until verified.
        """
        if not self._ensure():
            return None
        return None  # verified-and-enabled while wiring the pipecat pipeline


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


__all__ = [
    "SileroSpeechGate",
    "SmartTurnDetector",
    "get_speech_gate",
    "get_smart_turn",
    "confirm_end_of_turn",
]
