"""Shared resolvers for the A9 call-recording stores.

Two manifest stores, three on-disk directories:

  * artifacts.call_recordings
      - data/call_recordings/   → artifacts/call_recordings/
      - data/call_transcripts/  → artifacts/call_transcripts/
  * telephony.call_recordings
      - data/recordings/        → telephony/recordings/
        (RECORDINGS_DIR override — already used by voice_launch)

Resolved per call via ``resolve_store_path``. Nothing here copies bytes or
flips dial/voice flags — path authority only. Keep LEGACY when the runtime
root is unset.
"""

from __future__ import annotations

from pathlib import Path


def call_recordings_dir() -> Path:
    """Mixed conversation WAVs (vobiz / web-call uploads)."""
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="artifacts.call_recordings",
        legacy_path=Path("data") / "call_recordings",
        target_segments=("artifacts", "call_recordings"),
    )


def call_transcripts_dir() -> Path:
    """Per-day JSONL transcripts (training / insights fuel)."""
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="artifacts.call_recordings",
        legacy_path=Path("data") / "call_transcripts",
        target_segments=("artifacts", "call_transcripts"),
    )


def telephony_recordings_dir() -> Path:
    """Retention-governed telephony recordings (RECORDINGS_DIR override)."""
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="telephony.call_recordings",
        legacy_path=Path("data") / "recordings",
        target_segments=("telephony", "recordings"),
        override_env="RECORDINGS_DIR",
    )


__all__ = [
    "call_recordings_dir",
    "call_transcripts_dir",
    "telephony_recordings_dir",
]
