"""Public authority for media size and disk-headroom limits.

One place both the upload path and the snapshot path can consume. Previously
`snapshot.py` imported `contentplus._UPLOAD_MAX_BYTES` (a private API constant)
and documented `staff.py`'s alert threshold as its source — reaching across
modules into private state, and leaving two copies free to drift.

Ceilings are ADMISSION limits: a value here is the most that may be accepted,
never a licence to accept more.
"""

from __future__ import annotations

import os

# Canonical video upload ceiling. `app/api/contentplus.py` now CONSUMES this
# (its `_UPLOAD_MAX_BYTES` is a compatibility alias, not a second definition),
# so there is one value, not two that happen to agree.
_UPLOAD_MAX_BYTES_DEFAULT = 200 * 1024 * 1024  # 200 MB

# Free-space floor, as a percentage of the destination filesystem. Matches the
# threshold the platform health agent already alarms on, so writing media can
# never be the thing that drives the box into its own disk alert.
_MIN_FREE_PCT_DEFAULT = 10.0


class MediaLimitConfigError(ValueError):
    """Configuration is out of contract — callers must fail closed."""


def _int_env(name: str, *, low: int, high: int) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise MediaLimitConfigError(f"{name} not an integer: {raw!r}") from exc
    if not low <= value <= high:
        raise MediaLimitConfigError(f"{name} out of range {low}..{high}: {value}")
    return value


def max_upload_bytes() -> int:
    """Canonical maximum for any accepted media artifact."""
    mb = _int_env("MEDIA_UPLOAD_MAX_MB", low=1, high=2048)
    return mb * 1024 * 1024 if mb is not None else _UPLOAD_MAX_BYTES_DEFAULT


def max_snapshot_bytes() -> int:
    """Snapshot admission ceiling — may EQUAL or LOWER the upload ceiling.

    ``VIDEO_SNAPSHOT_MAX_MB`` can only tighten. An override above the canonical
    upload cap is a configuration error, not a silent contract expansion: the
    snapshot must never admit an artifact the upload path would have rejected.
    """
    ceiling = max_upload_bytes()
    mb = _int_env("VIDEO_SNAPSHOT_MAX_MB", low=1, high=2048)
    if mb is None:
        return ceiling
    requested = mb * 1024 * 1024
    if requested > ceiling:
        raise MediaLimitConfigError(
            f"VIDEO_SNAPSHOT_MAX_MB ({mb} MB) exceeds the canonical upload "
            f"ceiling ({ceiling // (1024 * 1024)} MB); snapshot may only tighten"
        )
    return requested


def min_free_percent() -> float:
    """Free-space floor that must survive the write."""
    raw = os.getenv("VIDEO_SNAPSHOT_MIN_FREE_PCT", "").strip()
    if not raw:
        return _MIN_FREE_PCT_DEFAULT
    try:
        pct = float(raw)
    except ValueError as exc:
        raise MediaLimitConfigError(f"VIDEO_SNAPSHOT_MIN_FREE_PCT not a number: {raw!r}") from exc
    if not 1.0 <= pct <= 90.0:
        raise MediaLimitConfigError(f"VIDEO_SNAPSHOT_MIN_FREE_PCT out of range 1..90: {pct}")
    return pct


__all__ = [
    "MediaLimitConfigError",
    "max_snapshot_bytes",
    "max_upload_bytes",
    "min_free_percent",
]
