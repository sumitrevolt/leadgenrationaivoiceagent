"""Platform output profiles — render only ratios needed by connected channels."""

from __future__ import annotations

from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "9:16": {
        "width": 720,
        "height": 1280,
        "label": "vertical_short",
        "platforms": ("ig_reels", "yt_shorts", "fb_reels"),
    },
    "1:1": {
        "width": 1080,
        "height": 1080,
        "label": "square_feed",
        "platforms": ("ig_feed", "fb_feed"),
    },
    "16:9": {"width": 1280, "height": 720, "label": "landscape", "platforms": ("yt", "linkedin")},
}

# Safe defaults when tenant channel list unknown — one vertical reel only.
DEFAULT_RATIOS = ("9:16",)


def ratios_for_channels(channels: list[str] | None) -> list[str]:
    ch = {str(c or "").lower() for c in (channels or [])}
    if not ch or ch <= {"share", "postiz"}:
        return list(DEFAULT_RATIOS)
    out: list[str] = []
    for ratio, meta in PROFILES.items():
        plats = set(meta["platforms"])
        if ch & plats or "postiz" in ch:
            out.append(ratio)
    return out or list(DEFAULT_RATIOS)


def resolve_profile(ratio: str = "9:16") -> dict[str, Any]:
    return dict(PROFILES.get(ratio) or PROFILES["9:16"])


__all__ = ["PROFILES", "DEFAULT_RATIOS", "ratios_for_channels", "resolve_profile"]
