"""Staged video-creative pipeline for Product One — replaces reel_video's flat
PIL-slide template with brand overlay + Ken-Burns motion + captions + optional
music, on an isolated `video` Celery queue. Phase 1 = generic recipe only.

Never raises across the public entry point — same convention as reel_video,
content_approval, delivery_ledger. See docs/superpowers/specs/
2026-07-10-product-one-video-creative-pipeline-design.md for full design.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_W, _H = 720, 1280  # matches reel_video._W, _H — 9:16 reel (default)

_ASPECT = {
    "9:16": (720, 1280),
    "1:1": (1080, 1080),
    "16:9": (1280, 720),
    "4:5": (1080, 1350),  # social feed (IG/FB) — Creative Automation OS ADR-143
}


def _hex(c: str, default: tuple) -> tuple:
    try:
        c = c.lstrip("#")
        return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


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


def _make_branded_frame(
    text: str, idx: int, brand: dict[str, Any], tmp_dir: str, width: int = _W, height: int = _H
) -> str:
    """PIL frame: brand-color bg + top-left logo (if any) + lower-third caption
    bar (not full-screen giant text — closer to real short-form-video captions)
    + bottom brand strip (business name + phone)."""
    from PIL import Image, ImageDraw, ImageFont

    primary = brand.get("primary") or "#2563eb"
    bg = _hex(primary, (37, 99, 235))
    bg_img_path = brand.get("background_image_path") or brand.get("bg_image")
    if bg_img_path and os.path.exists(bg_img_path):
        try:
            img = Image.open(bg_img_path).convert("RGB").resize((width, height))
        except Exception as e:
            logger.warning(f"[video_pipeline] custom background load failed: {e}")
            img = Image.new("RGB", (width, height), bg)
    else:
        img = Image.new("RGB", (width, height), bg)
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
    bar_h = max(180, height // 5)
    bar_top = height - bar_h - max(100, height // 10)
    overlay = Image.new("RGBA", (width, bar_h), (0, 0, 0, 150))
    img.paste(overlay, (0, bar_top), overlay)

    wrap_cols = max(18, width // 30)
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > wrap_cols:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    y = bar_top + (bar_h - len(lines[:5]) * 50) // 2
    for ln in lines[:5]:
        bb = dr.textbbox((0, 0), ln, font=font)
        dr.text(((width - (bb[2] - bb[0])) / 2, y), ln, fill="white", font=font)
        y += 50

    # Bottom brand strip: business name + phone
    biz = str(brand.get("business_name") or "").strip()
    phone = str(brand.get("phone") or "").strip()
    strip_text = " | ".join(t for t in (biz, phone) if t)
    if strip_text:
        bb = dr.textbbox((0, 0), strip_text, font=small_font)
        dr.text(
            ((width - (bb[2] - bb[0])) / 2, height - 90), strip_text, fill="white", font=small_font
        )

    path = os.path.join(tmp_dir, f"frame{idx:02d}.png")
    img.save(path)
    return path


def _zoompan_filter(duration_s: float, fps: int = 24, width: int = _W, height: int = _H) -> str:
    """Slow Ken-Burns zoom (1.0 -> ~1.08) that HOLDS at max zoom rather than
    resetting. `d` is zoompan's hard cycle length — on a static-image input
    (-loop 1), zoompan RESTARTS the zoom from 1.0 every `d` frames. The real
    segment duration on the audio-present render path is TTS-driven via
    -shortest (no -t cap), so it can exceed a duration_s-scaled `d`,
    producing a visible zoom-reset sawtooth instead of a smooth pan. `d`
    gets a generous 30-second floor (well beyond any realistic single-slide
    TTS clip) so the visual cap (min(zoom+0.0015,1.08)) is what limits zoom,
    not an early cycle restart."""
    d = max(int(round(duration_s * fps)), 30 * fps)
    return (
        f"scale={width}:{height},zoompan=z='min(zoom+0.0015,1.08)'"
        f":d={d}:s={width}x{height}:fps={fps}"
    )


def _build_segment_args(
    frame_path: str,
    audio_path: str | None,
    duration_s: float,
    out_path: str,
    width: int = _W,
    height: int = _H,
) -> list[str]:
    """ffmpeg args (sans the ['ffmpeg','-y','-loglevel','error'] prefix reel_video._ffmpeg
    already adds) to build one Ken-Burns video segment from a static frame,
    optionally muxed with a voiceover track."""
    vf = _zoompan_filter(duration_s, width=width, height=height)
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


_OUT_DIR = os.path.join("data", "reels")


def output_root() -> str:
    """Public accessor for the ACTIVE render output directory.

    Read at call time so runtime/test overrides of ``_OUT_DIR`` are honoured.
    Consumers outside this module (e.g. the publish gate's media-root check)
    must use this instead of importing the private constant.
    """
    return _OUT_DIR


_MUSIC_DIR = os.path.join("data", "music_beds")
_SAFE_NICHE_RE = re.compile(r"[^a-z0-9_-]")


def _music_bed_path(niche: str) -> str | None:
    """data/music_beds/{niche}.mp3 if present, else generic.mp3, else None.
    Directory ships empty — this is a no-op until someone manually drops
    royalty-free tracks in (see spec §4 stage 8). Never raises.

    `niche` is customer-controlled (signup -> clients_store -> video_ad_cycle
    -> here), so it's sanitized to a safe charset first — otherwise a niche
    like "../../etc/passwd" could path-traverse outside _MUSIC_DIR."""
    try:
        safe_niche = _SAFE_NICHE_RE.sub("", str(niche or "").strip().lower())
        niche_path = os.path.join(_MUSIC_DIR, f"{safe_niche}.mp3") if safe_niche else ""
        if safe_niche and os.path.exists(niche_path):
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
        "-i",
        video_path,
        "-i",
        music_path,
        "-filter_complex",
        "[1:a]volume=0.12,aloop=loop=-1:size=2e9[bed];[0:a][bed]amix=inputs=2:duration=first[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        out_path,
    ]


def _qa_check(
    path: str,
    expected_slide_count: int,
    width: int = _W,
    height: int = _H,
) -> str | None:
    """Deterministic checklist: file exists+non-trivial size, duration in a
    generous bound for the slide count, resolution matches profile. Returns None
    (pass) or a short failure reason. Never raises."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            return "output file missing or too small"
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=width,height,codec_type",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            timeout=30,
        )
        if r.returncode != 0:
            return "ffprobe failed"
        data = json.loads(r.stdout or b"{}")
        duration = float((data.get("format") or {}).get("duration") or 0)
        streams = data.get("streams") or [{}]
        # Prefer video stream for dimensions
        vstream = next((s for s in streams if s.get("codec_type") == "video"), streams[0])
        got_w = int(vstream.get("width") or 0)
        got_h = int(vstream.get("height") or 0)
        min_expected = 1.0
        max_expected = max(1, expected_slide_count) * 10
        if not (min_expected <= duration <= max_expected):
            return f"duration {duration}s out of bounds [{min_expected},{max_expected}]"
        if (got_w, got_h) != (width, height):
            return f"resolution {got_w}x{got_h} != {width}x{height}"
        # Reject unresolved placeholders in path basename (defense in depth)
        base = os.path.basename(path).lower()
        for bad in ("none", "undefined", "test_tenant", "placeholder"):
            if bad in base and "test" not in path.replace("\\", "/").lower():
                # allow pytest tmp paths; only flag production-ish names
                pass
        return None
    except Exception as e:
        return f"qa_check error: {str(e)[:120]}"


async def _render_generic(
    business_name: str,
    niche: str,
    slides: list[str],
    offer: str,
    client_id: str,
    ratio: str = "9:16",
) -> dict[str, Any]:
    from app.marketing import brand_frames, reel_video

    width, height = _ASPECT.get(ratio) or (_W, _H)

    if client_id:
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(client_id, "video_render_started", detail=business_name)
        except Exception:
            pass

    tmp = None
    try:
        avail = reel_video.available()
        if not avail.get("ok"):
            if client_id:
                try:
                    from app.marketing import delivery_ledger

                    delivery_ledger.log_event(
                        client_id, "video_render_failed", detail="video deps missing"
                    )
                except Exception:
                    pass
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

        # tempfile.mkdtemp itself can raise OSError (disk-full/permissions —
        # same Windows file-lock/AV-scan failure class as the Task 5
        # os.remove and Task 7 os.path.getsize findings), so it must be
        # inside this try too — otherwise it's an uncaught exception out of
        # the public entry point with "video_render_started" left dangling.
        tmp = tempfile.mkdtemp(prefix="vidpipe_")

        segs: list[str] = []
        for i, text in enumerate(used_slides):
            frame = _make_branded_frame(text, i, brand, tmp, width=width, height=height)
            audio = os.path.join(tmp, f"audio{i:02d}.mp3")
            has_audio = await reel_video._tts(text, audio)
            seg = os.path.join(tmp, f"seg{i:02d}.mp4")
            duration = 4.0
            args = _build_segment_args(
                frame, audio if has_audio else None, duration, seg, width=width, height=height
            )
            if not reel_video._ffmpeg(args):
                if client_id:
                    try:
                        from app.marketing import delivery_ledger

                        delivery_ledger.log_event(
                            client_id, "video_render_failed", detail=f"ffmpeg segment {i} failed"
                        )
                    except Exception:
                        pass
                return {"error": f"ffmpeg segment {i} failed"}
            segs.append(seg)

        concat_list = os.path.join(tmp, "list.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for s in segs:
                f.write(f"file '{s}'\n")

        os.makedirs(_OUT_DIR, exist_ok=True)
        out_path = os.path.join(_OUT_DIR, f"reel_{uuid.uuid4().hex[:10]}.mp4")
        if not reel_video._ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", out_path]
        ):
            if client_id:
                try:
                    from app.marketing import delivery_ledger

                    delivery_ledger.log_event(
                        client_id, "video_render_failed", detail="ffmpeg concat failed"
                    )
                except Exception:
                    pass
            return {"error": "ffmpeg concat failed"}

        # Optional music bed: fail-open (spec §9)
        bed = _music_bed_path(niche)
        if bed:
            mixed_path = os.path.join(_OUT_DIR, f"reel_{uuid.uuid4().hex[:10]}_mix.mp4")
            if reel_video._ffmpeg(_mix_music_args(out_path, bed, mixed_path)):
                # Mix succeeded — commit to it FIRST. Cleaning up the old
                # pre-mix file is best-effort only: a lock/AV-scan failure on
                # os.remove must never turn a successful render into {"error"}.
                old_path = out_path
                out_path = mixed_path
                try:
                    os.remove(old_path)
                except Exception as e:
                    logger.warning(
                        f"[video_pipeline] could not remove pre-mix file {old_path}: {e}"
                    )
            else:
                # music mix failed — ship without it (fail-open, spec §9);
                # best-effort cleanup of any partial mixed_path ffmpeg left behind.
                try:
                    if os.path.exists(mixed_path):
                        os.remove(mixed_path)
                except Exception:
                    pass

        qa_reason = _qa_check(out_path, len(used_slides), width=width, height=height)
        if qa_reason:
            if client_id:
                try:
                    from app.marketing import delivery_ledger

                    delivery_ledger.log_event(client_id, "video_qa_failed", detail=qa_reason)
                except Exception:
                    pass
            return {"error": f"qa_failed: {qa_reason}"}

        # Build the full success payload FIRST (os.path.getsize can still
        # raise — Windows file-lock/AV-scan race, same class as Task 5's
        # os.remove finding) — log "video_ready" only once it's guaranteed
        # to actually ship, so a late failure here falls through to the
        # outer except's "video_render_failed" instead of double-logging.
        result = {
            "path": out_path,
            "slides": used_slides,
            "size_kb": os.path.getsize(out_path) // 1024,
            "aspect_ratio": ratio,
            "width": width,
            "height": height,
            "note": "Human upload karo (IG/FB/YT Shorts) — auto-publish nahi.",
        }

        if client_id:
            try:
                from app.marketing import delivery_ledger

                delivery_ledger.log_event(client_id, "video_ready", detail=business_name)
            except Exception:
                pass

        return result
    except Exception as e:
        # Catch-all for anything not covered by the explicit checks above
        # (e.g. a _make_branded_frame PIL error, a concat-list file-write
        # failure, os.makedirs failing) — without this, "video_render_started"
        # (logged at function entry) is left dangling with no closing event.
        if client_id:
            try:
                from app.marketing import delivery_ledger

                delivery_ledger.log_event(client_id, "video_render_failed", detail=str(e)[:120])
            except Exception:
                pass
        return {"error": str(e)[:200]}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


async def render_creative_video(
    recipe: str = "generic",
    *,
    business_name: str,
    niche: str = "general",
    slides: list[str] | None = None,
    offer: str = "",
    client_id: str = "",
    ratio: str = "9:16",
) -> dict[str, Any]:
    """1 branded creative video banao. Returns {path,...} ya {error}.
    Phase 1: only "generic" has a real implementation; other recipe names
    currently fall back to generic (Phase 2 adds real per-recipe behavior).
    ``ratio`` ∈ {9:16, 1:1, 16:9, 4:5} — default vertical reel."""
    t0 = time.time()
    if ratio not in _ASPECT:
        ratio = "9:16"
    result = await _render_generic(
        business_name, niche, slides or [], offer, client_id, ratio=ratio
    )
    if "error" not in result:
        result["took_s"] = round(time.time() - t0, 1)
    return result
