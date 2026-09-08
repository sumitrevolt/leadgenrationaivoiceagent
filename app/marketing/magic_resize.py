"""
magic_resize.py — ek creative → saare social sizes (Canva "Magic Resize" lite).
================================================================================

Ek poster/photo do → square (IG), story (IG/FB), banner (FB/link preview),
wa_status — sab ek shot me. Raster input PIL se smart-letterbox hota hai
(brand primary color background — brand_kit se); SVG input ko letterboxed
SVG wrapper milta hai (no rasterizer dep).

  resize_pack(image_path=None, svg=None, sizes=None, slug="")
      -> {"ok", "files": {size: path}}   (raster → data/resized/*.png)
      -> {"ok", "svgs": {size: svg}}     (svg input)

Lazy PIL import, kabhi raise nahi — error pe {"ok": False, "error": ...}.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RESIZED_DIR = os.path.join("data", "resized")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_SVG_DIM_RE = re.compile(r'<svg[^>]*?\bwidth="(\d+)"[^>]*?\bheight="(\d+)"', re.I)

SIZES: dict[str, tuple[int, int]] = {
    "square": (1080, 1080),  # Instagram/GBP post
    "story": (1080, 1920),  # IG/FB story
    "banner": (1200, 628),  # FB/link-preview/ads banner
    "wa_status": (1080, 1920),  # WhatsApp status
}


def _bg_color(slug: str) -> str:
    """Brand primary color (brand_kit/clients_store se) warna safe white."""
    try:
        if slug:
            from app.marketing import brand_frames

            c = (brand_frames.resolve_brand(slug) or {}).get("primary") or ""
            if _HEX_RE.match(str(c)):
                return str(c)
    except Exception as e:  # pragma: no cover
        logger.debug(f"[magic_resize] brand color skip: {e}")
    return "#ffffff"


def _clean_sizes(sizes: Any) -> list[str]:
    if isinstance(sizes, str):
        sizes = [s.strip() for s in sizes.split(",")]
    if not isinstance(sizes, (list, tuple)) or not sizes:
        return list(SIZES.keys())
    out = [str(s).strip().lower() for s in sizes if str(s).strip().lower() in SIZES]
    return out or list(SIZES.keys())


def resize_pack(
    image_path: str | None = None,
    svg: str | None = None,
    sizes: Any = None,
    slug: str = "",
) -> dict[str, Any]:
    """Ek creative ko saare maange gaye social sizes me convert karo.

    image_path = raster file (png/jpg/webp) → PNG files data/resized/ me.
    svg        = SVG string → per-size letterboxed SVG wrapper strings.
    sizes      = list ya comma-string (default sab 4). Kabhi raise nahi.
    """
    try:
        wanted = _clean_sizes(sizes)
        if svg and str(svg).lstrip().lower().startswith("<svg"):
            return _resize_svg(str(svg), wanted, slug)
        path = str(image_path or "").strip()
        if not path:
            return {"ok": False, "error": "image_path ya svg do — dono khali hain."}
        if not os.path.isfile(path):
            return {"ok": False, "error": f"file nahi mili: {os.path.basename(path)[:80]}"}
        return _resize_raster(path, wanted, slug)
    except Exception as e:
        logger.warning(f"[magic_resize] resize_pack failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def _resize_raster(path: str, wanted: list[str], slug: str) -> dict[str, Any]:
    from PIL import Image  # lazy — heavy dep

    bg = _bg_color(slug)
    src = Image.open(path).convert("RGB")
    os.makedirs(_RESIZED_DIR, exist_ok=True)
    tag = re.sub(r"[^a-z0-9-]", "", (slug or "img").lower())[:32] or "img"
    batch = uuid.uuid4().hex[:8]
    files: dict[str, str] = {}
    for size_name in wanted:
        w, h = SIZES[size_name]
        canvas = Image.new("RGB", (w, h), bg)
        im = src.copy()
        im.thumbnail((w, h), Image.LANCZOS)
        canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
        out_path = os.path.join(_RESIZED_DIR, f"{tag}-{size_name}-{batch}.png")
        canvas.save(out_path, "PNG")
        files[size_name] = out_path
    return {
        "ok": True,
        "format": "png",
        "files": files,
        "note": "Har size 1-click download karke us platform pe daalo.",
    }


def _resize_svg(svg: str, wanted: list[str], slug: str) -> dict[str, Any]:
    """SVG ko per-size letterbox wrapper me daalo (scale + center, bg = brand)."""
    bg = _bg_color(slug)
    m = _SVG_DIM_RE.search(svg)
    sw, sh = (int(m.group(1)), int(m.group(2))) if m else (1080, 1080)
    sw = max(1, sw)
    sh = max(1, sh)
    svgs: dict[str, str] = {}
    for size_name in wanted:
        w, h = SIZES[size_name]
        scale = min(w / sw, h / sh)
        tx = (w - sw * scale) / 2
        ty = (h - sh * scale) / 2
        svgs[size_name] = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>'
            f'<g transform="translate({tx:.1f},{ty:.1f}) scale({scale:.4f})">{svg}</g>'
            f"</svg>"
        )
    return {"ok": True, "format": "svg", "svgs": svgs}


__all__ = ["resize_pack", "SIZES"]
