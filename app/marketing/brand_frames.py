"""
brand_frames.py — AdBanao-killer branded frames + daily ready-post feed.
=========================================================================

Kisi bhi template (SVG poster ya raster image) ke neeche client ka BRAND
FRAME (logo + business name + phone strip) overlay karo — AdBanao ka core
"apna naam-number wala poster" experience, free-stack me.

  compose_frame(template, brand)        -> {"ok", "svg"} ya {"ok", "png_path"}
  daily_feed(slug_or_id, date=None)     -> {"ok", "posts": [3 ready posts]}
       har post = festival/quote/offer template × client brand frame + caption
       (free-LLM caption, deterministic template fallback — KABHI empty nahi).

Reuses (REBUILD NAHI): posters.generate_poster (SVG templates + brand colors),
festivals.upcoming (calendar), brand_kit.get_brand, clients_store (slug→client),
data/logos/ (minisite_builder ke uploaded logos — `<slug>-<rand>.<ext>`).

Sab inputs XML-escaped (injection-safe). Top-level fns kabhi raise nahi —
error pe {"ok": False, "error": ...}.
"""

from __future__ import annotations

import base64
import glob
import json
import os
import re
import uuid
from datetime import date as _date
from datetime import datetime
from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FONT = "Segoe UI, Arial, sans-serif"
_LOGOS_DIR = os.path.join("data", "logos")
_FRAMES_DIR = os.path.join("data", "frames")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_SVG_DIM_RE = re.compile(r'<svg[^>]*?\bwidth="(\d+)"[^>]*?\bheight="(\d+)"', re.I)

_STRIP_H = 110  # bottom brand strip height (px)

# Deterministic Hinglish business quotes (day-of-year rotation — fallback feed)
_QUOTES = [
    "Mehnat ka koi shortcut nahi — bas roz thoda behtar.",
    "Customer ka bharosa hi sabse bada brand hai.",
    "Quality yaad rehti hai, daam bhool jaate hain.",
    "Aaj ka chhota kadam, kal ka bada business.",
    "Time pe service = free me marketing.",
    "Sapne bade rakho, kaam roz karo.",
    "Jo dikhta hai wahi bikta hai — roz post karo!",
]

_OFFER_LINES = [
    "Aaj ka Special Offer — abhi poochhein!",
    "Pehli booking par khaas discount!",
    "Limited slots — jaldi karein!",
    "Is hafte ki dhamaka deal!",
]


def _safe_color(c: Any, default: str) -> str:
    s = str(c or "").strip()
    return s if _HEX_RE.match(s) else default


def resolve_brand(slug_or_id: str) -> dict[str, Any]:
    """slug YA client_id → merged brand dict (clients_store + brand_kit).

    Hamesha dict deta hai (na mile to safe defaults) — kabhi raise nahi.
    Keys: client_id, slug, business_name, phone, tagline, niche, city,
    primary, accent, logo_data_uri.
    """
    out: dict[str, Any] = {
        "client_id": "",
        "slug": "",
        "business_name": "Aapka Business",
        "phone": "",
        "tagline": "",
        "niche": "general",
        "city": "",
        "primary": "",
        "accent": "",
        "logo_data_uri": "",
    }
    key = str(slug_or_id or "").strip()
    if not key:
        return out
    try:
        from app.marketing import clients_store

        client = clients_store.get_by_slug(key) or clients_store.get_client(key)
        if client:
            b = client.get("brand") or {}
            out.update(
                {
                    "client_id": str(client.get("id") or ""),
                    "slug": str(client.get("slug") or ""),
                    "business_name": str(client.get("business_name") or out["business_name"]),
                    "phone": str(client.get("phone") or ""),
                    "tagline": str(b.get("tagline") or ""),
                    "niche": str(client.get("niche") or "general"),
                    "city": str(client.get("city") or ""),
                    "primary": _safe_color(b.get("primary"), ""),
                    "accent": _safe_color(b.get("accent"), ""),
                }
            )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"[brand_frames] clients_store lookup skip: {e}")
    try:
        from app.marketing import brand_kit

        bk = brand_kit.get_brand(out["client_id"] or key)
        if bk:
            colors = bk.get("colors") or {}
            out["business_name"] = (
                out["business_name"]
                if out["business_name"] != "Aapka Business"
                else (bk.get("business_name") or out["business_name"])
            )
            out["phone"] = out["phone"] or str(bk.get("phone") or "")
            out["tagline"] = out["tagline"] or str(bk.get("tagline") or "")
            out["primary"] = out["primary"] or _safe_color(colors.get("primary"), "")
            out["accent"] = out["accent"] or _safe_color(colors.get("accent"), "")
    except Exception as e:  # pragma: no cover
        logger.debug(f"[brand_frames] brand_kit lookup skip: {e}")
    out["logo_data_uri"] = _find_logo_data_uri(out["slug"], out["client_id"])
    return out


def _find_logo_data_uri(slug: str, client_id: str = "") -> str:
    """data/logos/ me `<slug>-*.png|jpg|webp` ka newest file → base64 data URI.

    Logo na mile / read fail = "" (kabhi raise nahi). 1MB cap (SVG bloat na ho).
    """
    try:
        candidates: list[str] = []
        for key in (slug, client_id):
            k = str(key or "").strip()
            if not k:
                continue
            for ext in ("png", "jpg", "jpeg", "webp"):
                candidates.extend(glob.glob(os.path.join(_LOGOS_DIR, f"{k}-*.{ext}")))
        if not candidates:
            return ""
        newest = max(candidates, key=lambda p: os.path.getmtime(p))
        if os.path.getsize(newest) > 1_000_000:
            return ""
        ext = newest.rsplit(".", 1)[-1].lower()
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(ext, "image/png")
        with open(newest, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as e:  # pragma: no cover
        logger.debug(f"[brand_frames] logo lookup skip: {e}")
        return ""


def _strip_svg(width: int, y: int, brand: dict[str, Any]) -> str:
    """Bottom brand strip ka SVG fragment (logo + naam + phone). Escaped."""
    primary = _safe_color(brand.get("primary"), "#10203a")
    accent = _safe_color(brand.get("accent"), "#ffd56b")
    name = escape(str(brand.get("business_name") or "Aapka Business")[:48], quote=True)
    phone = escape(str(brand.get("phone") or "")[:20], quote=True)
    logo = str(brand.get("logo_data_uri") or "")
    text_x = 30
    parts = [
        f'<g id="brand-strip"><rect x="0" y="{y}" width="{width}" height="{_STRIP_H}" fill="{primary}"/>',
        f'<rect x="0" y="{y}" width="{width}" height="6" fill="{accent}"/>',
    ]
    if logo.startswith("data:image/"):
        parts.append(
            f'<image href="{logo}" x="22" y="{y + 18}" width="76" height="76" '
            'preserveAspectRatio="xMidYMid meet"/>'
        )
        text_x = 118
    parts.append(
        f'<text x="{text_x}" y="{y + 52}" font-family="{_FONT}" font-size="34" '
        f'font-weight="bold" fill="#ffffff">{name}</text>'
    )
    if phone:
        parts.append(
            f'<text x="{text_x}" y="{y + 90}" font-family="{_FONT}" font-size="26" '
            f'fill="{accent}">\U0001f4de {phone}</text>'
        )
    else:
        parts.append(
            f'<text x="{text_x}" y="{y + 90}" font-family="{_FONT}" font-size="24" '
            f'fill="{accent}">Powered by leadsgenai.in</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def compose_frame(template: str, brand: dict[str, Any] | None = None) -> dict[str, Any]:
    """Template ke neeche client brand frame lagao.

    template = SVG string (`<svg...`) YA raster image ka file path (png/jpg).
    brand = resolve_brand() jaisa dict (ya {"business_name","phone","primary",...}).
    SVG → {"ok": True, "format": "svg", "svg": ...} (canvas height +strip).
    Image → {"ok": True, "format": "png", "png_path": "data/frames/..."}.
    Kabhi raise nahi.
    """
    try:
        brand = brand if isinstance(brand, dict) else {}
        tpl = str(template or "").strip()
        if not tpl:
            return {"ok": False, "error": "template missing — SVG string ya image path do."}
        if tpl.lstrip().lower().startswith("<svg"):
            return _compose_svg(tpl, brand)
        if os.path.isfile(tpl):
            return _compose_raster(tpl, brand)
        return {"ok": False, "error": "template na SVG hai na valid image path."}
    except Exception as e:
        logger.warning(f"[brand_frames] compose_frame failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def _compose_svg(svg: str, brand: dict[str, Any]) -> dict[str, Any]:
    m = _SVG_DIM_RE.search(svg)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (1080, 1080)
    w = max(200, min(w, 4000))
    h = max(200, min(h, 4000))
    strip = _strip_svg(w, h, brand)
    out = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h + _STRIP_H}" '
        f'viewBox="0 0 {w} {h + _STRIP_H}">{svg}{strip}</svg>'
    )
    return {"ok": True, "format": "svg", "svg": out, "width": w, "height": h + _STRIP_H}


def _compose_raster(path: str, brand: dict[str, Any]) -> dict[str, Any]:
    from PIL import Image, ImageDraw  # lazy — heavy dep

    img = Image.open(path).convert("RGB")
    w, h = img.size
    strip_h = max(80, int(w * 0.10))
    canvas = Image.new("RGB", (w, h + strip_h), "#ffffff")
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    primary = _safe_color(brand.get("primary"), "#10203a")
    accent = _safe_color(brand.get("accent"), "#ffd56b")
    draw.rectangle([0, h, w, h + strip_h], fill=primary)
    draw.rectangle([0, h, w, h + max(4, strip_h // 18)], fill=accent)
    font_big = _load_font(int(strip_h * 0.34))
    font_small = _load_font(int(strip_h * 0.24))
    name = str(brand.get("business_name") or "Aapka Business")[:48]
    phone = str(brand.get("phone") or "")[:20]
    draw.text((int(w * 0.03), h + int(strip_h * 0.16)), name, fill="#ffffff", font=font_big)
    if phone:
        draw.text((int(w * 0.03), h + int(strip_h * 0.58)), phone, fill=accent, font=font_small)
    os.makedirs(_FRAMES_DIR, exist_ok=True)
    out_path = os.path.join(_FRAMES_DIR, f"frame_{uuid.uuid4().hex[:10]}.png")
    canvas.save(out_path, "PNG")
    return {"ok": True, "format": "png", "png_path": out_path, "width": w, "height": h + strip_h}


def _load_font(size: int):
    """System truetype font (Windows arial / Linux DejaVu), warna PIL default."""
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


# --------------------------------------------------------------------------- #
# Daily feed — aaj ke 3 ready posts (festival/quote/offer × brand frame)
# --------------------------------------------------------------------------- #
def _today(date_str: str | None) -> _date:
    try:
        if date_str:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        pass
    return _date.today()


def _fallback_captions(brand: dict[str, Any], items: list[dict[str, str]]) -> list[str]:
    name = brand.get("business_name") or "Aapka Business"
    phone = brand.get("phone") or ""
    tail = f"\n\U0001f4de {phone}" if phone else ""
    caps = []
    for it in items:
        kind = it.get("kind")
        if kind == "festival":
            caps.append(
                f"✨ {it.get('title')} ki hardik shubhkamnayein! {name} parivar ki "
                f"taraf se aapko khushiyon bhara tyohar mubarak. \U0001fa94{tail}"
            )
        elif kind == "quote":
            caps.append(
                f"\U0001f4ad {it.get('title')}\n— {name}. Aaj ka vichaar, roz ki mehnat.{tail}"
            )
        else:
            caps.append(
                f"\U0001f525 {it.get('title')} {name} par aaj hi visit karein — offer limited hai!{tail}"
            )
    return caps


async def _llm_captions(brand: dict[str, Any], items: list[dict[str, str]]) -> list[str]:
    """3 captions ek hi free-LLM call me (JSON list). Fail = [] (caller fallback)."""
    try:
        from app.voice_agent import free_ai

        listing = "; ".join(f"{i + 1}. {it['kind']}: {it['title']}" for i, it in enumerate(items))
        raw, _ = await free_ai.chat(
            (
                "Tu Indian local business ka social media caption writer hai. Har item ke "
                "liye chhota Hinglish caption (2 lines, emojis, halka CTA). Output SIRF JSON: "
                '["caption1","caption2","caption3"]'
            ),
            [
                {
                    "role": "user",
                    "content": f"Business: {brand.get('business_name')} ({brand.get('niche')}, "
                    f"{brand.get('city') or 'India'}). Items: {listing}",
                }
            ],
            max_tokens=400,
            temperature=0.8,
        )
        s, e = raw.find("["), raw.rfind("]")
        if s >= 0 and e > s:
            parsed = json.loads(raw[s : e + 1])
            caps = [str(c).strip()[:500] for c in parsed if str(c).strip()]
            if len(caps) >= len(items):
                return caps[: len(items)]
    except Exception as e:
        logger.debug(f"[brand_frames] llm captions fallback: {e}")
    return []


async def daily_feed(slug_or_id: str, date: str | None = None) -> dict[str, Any]:
    """Aaj ka ready-to-post feed: 3 branded-frame posts (festival/quote/offer).

    Har post: {"kind","title","caption","svg"} — svg = poster × brand frame.
    Caption free-LLM (1 call), fallback deterministic. KABHI empty/raise nahi.
    """
    try:
        brand = resolve_brand(slug_or_id)
        day = _today(date)
        doy = day.timetuple().tm_yday

        # --- aaj ke 3 items chuno --- #
        items: list[dict[str, str]] = []
        festival_name = ""
        try:
            from app.marketing import festivals

            up = festivals.upcoming(21)
            if up:
                festival_name = up[0].get("name", "")
        except Exception:
            pass
        if festival_name:
            items.append({"kind": "festival", "title": festival_name})
        else:
            items.append({"kind": "quote", "title": _QUOTES[(doy + 3) % len(_QUOTES)]})
        items.append({"kind": "quote", "title": _QUOTES[doy % len(_QUOTES)]})
        items.append({"kind": "offer", "title": _OFFER_LINES[doy % len(_OFFER_LINES)]})

        captions = await _llm_captions(brand, items)
        if len(captions) < len(items):
            captions = _fallback_captions(brand, items)

        # --- posters + frame --- #
        from app.marketing import posters

        tpl_map = {"festival": "diwali-special", "quote": "clean-pro", "offer": "offer-burst"}
        posts: list[dict[str, Any]] = []
        for it, cap in zip(items, captions):
            kind = it["kind"]
            poster = posters.generate_poster(
                tpl_map.get(kind, "clean-pro"),
                business_name=brand["business_name"],
                tagline=(it["title"] if kind == "quote" else brand.get("tagline", "")),
                offer=(it["title"] if kind == "offer" else "Aaj hi sampark karein!"),
                phone=brand.get("phone", ""),
                festival=(it["title"] if kind == "festival" else day.strftime("%d %b %Y")),
                brand_primary=brand.get("primary", ""),
                brand_accent=brand.get("accent", ""),
            )
            framed = compose_frame(poster.get("svg", ""), brand)
            svg = framed.get("svg") if framed.get("ok") else poster.get("svg", "")
            posts.append({"kind": kind, "title": it["title"], "caption": cap, "svg": svg})

        return {
            "ok": True,
            "date": day.isoformat(),
            "business_name": brand["business_name"],
            "slug": brand.get("slug") or str(slug_or_id or ""),
            "posts": posts,
            "note": "Har post 1-click download/copy karke WhatsApp/Insta/GBP pe daalo.",
        }
    except Exception as e:
        logger.warning(f"[brand_frames] daily_feed failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["compose_frame", "daily_feed", "resolve_brand"]
