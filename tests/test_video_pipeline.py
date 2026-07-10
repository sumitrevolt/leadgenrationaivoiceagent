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


def test_render_creative_video_success(monkeypatch, tmp_path):
    from app.marketing import reel_video

    monkeypatch.setattr(reel_video, "available", lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True})

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))

    result = asyncio.run(
        video_pipeline.render_creative_video(
            business_name="Sharma Solar", niche="solar", slides=["a", "b"], offer="20% off", client_id="c1"
        )
    )
    assert "error" not in result
    assert result["path"].endswith(".mp4")
    assert os.path.exists(result["path"])


def _write_dummy_output(args: list[str]) -> bool:
    out_path = args[-1]
    with open(out_path, "wb") as f:
        f.write(b"x" * 500)
    return True


def test_render_creative_video_ffmpeg_missing(monkeypatch):
    from app.marketing import reel_video

    monkeypatch.setattr(reel_video, "available", lambda: {"ffmpeg": False, "pillow": True, "edge_tts": True, "ok": False})

    result = asyncio.run(video_pipeline.render_creative_video(business_name="X"))
    assert "error" in result


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


def test_zoompan_filter_has_expected_shape():
    f = video_pipeline._zoompan_filter(4.0, fps=24)
    assert "zoompan" in f
    assert "d=96" in f  # 4.0s * 24fps
    assert "s=720x1280" in f


def test_build_segment_args_with_audio():
    args = video_pipeline._build_segment_args("frame.png", "audio.mp3", 5.0, "seg.mp4")
    assert args[:4] == ["-loop", "1", "-i", "frame.png"]
    assert "-i" in args and "audio.mp3" in args
    assert "-shortest" in args
    assert args[-1] == "seg.mp4"


def test_build_segment_args_without_audio():
    args = video_pipeline._build_segment_args("frame.png", None, 4.0, "seg.mp4")
    assert "-shortest" not in args
    assert args[-1] == "seg.mp4"


def test_music_bed_path_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(video_pipeline, "_MUSIC_DIR", str(tmp_path))
    assert video_pipeline._music_bed_path("solar") is None


def test_music_bed_path_prefers_niche_specific(monkeypatch, tmp_path):
    (tmp_path / "generic.mp3").write_bytes(b"x")
    (tmp_path / "solar.mp3").write_bytes(b"x")
    monkeypatch.setattr(video_pipeline, "_MUSIC_DIR", str(tmp_path))
    assert video_pipeline._music_bed_path("solar").endswith("solar.mp3")


def test_music_bed_path_falls_back_to_generic(monkeypatch, tmp_path):
    (tmp_path / "generic.mp3").write_bytes(b"x")
    monkeypatch.setattr(video_pipeline, "_MUSIC_DIR", str(tmp_path))
    assert video_pipeline._music_bed_path("solar").endswith("generic.mp3")


def test_mix_music_args_shape():
    args = video_pipeline._mix_music_args("video.mp4", "bed.mp3", "out.mp4")
    assert "video.mp4" in args and "bed.mp3" in args
    assert args[-1] == "out.mp4"


def test_render_creative_video_ships_without_music_on_mix_failure(monkeypatch, tmp_path):
    from app.marketing import reel_video

    monkeypatch.setattr(reel_video, "available", lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True})

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(video_pipeline, "_music_bed_path", lambda niche: "data/music_beds/generic.mp3")

    calls = {"n": 0}

    def _fake_ffmpeg(args):
        calls["n"] += 1
        if "-filter_complex" in args:  # the music-mix call — force it to fail
            return False
        return _write_dummy_output(args)

    monkeypatch.setattr(reel_video, "_ffmpeg", _fake_ffmpeg)
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))

    result = asyncio.run(video_pipeline.render_creative_video(business_name="X", slides=["a"]))
    assert "error" not in result
    assert os.path.exists(result["path"])
