# Product One Video Creative Pipeline — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `video_ad_cycle.py`'s flat PIL-slide-card renderer with a branded, Ken-Burns-animated, captioned, optionally-scored video, rendered on an isolated Celery queue — proving the free-stack "premium motion graphics" hypothesis on ONE recipe (generic) before building the other 4 recipes or the harder motion/caption work.

**Architecture:** New `app/marketing/video_pipeline.py` owns rendering; `video_ad_cycle.py`'s single call site swaps from `reel_video.build_reel()` to `video_pipeline.render_creative_video()` with an identical return contract, so the existing generate→approve→publish flow is untouched. Rendering moves off the shared worker onto a new flag-gated `video` Celery queue, mirroring the existing `heavy`/`worker-heavy` pattern exactly.

**Tech Stack:** Python 3.11+, ffmpeg (subprocess, no ffmpeg-python), Pillow, edge-tts, Celery, pytest (`asyncio.run()`, no pytest-asyncio), Docker Compose.

**Source spec:** `docs/superpowers/specs/2026-07-10-product-one-video-creative-pipeline-design.md`

## Global Constraints

- Free-stack only. No new paid dependency, no new external API. (spec §2.1)
- ffmpeg via `subprocess.run(["ffmpeg", "-y", "-loglevel", "error", ...], capture_output=True, timeout=180)` — same pattern as `reel_video._ffmpeg`, not the `ffmpeg-python` package.
- EdgeTTS via `edge_tts.Communicate(text, voice).save(path)` — reuse `reel_video._tts()` directly, do not reimplement.
- Voice = `hi-IN-SwaraNeural` (matches `reel_video._VOICE`).
- Output resolution 720×1280 (9:16), matching `reel_video._W, _H`.
- Every new function that can fail must return `{"error": str}` (or `None`/falsy for optional lookups) — **never raise** across a stage boundary, matching every module touched in this plan (`reel_video`, `content_approval`, `delivery_ledger`, `brand_frames`, `ai_image` are all "never raises" by their own docstrings).
- All new user-facing/log strings follow this codebase's existing Hinglish convention (see `delivery_ledger.LABELS`, `reel_video`'s docstrings).
- **No `git commit` steps in this plan.** CLAUDE.md forbids commit/push without the user explicitly asking, and this repo's working tree already has unrelated in-flight uncommitted work (2FA/rate-limit/signup files per `git status`) — do not run `git add -A` under any circumstance; if a task needs to stage files, stage the exact paths that task touched, nothing else, and only if the user has separately asked for a commit at that point.
- **No deploy, no push, no `docker compose up` against the VPS** in this plan. All work is local, verified via tests/`prod_check.py`.
- Do not touch any of the files already modified/untracked per this session's starting `git status` (billing.py, customer_auth.py, ratelimit.py, coordinator.py, etc., and the new `tests/test_2fa_*`/`test_signup_*`/etc. files) — that is unrelated in-flight work from another thread of work on this repo.
- Scope is Phase 1 only: **generic recipe only.** Festival/review-highlight/offer-announcement/spokesperson-lite recipes, word-synced karaoke captions, kinetic typography, icon/chart motion graphics, multi-platform export sizing, and LLM grammar-pass QA are explicit Phase-2 (see spec §11 backlog + `## Phase-2 backlog` at the end of this plan for what Phase-1 deliberately does not build and why).

---

### Task 1: Walking skeleton — `video_pipeline.render_creative_video()` seam + wire into `video_ad_cycle`

Proves the new module/call-site swap is safe before any real new rendering logic exists. `render_creative_video()` starts as a pure delegate to the existing `reel_video.build_reel()`, so behavior is byte-for-byte identical to today; every later task in this plan replaces pieces of the internals without ever changing this function's external signature or return contract, so `video_ad_cycle.py` and its test never need to change again after this task.

**Files:**
- Create: `app/marketing/video_pipeline.py`
- Modify: `app/marketing/video_ad_cycle.py:191` (import), `app/marketing/video_ad_cycle.py:197-203` (call site)
- Test: `tests/test_video_pipeline.py` (new), `tests/test_video_ad_cycle.py:59` (fixture retarget)

**Interfaces:**
- Produces: `async def render_creative_video(recipe: str = "generic", *, business_name: str, niche: str = "general", slides: list[str] | None = None, offer: str = "", client_id: str = "") -> dict[str, Any]` — on success returns a dict containing at minimum `{"path": str}`; on failure returns `{"error": str}`. This exact signature and return contract is depended on by every later task in this file and by `video_ad_cycle.generate_for_client` (unchanged lines 204-264).

- [ ] **Step 1: Write the failing test**

Create `tests/test_video_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.marketing.video_pipeline'`

- [ ] **Step 3: Write minimal implementation**

Create `app/marketing/video_pipeline.py`:

```python
"""Staged video-creative pipeline for Product One — replaces reel_video's flat
PIL-slide template with brand overlay + Ken-Burns motion + captions + optional
music, on an isolated `video` Celery queue. Phase 1 = generic recipe only.

Never raises across the public entry point — same convention as reel_video,
content_approval, delivery_ledger. See docs/superpowers/specs/
2026-07-10-product-one-video-creative-pipeline-design.md for full design.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def render_creative_video(
    recipe: str = "generic",
    *,
    business_name: str,
    niche: str = "general",
    slides: list[str] | None = None,
    offer: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """1 branded creative video banao. Returns {path,...} ya {error}.
    Phase 1: recipe is accepted but only "generic" has a real implementation;
    delegates to reel_video.build_reel unchanged (walking skeleton)."""
    from app.marketing import reel_video

    return await reel_video.build_reel(
        business_name=business_name,
        niche=niche,
        slides=slides,
        offer=offer,
        client_id=client_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v`
Expected: 2 passed

- [ ] **Step 5: Swap the call site in `video_ad_cycle.py`**

In `app/marketing/video_ad_cycle.py`, change line 191 from:
```python
        from app.marketing import clients_store, content_approval, reel_video
```
to:
```python
        from app.marketing import clients_store, content_approval, video_pipeline
```

Then change lines 197-203 from:
```python
        built = await reel_video.build_reel(
            business_name=str(client.get("business_name") or "Aapka Business"),
            niche=str(client.get("niche") or "general"),
            slides=slides,
            offer=str(client.get("offer") or ""),
            client_id=client_id,
        )
```
to:
```python
        built = await video_pipeline.render_creative_video(
            recipe="generic",
            business_name=str(client.get("business_name") or "Aapka Business"),
            niche=str(client.get("niche") or "general"),
            slides=slides,
            offer=str(client.get("offer") or ""),
            client_id=client_id,
        )
```

- [ ] **Step 6: Retarget the existing test fixture's mock**

In `tests/test_video_ad_cycle.py`, the `iso` fixture (line ~44-67) currently does:
```python
    async def _fake_reel(**kw):
        p = tmp_path / "reel.mp4"
        p.write_bytes(b"x")
        return {"path": str(p), "slides": kw.get("slides"), "size_kb": 1}

    monkeypatch.setattr(reel_video, "build_reel", _fake_reel)
```
Change the `monkeypatch.setattr` line (and only that line) to patch the new seam instead:
```python
    from app.marketing import video_pipeline

    monkeypatch.setattr(video_pipeline, "render_creative_video", _fake_reel)
```
Leave `_fake_reel`'s body and every other line of the fixture unchanged — `_fake_reel(**kw)` already accepts arbitrary kwargs (including the new `recipe=` kwarg `video_ad_cycle.py` now passes), so no signature change is needed there.

- [ ] **Step 7: Run both test files to verify nothing broke**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py tests/test_video_ad_cycle.py -v`
Expected: 10 passed (2 new + 8 existing, all green)

---

### Task 2: Brand resolution + logo temp-file helper

`brand_frames.resolve_brand()` already gives logo as a base64 data URI (for HTML/SVG use) — ffmpeg needs an actual file path to composite a logo overlay, so this task adds the decode-to-tempfile step.

**Files:**
- Modify: `app/marketing/video_pipeline.py`
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Consumes: `brand_frames.resolve_brand(slug_or_id: str) -> dict[str, Any]` (10 keys: `client_id, slug, business_name, phone, tagline, niche, city, primary, accent, logo_data_uri` — `logo_data_uri` is `""` or a `data:image/...;base64,...` string, per `app/marketing/brand_frames.py:71-132`).
- Produces: `def _logo_temp_file(logo_data_uri: str, tmp_dir: str) -> str | None` — writes a decoded PNG/JPG to `tmp_dir`, returns the path, or `None` if `logo_data_uri` is empty/malformed (never raises).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_video_pipeline.py`:

```python
import base64
import os
import tempfile


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k logo_temp_file`
Expected: FAIL with `AttributeError: module 'app.marketing.video_pipeline' has no attribute '_logo_temp_file'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/marketing/video_pipeline.py`:

```python
import base64
import os


def _logo_temp_file(logo_data_uri: str, tmp_dir: str) -> str | None:
    """brand_frames.resolve_brand()'s logo_data_uri (data:image/...;base64,...)
    ko ek disk file me decode karo — ffmpeg ko file path chahiye, data URI nahi.
    Never raises; malformed/empty input = None."""
    try:
        if not logo_data_uri or not logo_data_uri.startswith("data:image/"):
            return None
        header, _, b64_payload = logo_data_uri.partition(",")
        if not b64_payload:
            return None
        ext = "png"
        if "jpeg" in header or "jpg" in header:
            ext = "jpg"
        elif "webp" in header:
            ext = "webp"
        raw = base64.b64decode(b64_payload, validate=False)
        if not raw:
            return None
        path = os.path.join(tmp_dir, f"logo.{ext}")
        with open(path, "wb") as f:
            f.write(raw)
        return path
    except Exception as e:
        logger.warning(f"[video_pipeline] logo decode failed: {e}")
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k logo_temp_file`
Expected: 2 passed

---

### Task 3: Branded frame renderer with lower-third caption bar

Replaces `reel_video._make_frame()`'s giant centered text with: brand-color background (unchanged approach) + small top-left logo (if present) + a lower-third semi-transparent caption bar (closer to real short-form-video style than a full-screen text card) + bottom brand strip (business name + phone, when available).

**This lower-third bar IS Phase-1's Caption stage** (spec §4 stage 7) — since the bar's text is the exact same string handed to the Voice stage's TTS call (Task 4), text and voiceover are already duration-matched with no separate sync step needed. Word-level karaoke highlighting (spec's original "burned word-highlight captions") is a Phase-2 item requiring a different Voice-stage implementation (see Phase-2 backlog) — Phase-1 ships sentence-level captions only.

**Files:**
- Modify: `app/marketing/video_pipeline.py`
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Consumes: `_logo_temp_file` (Task 2). Brand dict shape from `brand_frames.resolve_brand()` (Task 2).
- Produces: `def _make_branded_frame(text: str, idx: int, brand: dict[str, Any], tmp_dir: str) -> str` — writes a 720×1280 PNG to `tmp_dir`, returns its path. Mirrors `reel_video._make_frame`'s signature shape (`text, idx, brand, tmp`) so it's a drop-in visual upgrade, not a new calling convention.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_video_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k make_branded_frame`
Expected: FAIL with `AttributeError: module 'app.marketing.video_pipeline' has no attribute '_make_branded_frame'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/marketing/video_pipeline.py`:

```python
_W, _H = 720, 1280  # matches reel_video._W, _H — 9:16 reel


def _hex(c: str, default: tuple) -> tuple:
    try:
        c = c.lstrip("#")
        return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def _make_branded_frame(text: str, idx: int, brand: dict[str, Any], tmp_dir: str) -> str:
    """PIL frame: brand-color bg + top-left logo (if any) + lower-third caption
    bar (not full-screen giant text — closer to real short-form-video captions)
    + bottom brand strip (business name + phone)."""
    from PIL import Image, ImageDraw, ImageFont

    primary = brand.get("primary") or "#2563eb"
    bg = _hex(primary, (37, 99, 235))
    img = Image.new("RGB", (_W, _H), bg)
    dr = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    # Logo, top-left, 90x90, if present
    logo_path = _logo_temp_file(str(brand.get("logo_data_uri") or ""), tmp_dir)
    if logo_path:
        try:
            logo = Image.open(logo_path).convert("RGBA").resize((90, 90))
            img.paste(logo, (30, 30), logo)
        except Exception as e:
            logger.warning(f"[video_pipeline] logo paste failed: {e}")

    # Lower-third caption bar: semi-transparent dark strip + word-wrapped white text
    bar_h = 260
    bar_top = _H - bar_h - 140  # leave room for the bottom brand strip below it
    overlay = Image.new("RGBA", (_W, bar_h), (0, 0, 0, 150))
    img.paste(overlay, (0, bar_top), overlay)

    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 24:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    y = bar_top + (bar_h - len(lines[:5]) * 50) // 2
    for ln in lines[:5]:
        bb = dr.textbbox((0, 0), ln, font=font)
        dr.text(((_W - (bb[2] - bb[0])) / 2, y), ln, fill="white", font=font)
        y += 50

    # Bottom brand strip: business name + phone
    biz = str(brand.get("business_name") or "").strip()
    phone = str(brand.get("phone") or "").strip()
    strip_text = " | ".join(t for t in (biz, phone) if t)
    if strip_text:
        bb = dr.textbbox((0, 0), strip_text, font=small_font)
        dr.text(((_W - (bb[2] - bb[0])) / 2, _H - 90), strip_text, fill="white", font=small_font)

    path = os.path.join(tmp_dir, f"frame{idx:02d}.png")
    img.save(path)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k make_branded_frame`
Expected: 1 passed

---

### Task 4: Ken-Burns (zoompan) segment builder

Replaces `reel_video`'s flat per-slide segment (static frame for N seconds) with the same frame slowly zooming — real, visible motion from existing static assets, no new external dependency. Reuses `reel_video._tts()` (Task's Global Constraints) and the same subprocess-based `_ffmpeg()` pattern.

**Files:**
- Modify: `app/marketing/video_pipeline.py`
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Consumes: `reel_video._tts(text: str, path: str) -> bool` (async, `app/marketing/reel_video.py:95-103`). `_make_branded_frame` (Task 3).
- Produces: `def _zoompan_filter(duration_s: float, fps: int = 24) -> str` — returns an ffmpeg `-vf` filter string. `def _build_segment_args(frame_path: str, audio_path: str | None, duration_s: float, out_path: str) -> list[str]` — returns the full ffmpeg args list (excluding the `["ffmpeg", "-y", "-loglevel", "error"]` prefix, matching `reel_video._ffmpeg`'s calling convention).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_video_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k "zoompan or build_segment_args"`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write minimal implementation**

Add to `app/marketing/video_pipeline.py`:

```python
def _zoompan_filter(duration_s: float, fps: int = 24) -> str:
    """Slow Ken-Burns zoom (1.0 -> ~1.08) across the whole frame duration.
    Applied to a single static PIL frame — creates real perceived motion
    without needing photographic/AI-generated background content."""
    d = max(1, int(round(duration_s * fps)))
    return f"scale=720:1280,zoompan=z='min(zoom+0.0015,1.08)':d={d}:s=720x1280:fps={fps}"


def _build_segment_args(
    frame_path: str, audio_path: str | None, duration_s: float, out_path: str
) -> list[str]:
    """ffmpeg args (sans the ['ffmpeg','-y','-loglevel','error'] prefix reel_video._ffmpeg
    already adds) to build one Ken-Burns video segment from a static frame,
    optionally muxed with a voiceover track."""
    vf = _zoompan_filter(duration_s)
    args = ["-loop", "1", "-i", frame_path]
    if audio_path:
        args += ["-i", audio_path, "-shortest"]
    else:
        args += ["-t", str(duration_s)]
    args += ["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24"]
    if audio_path:
        args += ["-c:a", "aac"]
    args += [out_path]
    return args
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k "zoompan or build_segment_args"`
Expected: 3 passed

- [ ] **Step 5: Wire the full render loop (slides -> branded frames -> Ken-Burns segments -> concat)**

Add to `app/marketing/video_pipeline.py` (this replaces Task 1's delegation to `reel_video.build_reel` — from here on `render_creative_video` has its own real implementation):

```python
import shutil
import subprocess
import tempfile
import time
import uuid

_OUT_DIR = os.path.join("data", "reels")


async def _render_generic(
    business_name: str, niche: str, slides: list[str], offer: str, client_id: str
) -> dict[str, Any]:
    from app.marketing import brand_frames, reel_video

    avail = reel_video.available()
    if not avail.get("ok"):
        return {"error": "video deps missing", "available": avail}

    brand = brand_frames.resolve_brand(client_id) if client_id else {}
    if not brand.get("business_name"):
        brand["business_name"] = business_name
    brand.setdefault("primary", "#2563eb")

    used_slides = slides or [
        business_name,
        offer or f"Aapke area ka bharosemand {niche} expert",
        "Call ya WhatsApp karo — turant response milega",
    ]

    tmp = tempfile.mkdtemp(prefix="vidpipe_")
    try:
        segs: list[str] = []
        for i, text in enumerate(used_slides):
            frame = _make_branded_frame(text, i, brand, tmp)
            audio = os.path.join(tmp, f"audio{i:02d}.mp3")
            has_audio = await reel_video._tts(text, audio)
            seg = os.path.join(tmp, f"seg{i:02d}.mp4")
            duration = 4.0
            args = _build_segment_args(frame, audio if has_audio else None, duration, seg)
            if not reel_video._ffmpeg(args):
                return {"error": f"ffmpeg segment {i} failed"}
            segs.append(seg)

        concat_list = os.path.join(tmp, "list.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for s in segs:
                f.write(f"file '{s}'\n")

        os.makedirs(_OUT_DIR, exist_ok=True)
        out_path = os.path.join(_OUT_DIR, f"reel_{uuid.uuid4().hex[:10]}.mp4")
        if not reel_video._ffmpeg(["-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", out_path]):
            return {"error": "ffmpeg concat failed"}

        return {
            "path": out_path,
            "slides": used_slides,
            "size_kb": os.path.getsize(out_path) // 1024,
            "note": "Human upload karo (IG/FB/YT Shorts) — auto-publish nahi.",
        }
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

Now replace `render_creative_video`'s body (from Task 1) with:

```python
async def render_creative_video(
    recipe: str = "generic",
    *,
    business_name: str,
    niche: str = "general",
    slides: list[str] | None = None,
    offer: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """1 branded creative video banao. Returns {path,...} ya {error}.
    Phase 1: only "generic" has a real implementation; other recipe names
    currently fall back to generic (Phase 2 adds real per-recipe behavior)."""
    t0 = time.time()
    result = await _render_generic(business_name, niche, slides or [], offer, client_id)
    if "error" not in result:
        result["took_s"] = round(time.time() - t0, 1)
    return result
```

- [ ] **Step 6: Update the walking-skeleton test to match the new real implementation**

The Task 1 tests monkeypatched `reel_video.build_reel` and asserted delegation — that's no longer true. Replace both tests in `tests/test_video_pipeline.py` (`test_render_creative_video_delegates_to_reel_video`, `test_render_creative_video_propagates_error`) with:

```python
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
```

- [ ] **Step 7: Run the full test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py tests/test_video_ad_cycle.py -v`
Expected: all passed (Task 1's 2 delegation tests replaced by 2 new ones; Tasks 2-4's tests + the 8 existing `test_video_ad_cycle.py` tests all still pass since the external contract never changed)

---

### Task 5: Optional music bed with ducking (empty-safe)

**Files:**
- Modify: `app/marketing/video_pipeline.py`
- Create: `data/music_beds/.gitkeep`
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Produces: `def _music_bed_path(niche: str) -> str | None` — `data/music_beds/{niche}.mp3` if present, else `data/music_beds/generic.mp3` if present, else `None`. `def _mix_music_args(video_path: str, music_path: str, out_path: str) -> list[str]` — ffmpeg args to mix a low-volume music bed under the existing audio track (constant-volume mix, NOT dynamic sidechain ducking — see note below).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_video_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k "music"`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write minimal implementation**

Create empty file `data/music_beds/.gitkeep` (so the directory exists and is trackable while shipping with zero real audio — sourcing real royalty-free tracks is an explicit manual follow-up, not part of this plan; see spec §4 stage 8).

Add to `app/marketing/video_pipeline.py`:

```python
_MUSIC_DIR = os.path.join("data", "music_beds")


def _music_bed_path(niche: str) -> str | None:
    """data/music_beds/{niche}.mp3 if present, else generic.mp3, else None.
    Directory ships empty — this is a no-op until someone manually drops
    royalty-free tracks in (see spec §4 stage 8). Never raises."""
    try:
        niche_path = os.path.join(_MUSIC_DIR, f"{niche}.mp3")
        if os.path.exists(niche_path):
            return niche_path
        generic_path = os.path.join(_MUSIC_DIR, "generic.mp3")
        if os.path.exists(generic_path):
            return generic_path
        return None
    except Exception:
        return None


def _mix_music_args(video_path: str, music_path: str, out_path: str) -> list[str]:
    """Mix a low, CONSTANT-volume music bed under the video's existing audio.
    Phase 1 simplification: constant-volume mix, not dynamic sidechain
    ducking (real ducking is a Phase-2 polish item — see plan's Phase-2
    backlog section)."""
    return [
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", "[1:a]volume=0.12,aloop=loop=-1:size=2e9[bed];[0:a][bed]amix=inputs=2:duration=first[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        out_path,
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k "music"`
Expected: 4 passed

- [ ] **Step 5: Wire music mixing into `_render_generic` (fail-open — skip on any error)**

In `app/marketing/video_pipeline.py`, in `_render_generic`, after the concat step succeeds (right before the `return {"path": out_path, ...}` in Step 5 of Task 4), insert:

```python
        bed = _music_bed_path(niche)
        if bed:
            mixed_path = os.path.join(_OUT_DIR, f"reel_{uuid.uuid4().hex[:10]}_mix.mp4")
            if reel_video._ffmpeg(_mix_music_args(out_path, bed, mixed_path)):
                os.remove(out_path)
                out_path = mixed_path
            # else: music mix failed — ship without it (fail-open, spec §9)
```

- [ ] **Step 6: Add a test proving music failure doesn't break the render**

Add to `tests/test_video_pipeline.py`:

```python
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
```

- [ ] **Step 7: Run full test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v`
Expected: all passed

---

### Task 6: QA checklist (ffprobe-based)

Deterministic checks only (file exists/size, duration bounds, resolution) — no LLM grammar-pass in Phase 1 (slide text already comes from the proven `post_generator`/caller-supplied path; re-checking it is a Phase-2 nice-to-have, not a Phase-1 requirement).

**Files:**
- Modify: `app/marketing/video_pipeline.py`
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Produces: `def _qa_check(path: str, expected_slide_count: int) -> str | None` — returns `None` if all checks pass, else a short reason string.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_video_pipeline.py`:

```python
def test_qa_check_missing_file():
    assert video_pipeline._qa_check("does/not/exist.mp4", 3) is not None


def test_qa_check_passes_on_valid_probe(monkeypatch, tmp_path):
    p = tmp_path / "out.mp4"
    p.write_bytes(b"x" * 5000)

    def _fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = b'{"format": {"duration": "12.0"}, "streams": [{"width": 720, "height": 1280}]}'

        return R()

    monkeypatch.setattr(video_pipeline.subprocess, "run", _fake_run)
    assert video_pipeline._qa_check(str(p), 3) is None


def test_qa_check_fails_on_wrong_resolution(monkeypatch, tmp_path):
    p = tmp_path / "out.mp4"
    p.write_bytes(b"x" * 5000)

    def _fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = b'{"format": {"duration": "12.0"}, "streams": [{"width": 1080, "height": 1080}]}'

        return R()

    monkeypatch.setattr(video_pipeline.subprocess, "run", _fake_run)
    reason = video_pipeline._qa_check(str(p), 3)
    assert reason is not None and "resolution" in reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k qa_check`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write minimal implementation**

Add to `app/marketing/video_pipeline.py`:

```python
import json


def _qa_check(path: str, expected_slide_count: int) -> str | None:
    """Deterministic checklist: file exists+non-trivial size, duration in a
    generous bound for the slide count, resolution == 720x1280. Returns None
    (pass) or a short failure reason. Never raises."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            return "output file missing or too small"
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
                "-of", "json", path,
            ],
            capture_output=True,
            timeout=30,
        )
        if r.returncode != 0:
            return "ffprobe failed"
        data = json.loads(r.stdout or b"{}")
        duration = float((data.get("format") or {}).get("duration") or 0)
        streams = data.get("streams") or [{}]
        width = int(streams[0].get("width") or 0)
        height = int(streams[0].get("height") or 0)
        min_expected = max(1, expected_slide_count) * 2.5
        max_expected = max(1, expected_slide_count) * 10
        if not (min_expected <= duration <= max_expected):
            return f"duration {duration}s out of bounds [{min_expected},{max_expected}]"
        if (width, height) != (720, 1280):
            return f"resolution {width}x{height} != 720x1280"
        return None
    except Exception as e:
        return f"qa_check error: {str(e)[:120]}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k qa_check`
Expected: 3 passed

- [ ] **Step 5: Wire QA into `_render_generic`**

In `app/marketing/video_pipeline.py`, in `_render_generic`, right before the final `return {"path": out_path, ...}`, insert:

```python
        qa_reason = _qa_check(out_path, len(used_slides))
        if qa_reason:
            return {"error": f"qa_failed: {qa_reason}"}
```

This mirrors `reel_video.build_reel`'s existing failure contract exactly (`{"error": str}`), so `video_ad_cycle.generate_for_client`'s unchanged line 204 (`if built.get("error"):`) short-circuits and no approval record is created — same behavior as any other pre-existing render failure, not a new review-queue path.

- [ ] **Step 6: Add a test proving QA failure blocks the return without crashing**

Add to `tests/test_video_pipeline.py`:

```python
def test_render_creative_video_qa_failure_returns_error(monkeypatch, tmp_path):
    from app.marketing import reel_video

    monkeypatch.setattr(reel_video, "available", lambda: {"ffmpeg": True, "pillow": True, "edge_tts": True, "ok": True})

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"x" * 200)
        return True

    monkeypatch.setattr(reel_video, "_tts", _fake_tts)
    monkeypatch.setattr(reel_video, "_ffmpeg", lambda args: _write_dummy_output(args))
    monkeypatch.setattr(video_pipeline, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(video_pipeline, "_qa_check", lambda path, n: "forced failure for test")

    result = asyncio.run(video_pipeline.render_creative_video(business_name="X", slides=["a"]))
    assert result.get("error") == "qa_failed: forced failure for test"
```

- [ ] **Step 7: Run full test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v`
Expected: all passed

---

### Task 7: `delivery_ledger` events

**Files:**
- Modify: `app/marketing/delivery_ledger.py:53-81` (add LABELS entries), `app/marketing/video_pipeline.py` (log calls)
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Consumes: `delivery_ledger.log_event(client_id: str, event: str, *, detail: str = "", meta: dict | None = None, actor: str = "system", key: str | None = None) -> bool` (`app/marketing/delivery_ledger.py:162-170`).

- [ ] **Step 1: Add new event types to `LABELS`**

In `app/marketing/delivery_ledger.py`, add these entries inside the `LABELS` dict (right before the closing `}` at line 81), following the exact existing tuple shape `(icon, customer_hi_label, admin_en_label, customer_visible)`:

```python
    # Video Creative Pipeline (2026-07-10) — Phase 1, generic recipe only.
    "video_render_started": ("🎬", "Aapka video ban raha hai", "Video render started", True),
    "video_qa_failed": ("⚠️", "", "Video QA check failed — not published", False),
    "video_render_failed": ("⚠️", "", "Video render failed", False),
    "video_ready": ("🎥", "Naya video taiyaar — approve karein", "Video render succeeded, pending approval", True),
```

Do not modify `EVENT_TYPES` — it is derived automatically from `LABELS.keys()` (line 82).

- [ ] **Step 2: Write the failing test**

Add to `tests/test_video_pipeline.py`:

```python
def test_new_ledger_events_are_registered():
    from app.marketing import delivery_ledger

    for ev in ("video_render_started", "video_qa_failed", "video_render_failed", "video_ready"):
        assert ev in delivery_ledger.EVENT_TYPES, f"{ev} missing from delivery_ledger.LABELS"
```

- [ ] **Step 3: Run test to verify it passes** (this one should already pass after Step 1 — confirms the wiring)

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k ledger_events`
Expected: 1 passed

- [ ] **Step 4: Log events from `_render_generic`**

In `app/marketing/video_pipeline.py`, at the top of `_render_generic` (after the `avail` check), add:

```python
    if client_id:
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(client_id, "video_render_started", detail=business_name)
        except Exception:
            pass
```

At each of the three failure returns inside `_render_generic` (deps missing, ffmpeg segment fail, ffmpeg concat fail) and the QA-failure return added in Task 6 Step 5, log the corresponding failure event right before the `return`, e.g. for the QA failure:

```python
        qa_reason = _qa_check(out_path, len(used_slides))
        if qa_reason:
            if client_id:
                try:
                    from app.marketing import delivery_ledger

                    delivery_ledger.log_event(client_id, "video_qa_failed", detail=qa_reason)
                except Exception:
                    pass
            return {"error": f"qa_failed: {qa_reason}"}
```

and for the other three failure points, the same pattern with event `"video_render_failed"` and `detail=` set to the specific error string.

At the final success return, add:

```python
        if client_id:
            try:
                from app.marketing import delivery_ledger

                delivery_ledger.log_event(client_id, "video_ready", detail=business_name)
            except Exception:
                pass
        return {
```
(i.e. log immediately before constructing the existing success-return dict)

- [ ] **Step 5: Run full test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py tests/test_video_ad_cycle.py -v`
Expected: all passed

---

### Task 8: `video` Celery queue — router function + flag in `app/worker.py`

Mirrors `_route_staff_task`/`_heavy_queue_enabled` exactly, as its own router (not folded into the static dict — spec's original static-dict wording was wrong; this needs flag-gated fallback behavior, which only a router function provides in this codebase's Celery config).

**Files:**
- Modify: `app/worker.py:22-31` (include list), `app/worker.py:44-63` (add router+flag), `app/worker.py:76` (task_routes tuple)
- Test: `tests/test_celery_queue_routing.py`

**Interfaces:**
- Produces: `def _video_queue_enabled() -> bool`, `def _route_video_task(name, args, kwargs, options, task=None, **kw) -> dict | None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_celery_queue_routing.py`:

```python
def test_video_router_routes_when_flag_on(monkeypatch):
    from app import worker

    monkeypatch.setenv("CELERY_VIDEO_QUEUE", "1")
    route = worker._route_video_task(
        "app.tasks.video_jobs.build_creative_video_task", (), {}, {}
    )
    assert route == {"queue": "video"}


def test_video_router_none_when_flag_off(monkeypatch):
    from app import worker

    monkeypatch.delenv("CELERY_VIDEO_QUEUE", raising=False)
    route = worker._route_video_task(
        "app.tasks.video_jobs.build_creative_video_task", (), {}, {}
    )
    assert route is None


def test_video_router_none_for_other_tasks(monkeypatch):
    from app import worker

    monkeypatch.setenv("CELERY_VIDEO_QUEUE", "1")
    route = worker._route_video_task("app.tasks.scraping.scrape_leads", (), {}, {})
    assert route is None


def test_static_routes_unchanged_by_video_addition():
    # video is router-fn based (like "heavy"), NOT added to the static dict —
    # this assertion must stay exactly as it is today.
    assert _statically_routed_queues() == {"scraping", "calling", "reporting", "sync", "training"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_celery_queue_routing.py -v -k video_router`
Expected: FAIL with `AttributeError: module 'app.worker' has no attribute '_route_video_task'`

- [ ] **Step 3: Write minimal implementation**

In `app/worker.py`, right after the existing `_route_staff_task` function (after line 63), add:

```python
def _video_queue_enabled() -> bool:
    return os.environ.get("CELERY_VIDEO_QUEUE", "0").strip().lower() in ("1", "true", "yes")


def _route_video_task(name, args, kwargs, options, task=None, **kw):
    """Router fn: video-pipeline render task -> 'video' queue (sirf flag ON pe).
    Mirrors _route_staff_task's heavy-queue pattern exactly — separate router
    (not the static dict) so it's flag-gated with a safe unset->default-queue
    fallback, matching this project's INERT-default feature convention."""
    try:
        if name == "app.tasks.video_jobs.build_creative_video_task" and _video_queue_enabled():
            return {"queue": "video"}
    except Exception as _e:
        logger.debug("_route_video_task routing failed, using default queue: %s", _e)
    return None
```

Change the `task_routes` tuple (line 76) from:
```python
    task_routes=(
        _route_staff_task,
        {
```
to:
```python
    task_routes=(
        _route_staff_task,
        _route_video_task,
        {
```

In the `include=[...]` list near the top of the file (lines 22-31), add `"app.tasks.video_jobs"` alongside the existing `"app.tasks.scraping"` etc. entries.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_celery_queue_routing.py -v`
Expected: all passed (existing 5 tests + 4 new ones)

- [ ] **Step 5: Document the new flag**

In `.env.example`, right after the existing `CELERY_HEAVY_QUEUE=0` line, add:
```
CELERY_VIDEO_QUEUE=0           # 1 => video-pipeline render tasks alag 'video' queue me (dedicated worker chahiye).
```

---

### Task 9: `app/tasks/video_jobs.py` Celery task

**Files:**
- Create: `app/tasks/video_jobs.py`
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Consumes: `video_pipeline.render_creative_video(...)` (Task 1/4).
- Produces: `build_creative_video_task` — a Celery task, sync wrapper around the async `render_creative_video`, name `app.tasks.video_jobs.build_creative_video_task` (must match the literal string `_route_video_task` checks in Task 8).

- [ ] **Step 1: Look at the existing task-module pattern**

Read `app/tasks/scraping.py`'s top ~20 lines first (its `celery_app` import + `@celery_app.task` decorator shape) — this task must mirror that exact pattern, not invent a new one. (No code change in this step — just confirms the import path before Step 3.)

- [ ] **Step 2: Write the failing test**

Add to `tests/test_video_pipeline.py`:

```python
def test_build_creative_video_task_registered():
    from app.worker import celery_app

    assert "app.tasks.video_jobs.build_creative_video_task" in celery_app.tasks
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k build_creative_video_task`
Expected: FAIL (task not registered — module doesn't exist yet)

- [ ] **Step 4: Write minimal implementation**

Create `app/tasks/video_jobs.py`:

```python
"""Celery task wrapper for the video-creative pipeline — routes to the
dedicated 'video' queue when CELERY_VIDEO_QUEUE=1 (app/worker.py
_route_video_task), falls back to the default queue otherwise. HEAVY
(ffmpeg) — never call render_creative_video directly from a web request."""

from __future__ import annotations

import asyncio
from typing import Any

from app.utils.logger import setup_logger
from app.worker import celery_app

logger = setup_logger(__name__)


@celery_app.task(name="app.tasks.video_jobs.build_creative_video_task")
def build_creative_video_task(
    recipe: str = "generic",
    *,
    business_name: str,
    niche: str = "general",
    slides: list[str] | None = None,
    offer: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    from app.marketing import video_pipeline

    return asyncio.run(
        video_pipeline.render_creative_video(
            recipe=recipe,
            business_name=business_name,
            niche=niche,
            slides=slides,
            offer=offer,
            client_id=client_id,
        )
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k build_creative_video_task`
Expected: 1 passed

---

### Task 10: docker-compose wiring (3 files) + queue-routing test extensions

**Files:**
- Modify: `docker-compose.vps.yml` (new `worker-video` service), `docker-compose.prod.yml`, `docker-compose.yml` (add `video` to single worker's `-Q`)
- Test: `tests/test_celery_queue_routing.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_celery_queue_routing.py`:

```python
def test_vps_worker_video_consumes_video_queue():
    cmd = _worker_command(REPO_ROOT / "docker-compose.vps.yml", "worker-video")
    assert "video" in _dash_q_queues(cmd)


def test_vps_worker_does_not_drain_video():
    # worker-video isolates it — same starve-prevention shape as worker-heavy.
    cmd = _worker_command(REPO_ROOT / "docker-compose.vps.yml", "worker")
    assert "video" not in _dash_q_queues(cmd)
```

Change `test_prod_worker_consumes_every_routed_queue_plus_heavy` to:
```python
def test_prod_worker_consumes_every_routed_queue_plus_heavy_and_video():
    """docker-compose.prod.yml has no separate heavy or video worker, so its
    single `worker` service must drain both."""
    cmd = _worker_command(REPO_ROOT / "docker-compose.prod.yml", "worker")
    consumed = _dash_q_queues(cmd)
    missing = (_statically_routed_queues() | {"heavy", "video"}) - consumed
    assert not missing, f"docker-compose.prod.yml worker never drains: {missing}"
```

Change `test_base_compose_worker_consumes_every_routed_queue_plus_heavy` to the equivalent `..._plus_heavy_and_video` form for `docker-compose.yml`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_celery_queue_routing.py -v`
Expected: 4 new/changed tests FAIL (service doesn't exist yet / queue not in `-Q` list)

- [ ] **Step 3: Add the `worker-video` service to `docker-compose.vps.yml`**

Insert this block immediately after the existing `worker-heavy` service block (after its closing `networks: [leadgen_net]` line, before the `scheduler:` key):

```yaml
  # ---------------------------------------------------------------------------
  # VIDEO worker — video-creative pipeline (ffmpeg-heavy) isolated onto its own
  # queue/process, same starve-prevention shape as worker-heavy above.
  # CELERY_VIDEO_QUEUE flag SEND-side routing on karta (scheduler/app/worker
  # pe bhi set — see app/worker.py _route_video_task). Default OFF (INERT) —
  # unset means video tasks fall back to the default "celery" queue, so this
  # ships safely before this service is ever started.
  # ---------------------------------------------------------------------------
  worker-video:
    profiles: ["celery"]
    image: ghcr.io/sumitrevolt/leadgenrationaivoiceagent:${APP_VERSION:-latest}
    build:
      context: .
      dockerfile: Dockerfile.lock
    container_name: leadgen_worker_video
    mem_limit: 2000m
    mem_reservation: 512m
    cpus: "1.5"
    user: "0:0"
    command: celery -A app.worker worker -Q video --loglevel=info --concurrency=1
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-leadgen}:${POSTGRES_PASSWORD:-leadgen}@pgbouncer:6432/${POSTGRES_DB:-leadgen}
      REDIS_URL: redis://redis:6379/0
      CACHE_REDIS_URL: redis://redis-cache:6379/0
      RUN_IN_PROCESS_SCHEDULER: "0"
      QDRANT_URL: http://qdrant:6333
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      pgbouncer:
        condition: service_healthy
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "celery -A app.worker inspect ping -d celery@$$HOSTNAME -t 8 | grep -q pong || exit 1"]
      interval: 60s
      timeout: 15s
      start_period: 90s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"
    networks: [leadgen_net]
```

Note: `CELERY_VIDEO_QUEUE` is deliberately **not** set to `"1"` anywhere yet (unlike `CELERY_HEAVY_QUEUE: "1"` on the other services) — per Global Constraints, this plan ships the capability INERT; a human flips the flag in all 4 places (`app`, `worker`, `worker-video`, `scheduler` environments) as a separate, deliberate go-live step once Phase-1 output has been reviewed, exactly like the other gated flags in this codebase's `AUTOMATION_FLAGS` registry.

- [ ] **Step 4: Add `video` to the `worker` service's `-Q` list in `docker-compose.prod.yml` and `docker-compose.yml`**

In `docker-compose.prod.yml` line 91, change:
```yaml
    command: celery -A app.worker worker -Q celery,calling,scraping,reporting,sync,training,heavy --loglevel=info --concurrency=8
```
to:
```yaml
    command: celery -A app.worker worker -Q celery,calling,scraping,reporting,sync,training,heavy,video --loglevel=info --concurrency=8
```

In `docker-compose.yml` line 71, change:
```yaml
    command: celery -A app.worker worker -Q celery,calling,scraping,reporting,sync,training,heavy --loglevel=info --concurrency=4
```
to:
```yaml
    command: celery -A app.worker worker -Q celery,calling,scraping,reporting,sync,training,heavy,video --loglevel=info --concurrency=4
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_celery_queue_routing.py -v`
Expected: all passed

---

### Task 11: Integration test + full verification gate

**Files:**
- Test: `tests/test_video_pipeline.py`

- [ ] **Step 1: Write one real, short, low-res end-to-end render test**

Add to `tests/test_video_pipeline.py`:

```python
import pytest


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
            business_name="Test Business", niche="general", slides=["Hello world"], offer="", client_id=""
        )
    )
    assert "error" not in result, result.get("error")
    assert os.path.exists(result["path"])
    assert os.path.getsize(result["path"]) > 5000
```

- [ ] **Step 2: Run it**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py -v -k real_end_to_end`
Expected: PASS (or SKIP if ffmpeg/edge-tts unavailable in this environment — do not treat a skip as a failure, but do not report Phase 1 done on a skip either; re-run where ffmpeg is actually installed before calling this task complete)

- [ ] **Step 3: Run the full targeted suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_video_pipeline.py tests/test_video_ad_cycle.py tests/test_celery_queue_routing.py -v`
Expected: all passed

- [ ] **Step 4: Run the project verification gate**

Run: `.venv\Scripts\python.exe scripts\prod_check.py`
Expected: ALL CHECKS PASSED (in particular: no duplicate routes, no orphaned worker `-Q` queues, app still imports cleanly with the new `app/tasks/video_jobs.py` module and its `include=[...]` entry)

Run: `.venv\Scripts\python.exe scripts\check_secrets.py`
Expected: clean (no secrets in any file this plan touched)

- [ ] **Step 5: Manually watch the one real rendered video against the "premium" bar**

Open `tests`-produced or a manually-triggered `data/reels/*.mp4` output and actually look at it (this is the entire point of cutting to Phase 1 — spec §2.3's "premium/cinematic" redefinition is a hypothesis until someone watches real output). Compare against: does the Ken-Burns motion read as intentional, not choppy? Is the lower-third caption legible? Is the brand logo/strip visibly correct? Report this back before deciding whether Phase-2 (kinetic typography, word-synced captions, remaining 4 recipes, multi-platform export) proceeds as scoped or needs adjustment first.

---

## Phase-2 backlog (deliberately deferred, not forgotten)

Carried over/refined from spec §11, plus items discovered during this plan's research that weren't in the original spec:

- **Word-synced (karaoke-style) captions** — needs a new Voice-stage function that captures `edge_tts`'s `WordBoundary` events via `.stream()` (not `.save()`, which discards timing) — a materially different code path from the `_tts()` reused in Phase 1, not a small extension of it.
- **Kinetic typography / animated icon+chart overlays** — the actual "motion graphics" quality lever beyond Ken-Burns; deferred until Phase-1's plain Ken-Burns+lower-third-caption output has been watched and judged against the "premium" bar (Task 11 Step 5).
- **Festival / review-highlight-testimonial / offer-announcement / spokesperson-lite recipes.** Research surfaced two corrections the spec didn't have: (a) the real review data source is `review_monitor.recent_drafts()`/`fetch_reviews()`, not `review_to_post.py`/`review_engine.py` (those consume a review, they don't fetch one); (b) there is no per-client "current offer" store anywhere in this codebase (`combo_packages.py` is this SaaS's own pricing catalog, not client offer data; `client.get("offer")` is a dead read — not in `clients_store._ALLOWED_FIELDS`) — offer-announcement must be an on-demand recipe taking `offer` as a human-supplied call-time parameter, not something `video_ad_cycle`'s automatic weekly cadence can source on its own.
- **B-roll stage (spec §4 stage 6) is entirely absent from Phase 1** — the generic recipe never needed it (it was always "optional, one beat"), and no other Phase-1 recipe exists to need it either. First real use is the spokesperson-lite recipe below.
- **Spokesperson-lite** needs a new small "download this Pollinations `video_url` to a local file" step (`ai_image.py` has no async video-fetch-bytes equivalent to its `fetch_image_bytes` for images) before that clip can be composited/captioned/exported by the rest of the pipeline — falls back to Ken-Burns on any fetch failure, per the existing fail-open convention.
- **Multi-platform export (square/banner/etc.)** — Phase 1 ships one 9:16 size only (already covers Reels/Shorts/Stories, the highest-value formats). `magic_resize.resize_pack()` cannot be called directly for video (it's PIL/image-only) — a video-export function needs its own ffmpeg crop/pad logic; reuse `magic_resize.SIZES`' dimensions as the reference, don't call the function itself.
- **Dynamic sidechain music ducking** — Phase 1 uses a constant low music volume, not true ducking; real ducking (volume drops only while voice is speaking) is a `sidechaincompress`/keyframe-envelope upgrade.
- **LLM grammar-pass QA** — Phase 1's QA is deterministic-only (file/duration/resolution); an `free_ai` grammar-check pass over the script text is cheap to add once there's a real (non-generic) Script stage worth checking.
- **Per-plan cadence ramp** — only once real render-time/queue-depth data exists from `worker-video` in production (needs the flag actually flipped + observed first).
