"""
email_signature.py — signature marketing kit (har bheji email = free ad).
==========================================================================

Client ke roz ke emails ke neeche ek branded HTML signature: naam, business,
phone, WhatsApp link, mini-site link (UTM'd), brand colors (brand_kit reuse)
+ optional rotating campaign banner line. Plain-text fallback + Hinglish
copy-paste instructions (Gmail/Outlook).

Pure logic — koi flag nahi, koi network nahi, koi send nahi. Never raises.

Public API:
  - generate(client_id=None, slug=None, campaign_banner_text=None)
        -> {ok, html, text, instructions, business_name}
"""

from __future__ import annotations

import html as _html
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SITE_URL = "https://leadsgenai.in"
_DEFAULT_PRIMARY = "#4f46e5"
_UTM = "utm_source=email_signature"


def _resolve_client(client_id: str | None, slug: str | None) -> dict[str, Any]:
    """clients_store se client (id ya slug se). Na mile to {}. Never raises."""
    try:
        from app.marketing import clients_store

        if client_id:
            c = clients_store.get_client(str(client_id))
            if c:
                return c
        if slug:
            c = clients_store.get_by_slug(str(slug))
            if c:
                return c
    except Exception as e:
        logger.debug(f"[email_signature] client resolve skip: {e}")
    return {}


def _brand_colors(client_id: str) -> tuple[str, str]:
    try:
        from app.marketing import brand_kit

        brand = brand_kit.get_brand(client_id) or {}
        colors = brand.get("colors") or {}
        primary = str(colors.get("primary") or "").strip()
        accent = str(colors.get("accent") or "").strip()
        return (primary or _DEFAULT_PRIMARY, accent or primary or _DEFAULT_PRIMARY)
    except Exception:
        return (_DEFAULT_PRIMARY, _DEFAULT_PRIMARY)


def _wa_url(phone: str) -> str:
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(d) == 10:
        d = "91" + d
    return f"https://wa.me/{d}" if d else ""


def generate(
    client_id: str | None = None,
    slug: str | None = None,
    campaign_banner_text: str | None = None,
) -> dict[str, Any]:
    """Branded email signature kit. Client na mile to bhi generic kit deta hai
    (never raises, never empty)."""
    try:
        client = _resolve_client(client_id, slug)
        cid = str(client.get("id") or client_id or "").strip()
        biz = str(client.get("business_name") or "").strip() or "Aapka Business"
        owner = str(client.get("owner_name") or client.get("contact_name") or "").strip()
        phone = str(client.get("phone") or "").strip()
        the_slug = str(client.get("slug") or slug or "").strip()
        niche = str(client.get("niche") or "").replace("_", " ").strip()

        primary, accent = _brand_colors(cid) if cid else (_DEFAULT_PRIMARY, _DEFAULT_PRIMARY)
        wa = _wa_url(phone)
        minisite = f"{_SITE_URL}/b/{quote(the_slug)}?{_UTM}" if the_slug else ""
        banner = str(campaign_banner_text or "").strip()[:140]

        e = _html.escape
        rows: list[str] = []
        name_line = e(owner) if owner else e(biz)
        sub_line = (
            f"{e(biz)}" + (f" · {e(niche.title())}" if niche else "")
            if owner
            else (e(niche.title()) if niche else "")
        )
        rows.append(
            f"<div style='font-weight:bold;font-size:15px;color:{e(primary)};'>{name_line}</div>"
        )
        if sub_line:
            rows.append(f"<div style='color:#444;font-size:13px;'>{sub_line}</div>")
        links: list[str] = []
        if phone:
            links.append(
                f"<a href='tel:{e(phone)}' style='color:{e(accent)};text-decoration:none;'>📞 {e(phone)}</a>"
            )
        if wa:
            links.append(
                f"<a href='{e(wa)}' style='color:#25D366;text-decoration:none;'>💬 WhatsApp</a>"
            )
        if minisite:
            links.append(
                f"<a href='{e(minisite)}' style='color:{e(accent)};text-decoration:none;'>🌐 Book / Visit</a>"
            )
        if links:
            rows.append(
                "<div style='margin-top:4px;font-size:13px;'>"
                + " &nbsp;|&nbsp; ".join(links)
                + "</div>"
            )
        if banner:
            banner_link = minisite or (_SITE_URL + "?" + _UTM)
            rows.append(
                f"<div style='margin-top:8px;background:{e(primary)};color:#fff;padding:6px 12px;"
                "border-radius:6px;font-size:13px;display:inline-block;'>"
                f"<a href='{e(banner_link)}' style='color:#fff;text-decoration:none;'>🎉 {e(banner)}</a></div>"
            )
        html_sig = (
            "<table cellpadding='0' cellspacing='0' border='0' "
            "style='font-family:Arial,Helvetica,sans-serif;line-height:1.45;'>"
            f"<tr><td style='border-left:3px solid {e(primary)};padding-left:12px;'>"
            + "".join(rows)
            + "</td></tr></table>"
        )

        text_lines = [owner or biz]
        if owner:
            text_lines.append(biz + (f" | {niche.title()}" if niche else ""))
        if phone:
            text_lines.append(f"Phone: {phone}")
        if wa:
            text_lines.append(f"WhatsApp: {wa}")
        if minisite:
            text_lines.append(f"Book/Visit: {minisite}")
        if banner:
            text_lines.append(f"** {banner} **")
        text_sig = "\n".join(text_lines)

        instructions = (
            "📋 Signature lagane ka tareeka (1 baar, 2 minute):\n\n"
            "GMAIL: Settings (⚙️) → 'See all settings' → General tab → 'Signature' → "
            "'Create new' → neeche wala HTML signature COPY karke PASTE karo (formatting "
            "ke saath) → Save Changes. Bas — ab har email ke neeche aapka branded "
            "signature jayega.\n\n"
            "OUTLOOK: Settings → Mail → Compose and reply → Email signature box me "
            "paste karo → Save.\n\n"
            "MOBILE (Gmail app): Settings → apna account → Mobile signature — wahan "
            "sirf plain-text wala version paste karo.\n\n"
            "Tip: banner line har campaign pe badalte raho (festival offer, naya "
            "product) — har bheji email free advertisement ban jaati hai!"
        )

        return {
            "ok": True,
            "business_name": biz,
            "client_id": cid,
            "slug": the_slug,
            "html": html_sig,
            "text": text_sig,
            "banner": banner,
            "instructions": instructions,
        }
    except Exception as e:
        logger.warning(f"[email_signature] generate failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["generate"]
