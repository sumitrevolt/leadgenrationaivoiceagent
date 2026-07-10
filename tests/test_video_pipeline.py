"""video_pipeline — staged renderer replacing reel_video's flat PIL-slide
template for video_ad_cycle. Phase 1 = generic recipe only (see
docs/superpowers/plans/2026-07-10-product-one-video-creative-pipeline-phase1.md).
Heavy ffmpeg/EdgeTTS stubbed in unit tests (matches test_video_ad_cycle.py's
"mock one level above the heavy call" convention)."""

from __future__ import annotations

import asyncio

from app.marketing import video_pipeline


def test_render_creative_video_delegates_to_reel_video(monkeypatch):
    async def _fake_build_reel(**kw):
        return {"path": "data/reels/fake.mp4", "slides": kw.get("slides"), "size_kb": 1}

    from app.marketing import reel_video

    monkeypatch.setattr(reel_video, "build_reel", _fake_build_reel)

    result = asyncio.run(
        video_pipeline.render_creative_video(
            business_name="Sharma Solar", niche="solar", slides=["a", "b"], offer="20% off", client_id="c1"
        )
    )
    assert result["path"] == "data/reels/fake.mp4"
    assert result["slides"] == ["a", "b"]


def test_render_creative_video_propagates_error(monkeypatch):
    async def _fake_build_reel(**kw):
        return {"error": "ffmpeg missing"}

    from app.marketing import reel_video

    monkeypatch.setattr(reel_video, "build_reel", _fake_build_reel)

    result = asyncio.run(video_pipeline.render_creative_video(business_name="X"))
    assert result["error"] == "ffmpeg missing"
