"""
posters.py — AdBanao-lite SVG poster generator (NO image-AI, NO external assets).
=================================================================================

6 inline 1080x1080 SVG templates — gradients/shapes/emoji-text only, system
fonts (Segoe UI/Arial). Placeholders: {business_name} {tagline} {offer}
{phone} {festival}. Inputs XML-ESCAPED hote hain (injection-safe).

PURE LOGIC — koi LLM/network nahi, kabhi raise nahi. SVG string browser me
direct render hota hai aur PNG me convert bhi kar sakte ho (client-side).
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FONT = "Segoe UI, Arial, sans-serif"

# ============================================================================ #
# Templates — 1080x1080, sirf gradients/shapes/emoji (no external images/fonts)
# NOTE: .format() use hota hai — SVG me literal { } kahin nahi (no <style> blocks).
# ============================================================================ #

_SVG_FESTIVAL_GLOW = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
    "<defs>"
    '<radialGradient id="bg" cx="50%" cy="35%" r="80%">'
    '<stop offset="0%" stop-color="#43240a"/><stop offset="55%" stop-color="#23130a"/>'
    '<stop offset="100%" stop-color="#0d0704"/></radialGradient>'
    '<radialGradient id="glow" cx="50%" cy="50%" r="50%">'
    '<stop offset="0%" stop-color="#ffd56b" stop-opacity="0.85"/>'
    '<stop offset="100%" stop-color="#ffd56b" stop-opacity="0"/></radialGradient>'
    "</defs>"
    '<rect width="1080" height="1080" fill="url(#bg)"/>'
    '<circle cx="540" cy="430" r="320" fill="url(#glow)"/>'
    '<circle cx="150" cy="150" r="6" fill="#ffd56b" opacity="0.8"/>'
    '<circle cx="930" cy="120" r="5" fill="#ffd56b" opacity="0.7"/>'
    '<circle cx="990" cy="320" r="4" fill="#ffe9a8" opacity="0.6"/>'
    '<circle cx="90" cy="380" r="4" fill="#ffe9a8" opacity="0.6"/>'
    f'<text x="540" y="225" font-family="{_FONT}" font-size="72" font-weight="bold" '
    'fill="#ffd56b" text-anchor="middle">{festival}</text>'
    '<text x="540" y="490" font-size="190" text-anchor="middle">\U0001fad4</text>'
    f'<text x="540" y="640" font-family="{_FONT}" font-size="58" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">{business_name}</text>'
    f'<text x="540" y="710" font-family="{_FONT}" font-size="34" fill="#ffe9a8" '
    'text-anchor="middle">{tagline}</text>'
    '<rect x="240" y="770" width="600" height="86" rx="43" fill="#ffd56b"/>'
    f'<text x="540" y="827" font-family="{_FONT}" font-size="38" font-weight="bold" '
    'fill="#2a1606" text-anchor="middle">{offer}</text>'
    f'<text x="540" y="960" font-family="{_FONT}" font-size="34" fill="#ffffff" '
    'text-anchor="middle">{phone}</text>'
    "</svg>"
)

_SVG_OFFER_BURST = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
    '<defs><linearGradient id="bg2" x1="0%" y1="0%" x2="100%" y2="100%">'
    '<stop offset="0%" stop-color="#c4150c"/><stop offset="100%" stop-color="#8e0d06"/>'
    "</linearGradient></defs>"
    '<rect width="1080" height="1080" fill="url(#bg2)"/>'
    '<polygon points="540,90 600,260 780,200 680,350 870,400 690,470 800,620 620,540 600,730 540,560 480,730 460,540 280,620 390,470 210,400 400,350 300,200 480,260" '
    'fill="#ffce00"/>'
    f'<text x="540" y="370" font-family="{_FONT}" font-size="60" font-weight="bold" '
    'fill="#8e0d06" text-anchor="middle">DHAMAKA</text>'
    f'<text x="540" y="450" font-family="{_FONT}" font-size="46" font-weight="bold" '
    'fill="#8e0d06" text-anchor="middle">OFFER</text>'
    f'<text x="540" y="660" font-family="{_FONT}" font-size="62" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">{business_name}</text>'
    '<rect x="170" y="710" width="740" height="96" rx="48" fill="#ffce00"/>'
    f'<text x="540" y="773" font-family="{_FONT}" font-size="42" font-weight="bold" '
    'fill="#8e0d06" text-anchor="middle">{offer}</text>'
    f'<text x="540" y="880" font-family="{_FONT}" font-size="32" fill="#ffe9a8" '
    'text-anchor="middle">{tagline}</text>'
    f'<text x="540" y="980" font-family="{_FONT}" font-size="36" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">\U0001f4de {phone}</text>'
    "</svg>"
)

_SVG_CLEAN_PRO = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
    '<rect width="1080" height="1080" fill="#ffffff"/>'
    '<rect x="0" y="0" width="1080" height="26" fill="#0b5fff"/>'
    '<rect x="0" y="1054" width="1080" height="26" fill="#0b5fff"/>'
    '<rect x="80" y="170" width="160" height="10" rx="5" fill="#0b5fff"/>'
    f'<text x="80" y="300" font-family="{_FONT}" font-size="74" font-weight="bold" '
    'fill="#10203a" text-anchor="start">{business_name}</text>'
    f'<text x="80" y="380" font-family="{_FONT}" font-size="38" fill="#44506a" '
    'text-anchor="start">{tagline}</text>'
    '<rect x="80" y="470" width="920" height="3" fill="#e3e9f5"/>'
    f'<text x="80" y="590" font-family="{_FONT}" font-size="48" font-weight="bold" '
    'fill="#0b5fff" text-anchor="start">{offer}</text>'
    f'<text x="80" y="680" font-family="{_FONT}" font-size="34" fill="#44506a" '
    'text-anchor="start">{festival}</text>'
    '<rect x="80" y="860" width="520" height="84" rx="42" fill="#0b5fff"/>'
    f'<text x="340" y="915" font-family="{_FONT}" font-size="34" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">\U0001f4de {phone}</text>'
    f'<text x="1000" y="930" font-family="{_FONT}" font-size="120" text-anchor="end">⭐</text>'
    "</svg>"
)

_SVG_DIWALI_SPECIAL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
    '<defs><linearGradient id="bg4" x1="0%" y1="0%" x2="0%" y2="100%">'
    '<stop offset="0%" stop-color="#3d1059"/><stop offset="60%" stop-color="#6b1782"/>'
    '<stop offset="100%" stop-color="#b3541e"/></linearGradient></defs>'
    '<rect width="1080" height="1080" fill="url(#bg4)"/>'
    '<text x="170" y="180" font-size="64" text-anchor="middle">✨</text>'
    '<text x="910" y="200" font-size="64" text-anchor="middle">\U0001f386</text>'
    '<text x="540" y="170" font-size="84" text-anchor="middle">\U0001fa94</text>'
    f'<text x="540" y="320" font-family="{_FONT}" font-size="80" font-weight="bold" '
    'fill="#ffd56b" text-anchor="middle">{festival}</text>'
    f'<text x="540" y="395" font-family="{_FONT}" font-size="38" fill="#ffe9d2" '
    'text-anchor="middle">ki hardik shubhkamnayein</text>'
    '<text x="280" y="560" font-size="100" text-anchor="middle">\U0001fad4</text>'
    '<text x="540" y="590" font-size="130" text-anchor="middle">\U0001fad4</text>'
    '<text x="800" y="560" font-size="100" text-anchor="middle">\U0001fad4</text>'
    f'<text x="540" y="720" font-family="{_FONT}" font-size="56" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">{business_name}</text>'
    f'<text x="540" y="785" font-family="{_FONT}" font-size="32" fill="#ffe9d2" '
    'text-anchor="middle">{tagline}</text>'
    '<rect x="220" y="830" width="640" height="84" rx="42" fill="#ffd56b"/>'
    f'<text x="540" y="886" font-family="{_FONT}" font-size="36" font-weight="bold" '
    'fill="#3d1059" text-anchor="middle">{offer}</text>'
    f'<text x="540" y="985" font-family="{_FONT}" font-size="34" fill="#ffffff" '
    'text-anchor="middle">\U0001f4de {phone}</text>'
    "</svg>"
)

_SVG_NEW_YEAR = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
    '<defs><radialGradient id="bg5" cx="50%" cy="20%" r="90%">'
    '<stop offset="0%" stop-color="#13235b"/><stop offset="100%" stop-color="#060b1f"/>'
    "</radialGradient></defs>"
    '<rect width="1080" height="1080" fill="url(#bg5)"/>'
    '<text x="200" y="220" font-size="110" text-anchor="middle">\U0001f386</text>'
    '<text x="880" y="260" font-size="110" text-anchor="middle">\U0001f387</text>'
    '<text x="540" y="180" font-size="90" text-anchor="middle">\U0001f389</text>'
    '<circle cx="320" cy="380" r="4" fill="#ffd56b"/><circle cx="760" cy="420" r="5" fill="#ffd56b"/>'
    '<circle cx="540" cy="300" r="4" fill="#9fd0ff"/><circle cx="140" cy="500" r="4" fill="#9fd0ff"/>'
    f'<text x="540" y="450" font-family="{_FONT}" font-size="92" font-weight="bold" '
    'fill="#ffd56b" text-anchor="middle">Happy New Year</text>'
    f'<text x="540" y="530" font-family="{_FONT}" font-size="40" fill="#cfe2ff" '
    'text-anchor="middle">{festival}</text>'
    f'<text x="540" y="660" font-family="{_FONT}" font-size="58" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">{business_name}</text>'
    f'<text x="540" y="730" font-family="{_FONT}" font-size="34" fill="#cfe2ff" '
    'text-anchor="middle">{tagline}</text>'
    '<rect x="240" y="790" width="600" height="86" rx="43" fill="#ffd56b"/>'
    f'<text x="540" y="847" font-family="{_FONT}" font-size="36" font-weight="bold" '
    'fill="#13235b" text-anchor="middle">{offer}</text>'
    f'<text x="540" y="965" font-family="{_FONT}" font-size="34" fill="#ffffff" '
    'text-anchor="middle">\U0001f4de {phone}</text>'
    "</svg>"
)

_SVG_GENERIC_SALE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
    '<defs><linearGradient id="bg6" x1="0%" y1="0%" x2="100%" y2="0%">'
    '<stop offset="0%" stop-color="#00838f"/><stop offset="100%" stop-color="#006064"/>'
    "</linearGradient></defs>"
    '<rect width="1080" height="1080" fill="url(#bg6)"/>'
    '<circle cx="900" cy="180" r="260" fill="#ff8f00" opacity="0.25"/>'
    '<circle cx="160" cy="920" r="300" fill="#ff8f00" opacity="0.2"/>'
    f'<text x="540" y="290" font-family="{_FONT}" font-size="150" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle" opacity="0.95">SALE</text>'
    f'<text x="540" y="380" font-family="{_FONT}" font-size="42" fill="#ffe0b2" '
    'text-anchor="middle">{festival}</text>'
    '<rect x="150" y="450" width="780" height="120" rx="60" fill="#ff8f00"/>'
    f'<text x="540" y="528" font-family="{_FONT}" font-size="48" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">{offer}</text>'
    f'<text x="540" y="700" font-family="{_FONT}" font-size="60" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">{business_name}</text>'
    f'<text x="540" y="770" font-family="{_FONT}" font-size="34" fill="#b2ebf2" '
    'text-anchor="middle">{tagline}</text>'
    f'<text x="540" y="930" font-family="{_FONT}" font-size="38" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">\U0001f4de {phone} • Abhi call karein!</text>'
    "</svg>"
)

TEMPLATES: dict[str, dict[str, str]] = {
    "festival-glow": {
        "name": "Festival Glow (diya, dark-gold)",
        "best_for": "Diwali/Dhanteras/kisi bhi tyohar ki premium greeting",
        "svg": _SVG_FESTIVAL_GLOW,
    },
    "offer-burst": {
        "name": "Offer Burst (red-yellow dhamaka)",
        "best_for": "Flash sale, discount announce, loud retail offers",
        "svg": _SVG_OFFER_BURST,
    },
    "clean-pro": {
        "name": "Clean Pro (white + brand stripe)",
        "best_for": "Services/B2B — clinics, consultants, real-estate, corporate look",
        "svg": _SVG_CLEAN_PRO,
    },
    "diwali-special": {
        "name": "Diwali/Navratri Special (purple-orange, diye)",
        "best_for": "Diwali, Navratri, Dussehra festive offers",
        "svg": _SVG_DIWALI_SPECIAL,
    },
    "new-year": {
        "name": "New Year (midnight fireworks)",
        "best_for": "New Year wishes + January offers",
        "svg": _SVG_NEW_YEAR,
    },
    "generic-sale": {
        "name": "Generic Sale (teal-orange)",
        "best_for": "Season-end sale, clearance, koi bhi evergreen offer",
        "svg": _SVG_GENERIC_SALE,
    },
}

_DEFAULT_TEMPLATE = "clean-pro"

# Brand-color slots (brand_kit integration): per-template kaunse default colors
# brand primary/accent se REPLACE hote hain. Params na milein to default unchanged.
_BRAND_SLOTS: dict[str, dict[str, list[str]]] = {
    "festival-glow": {"primary": ["#43240a", "#23130a"], "accent": ["#ffd56b"]},
    "offer-burst": {"primary": ["#c4150c", "#8e0d06"], "accent": ["#ffce00"]},
    "clean-pro": {"primary": ["#0b5fff"], "accent": []},
    "diwali-special": {"primary": ["#3d1059", "#6b1782"], "accent": ["#ffd56b"]},
    "new-year": {"primary": ["#13235b", "#060b1f"], "accent": ["#ffd56b"]},
    "generic-sale": {"primary": ["#00838f", "#006064"], "accent": ["#ff8f00"]},
}

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _apply_brand_colors(svg: str, template_id: str, brand_primary: str, brand_accent: str) -> str:
    """Valid #RRGGBB brand colors ko template ke slot-colors par replace karo.

    Invalid/khali color = no-op (injection-safe — sirf strict hex pass hota hai).
    """
    slots = _BRAND_SLOTS.get(template_id, {})
    for color, slot in ((brand_primary, "primary"), (brand_accent, "accent")):
        c = (color or "").strip()
        if c and _HEX_COLOR_RE.match(c):
            for old in slots.get(slot, []):
                svg = svg.replace(old, c)
    return svg


def list_templates() -> list[dict[str, str]]:
    """Available poster templates: [{"id","name","best_for"}]."""
    return [
        {"id": tid, "name": t["name"], "best_for": t["best_for"]} for tid, t in TEMPLATES.items()
    ]


def _esc(value: str, default: str = "") -> str:
    """XML-escape (quotes included) — SVG injection-safe."""
    v = (value or "").strip() or default
    return escape(v, quote=True)


def generate_poster(
    template_id: str,
    business_name: str,
    tagline: str = "",
    offer: str = "",
    phone: str = "",
    festival: str = "",
    brand_primary: str = "",
    brand_accent: str = "",
) -> dict[str, Any]:
    """1080x1080 SVG poster banao. Unknown template => clean-pro. Kabhi raise nahi.

    brand_primary/brand_accent (#RRGGBB, optional — brand_kit se) template ke
    default gradient/accent colors replace karte hain; khali = default look.
    Returns: {"svg": str, "template": id, "width": 1080, "height": 1080}.
    """
    tid = (template_id or "").strip().lower()
    if tid not in TEMPLATES:
        tid = _DEFAULT_TEMPLATE

    try:
        svg = TEMPLATES[tid]["svg"].format(
            business_name=_esc(business_name, "Aapka Business"),
            tagline=_esc(tagline, "Quality service, sahi daam"),
            offer=_esc(offer, "Special Offer — aaj hi poochhein!"),
            phone=_esc(phone, "Call / WhatsApp karein"),
            festival=_esc(festival, "Shubh Avsar"),
        )
        svg = _apply_brand_colors(svg, tid, brand_primary, brand_accent)
    except Exception as e:  # pragma: no cover - format keys fixed hain
        logger.error(f"generate_poster format failed ({tid}): {e}")
        name = _esc(business_name, "Aapka Business")
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080">'
            '<rect width="1080" height="1080" fill="#0b5fff"/>'
            f'<text x="540" y="540" font-family="{_FONT}" font-size="60" '
            f'fill="#ffffff" text-anchor="middle">{name}</text></svg>'
        )

    return {"svg": svg, "template": tid, "width": 1080, "height": 1080}
