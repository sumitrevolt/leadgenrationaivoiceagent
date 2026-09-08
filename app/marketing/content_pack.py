"""
content_pack.py — 1-click MONTHLY client deliverable bundle (free stack).
==========================================================================

Client fulfillment automation: ek hi call me poora monthly marketing pack —
  7-din content calendar + 3 ready posts (normal / offer / festival) +
  2 posters (SVG, brand colors agar brand_kit saved hai) + GBP description
  & services + WhatsApp pack + nearest-3 festival plan.

Sab pieces existing generators se CONCURRENTLY bante hain (asyncio.gather);
har piece ka apna try/except → fallback (generators khud bhi never-empty
hain). Output ek SELF-CONTAINED violet-brand HTML (iframe preview ya download
karke WhatsApp/email se client ko bhejo). KABHI raise nahi karta.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))

try:
    from app.marketing.post_generator import _niche_name  # type: ignore
except Exception:  # pragma: no cover

    def _niche_name(niche: str) -> str:  # type: ignore
        return (niche or "general").replace("_", " ").title()


def _e(s: Any) -> str:
    """HTML-escape (quotes included) — pack me sab text isi se jaata hai."""
    return escape(str(s or ""), quote=True)


async def _safe(coro, fallback: Any) -> Any:
    """Ek pack-piece ko guard karo — fail ho to fallback (pack kabhi nahi girta)."""
    try:
        return await coro
    except Exception as e:
        logger.warning(f"[content_pack] piece failed, using fallback: {e}")
        return fallback


async def _calendar(business_name: str, niche: str) -> list[dict[str, str]]:
    from app.marketing import post_generator

    return await post_generator.content_calendar(business_name, niche, days=7)


async def _post(business_name: str, niche: str, occasion: str, offer: str) -> dict[str, Any]:
    from app.marketing import post_generator

    return await post_generator.generate_post(
        business_name, niche=niche, occasion=occasion, offer=offer
    )


async def _gbp(business_name: str, niche: str) -> dict[str, Any]:
    from app.marketing import gbp_text

    return await gbp_text.gbp_texts(business_name, niche)


async def _wa(business_name: str, niche: str, offer: str) -> dict[str, Any]:
    from app.marketing import whatsapp_pack

    return await whatsapp_pack.broadcast_pack(business_name, niche, offer=offer)


async def _poster(template_id: str, **kwargs: Any) -> dict[str, Any]:
    from app.marketing import posters

    return posters.generate_poster(template_id, **kwargs)


def _upcoming_festivals() -> list[dict[str, str]]:
    """Nearest-3 festivals (45-din window; khali ho to aage tak dekho)."""
    try:
        from app.marketing import festivals

        fest = festivals.upcoming(45) or []
        if not fest:
            fest = festivals.upcoming(730) or []
        return fest[:3]
    except Exception as e:
        logger.debug(f"[content_pack] festivals skipped: {e}")
        return []


# --------------------------------------------------------------------------- #
# HTML assembly (self-contained, violet brand — monthly_report jaisa look)
# --------------------------------------------------------------------------- #


def _sec(title: str, body: str) -> str:
    return f"<div class='sec'><h2>{title}</h2>{body}</div>"


def _build_html(
    business_name: str,
    niche: str,
    month: str,
    calendar: list[dict[str, str]],
    posts: list[dict[str, Any]],
    poster_svgs: list[str],
    gbp: dict[str, Any],
    wa: dict[str, Any],
    fests: list[dict[str, str]],
) -> str:
    # --- Content Calendar table ---
    cal_rows = (
        "".join(
            f"<tr><td class='dy'>{_e(c.get('day'))}</td>"
            f"<td class='th'>{_e(c.get('theme'))}</td>"
            f"<td>{_e(c.get('caption_short') or c.get('caption'))}</td></tr>"
            for c in calendar
        )
        or "<tr><td colspan='3'>Calendar is mahine manually plan karein.</td></tr>"
    )
    cal_html = f"<table><tr><th>Din</th><th>Theme</th><th>Caption</th></tr>{cal_rows}</table>"

    # --- Posts (caption + hashtags copy-friendly <pre>) ---
    labels = ["1) Brand post", "2) Offer post", "3) Festival post"]
    posts_html = ""
    for i, p in enumerate(posts):
        if not isinstance(p, dict) or not str(p.get("caption") or "").strip():
            continue
        tags = " ".join(p.get("hashtags") or [])
        body = (p.get("caption") or "").strip() + ("\n\n" + tags if tags else "")
        idea = str(p.get("image_idea") or "").strip()
        label = labels[i] if i < len(labels) else str(i + 1) + ") Post"
        posts_html += f"<h3>{_e(label)}</h3><pre>{_e(body)}</pre>" + (
            f"<p class='idea'>🖼️ Photo idea: {_e(idea)}</p>" if idea else ""
        )
    posts_html = posts_html or "<p>Posts generate nahi hue — Posts tab se alag se banayein.</p>"

    # --- Posters (inline SVG) ---
    poster_html = "".join(f"<div class='posterbox'>{svg}</div>" for svg in poster_svgs if svg)
    poster_html = (
        (
            f"<div class='posters'>{poster_html}</div>"
            "<p class='idea'>Tip: poster ko screenshot/PNG karke status + GBP par lagayein.</p>"
        )
        if poster_html
        else "<p>Posters nahi bane — Poster tab se banayein.</p>"
    )

    # --- GBP description + services ---
    desc = str(gbp.get("description") or "").strip()
    gbp_html = (
        (
            f"<p><b>Description (Edit profile → From the business me paste karein):</b></p>"
            f"<pre>{_e(desc)}</pre>"
        )
        if desc
        else "<p>GBP description nahi bana.</p>"
    )
    for s in gbp.get("services") or []:
        nm = str((s or {}).get("name") or "").strip()
        sd = str((s or {}).get("desc") or "").strip()
        if nm and sd:
            gbp_html += f"<p><b>Service — {_e(nm)}:</b></p><pre>{_e(sd)}</pre>"

    # --- WhatsApp messages ---
    wa_html = ""
    for i, b in enumerate(wa.get("broadcast") or [], 1):
        wa_html += f"<p><b>Broadcast {i}:</b></p><pre>{_e(b)}</pre>"
    status_lines = [s for s in (wa.get("status_lines") or []) if str(s).strip()]
    if status_lines:
        wa_html += (
            "<p><b>Status lines:</b></p><ul>"
            + "".join(f"<li>{_e(s)}</li>" for s in status_lines)
            + "</ul>"
        )
    for i, r in enumerate(wa.get("reply_templates") or [], 1):
        wa_html += f"<p><b>Inquiry reply {i}:</b></p><pre>{_e(r)}</pre>"
    wa_html = wa_html or "<p>WhatsApp pack nahi bana — WhatsApp tab se banayein.</p>"

    # --- Festival plan ---
    fest_rows = (
        "".join(
            f"<tr><td class='dy'>{_e(f.get('date'))}</td>"
            f"<td class='th'>{_e(f.get('name'))}</td>"
            f"<td>{_e(f.get('marketing_angle'))}</td></tr>"
            for f in fests
        )
        or "<tr><td colspan='3'>Agle 45 din me koi bada festival nahi — evergreen offers chalayein.</td></tr>"
    )
    fest_html = (
        f"<table><tr><th>Date</th><th>Festival</th><th>Marketing angle</th></tr>{fest_rows}</table>"
    )

    return (
        "<!DOCTYPE html><html lang='hi'><head><meta charset='utf-8'>"
        f"<title>Monthly Marketing Pack — {_e(business_name)}</title><style>"
        "body{font-family:'Segoe UI',Arial,sans-serif;background:#f5f3ff;margin:0;"
        "padding:24px;color:#1f2937}"
        ".card{max-width:780px;margin:0 auto;background:#fff;border-radius:16px;"
        "overflow:hidden;box-shadow:0 4px 24px rgba(124,58,237,.18)}"
        ".head{background:linear-gradient(135deg,#7c3aed,#5b21b6);color:#fff;padding:28px 32px}"
        ".head h1{margin:0;font-size:22px}.head p{margin:6px 0 0;color:#e9d5ff;font-size:13px}"
        ".sec{padding:20px 32px;border-bottom:1px solid #ede9fe}"
        ".sec h2{font-size:17px;color:#5b21b6;margin:0 0 12px}"
        ".sec h3{font-size:14px;color:#7c3aed;margin:14px 0 6px}"
        "pre{white-space:pre-wrap;word-break:break-word;background:#f8f7ff;"
        "border:1px solid #ede9fe;border-radius:10px;padding:12px;margin:6px 0;"
        "font-family:inherit;font-size:13.5px;line-height:1.5}"
        "table{width:100%;border-collapse:collapse;font-size:13px}"
        "th{text-align:left;color:#5b21b6;padding:6px;border-bottom:2px solid #ddd6fe}"
        "td{padding:7px 6px;border-bottom:1px solid #f3f4f6;vertical-align:top}"
        ".dy{white-space:nowrap;font-weight:700;color:#7c3aed}.th{font-weight:600}"
        ".posters{display:flex;gap:14px;flex-wrap:wrap}"
        ".posterbox{flex:1 1 280px;max-width:360px}"
        ".posterbox svg{width:100%;height:auto;border-radius:12px;display:block}"
        ".idea{font-size:12.5px;color:#6b7280;margin:4px 0}"
        "ul{margin:6px 0;padding-left:20px}li{margin:5px 0;font-size:13.5px}"
        "p{font-size:13.5px;margin:8px 0 2px}"
        ".foot{padding:16px 32px;font-size:12px;color:#8b8fa3;text-align:center}"
        "</style></head><body><div class='card'>"
        f"<div class='head'><h1>📦 {_e(business_name)} — Monthly Marketing Pack ({_e(month)})</h1>"
        f"<p>{_e(_niche_name(niche))} · taiyar content — copy, paste, publish</p></div>"
        + _sec("📅 Content Calendar (7 din)", cal_html)
        + _sec("📝 Ready Posts", posts_html)
        + _sec("🖼️ Posters", poster_html)
        + _sec("📍 Google Business Profile", gbp_html)
        + _sec("💬 WhatsApp Messages", wa_html)
        + _sec("🎉 Festival Plan", fest_html)
        + "<div class='foot'>Generated by LeadGen AI — leadsgenai.in</div>"
        "</div></body></html>"
    )


# --------------------------------------------------------------------------- #
# Main entry
# --------------------------------------------------------------------------- #


async def build_client_pack(
    business_name: str,
    niche: str = "general",
    client_id: str = "",
    offer: str = "",
    phone: str = "",
) -> dict[str, Any]:
    """MONTHLY deliverable bundle ek call me. KABHI raise nahi karta.

    Returns: {"html": self-contained pack, "counts": {posts, posters,
    calendar_days, gbp_services, whatsapp_msgs, festivals}, "business_name",
    "month"}.
    """
    business_name = (business_name or "").strip() or "Aapka Business"
    niche = (niche or "general").strip().lower() or "general"
    offer = (offer or "").strip()
    phone = (phone or "").strip()
    month = datetime.now(_IST).strftime("%B %Y")

    try:
        # --- brand (optional — saved brand_kit se tagline/phone/colors) ---
        brand: dict[str, Any] | None = None
        if (client_id or "").strip():
            try:
                from app.marketing.brand_kit import get_brand

                brand = get_brand(client_id)
            except Exception as e:
                logger.debug(f"[content_pack] brand lookup skipped: {e}")
        brand = brand if isinstance(brand, dict) else None
        tagline = str((brand or {}).get("tagline") or "").strip()
        phone_eff = phone or str((brand or {}).get("phone") or "").strip()
        colors = (brand or {}).get("colors") or {}
        brand_primary = str(colors.get("primary") or "").strip()
        brand_accent = str(colors.get("accent") or "").strip()

        # --- nearest festivals (post-3 + poster-1 + plan section ke liye) ---
        fests = _upcoming_festivals()
        fest_name = str((fests[0] if fests else {}).get("name") or "").strip()

        # Offer-post ko template-mode me bhi distinct rakhne ke liye default offer.
        offer_eff = offer or "Is mahine ka special offer — abhi poochhein!"

        # --- sab pieces CONCURRENTLY (har ek guarded → fallback) ---
        (
            calendar,
            post_plain,
            post_offer,
            post_fest,
            gbp,
            wa,
            poster_fest,
            poster_offer,
        ) = await asyncio.gather(
            _safe(_calendar(business_name, niche), []),
            _safe(_post(business_name, niche, "", ""), {}),
            _safe(_post(business_name, niche, "", offer_eff), {}),
            _safe(_post(business_name, niche, fest_name, offer), {}),
            _safe(_gbp(business_name, niche), {}),
            _safe(_wa(business_name, niche, offer), {}),
            _safe(
                _poster(
                    "festival-glow",
                    business_name=business_name,
                    tagline=tagline,
                    offer=offer,
                    phone=phone_eff,
                    festival=fest_name,
                    brand_primary=brand_primary,
                    brand_accent=brand_accent,
                ),
                {},
            ),
            _safe(
                _poster(
                    "offer-burst",
                    business_name=business_name,
                    tagline=tagline,
                    offer=offer,
                    phone=phone_eff,
                    brand_primary=brand_primary,
                    brand_accent=brand_accent,
                ),
                {},
            ),
        )

        calendar = calendar if isinstance(calendar, list) else []
        gbp = gbp if isinstance(gbp, dict) else {}
        wa = wa if isinstance(wa, dict) else {}
        posts = [
            p
            for p in (post_plain, post_offer, post_fest)
            if isinstance(p, dict) and str(p.get("caption") or "").strip()
        ]
        poster_svgs = [str((p or {}).get("svg") or "").strip() for p in (poster_fest, poster_offer)]
        poster_svgs = [s for s in poster_svgs if s.startswith("<svg")]

        html = _build_html(
            business_name, niche, month, calendar, posts, poster_svgs, gbp, wa, fests
        )
        counts = {
            "posts": len(posts),
            "posters": len(poster_svgs),
            "calendar_days": len(calendar),
            "gbp_services": len(gbp.get("services") or []),
            "whatsapp_msgs": (
                len(wa.get("broadcast") or [])
                + len(wa.get("status_lines") or [])
                + len(wa.get("reply_templates") or [])
            ),
            "festivals": len(fests),
        }
        return {
            "html": html,
            "counts": counts,
            "business_name": business_name,
            "niche": niche,
            "month": month,
        }
    except Exception as e:  # pragma: no cover - sab pieces khud guarded hain
        logger.error(f"build_client_pack failed: {e}")
        name = _e(business_name)
        html = (
            "<!DOCTYPE html><html lang='hi'><head><meta charset='utf-8'>"
            f"<title>Monthly Marketing Pack — {name}</title></head><body>"
            f"<h1>📦 {name} — Monthly Marketing Pack ({_e(month)})</h1>"
            "<p>Pack abhi generate nahi ho paya — thodi der me dobara try "
            "karein ya tabs se alag-alag content banayein.</p></body></html>"
        )
        return {
            "html": html,
            "counts": {
                "posts": 0,
                "posters": 0,
                "calendar_days": 0,
                "gbp_services": 0,
                "whatsapp_msgs": 0,
                "festivals": 0,
            },
            "business_name": business_name,
            "niche": niche,
            "month": month,
            "error": str(e),
        }
