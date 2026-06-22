"""
catalog.py — price-list catalog card + WhatsApp catalog text (free stack).
===========================================================================

Chhote business ka digital catalog:
  - build_catalog(business_name, items, style="price_list") -> dict:
      1080x1350 SVG price-list card (brand violet header, rows naam….₹price,
      max 12 items) + WhatsApp catalog-style text (numbered + order CTA) +
      per-item 1-line AI descriptions (SINGLE LLM call via free_ai;
      fallback = item ka apna desc ya naam as-is — KABHI empty nahi).

Sab inputs XML-escaped (injection-safe). Generator kabhi raise nahi karta.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

_FONT = "Segoe UI, Arial, sans-serif"
_MAX_ITEMS = 12

_DESC_LINE_RE = re.compile(r"^\s*(\d+)\s*[.)\-:]\s*(.+)$")


def _fmt_price(raw: Any) -> str:
    """Price ko display string me: 249 -> '₹249'; non-numeric string as-is."""
    s = str(raw if raw is not None else "").strip()
    if not s:
        return ""
    cleaned = s.replace("₹", "").replace(",", "").replace("Rs.", "").replace("Rs", "").strip()
    try:
        val = float(cleaned)
        if val < 0:
            return ""
        txt = f"{int(val)}" if abs(val - int(val)) < 1e-9 else f"{val:.2f}"
        return f"₹{txt}"
    except Exception:
        return s[:14]


def _norm_items(items: Any) -> list[dict[str, str]]:
    """Items normalize: [{'name','price','desc'}] — khali naam skip, cap 12."""
    out: list[dict[str, str]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()[:80]
        if not name:
            continue
        out.append(
            {
                "name": name,
                "price": _fmt_price(it.get("price")),
                "desc": str(it.get("desc") or "").strip()[:160],
            }
        )
        if len(out) >= _MAX_ITEMS:
            break
    return out


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else (s[: n - 1].rstrip() + "…")


def _catalog_svg(biz: str, items: list[dict[str, str]]) -> str:
    """1080x1350 price-list card. Inputs escape karke hi aate hain."""
    rows: list[str] = []
    y = 330
    for it in items:
        name = escape(_clip(it["name"], 30), quote=True)
        price = escape(_clip(it["price"] or "—", 14), quote=True)
        desc = escape(_clip(it["desc"], 58), quote=True)
        rows.append(
            f'<text x="80" y="{y}" font-family="{_FONT}" font-size="33" '
            f'font-weight="bold" fill="#1e1b2e" text-anchor="start">{name}</text>'
            f'<text x="1000" y="{y}" font-family="{_FONT}" font-size="33" '
            f'font-weight="bold" fill="#6d28d9" text-anchor="end">{price}</text>'
        )
        if desc:
            rows.append(
                f'<text x="80" y="{y + 32}" font-family="{_FONT}" font-size="21" '
                f'fill="#6b7280" text-anchor="start">{desc}</text>'
            )
        rows.append(
            f'<line x1="80" y1="{y + 44}" x2="1000" y2="{y + 44}" '
            'stroke="#c4b5fd" stroke-width="2" stroke-dasharray="2,7" opacity="0.7"/>'
        )
        y += 78
    biz_esc = escape(_clip(biz, 30), quote=True)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350" viewBox="0 0 1080 1350">'
        '<defs><linearGradient id="catbg" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#6d28d9"/><stop offset="100%" stop-color="#4f46e5"/>'
        "</linearGradient></defs>"
        '<rect width="1080" height="1350" fill="#ffffff"/>'
        '<rect width="1080" height="220" fill="url(#catbg)"/>'
        f'<text x="540" y="105" font-family="{_FONT}" font-size="52" font-weight="bold" '
        f'fill="#ffffff" text-anchor="middle">{biz_esc}</text>'
        f'<text x="540" y="172" font-family="{_FONT}" font-size="30" fill="#ddd6fe" '
        'text-anchor="middle">✨ Price List ✨</text>'
        + "".join(rows)
        + '<rect x="140" y="1252" width="800" height="70" rx="35" fill="#6d28d9"/>'
        f'<text x="540" y="1298" font-family="{_FONT}" font-size="30" font-weight="bold" '
        'fill="#ffffff" text-anchor="middle">📞 Order / Enquiry — WhatsApp karein</text>'
        "</svg>"
    )


def _wa_catalog_text(biz: str, items: list[dict[str, str]]) -> str:
    lines = [f"🛍️ *{biz} — Price List*", ""]
    for i, it in enumerate(items, 1):
        price = f" — {it['price']}" if it["price"] else ""
        lines.append(f"{i}. {it['name']}{price}")
        if it["desc"]:
            lines.append(f"   _{_clip(it['desc'], 80)}_")
    lines += ["", "📲 Order karne ke liye isi number par message karein — aaj hi!"]
    return "\n".join(lines)


async def _ai_descriptions(biz: str, items: list[dict[str, str]]) -> str:
    """SINGLE LLM call — har item ki 1-line Hinglish selling line. '' = fail."""
    if free_ai is None or not items:
        return ""
    menu = "\n".join(
        f"{i}. {it['name']}" + (f" ({it['price']})" if it["price"] else "")
        for i, it in enumerate(items, 1)
    )
    system = (
        "Tu ek Indian local business ka marketing copywriter hai. Har item ke "
        "liye EK chhoti (max 10 shabd) Hinglish selling line likh jo customer "
        "ko lalchaye. Output format: har line par 'N. description' (N = item "
        "number). Koi extra commentary/heading nahi."
    )
    try:
        text, provider = await free_ai.chat(
            system,
            [{"role": "user", "content": f"Business: {biz}\nItems:\n{menu}"}],
            max_tokens=320,
            temperature=0.7,
        )
        if text and text.strip():
            return text.strip()
    except Exception as e:  # free_ai.chat khud nahi raise karta, par safety
        logger.warning(f"build_catalog LLM failed, using fallback: {e}")
    return ""


async def build_catalog(
    business_name: str, items: list[dict[str, Any]], style: str = "price_list"
) -> dict[str, Any]:
    """Catalog kit: SVG card + WA text + AI item-descriptions. Kabhi raise nahi.

    Descriptions: LLM 1 call; fail/missing par item ka apna desc, warna NAAM
    as-is (never-empty guarantee).
    """
    biz = (business_name or "").strip()[:120] or "Aapka Business"
    norm = _norm_items(items)
    provider = "template"

    if norm:
        raw = await _ai_descriptions(biz, norm)
        ai_map: dict[int, str] = {}
        for ln in raw.splitlines():
            m = _DESC_LINE_RE.match(ln)
            if m:
                ai_map[int(m.group(1))] = m.group(2).strip()[:90]
        if ai_map:
            provider = "llm"
        for i, it in enumerate(norm, 1):
            it["desc"] = (ai_map.get(i) or it["desc"] or it["name"]).strip()[:90]

    try:
        svg = _catalog_svg(biz, norm)
    except Exception as e:  # pragma: no cover - deterministic
        logger.error(f"catalog svg failed: {e}")
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350">'
            f'<rect width="1080" height="1350" fill="#6d28d9"/>'
            f'<text x="540" y="675" font-family="{_FONT}" font-size="56" fill="#ffffff" '
            f'text-anchor="middle">{escape(biz, quote=True)}</text></svg>'
        )

    return {
        "business_name": biz,
        "style": (style or "price_list").strip() or "price_list",
        "items": norm,
        "count": len(norm),
        "svg": svg,
        "width": 1080,
        "height": 1350,
        "wa_catalog_text": _wa_catalog_text(biz, norm),
        "provider": provider,
        "tip": "PNG download karke WhatsApp status + Instagram pe lagao; "
        "text version broadcast list me bhejo.",
    }
