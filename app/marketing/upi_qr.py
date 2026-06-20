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


# =========================================================================== #
# Engage-batch additions (additive) — client-record-driven payment QR pack.
# upi_kit.payment_kit REUSE hota hai (slip/WA msg duplicate nahi banate).
# =========================================================================== #
def build_upi_uri(vpa: str, name: str, amount: Any | None = None, note: str | None = None) -> str:
    """NPCI-spec `upi://pay` deep link — URL-encoded, VPA validated (x@y).

    Invalid VPA = "" (caller error dikhaye). Kabhi raise nahi.
    """
    try:
        from app.marketing import upi_kit

        vpa_clean = (vpa or "").strip().replace(" ", "")[:100]
        if not upi_kit._VPA_RE.match(vpa_clean):
            return ""
        amount_str = upi_kit._fmt_amount(amount)
        return upi_kit._build_upi_link(
            vpa_clean,
            (name or "").strip()[:120] or "Business",
            amount_str,
            (note or "").strip()[:100],
        )
    except Exception as e:  # pragma: no cover - sab deterministic
        logger.warning(f"build_upi_uri failed: {e}")
        return ""


def qr_image_url(data: str, size: int = 400) -> str:
    """Free no-key QR image URL (api.qrserver.com — docs/Free_APIs_Curated.md).

    PNG chahiye (WhatsApp share/print) to yeh; SVG embed ke liye review_kit.qr_svg.
    """
    try:
        size = max(100, min(int(size or 400), 1000))
    except Exception:
        size = 400
    return (
        f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}"
        f"&data={quote((data or '').strip(), safe='')}"
    )


def payment_qr_pack(
    client_id: str, amount: Any | None = None, note: str | None = None
) -> dict[str, Any]:
    """Client record se UPI payment QR pack — uri + QR-image URL + branded slip
    poster (upi_kit reuse) + WhatsApp share text. Never raises, error dicts.

    Client field `upi_vpa` chahiye (clients_store.update_client se set hota).
    """
    try:
        from app.marketing import clients_store, upi_kit

        cid = (client_id or "").strip()
        client = clients_store.get_client(cid) or clients_store.get_by_slug(cid) or {}
        if not client:
            return {"ok": False, "error": "client nahi mila — /app/clients me pehle add karo."}
        vpa = str(client.get("upi_vpa") or "").strip()
        if not vpa:
            return {
                "ok": False,
                "error": "client ka upi_vpa set nahi hai — client update me UPI ID (naam@bank) daalo.",
            }
        name = str(client.get("business_name") or "Business").strip()
        kit = upi_kit.payment_kit(name, vpa, amount=amount, note=note or "")
        uri = kit.get("upi_link") or build_upi_uri(vpa, name, amount, note)
        share_text = kit.get("wa_payment_msg") or f"{name} ko UPI se pay karein: {uri}"
        return {
            "ok": True,
            "client_id": str(client.get("id") or cid),
            "business_name": name,
            "vpa": vpa,
            "vpa_valid": bool(kit.get("vpa_valid")),
            "upi_uri": uri,
            "qr_url": qr_image_url(uri),
            "poster_svg": kit.get("slip_svg") or "",
            "share_text": share_text,
            "wa_share_url": "https://wa.me/?text=" + quote(share_text, safe=""),
            "instructions": kit.get("instructions") or [],
        }
    except Exception as e:
        logger.warning(f"payment_qr_pack failed: {e}")
        return {"ok": False, "error": str(e)[:160]}
