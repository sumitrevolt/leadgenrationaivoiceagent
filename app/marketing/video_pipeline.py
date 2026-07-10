"""Staged video-creative pipeline for Product One — replaces reel_video's flat
PIL-slide template with brand overlay + Ken-Burns motion + captions + optional
music, on an isolated `video` Celery queue. Phase 1 = generic recipe only.

Never raises across the public entry point — same convention as reel_video,
content_approval, delivery_ledger. See docs/superpowers/specs/
2026-07-10-product-one-video-creative-pipeline-design.md for full design.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_W, _H = 720, 1280  # matches reel_video._W, _H — 9:16 reel


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
