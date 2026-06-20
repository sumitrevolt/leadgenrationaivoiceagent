"""
sticker_pack.py — WhatsApp sticker pack (6 PNG, 512x512 transparent) per client.
=================================================================================

Chhote business WhatsApp pe hi chalte hain — apne brand-color Hinglish stickers
("Shukriya!", "Offer Hai!", ...) = roz free branding har chat me. PIL text-art
(system fonts; emoji glyph dependency NAHI — shapes se accent), transparent
512x512 = WhatsApp sticker spec.

  generate_stickers(slug="", business_name="", niche="") ->
      {"ok", "dir", "files": [6 paths], "count": 6}

Files: data/stickers/<slug>/sticker_<n>.png. Lazy PIL import. Kabhi raise
nahi — error pe {"ok": False, "error": ...}.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STICKERS_DIR = os.path.join("data", "stickers")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# (badi line, chhoti line) — pure latin text (PIL system fonts emoji nahi
# khinch paate; accent shapes code se bante hain).
_STICKER_TEXTS: list[tuple[str, str]] = [
    ("Shukriya!", "Aapka bharosa anmol hai"),
    ("Offer Hai!", "Aaj hi poochhiye"),
    ("Welcome Ji!", "Seva me hazir hain"),
    ("Ho Gaya!", "Kaam done, tension gone"),
    ("Call Karo", "Turant jawab milega"),
    ("5-Star Kaam", "Quality ki guarantee"),
]


def _safe_color(c: Any, default: str) -> str:
    s = str(c or "").strip()
    return s if _HEX_RE.match(s) else default


def _hex_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _load_font(size: int):
    from PIL import ImageFont  # lazy

    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:  # pragma: no cover - old Pillow
        return ImageFont.load_default()


def _fit_font(draw, text: str, max_width: int, start: int = 88, floor: int = 30):
    """Text ko max_width me fit karne wala sabse bada font."""
    size = start
    font = _load_font(size)
    while size > floor:
        w = draw.textlength(text, font=font)
        if w <= max_width:
            break
        size -= 6
        font = _load_font(size)
    return font


def _star_points(cx: float, cy: float, r_out: float, r_in: float) -> list[tuple[float, float]]:
    import math

    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    return pts


def _draw_sticker(big: str, small: str, brand_name: str, primary: str, accent: str) -> Any:
    """Ek 512x512 RGBA transparent sticker image."""
    from PIL import Image, ImageDraw  # lazy

    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    p_rgb = _hex_rgb(primary)
    a_rgb = _hex_rgb(accent)

    # Badge: rounded rect with white border (sticker look)
    draw.rounded_rectangle(
        [26, 96, 486, 416], radius=70, fill=p_rgb + (255,), outline=(255, 255, 255, 255), width=10
    )
    # Accent star (top-left) + dot (bottom-right)
    draw.polygon(_star_points(88, 96, 44, 18), fill=a_rgb + (255,), outline=(255, 255, 255, 255))
    draw.ellipse([432, 380, 488, 436], fill=a_rgb + (255,), outline=(255, 255, 255, 255), width=6)

    # Texts (centered)
    f_big = _fit_font(draw, big, 400, start=92, floor=36)
    w_big = draw.textlength(big, font=f_big)
    draw.text(((512 - w_big) / 2, 180), big, font=f_big, fill=(255, 255, 255, 255))

    f_small = _fit_font(draw, small, 400, start=38, floor=20)
    w_small = draw.textlength(small, font=f_small)
    draw.text(((512 - w_small) / 2, 296), small, font=f_small, fill=a_rgb + (255,))

    # Brand name footer pill
    f_brand = _fit_font(draw, brand_name, 360, start=32, floor=18)
    w_brand = draw.textlength(brand_name, font=f_brand)
    pill_w = min(440, int(w_brand) + 48)
    x0 = (512 - pill_w) / 2
    draw.rounded_rectangle([x0, 432, x0 + pill_w, 492], radius=30, fill=(255, 255, 255, 235))
    draw.text(((512 - w_brand) / 2, 444), brand_name, font=f_brand, fill=p_rgb + (255,))
    return img


def generate_stickers(slug: str = "", business_name: str = "", niche: str = "") -> dict[str, Any]:
    """6 WhatsApp stickers (512x512 transparent PNG) brand colors me banao.

    slug se brand auto-resolve (clients_store/brand_kit); business_name override
    bhi de sakte ho. Files data/stickers/<slug>/ me. Kabhi raise nahi.
    """
    try:
        brand: dict[str, Any] = {}
        try:
            from app.marketing import brand_frames

            brand = brand_frames.resolve_brand(slug) if slug else {}
        except Exception:
            brand = {}
        name = (business_name or "").strip() or str(brand.get("business_name") or "Aapka Business")
        name = name[:30]
        primary = _safe_color(brand.get("primary"), "#0b5fff")
        accent = _safe_color(brand.get("accent"), "#ffd56b")

        tag = re.sub(r"[^a-z0-9-]", "", (slug or name).lower().replace(" ", "-"))[:48] or "pack"
        out_dir = os.path.join(_STICKERS_DIR, tag)
        os.makedirs(out_dir, exist_ok=True)

        files: list[str] = []
        for i, (big, small) in enumerate(_STICKER_TEXTS, start=1):
            img = _draw_sticker(big, small, name, primary, accent)
            path = os.path.join(out_dir, f"sticker_{i}.png")
            img.save(path, "PNG")
            files.append(path)

        return {
            "ok": True,
            "dir": out_dir,
            "files": files,
            "count": len(files),
            "business_name": name,
            "note": "WhatsApp pe 'Sticker Maker' jaisi app me yeh 6 PNG import karke "
            "pack banao — har chat me free branding.",
        }
    except Exception as e:
        logger.warning(f"[sticker_pack] generate_stickers failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def safe_sticker_path(slug: str, name: str) -> str | None:
    """Regex-locked file path (serve endpoint ke liye) — traversal-safe."""
    try:
        tag = re.sub(r"[^a-z0-9-]", "", str(slug or "").lower())[:48]
        if not tag or not re.match(r"^sticker_[1-9]\d?\.png$", str(name or "")):
            return None
        p = os.path.join(_STICKERS_DIR, tag, name)
        return p if os.path.isfile(p) else None
    except Exception:
        return None


__all__ = ["generate_stickers", "safe_sticker_path"]
