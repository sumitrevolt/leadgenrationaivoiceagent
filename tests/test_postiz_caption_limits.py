"""Per-platform caption truncation for Postiz publish (X 280-char guard)."""

from __future__ import annotations

from app.marketing.postiz_publish import _caption_limit


def test_x_caption_limit():
    assert _caption_limit("x") == 280
    assert _caption_limit("twitter") == 280


def test_longer_platform_limits():
    assert _caption_limit("instagram") == 2200
    assert _caption_limit("linkedin") == 3000
    assert _caption_limit("facebook") == 5000
    assert _caption_limit("youtube") == 5000


def test_unknown_platform_falls_back_to_2000():
    assert _caption_limit("") == 2000
    assert _caption_limit("unknown") == 2000
    assert _caption_limit("X".upper()) == 280  # case-insensitive
