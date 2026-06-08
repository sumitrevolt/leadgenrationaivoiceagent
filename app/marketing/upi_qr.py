"""
upi_qr.py — UPI Payment QR Poster generator (100% free stack).
=============================================================

Generates standard BHIM UPI payment link and wraps it inside a beautiful,
printable counter-stand SVG poster:
  - upi_link(vpa, name, amount): formats upi://pay URI.
  - generate_upi_poster(vpa, name, amount, brand_primary, brand_accent):
    generates 800x1000 SVG with embedded QR.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

from app.marketing.review_kit import qr_svg
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FONT = "Segoe UI, Arial, sans-serif"

_POSTER_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000" viewBox="0 0 800 1000">'
    "<defs>"
    '<linearGradient id="upibg" x1="0%" y1="0%" x2="0%" y2="100%">'
    '<stop offset="0%" stop-color="{primary}"/><stop offset="100%" stop-color="{accent}"/>'
    "</linearGradient>"
    "</defs>"
    '<rect width="800" height="1000" fill="#ffffff"/>'
    '<rect width="800" height="260" fill="url(#upibg)"/>'
    # Business name
    '<text x="400" y="100" font-family="{font}" font-size="44" font-weight="bold" fill="#ffffff" text-anchor="middle">{business_name}</text>'
    '<text x="400" y="165" font-family="{font}" font-size="28" fill="#fde68a" text-anchor="middle" font-weight="600">Scan &amp; Pay with Any UPI App</text>'
    # QR border
    '<rect x="220" y="400" width="360" height="360" rx="20" fill="#fcfbfd" stroke="{primary}" stroke-width="4"/>'
    # QR Code placeholder
    "{qr}"
    # VPA display
    '<text x="400" y="820" font-family="{font}" font-size="26" font-weight="bold" fill="#1f2937" text-anchor="middle">UPI ID: {vpa}</text>'
    # Amount note if set
    "{amount_block}"
    # Payment Apps footer text
    '<text x="400" y="940" font-family="{font}" font-size="22" fill="#6b7280" text-anchor="middle" font-weight="600">GPAY  |  PHONEPE  |  PAYTM  |  BHIM UPI</text>'
    "</svg>"
)


def upi_link(vpa: str, name: str, amount: float = 0.0) -> str:
    """UPI payment deep link format."""
    vpa_clean = (vpa or "").strip()
    name_clean = (name or "").strip()
    # Format: upi://pay?pa=vpa&pn=name&cu=INR
    link = f"upi://pay?pa={quote(vpa_clean)}&pn={quote(name_clean)}&cu=INR"
    if amount > 0:
        link += f"&am={amount:.2f}"
    return link


def generate_upi_poster(
    vpa: str,
    business_name: str,
    amount: float = 0.0,
    brand_primary: str = "",
    brand_accent: str = "",
) -> dict[str, Any]:
    """UPI QR payment poster SVG generation. 100% free, no external libraries."""
    vpa = (vpa or "").strip() or "payee@upi"
    name = (business_name or "").strip() or "Our Shop"
    primary = (brand_primary or "").strip() or "#059669"  # Default emerald-600
    accent = (brand_accent or "").strip() or "#047857"  # Default emerald-700

    link = upi_link(vpa, name, amount)
    qr = qr_svg(link, 320)

    # Embed the QR in the center of the poster
    embedded_qr = qr.replace("<svg ", '<svg x="240" y="420" ', 1)

    amount_block = ""
    if amount > 0:
        amount_block = (
            f'<text x="400" y="870" font-family="{_FONT}" font-size="32" font-weight="800" '
            f'fill="#059669" text-anchor="middle">Amount: ₹{amount:,.2f}</text>'
        )

    poster = _POSTER_TEMPLATE.format(
        primary=primary,
        accent=accent,
        business_name=escape(name),
        font=_FONT,
        qr=embedded_qr,
        vpa=escape(vpa),
        amount_block=amount_block,
    )

    return {
        "vpa": vpa,
        "business_name": name,
        "amount": amount,
        "payment_url": link,
        "poster_svg": poster,
    }
