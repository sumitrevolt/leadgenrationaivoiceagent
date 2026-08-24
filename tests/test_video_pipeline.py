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

import pytest

from app.marketing import video_pipeline


def test_render_creative_video_success(monkeypatch, tmp_path):
    from app.marketing import reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(video_pipeline, "_qa_check", lambda path, n, **kw: None)

    result = asyncio.run(
        video_pipeline.render_creative_video(
            business_name="Sharma Solar",
            niche="solar",
            slides=["a", "b"],
            offer="20% off",
            client_id="c1",
        )
    )
    assert "error" not in result
    assert result["path"].endswith(".mp4")
    assert os.path.exists(result["path"])


def test_render_ships_when_tts_fails(monkeypatch, tmp_path):
    """EdgeTTS is a network adapter — TTS failure must still yield a silent video."""
    from app.marketing import reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )

    async def _tts_fail(text, path):
        return False

    monkeypatch.setattr(reel_video, "_tts", _tts_fail)
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(video_pipeline, "_qa_check", lambda path, n, **kw: None)

    result = asyncio.run(
        video_pipeline.render_creative_video(business_name="X", slides=["silent slide"])
    )
    assert "error" not in result
    assert result["path"].endswith(".mp4")


def _write_dummy_output(args: list[str]) -> bool:
    out_path = args[-1]
    with open(out_path, "wb") as f:
        f.write(b"x" * 5000)
    return True


def test_render_creative_video_ffmpeg_missing(monkeypatch):
    from app.marketing import reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": False, "pillow": True, "edge_tts": True, "ok": False},
    )

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
        "business_name": "Sharma Solar",
        "phone": "9876543210",
        "primary": "#2563eb",
        "accent": "#f59e0b",
        "logo_data_uri": "",
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
    # d has a 30s floor (max(96, 720)=720) so the zoom holds at its 1.08 cap
    # instead of resetting mid-slide when TTS audio runs longer than 4s.
    assert "d=720" in f
    assert "s=720x1280" in f


def test_zoompan_filter_d_scales_above_floor():
    # A genuinely long segment (40s) should push d above the 30s*24fps=720
    # floor — proving d still scales UP for real long durations, not just
    # pinned at the floor.
    f = video_pipeline._zoompan_filter(40.0, fps=24)
    assert "d=960" in f  # 40.0s * 24fps = 960 > 720 floor


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

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(
        video_pipeline, "_music_bed_path", lambda niche: "data/music_beds/generic.mp3"
    )

    calls = {"n": 0}

    def _fake_ffmpeg(args):
        calls["n"] += 1
        if "-filter_complex" in args:  # the music-mix call — force it to fail
            return False
        return _write_dummy_output(args)

    monkeypatch.setattr(reel_video, "_ffmpeg", _fake_ffmpeg)
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(video_pipeline, "_qa_check", lambda path, n, **kw: None)

    result = asyncio.run(video_pipeline.render_creative_video(business_name="X", slides=["a"]))
    assert "error" not in result
    assert os.path.exists(result["path"])


def test_render_creative_video_music_mix_success_survives_remove_failure(monkeypatch, tmp_path):
    """Review fix #1: a successful music mix must still ship even if cleaning
    up the pre-mix file raises (e.g. a Windows file-lock on the old output).
    Pre-fix, the unguarded os.remove(out_path) propagates to the outer
    try/except and turns a successful render into {"error": ...}."""
    from app.marketing import reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(
        video_pipeline, "_music_bed_path", lambda niche: "data/music_beds/generic.mp3"
    )
    # Every ffmpeg call succeeds, including the music-mix call.
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(video_pipeline, "_qa_check", lambda path, n, **kw: None)

    def _raise_remove(path):
        raise OSError("simulated Windows file-lock on cleanup")

    monkeypatch.setattr(os, "remove", _raise_remove)

    result = asyncio.run(video_pipeline.render_creative_video(business_name="X", slides=["a"]))
    assert "error" not in result
    assert result["path"].endswith("_mix.mp4")
    assert os.path.exists(result["path"])


def test_music_bed_path_rejects_traversal_niche(monkeypatch, tmp_path):
    """Review fix #2: a path-traversal niche must never resolve to a file
    outside _MUSIC_DIR, even when a same-named file exists at the traversal
    target (mirrors the reviewer's own probe: "../_review_probe/secret")."""
    music_dir = tmp_path / "music_beds"
    music_dir.mkdir()
    monkeypatch.setattr(video_pipeline, "_MUSIC_DIR", str(music_dir))

    # Plant a file at the traversal target that an unsanitized os.path.join
    # WOULD resolve to and find.
    outside = tmp_path / "_review_probe"
    outside.mkdir()
    (outside / "secret.mp3").write_bytes(b"secret-audio")

    result = video_pipeline._music_bed_path("../_review_probe/secret")
    assert result is None
    assert result != str(outside / "secret.mp3")


def test_music_bed_path_normal_niche_unaffected_by_sanitizer(monkeypatch, tmp_path):
    """The safe-charset filter must be a no-op for ordinary niches like
    "solar" — exact path match, not just precedence."""
    (tmp_path / "solar.mp3").write_bytes(b"x")
    monkeypatch.setattr(video_pipeline, "_MUSIC_DIR", str(tmp_path))
    result = video_pipeline._music_bed_path("solar")
    assert result == os.path.join(str(tmp_path), "solar.mp3")


def test_qa_check_missing_file():
    assert video_pipeline._qa_check("does/not/exist.mp4", 3) is not None


def test_qa_check_passes_on_valid_probe(monkeypatch, tmp_path):
    p = tmp_path / "out.mp4"
    p.write_bytes(b"x" * 5000)

    def _fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = (
                b'{"format": {"duration": "12.0"}, "streams": [{"width": 720, "height": 1280}]}'
            )

        return R()

    monkeypatch.setattr(video_pipeline.subprocess, "run", _fake_run)
    assert video_pipeline._qa_check(str(p), 3) is None


def test_qa_check_accepts_short_valid_render(monkeypatch, tmp_path):
    """Review fix: a genuinely correct render with short slide text (e.g.
    "20% off") can legitimately land well under the old `expected_slide_count
    * 2.5` floor — EdgeTTS segments are built with -shortest and NO enforced
    minimum duration when audio succeeds (only the no-audio fallback path is
    a fixed 4.0s). duration=1.5 for 3 slides would have failed the OLD bound
    (needed >=7.5) but must pass the new flat floor (1.0)."""
    p = tmp_path / "out.mp4"
    p.write_bytes(b"x" * 5000)

    def _fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = b'{"format": {"duration": "1.5"}, "streams": [{"width": 720, "height": 1280}]}'

        return R()

    monkeypatch.setattr(video_pipeline.subprocess, "run", _fake_run)
    assert video_pipeline._qa_check(str(p), 3) is None


def test_qa_check_fails_on_near_zero_duration(monkeypatch, tmp_path):
    """The flat floor must still catch catastrophically broken output (a
    near-empty/corrupt file, a single frozen frame) — that's the actual
    purpose of the duration check, not enforcing a pacing assumption."""
    p = tmp_path / "out.mp4"
    p.write_bytes(b"x" * 5000)

    def _fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = b'{"format": {"duration": "0.1"}, "streams": [{"width": 720, "height": 1280}]}'

        return R()

    monkeypatch.setattr(video_pipeline.subprocess, "run", _fake_run)
    reason = video_pipeline._qa_check(str(p), 3)
    assert reason is not None and "duration" in reason


def test_qa_check_fails_on_wrong_resolution(monkeypatch, tmp_path):
    p = tmp_path / "out.mp4"
    p.write_bytes(b"x" * 5000)

    def _fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = (
                b'{"format": {"duration": "12.0"}, "streams": [{"width": 1080, "height": 1080}]}'
            )

        return R()

    monkeypatch.setattr(video_pipeline.subprocess, "run", _fake_run)
    reason = video_pipeline._qa_check(str(p), 3)
    assert reason is not None and "resolution" in reason


def test_render_creative_video_qa_failure_returns_error(monkeypatch, tmp_path):
    from app.marketing import reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        video_pipeline, "_qa_check", lambda path, n, **kw: "forced failure for test"
    )

    result = asyncio.run(video_pipeline.render_creative_video(business_name="X", slides=["a"]))
    assert result.get("error") == "qa_failed: forced failure for test"


def test_render_creative_video_survives_ledger_logging_failure(monkeypatch, tmp_path):
    """Review fix (Task 7): delivery_ledger.log_event is best-effort only —
    a logging failure must NEVER change the return value. Forces log_event
    to raise on every call (video_render_started AND the now-reordered,
    post-dict-build video_ready call) and asserts the render still returns
    success with no "error" key."""
    from app.marketing import delivery_ledger, reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(video_pipeline, "_qa_check", lambda path, n, **kw: None)

    calls = {"n": 0}

    def _raise_log_event(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("simulated ledger write failure")

    monkeypatch.setattr(delivery_ledger, "log_event", _raise_log_event)

    result = asyncio.run(
        video_pipeline.render_creative_video(
            business_name="Sharma Solar",
            niche="solar",
            slides=["a", "b"],
            offer="20% off",
            client_id="c1",
        )
    )
    assert "error" not in result
    assert result["path"].endswith(".mp4")
    assert os.path.exists(result["path"])
    # video_render_started + video_ready both attempted (and both raised,
    # harmlessly) — proves the raising log_event was actually exercised.
    assert calls["n"] >= 2


def test_render_creative_video_unexpected_exception_logs_exactly_once(monkeypatch, tmp_path):
    """Review fix (Task 7): an exception NOT covered by the 4 explicit
    checks (deps missing / segment fail / concat fail / QA fail) — e.g. a
    _make_branded_frame PIL error — must fall into the outer except and
    fire exactly ONE video_render_failed event: not zero (the dangling-
    "started"-with-no-close bug this task fixes) and not two (the
    video_ready-then-video_render_failed double-log this task also fixes)."""
    from app.marketing import delivery_ledger, reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))

    def _raise_frame(text, idx, brand, tmp_dir, **kw):
        raise ValueError("simulated PIL frame-render error")

    monkeypatch.setattr(video_pipeline, "_make_branded_frame", _raise_frame)

    logged: list[tuple[str, str]] = []

    def _record_log_event(client_id, event, *, detail="", **kw):
        logged.append((client_id, event))
        return True

    monkeypatch.setattr(delivery_ledger, "log_event", _record_log_event)

    result = asyncio.run(
        video_pipeline.render_creative_video(business_name="X", slides=["a"], client_id="c1")
    )
    assert "error" in result
    failed_events = [e for e in logged if e == ("c1", "video_render_failed")]
    assert len(failed_events) == 1, f"expected exactly one video_render_failed log, got {logged}"
    ready_events = [e for e in logged if e[1] == "video_ready"]
    assert not ready_events, f"video_ready must never fire on an unexpected exception, got {logged}"


def test_render_creative_video_getsize_failure_never_double_logs(monkeypatch, tmp_path):
    """Review fix (Task 7) — locks in the EXACT subtlety the review flagged:
    pre-fix, "video_ready" logged BEFORE the success dict (which calls
    os.path.getsize) was fully built, so a getsize failure AFTER that log
    would have produced a contradictory double-log (video_ready immediately
    followed by video_render_failed for the same render). QA is mocked out
    and _music_bed_path only uses os.path.exists (never getsize), so the
    dict-build line is the ONLY reachable os.path.getsize call on this path
    — this isolates the exact regression: if video_ready is ever moved back
    above the dict build, video_ready fires (failing the ready_events
    assertion) in addition to video_render_failed from the outer except."""
    from app.marketing import delivery_ledger, reel_video

    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(video_pipeline, "_qa_check", lambda path, n, **kw: None)

    logged: list[tuple[str, str]] = []

    def _record_log_event(client_id, event, *, detail="", **kw):
        logged.append((client_id, event))
        return True

    monkeypatch.setattr(delivery_ledger, "log_event", _record_log_event)

    def _raise_getsize(path):
        raise OSError("simulated Windows file-lock/AV-scan race on getsize")

    monkeypatch.setattr(os.path, "getsize", _raise_getsize)

    result = asyncio.run(
        video_pipeline.render_creative_video(business_name="X", slides=["a"], client_id="c1")
    )
    assert "error" in result
    ready_events = [e for e in logged if e[1] == "video_ready"]
    failed_events = [e for e in logged if e == ("c1", "video_render_failed")]
    assert not ready_events, (
        f"video_ready must never fire when getsize raises building the result dict, got {logged}"
    )
    assert len(failed_events) == 1, f"expected exactly one video_render_failed log, got {logged}"


def test_new_ledger_events_are_registered():
    from app.marketing import delivery_ledger

    for ev in ("video_render_started", "video_qa_failed", "video_render_failed", "video_ready"):
        assert ev in delivery_ledger.EVENT_TYPES, f"{ev} missing from delivery_ledger.LABELS"


def test_render_creative_video_mkdtemp_failure_never_raises(monkeypatch, tmp_path):
    """Review fix (Task 7, 2nd pass): tempfile.mkdtemp() sat OUTSIDE the
    try/finally, alongside reel_video.available() and brand_frames.
    resolve_brand() (both independently documented as never-raising, unlike
    raw mkdtemp). If mkdtemp raises OSError (disk-full/permissions — same
    Windows file-lock/AV-scan class as the Task 5 os.remove and Task 7
    os.path.getsize findings), it must be caught by the SAME outer except
    that logs video_render_failed — not propagate uncaught out of the
    public entry point (docstring: "Never raises across the public entry
    point"), and must not leave video_render_started dangling."""
    from app.marketing import delivery_ledger, reel_video

    # Must reach mkdtemp — if available() reports ok:False (e.g. ffmpeg
    # missing on the test host), the deps-missing return fires BEFORE
    # mkdtemp is ever called and this test would guard nothing.
    monkeypatch.setattr(
        reel_video,
        "available",
        lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True},
    )
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))

    def _raise_mkdtemp(*a, **kw):
        raise OSError("simulated disk-full/permissions failure on mkdtemp")

    monkeypatch.setattr(video_pipeline.tempfile, "mkdtemp", _raise_mkdtemp)

    logged: list[tuple[str, str]] = []

    def _record_log_event(client_id, event, *, detail="", **kw):
        logged.append((client_id, event))
        return True

    monkeypatch.setattr(delivery_ledger, "log_event", _record_log_event)

    result = asyncio.run(
        video_pipeline.render_creative_video(business_name="X", slides=["a"], client_id="c1")
    )
    assert "error" in result
    # Exact order + count: started then failed, nothing else, nothing
    # dangling, nothing double-logged.
    assert logged == [
        ("c1", "video_render_started"),
        ("c1", "video_render_failed"),
    ], f"expected exactly [started, failed] in order, got {logged}"


def test_build_creative_video_task_registered():
    import app.tasks.video_jobs  # noqa: F401 — trigger task registration
    from app.worker import celery_app

    assert "app.tasks.video_jobs.build_creative_video_task" in celery_app.tasks


def test_build_creative_video_task_success_path(monkeypatch):
    """Test that build_creative_video_task forwards kwargs correctly to
    render_creative_video and returns its result unmodified on success."""
    import app.tasks.video_jobs
    from app.marketing import video_pipeline

    expected_result = {"path": "data/reels/test_123.mp4", "slides": ["a"], "size_bytes": 5000}
    calls = []

    async def _mock_render(**kwargs):
        calls.append(kwargs)
        return expected_result

    monkeypatch.setattr(video_pipeline, "render_creative_video", _mock_render)

    result = app.tasks.video_jobs.build_creative_video_task(
        business_name="Sharma Solar",
        slides=["slide1"],
        niche="solar",
        offer="20% off",
        client_id="c1",
    )

    assert result == expected_result
    assert "error" not in result
    assert len(calls) == 1
    assert calls[0]["business_name"] == "Sharma Solar"
    assert calls[0]["slides"] == ["slide1"]
    assert calls[0]["niche"] == "solar"
    assert calls[0]["offer"] == "20% off"
    assert calls[0]["client_id"] == "c1"
    assert calls[0]["recipe"] == "generic"  # default value


def test_build_creative_video_task_exception_handling(monkeypatch):
    """Test that build_creative_video_task catches exceptions from
    render_creative_video and returns them as {"error": ...} without
    propagating, while ensuring render was actually called."""
    import app.tasks.video_jobs
    from app.marketing import video_pipeline

    calls = []

    async def _mock_render_raises(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("Mocked ffmpeg crash: encoding failed")

    monkeypatch.setattr(video_pipeline, "render_creative_video", _mock_render_raises)

    result = app.tasks.video_jobs.build_creative_video_task(business_name="Test Business")

    assert "error" in result
    assert result["error"] == "Mocked ffmpeg crash: encoding failed"
    assert len(result["error"]) <= 200  # verify truncation constraint holds
    assert len(calls) == 1  # render was actually called
    assert calls[0]["business_name"] == "Test Business"


def test_real_end_to_end_render_generic_recipe(tmp_path, monkeypatch):
    """One REAL render (no mocks) — slow (network TTS + ffmpeg), keep the
    slide count small so it stays CI-safe. Confirms the whole chain (brand
    frame -> Ken-Burns segment -> concat -> QA -> optional music-skip)
    actually produces a valid file, not just that the mocked seams agree."""
    from app.marketing import reel_video

    if not reel_video.available().get("ok"):
        pytest.skip("ffmpeg/Pillow/edge-tts not installed")

    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    result = asyncio.run(
        video_pipeline.render_creative_video(
            business_name="Test Business",
            niche="general",
            slides=["Hello world"],
            offer="",
            client_id="",
        )
    )
    assert "error" not in result, result.get("error")
    assert os.path.exists(result["path"])
    assert os.path.getsize(result["path"]) > 5000
