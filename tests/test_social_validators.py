"""Loop-social-10 (2026-07-11): platform-adaptation validators.

Contract:
- `validate_post(platform, post)` returns list of issues (error+warn), never
  raises.
- Per-platform: caption length cap, hashtag count cap, media-type support,
  Instagram/YouTube require media, prohibited-claim scan, sponsored-disclosure
  check, injection-char detection, duplicate-content check.
- `has_blocking_error(issues)` = True iff any severity=error.
"""

from __future__ import annotations

import pytest

from app.social_engine import validators as v


def test_clean_post_no_issues():
    issues = v.validate_post("facebook", {"caption": "hello world", "media_type": "text"})
    assert issues == []
    assert v.has_blocking_error(issues) is False


def test_caption_too_long_for_x():
    issues = v.validate_post("x", {"caption": "a" * 300, "media_type": "text"})
    errs = [i for i in issues if i["rule"] == "caption_length"]
    assert errs and errs[0]["severity"] == "error"
    assert v.has_blocking_error(issues) is True


def test_hashtag_over_instagram_limit():
    issues = v.validate_post(
        "instagram",
        {
            "caption": "hi",
            "media_type": "image",
            "hashtags": ["t" + str(i) for i in range(50)],
        },
    )
    errs = [i for i in issues if i["rule"] == "hashtag_limit"]
    assert errs and errs[0]["severity"] == "error"


def test_youtube_requires_media():
    issues = v.validate_post("youtube", {"caption": "hi", "media_type": "text"})
    assert v.has_blocking_error(issues) is True
    assert any(i["rule"] == "missing_media" for i in issues)


def test_instagram_requires_media():
    issues = v.validate_post("instagram", {"caption": "hi", "media_type": "text"})
    assert v.has_blocking_error(issues) is True


def test_gbp_rejects_video():
    issues = v.validate_post("gbp", {"caption": "hi", "media_type": "video"})
    assert any(i["rule"] == "unsupported_media" and i["severity"] == "error" for i in issues)


def test_prohibited_claim_is_warn_not_block():
    issues = v.validate_post(
        "facebook",
        {
            "caption": "100% safe cure for diabetes — GUARANTEED results!",
            "media_type": "text",
        },
    )
    assert any(i["rule"] == "prohibited_claims" for i in issues)
    # It's a warn (context could qualify), so it does not block.
    assert v.has_blocking_error([i for i in issues if i["rule"] == "prohibited_claims"]) is False


def test_sponsored_missing_disclaimer_is_error():
    issues = v.validate_post(
        "instagram",
        {
            "caption": "Check out this amazing product!",
            "media_type": "image",
            "content_type": "sponsored",
        },
    )
    assert any(i["rule"] == "missing_disclaimer" and i["severity"] == "error" for i in issues)


def test_sponsored_with_ad_hashtag_passes():
    issues = v.validate_post(
        "instagram",
        {
            "caption": "Check out this amazing product! #ad",
            "media_type": "image",
            "content_type": "sponsored",
            "hashtags": ["ad"],
        },
    )
    assert not any(i["rule"] == "missing_disclaimer" for i in issues)


def test_zero_width_injection_flagged_as_warn():
    # Zero-width joiner injected mid-word.
    issues = v.validate_post("facebook", {"caption": "hi​there", "media_type": "text"})
    assert any(i["rule"] == "unsupported_characters" for i in issues)
    assert not v.has_blocking_error([i for i in issues if i["rule"] == "unsupported_characters"])


def test_duplicate_content_detected_with_recent_list():
    issues = v.validate_post(
        "facebook",
        {"caption": "Diwali offer 30% off!", "media_type": "text"},
        recent_captions=["diwali offer 30% off!"],  # case+normalized match
    )
    assert any(i["rule"] == "duplicate_content" for i in issues)


def test_engine_dispatch_blocks_on_validation_error(monkeypatch, tmp_path):
    """End-to-end: an over-length X caption results in a validation-branded
    error from _dispatch_one instead of hitting provider.publish()."""
    import asyncio

    from app.social_engine import engine, store, vault
    from app.social_engine.base import PublishResult, SocialProvider

    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "tokens.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.delenv("SOCIAL_DRY_RUN", raising=False)
    monkeypatch.delenv("SOCIAL_PAUSED_PLATFORMS", raising=False)

    class _P(SocialProvider):
        name = "x"
        publish_calls = 0

        def configured(self, account=None):
            return True

        async def publish(self, req, account):
            self.publish_calls += 1
            return PublishResult(ok=True, platform="x", post_id="X")

    prov = _P()
    monkeypatch.setattr(engine, "_REGISTRY", {"x": prov})

    engine.enqueue_publish("c1", caption="a" * 300, platforms=["x"])
    out = asyncio.run(engine.process_queue())
    assert out["published"] == 0
    assert prov.publish_calls == 0
    # Went to retry (or dead if attempts overshot). Either way not "published".
    assert out["retried"] + out["dead"] + out["skipped"] >= 1
