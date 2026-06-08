"""
upi_kit.py — UPI payment kit (scan-and-pay QR + slip + WA message). 100% free.
===============================================================================

Chhote business ke liye payment maangne ka poora kit:
  - payment_kit(business_name, vpa, amount=None, note="") -> dict:
      upi:// deep-link (pa/pn[/am/tn]) + QR SVG (review_kit ka pure-python
      encoder REUSE — koi lib nahi) + branded 800x1000 payment-slip SVG
      (QR embedded) + Hinglish WhatsApp payment-request message +
      2 instructions.

PURE LOGIC — koi LLM/network nahi, kabhi raise nahi. Inputs XML-escaped.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import quote

from app.marketing.review_kit import qr_svg  # pure-python QR encoder (reuse)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FONT = "Segoe UI, Arial, sans-serif"

# VPA = handle@psp (e.g. 9876543210@ybl, sharma.solar@oksbi)
_VPA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,255}@[A-Za-z][A-Za-z0-9]{1,63}$")


def _fmt_amount(amount: Any) -> str:
    """Amount ko clean string me ('' = skip). 499.0 -> '499', 499.5 -> '499.50'."""
    try:
        if amount is None or str(amount).strip() == "":
            return ""
        val = float(str(amount).strip().replace(",", "").replace("₹", ""))
        if not (0 < val <= 10_000_000):
            return ""
        return f"{int(val)}" if abs(val - int(val)) < 1e-9 else f"{val:.2f}"
    except Exception:
        return ""


def _build_upi_link(vpa: str, name: str, amount_str: str, note: str) -> str:
    """upi://pay deep-link (NPCI spec): pa + pn (+am +tn) + cu=INR."""
    parts = [f"pa={quote(vpa, safe='@')}", f"pn={quote(name)}"]
    if amount_str:
        parts.append(f"am={amount_str}")
    if note:
        parts.append(f"tn={quote(note[:80])}")
    parts.append("cu=INR")
    return "upi://pay?" + "&".join(parts)


def _slip_svg(name: str, vpa: str, amount_str: str, note: str) -> str:
    """800x1000 branded payment-slip SVG with {qr} slot. Inputs escape ho ke aate."""
    amount_block = (
        (
            '<rect x="250" y="775" width="300" height="70" rx="35" fill="#7c3aed"/>'
            f'<text x="400" y="822" font-family="{_FONT}" font-size="36" font-weight="bold" '
            f'fill="#ffffff" text-anchor="middle">₹ {amount_str}</text>'
        )
        if amount_str
        else (
            f'<text x="400" y="810" font-family="{_FONT}" font-size="26" fill="#6b7280" '
            'text-anchor="middle">Amount aap khud enter karein</text>'
        )
    )
    note_block = (
        (
            f'<text x="400" y="885" font-family="{_FONT}" font-size="24" fill="#6b7280" '
            f'text-anchor="middle">Note: {note}</text>'
        )
        if note
        else ""
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1000" viewBox="0 0 800 1000">'
        '<defs><linearGradient id="upibg" x1="0%" y1="0%" x2="0%" y2="100%">'
        '<stop offset="0%" stop-color="#7c3aed"/><stop offset="100%" stop-color="#5b21b6"/>'
        "</linearGradient></defs>"
        '<rect width="800" height="1000" fill="#ffffff"/>'
        '<rect width="800" height="210" fill="url(#upibg)"/>'
        f'<text x="400" y="92" font-family="{_FONT}" font-size="40" font-weight="bold" '
        f'fill="#ffffff" text-anchor="middle">💳 {name}</text>'
        f'<text x="400" y="155" font-family="{_FONT}" font-size="30" fill="#ddd6fe" '
        'text-anchor="middle">ko pay karein</text>'
        f'<text x="400" y="272" font-family="{_FONT}" font-size="28" fill="#374151" '
        'text-anchor="middle">📱 Scan &amp; Pay — koi bhi UPI app</text>'
        '<rect x="220" y="310" width="360" height="360" rx="18" fill="#f5f3ff" '
        'stroke="#7c3aed" stroke-width="3"/>'
        "{qr}"
        f'<text x="400" y="742" font-family="{_FONT}" font-size="30" font-weight="bold" '
        f'fill="#1f2937" text-anchor="middle">UPI ID: {vpa}</text>'
        f"{amount_block}{note_block}"
        f'<text x="400" y="950" font-family="{_FONT}" font-size="24" fill="#6b7280" '
        'text-anchor="middle">GPay • PhonePe • Paytm • BHIM — sab chalega ✅</text>'
        "</svg>"
    )


def payment_kit(
    business_name: str, vpa: str, amount: Any | None = None, note: str = ""
) -> dict[str, Any]:
    """UPI payment kit: link + QR + slip (QR embedded) + WA message + steps.

    Pure logic — instant, deterministic, KABHI raise nahi. Invalid VPA par bhi
    kit banta hai (vpa_valid=False + warning), taaki UI kabhi khali na ho.
    """
    name = (business_name or "").strip()[:120] or "Aapka Business"
    vpa_clean = (vpa or "").strip().replace(" ", "")[:100]
    vpa_valid = bool(_VPA_RE.match(vpa_clean))
    amount_str = _fmt_amount(amount)
    note_clean = (note or "").strip()[:100]

    try:
        upi_link = _build_upi_link(vpa_clean or "apna-upi@bank", name, amount_str, note_clean)
        qr = qr_svg(upi_link, 320)
        embedded = qr.replace("<svg ", '<svg x="240" y="330" ', 1)
        slip = _slip_svg(
            escape(name, quote=True),
            escape(vpa_clean or "apna-upi@bank", quote=True),
            amount_str,
            escape(note_clean, quote=True),
        ).replace("{qr}", embedded)
    except Exception as e:  # pragma: no cover - sab deterministic hai
        logger.error(f"payment_kit build failed: {e}")
        upi_link = f"upi://pay?pa={quote(vpa_clean, safe='@')}&pn={quote(name)}&cu=INR"
        qr = qr_svg(upi_link, 320)
        slip = qr

    amt_line = f"\n💰 Amount: ₹{amount_str}" if amount_str else ""
    note_line = f"\n📝 {note_clean}" if note_clean else ""
    wa_payment_msg = (
        f"Namaste! 🙏 {name} ki payment ab UPI se seedha ho jayegi."
        f"\n💳 UPI ID: {vpa_clean}{amt_line}{note_line}"
        f"\n\nIs link par tap karke pay karein:\n{upi_link}"
        "\n\n(Ya QR scan karein — GPay/PhonePe/Paytm sab chalega ✅) Dhanyawad!"
    )

    instructions = [
        "Payment slip print karke counter pe rakho ya customer ko WhatsApp pe "
        "bhejo — wo kisi bhi UPI app se QR scan karke turant pay kar dega.",
        "Fixed amount chahiye to upar amount daal kar naya QR banao — customer "
        "ko sirf UPI PIN dalna padega, galat amount ka jhanjhat khatam.",
    ]
    if not vpa_valid:
        instructions = [
            "⚠️ UPI ID format sahi nahi lag raha (sahi format: naam@bank, "
            "jaise 9876543210@ybl) — pehle apni UPI app me 'My UPI ID' check karo.",
            instructions[0],
        ]

    return {
        "business_name": name,
        "vpa": vpa_clean,
        "vpa_valid": vpa_valid,
        "amount": amount_str,
        "note": note_clean,
        "upi_link": upi_link,
        "qr_svg": qr,
        "slip_svg": slip,
        "wa_payment_msg": wa_payment_msg,
        "instructions": instructions[:2],
    }
