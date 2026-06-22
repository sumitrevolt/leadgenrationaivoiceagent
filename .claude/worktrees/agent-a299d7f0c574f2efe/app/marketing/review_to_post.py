"""
review_to_post.py — 4-5★ review → branded thank-you poster + caption.
======================================================================

Khush customer ka review = sabse sasta marketing asset. Yeh module 4-5 star
review ko ek share-ready "thank you" poster (SVG, brand colors) + Hinglish
caption me badal deta hai (free-LLM caption, deterministic fallback).

  from_review(review_text, author, rating, slug) ->
      {"ok", "svg", "caption", "rating", "author"}

<4 star = politely reject (negative review ko poster mat banao — review_engine
ka private-feedback path use karo). Sab text XML-escaped. Kabhi raise nahi.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FONT = "Segoe UI, Arial, sans-serif"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _safe_color(c: Any, default: str) -> str:
    s = str(c or "").strip()
    return s if _HEX_RE.match(s) else default


def _wrap(text: str, width: int = 38, max_lines: int = 6) -> list[str]:
    """Word-wrap (greedy). Lambi review truncate hoti hai '…' ke saath."""
    words = str(text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if lines and len(" ".join(lines)) < len(" ".join(words)):
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    return lines or ["Bahut badhiya service!"]


def _poster_svg(review: str, author: str, rating: int, brand: dict[str, Any]) -> str:
    primary = _safe_color(brand.get("primary"), "#10203a")
    accent = _safe_color(brand.get("accent"), "#ffd56b")
    name = escape(str(brand.get("business_name") or "Aapka Business")[:48], quote=True)
    phone = escape(str(brand.get("phone") or "")[:20], quote=True)
    author_e = escape(str(author or "Khush Customer")[:40], quote=True)
    stars = "★" * max(1, min(5, rating)) + "☆" * (5 - max(1, min(5, rating)))

    lines = [escape(ln, quote=True) for ln in _wrap(review)]
    tspans = "".join(
        f'<tspan x="540" dy="{0 if i == 0 else 52}">{ln}</tspan>' for i, ln in enumerate(lines)
    )
    review_block_y = 430 - (len(lines) - 1) * 22

    phone_line = (
        f'<text x="540" y="990" font-family="{_FONT}" font-size="30" fill="#ffffff" '
        f'text-anchor="middle">\U0001f4de {phone}</text>'
        if phone
        else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
        f"<defs>"
        f'<linearGradient id="rvbg" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{primary}"/>'
        f'<stop offset="100%" stop-color="#111827"/>'
        f"</linearGradient>"
        f"</defs>"
        f'<rect width="1080" height="1080" fill="url(#rvbg)"/>'
        f'<text x="120" y="200" font-family="Georgia, serif" font-size="220" fill="{accent}" '
        f'opacity="0.35">“</text>'
        f'<text x="540" y="150" font-family="{_FONT}" font-size="40" font-weight="bold" '
        f'fill="{accent}" text-anchor="middle">⭐ Khush Customer!</text>'
        f'<text x="540" y="240" font-family="{_FONT}" font-size="52" fill="{accent}" '
        f'text-anchor="middle" letter-spacing="8">{stars}</text>'
        f'<text x="540" y="{review_block_y}" font-family="{_FONT}" font-size="36" '
        f'fill="#ffffff" text-anchor="middle" font-style="italic">{tspans}</text>'
        f'<text x="540" y="720" font-family="{_FONT}" font-size="30" fill="{accent}" '
        f'text-anchor="middle">— {author_e}</text>'
        f'<rect x="240" y="790" width="600" height="4" fill="{accent}" opacity="0.6"/>'
        f'<text x="540" y="880" font-family="{_FONT}" font-size="46" font-weight="bold" '
        f'fill="#ffffff" text-anchor="middle">{name}</text>'
        f'<text x="540" y="930" font-family="{_FONT}" font-size="26" fill="#d1d5db" '
        f'text-anchor="middle">Aapka bharosa, hamari shaan \U0001f64f</text>'
        f"{phone_line}"
        f"</svg>"
    )


def _fallback_caption(review: str, author: str, business: str) -> str:
    short = str(review or "").strip()
    if len(short) > 120:
        short = short[:117].rstrip() + "…"
    return (
        f'⭐ Khush customer! "{short}" — {author or "ek pyara customer"}.\n'
        f"Shukriya {business}! Aise reviews hi hamari asli kamai hain. \U0001f64f\n"
        f"Aap bhi service ka anubhav lijiye — abhi sampark karein!"
    )


async def from_review(
    review_text: str, author: str = "", rating: int = 5, slug: str = ""
) -> dict[str, Any]:
    """4-5★ review → branded thank-you poster SVG + Hinglish caption.

    rating < 4 → {"ok": False, ...} (negative review public poster NAHI banana).
    Kabhi raise nahi, caption kabhi empty nahi.
    """
    try:
        try:
            r = int(rating)
        except Exception:
            r = 5
        if r < 4:
            return {
                "ok": False,
                "error": "Sirf 4-5 star reviews se poster banta hai — kam rating ko "
                "private feedback me lo (review_engine).",
            }
        text = str(review_text or "").strip()[:600] or "Bahut badhiya service, highly recommended!"
        author_c = str(author or "").strip()[:60]

        from app.marketing import brand_frames

        brand = brand_frames.resolve_brand(slug)
        business = brand.get("business_name") or "Aapka Business"

        caption = ""
        try:
            from app.voice_agent import free_ai

            raw, _ = await free_ai.chat(
                (
                    "Tu Indian local-business ka social media writer hai. Ek customer review "
                    "ko thank-you post caption me badal (Hinglish, 2-3 lines, emojis, "
                    "gratitude + halka CTA). Sirf caption likh, koi commentary nahi."
                ),
                [
                    {
                        "role": "user",
                        "content": f"Business: {business}. Review ({r}★) by "
                        f"{author_c or 'customer'}: {text}",
                    }
                ],
                max_tokens=200,
                temperature=0.8,
            )
            caption = (raw or "").strip()[:500]
        except Exception as e:
            logger.debug(f"[review_to_post] llm caption fallback: {e}")
        if not caption:
            caption = _fallback_caption(text, author_c, business)

        return {
            "ok": True,
            "svg": _poster_svg(text, author_c, r, brand),
            "caption": caption,
            "rating": r,
            "author": author_c or "Khush Customer",
            "business_name": business,
            "note": "Poster download karke caption ke saath post karo — social proof gold hai.",
        }
    except Exception as e:
        logger.warning(f"[review_to_post] from_review failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["from_review"]
