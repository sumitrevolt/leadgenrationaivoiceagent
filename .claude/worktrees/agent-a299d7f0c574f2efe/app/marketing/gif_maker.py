"""
gif_maker.py — PIL animated text GIF (Sale!/Offer stickers, WA/status ready).
==============================================================================

Chhote business ke liye 1-click animated GIF — text pop/pulse/blink on
brand-color background. 512x512, 8-12 frames, loop forever. Brand colors
`brand_kit.get_brand(slug)` se (saved ho to), warna default indigo/amber.

Public API (never-raise):
  - available()                          -> {"pillow": bool}
  - PRESETS                              -> Hinglish ready texts
  - make_gif(text, slug, style="pulse")  -> {"ok", "file", "url", ...}
        styles: pulse (saans jaisa scale) | pop (chhota→bada bounce) |
                blink (bg primary/accent alternate)

Output: data/gifs/<slug>/<hash>.gif — serve /api/contentplus/gif-file/{slug}/{name}.
HEAVY-lite (PIL CPU) — endpoint asyncio.to_thread se chalata hai.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_GIF_DIR = os.path.join("data", "gifs")
_SIZE = 512
_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]")

PRESETS: list[str] = [
    "Sale!",
    "Offer Hai!",
    "Shukriya 🙏",
    "Naya Stock Aaya!",
    "Aaj Hi Book Karein!",
    "Diwali Dhamaka!",
]

_DEFAULT_PRIMARY = "#4f46e5"
_DEFAULT_ACCENT = "#f59e0b"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def available() -> dict[str, Any]:
    try:
        import PIL  # noqa: F401

        return {"pillow": True}
    except Exception:
        return {"pillow": False}


def _safe_slug(slug: Any) -> str:
    s = _SAFE_RE.sub("_", str(slug or "").strip())[:64]
    return s or "default"


def _brand_colors(slug: str) -> tuple[str, str]:
    primary, accent = _DEFAULT_PRIMARY, _DEFAULT_ACCENT
    try:
        from app.marketing import brand_kit

        brand = brand_kit.get_brand(slug) or {}
        colors = brand.get("colors") or {}
        p, a = str(colors.get("primary") or ""), str(colors.get("accent") or "")
        if _HEX_RE.match(p):
            primary = p
        if _HEX_RE.match(a):
            accent = a
    except Exception:
        pass
    return primary, accent


def _font(size: int):
    """Best-effort bold font — truetype candidates, warna default."""
    from PIL import ImageFont

    for cand in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10
    except Exception:
        return ImageFont.load_default()


def _draw_frame(text: str, bg: str, scale: float):
    """Ek frame — centered text, scale ke hisaab se font size."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (_SIZE, _SIZE), bg)
    d = ImageDraw.Draw(img)
    base = 88 if len(text) <= 10 else (64 if len(text) <= 18 else 44)
    size = max(12, int(base * max(0.05, scale)))
    font = _font(size)
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (_SIZE - w) / 2 - bbox[0], (_SIZE - h) / 2 - bbox[1]
    except Exception:
        x, y = _SIZE * 0.2, _SIZE * 0.45
    # soft shadow + white text
    try:
        d.text((x + 3, y + 3), text, font=font, fill="#00000055")
    except Exception:
        pass
    d.text((x, y), text, font=font, fill="#ffffff")
    return img


def make_gif(text: str = "", slug: str = "default", style: str = "pulse") -> dict[str, Any]:
    """Animated text GIF banao (512², 10 frames, loop). Never raises.

    Returns {"ok", "file", "url", "frames", "style"} ya {"ok": False, ...}.
    """
    try:
        if not available()["pillow"]:
            return {
                "ok": False,
                "reason": "pillow_missing",
                "hint": "Pillow install karo — `pip install Pillow`.",
            }
        text = str(text or "").strip() or PRESETS[0]
        text = text[:40]
        slug = _safe_slug(slug)
        style = str(style or "pulse").strip().lower()
        if style not in {"pulse", "pop", "blink"}:
            style = "pulse"
        primary, accent = _brand_colors(slug)

        n = 10
        frames = []
        for i in range(n):
            t = i / (n - 1)
            if style == "pop":
                # chhota → overshoot → settle
                scale = 0.3 + 0.9 * min(1.0, t * 1.6)
                if t > 0.7:
                    scale = 1.0 + 0.08 * math.sin((t - 0.7) / 0.3 * math.pi)
                bg = primary
            elif style == "blink":
                scale = 1.0
                bg = primary if (i // 2) % 2 == 0 else accent
            else:  # pulse
                scale = 1.0 + 0.12 * math.sin(2 * math.pi * t)
                bg = primary
            frames.append(_draw_frame(text, bg, scale))

        out_dir = os.path.join(_GIF_DIR, slug)
        os.makedirs(out_dir, exist_ok=True)
        name = hashlib.sha1(f"{text}|{style}|{primary}".encode()).hexdigest()[:10] + ".gif"
        path = os.path.join(out_dir, name)
        frames[0].save(
            path, save_all=True, append_images=frames[1:], duration=90, loop=0, optimize=True
        )
        return {
            "ok": True,
            "file": name,
            "path": path,
            "url": f"/api/contentplus/gif-file/{slug}/{name}",
            "frames": n,
            "style": style,
            "text": text,
            "note": "WA status / story ke liye ready — 1-click download + share.",
        }
    except Exception as e:  # absolute guard
        logger.warning(f"[gif_maker] make_gif failed: {e}")
        return {"ok": False, "reason": "error", "error": str(e)[:200]}


__all__ = ["available", "make_gif", "PRESETS"]
