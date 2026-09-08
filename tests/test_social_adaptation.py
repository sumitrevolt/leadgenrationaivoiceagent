"""Loop-social-15 (2026-07-11): platform-specific post adaptation.

Contract:
- adapt_for_platform NEVER mutates the input dict.
- Instagram: URLs stripped → "Link in bio" note appended; hashtag tail up to 30
  merged into caption.
- X: long text split into thread parts with "(k/n)" suffixes.
- GBP: hashtags removed entirely; caption truncated to 1500.
- LinkedIn: hashtag tail limited to 5 (algorithm pref).
- YouTube: description = caption + up to 15 tags.
- Facebook: pass-through with hashtag tail up to 10.
- WhatsApp: caption + tail up to 5.
- Never raises.
"""

from __future__ import annotations

import pytest

from app.social_engine import adaptation as adp


def test_no_mutation_of_input():
    post = {"caption": "hi", "hashtags": ["diwali", "sale"]}
    _ = adp.adapt_for_platform(post, "instagram")
    assert post == {"caption": "hi", "hashtags": ["diwali", "sale"]}


def test_instagram_strips_url_and_adds_link_in_bio():
    post = {
        "caption": "Diwali sale https://shop.example.com — check it out!",
        "hashtags": ["diwali"],
    }
    out = adp.adapt_for_platform(post, "instagram")
    assert "https://" not in out["caption"]
    assert "link in bio" in out["caption"].lower()
    assert "#diwali" in out["caption"]
    assert out["_adapted"] == "instagram"


def test_instagram_hashtag_tail_cap_30():
    tags = [f"t{i}" for i in range(50)]
    post = {"caption": "hi", "hashtags": tags}
    out = adp.adapt_for_platform(post, "instagram")
    assert out["caption"].count("#") == 30


def test_x_short_caption_passes_through():
    post = {"caption": "Quick tweet.", "hashtags": ["sale"]}
    out = adp.adapt_for_platform(post, "x")
    assert out["caption"].startswith("Quick tweet.")
    assert out.get("extra", {}).get("thread_parts") is None


def test_x_long_caption_thread_split():
    long_text = " ".join(["word"] * 200)  # ~1000 chars
    post = {"caption": long_text, "hashtags": []}
    out = adp.adapt_for_platform(post, "x")
    parts = out.get("extra", {}).get("thread_parts") or []
    assert len(parts) > 1
    assert "(1/" in parts[0]


def test_gbp_removes_hashtags():
    post = {"caption": "Store open", "hashtags": ["sale", "offer"]}
    out = adp.adapt_for_platform(post, "gbp")
    assert out["hashtags"] == []
    assert "#" not in out["caption"]


def test_gbp_truncates_over_1500():
    post = {"caption": "a" * 2000, "hashtags": []}
    out = adp.adapt_for_platform(post, "gbp")
    assert len(out["caption"]) <= 1500


def test_linkedin_caps_hashtags_at_5():
    tags = [f"t{i}" for i in range(20)]
    post = {"caption": "professional post", "hashtags": tags}
    out = adp.adapt_for_platform(post, "linkedin")
    assert out["caption"].count("#") == 5


def test_youtube_description_includes_up_to_15_tags():
    tags = [f"t{i}" for i in range(30)]
    post = {"caption": "video", "hashtags": tags}
    out = adp.adapt_for_platform(post, "youtube")
    assert out["caption"].count("#") == 15


def test_facebook_pass_through_10_tags():
    tags = [f"t{i}" for i in range(30)]
    post = {"caption": "post", "hashtags": tags}
    out = adp.adapt_for_platform(post, "facebook")
    assert out["caption"].count("#") == 10


def test_unknown_platform_passes_through():
    post = {"caption": "test", "hashtags": ["x"]}
    out = adp.adapt_for_platform(post, "myspace")
    assert out["caption"] == "test"


def test_never_raises_on_bad_input():
    # Non-dict caption etc.
    out = adp.adapt_for_platform({"caption": None, "hashtags": None}, "instagram")
    assert isinstance(out, dict)
