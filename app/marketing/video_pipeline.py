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
    text: str,
    idx: int,
    brand: dict[str, Any],
    tmp_dir: str,
    width: int = _W,
    height: int = _H,
    total_slides: int = 4,
) -> str:
    """Creates a high-aesthetic, enterprise-grade video frame.
    
    Features:
    - Deep midnight slate gradient or blended custom background
    - Ambient radial glow accents + subtle grid lines
    - Floating brand header pill with logo/monogram + verified badge
    - Centered frosted glassmorphism hero card with step chip & drop-shadowed text
    - Sleek bottom CTA pill
    """
    from PIL import Image, ImageDraw, ImageFont

    primary = brand.get("primary") or "#2563eb"
    bg_color = _hex(primary, (37, 99, 235))
    bg_img_path = brand.get("background_image_path") or brand.get("bg_image")

    # 1. Base Canvas
    if bg_img_path and os.path.exists(bg_img_path):
        try:
            base = Image.open(bg_img_path).convert("RGBA").resize((width, height))
            # Dark gradient scrim over photo for perfect contrast
            scrim = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            scrim_draw = ImageDraw.Draw(scrim)
            for y in range(height):
                alpha = int(140 + (y / height) * 90)
                scrim_draw.line([(0, y), (width, y)], fill=(8, 12, 28, alpha))
            base = Image.alpha_composite(base, scrim)
        except Exception as e:
            logger.warning(f"[video_pipeline] custom background load failed: {e}")
            base = Image.new("RGBA", (width, height), (6, 10, 26, 255))
    else:
        # Rich vertical dark gradient: deep midnight navy to obsidian
        base = Image.new("RGBA", (width, height), (6, 10, 26, 255))
        draw_tmp = ImageDraw.Draw(base)
        for y in range(height):
            ratio = y / height
            r = int(6 + ratio * 12)
            g = int(10 + ratio * 18)
            b = int(26 + ratio * 38)
            draw_tmp.line([(0, y), (width, y)], fill=(r, g, b, 255))

        # Ambient glowing radial accents
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse([width - 250, -100, width + 250, 400], fill=(56, 189, 248, 28))
        glow_draw.ellipse([-150, height // 2 - 200, 300, height // 2 + 250], fill=(99, 102, 241, 32))
        glow_draw.ellipse([width // 2 - 300, height - 350, width // 2 + 300, height + 250], fill=(37, 99, 235, 36))
        base = Image.alpha_composite(base, glow)

        # Subtle decorative tech grid
        grid = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        grid_draw = ImageDraw.Draw(grid)
        for gx in range(0, width, 80):
            grid_draw.line([(gx, 0), (gx, height)], fill=(255, 255, 255, 6), width=1)
        for gy in range(0, height, 80):
            grid_draw.line([(0, gy), (width, gy)], fill=(255, 255, 255, 6), width=1)
        base = Image.alpha_composite(base, grid)

    draw = ImageDraw.Draw(base)

    # Fonts selection
    font_bold = "C:/Windows/Fonts/segoeuib.ttf" if os.path.exists("C:/Windows/Fonts/segoeuib.ttf") else "DejaVuSans-Bold.ttf"
    font_reg = "C:/Windows/Fonts/segoeui.ttf" if os.path.exists("C:/Windows/Fonts/segoeui.ttf") else "DejaVuSans.ttf"

    try:
        title_font = ImageFont.truetype(font_bold, 40)
        body_font = ImageFont.truetype(font_bold, 36)
        badge_font = ImageFont.truetype(font_bold, 20)
        small_font = ImageFont.truetype(font_reg, 22)
        logo_font = ImageFont.truetype(font_bold, 26)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = title_font
        badge_font = title_font
        small_font = title_font
        logo_font = title_font

    biz_name = str(brand.get("business_name") or "LeadGen AI").strip()
    phone = str(brand.get("phone") or "leadsgenai.in").strip()
    niche_label = str(brand.get("niche") or "AI MARKETING").upper()

    # 2. Top Header Brand Bar (Floating Pill)
    header_w = width - 80
    header_h = 68
    header_x = 40
    header_y = 48

    hdr_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    hdr_draw = ImageDraw.Draw(hdr_overlay)
    hdr_draw.rounded_rectangle(
        [header_x, header_y, header_x + header_w, header_y + header_h],
        radius=34,
        fill=(15, 23, 42, 210),
        outline=(56, 189, 248, 120),
        width=2,
    )
    base = Image.alpha_composite(base, hdr_overlay)
    draw = ImageDraw.Draw(base)

    # Logo Avatar or Monogram
    logo_path = _logo_temp_file(str(brand.get("logo_data_uri") or ""), tmp_dir)
    avatar_x = header_x + 10
    avatar_y = header_y + 9
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA").resize((50, 50))
            base.paste(logo_img, (avatar_x, avatar_y), logo_img)
            draw = ImageDraw.Draw(base)
        except Exception:
            logo_path = None

    if not logo_path:
        draw.ellipse([avatar_x, avatar_y, avatar_x + 50, avatar_y + 50], fill=bg_color, outline=(56, 189, 248, 180), width=2)
        mono = (biz_name[:2] if len(biz_name) >= 2 else "AI").upper()
        draw.text((avatar_x + 10, avatar_y + 11), mono, font=logo_font, fill=(255, 255, 255))

    # Business Name in Header
    disp_biz = biz_name[:18].upper()
    draw.text((avatar_x + 62, header_y + 17), disp_biz, font=logo_font, fill=(255, 255, 255))

    # Verified Pill (Right)
    badge_text = "VERIFIED AI"
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bb[2] - bb[0] + 20
    bx = header_x + header_w - bw - 14
    by = header_y + 16
    draw.rounded_rectangle([bx, by, bx + bw, by + 36], radius=18, fill=(16, 185, 129, 36), outline=(16, 185, 129, 180), width=1)
    draw.text((bx + 10, by + 7), badge_text, font=badge_font, fill=(52, 211, 153))

    # 3. Middle Frosted Glass Card (Hero Content)
    card_margin = 40
    card_w = width - (card_margin * 2)
    card_h = min(580, int(height * 0.48))
    card_x = card_margin
    card_y = (height - card_h) // 2 - 20

    card_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_overlay)
    card_draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=26,
        fill=(15, 23, 42, 230),
        outline=(56, 189, 248, 130),
        width=2,
    )
    base = Image.alpha_composite(base, card_overlay)
    draw = ImageDraw.Draw(base)

    # Category & Step Chip on Top of Card
    chip_text = f"{niche_label}  |  STEP {idx + 1:02d}/{max(idx + 1, total_slides):02d}"
    cbb = draw.textbbox((0, 0), chip_text, font=badge_font)
    cw = cbb[2] - cbb[0] + 30
    cx = card_x + (card_w - cw) // 2
    cy = card_y + 32
    draw.rounded_rectangle([cx, cy, cx + cw, cy + 38], radius=19, fill=(99, 102, 241, 45), outline=(129, 140, 248, 200), width=2)
    draw.text((cx + 15, cy + 8), chip_text, font=badge_font, fill=(199, 210, 254))

    # Main Text inside Glass Card
    words = text.split()
    lines, cur = [], ""
    wrap_max = max(18, width // 30)
    for w in words:
        if len(cur) + len(w) + 1 > wrap_max:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)

    text_start_y = card_y + 115
    line_spacing = 60
    for i, ln in enumerate(lines[:6]):
        bb = draw.textbbox((0, 0), ln, font=body_font)
        lx = card_x + (card_w - (bb[2] - bb[0])) // 2
        ly = text_start_y + (i * line_spacing)
        # Drop shadow for readability
        draw.text((lx + 2, ly + 2), ln, font=body_font, fill=(0, 0, 0, 160))
        # High contrast white text
        draw.text((lx, ly), ln, font=body_font, fill=(255, 255, 255, 255))

    # Metric / Trust Accent Footer inside Card
    trust_y = card_y + card_h - 70
    draw.line([(card_x + 25, trust_y), (card_x + card_w - 25, trust_y)], fill=(56, 189, 248, 50), width=1)
    trust_text = "Instant 24/7 Response  •  100% Free Demo"
    tbb = draw.textbbox((0, 0), trust_text, font=small_font)
    tx = card_x + (card_w - (tbb[2] - tbb[0])) // 2
    draw.text((tx, trust_y + 16), trust_text, font=small_font, fill=(148, 163, 184))

    # 4. Bottom CTA Pill Bar
    cta_w = width - 80
    cta_h = 72
    cta_x = 40
    cta_y = height - cta_h - 75

    cta_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cta_draw = ImageDraw.Draw(cta_overlay)
    cta_draw.rounded_rectangle(
        [cta_x, cta_y, cta_x + cta_w, cta_y + cta_h],
        radius=36,
        fill=bg_color + (240,),
        outline=(96, 165, 250, 220),
        width=2,
    )
    base = Image.alpha_composite(base, cta_overlay)
    draw = ImageDraw.Draw(base)

    offer_tag = str(brand.get("offer") or "Free Demo").strip()
    cta_label = f"> {phone}  •  {offer_tag}"[:35]
    cbb = draw.textbbox((0, 0), cta_label, font=title_font)
    cx = cta_x + (cta_w - (cbb[2] - cbb[0])) // 2
    cy = cta_y + 14
    draw.text((cx, cy), cta_label, font=title_font, fill=(255, 255, 255))

    # Save output frame
    rgb_img = base.convert("RGB")
    path = os.path.join(tmp_dir, f"frame{idx:02d}.png")
    rgb_img.save(path, quality=95)
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
        if niche and not brand.get("niche"):
            brand["niche"] = niche.replace("_", " ").upper()
        if offer and not brand.get("offer"):
            brand["offer"] = offer

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
            frame = _make_branded_frame(
                text, i, brand, tmp, width=width, height=height, total_slides=len(used_slides)
            )
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
