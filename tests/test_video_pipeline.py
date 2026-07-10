"""video_pipeline — staged renderer replacing reel_video's flat PIL-slide
template for video_ad_cycle. Phase 1 = generic recipe only (see
docs/superpowers/plans/2026-07-10-product-one-video-creative-pipeline-phase1.md).
Heavy ffmpeg/EdgeTTS stubbed in unit tests (matches test_video_ad_cycle.py's
"mock one level above the heavy call" convention)."""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile

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


def test_logo_temp_file_decodes_data_uri():
    # 1x1 red PNG, base64-encoded
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFBQIA"
        "X8jx0gAAAABJRU5ErkJggg=="
    )
    uri = f"data:image/png;base64,{png_b64}"
    with tempfile.TemporaryDirectory() as tmp:
        path = video_pipeline._logo_temp_file(uri, tmp)
        assert path is not None
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0


def test_logo_temp_file_returns_none_for_empty():
    with tempfile.TemporaryDirectory() as tmp:
        assert video_pipeline._logo_temp_file("", tmp) is None
        assert video_pipeline._logo_temp_file("not-a-data-uri", tmp) is None


def test_make_branded_frame_writes_png():
    brand = {
        "business_name": "Sharma Solar", "phone": "9876543210",
        "primary": "#2563eb", "accent": "#f59e0b", "logo_data_uri": "",
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = video_pipeline._make_branded_frame("Aapka Business — Solar expert", 0, brand, tmp)
        assert os.path.exists(path)
        from PIL import Image

        img = Image.open(path)
        assert img.size == (720, 1280)
        img.close()
