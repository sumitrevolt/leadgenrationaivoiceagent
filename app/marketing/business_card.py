"""
business_card.py — digital visiting card per client (mobile-first + .vcf).
===========================================================================

Har client ko ek share-karne-laayak digital card: naam, business, call/WhatsApp
buttons, services line, mini-site link, scannable QR (review_kit ka pure-python
QR encoder reuse) + "Save Contact" (.vcf vCard 3.0).

  card_data(slug)        -> dict (clients_store + brand_kit merge)
  render_card_html(slug) -> {"ok", "html"}   (standalone mobile-first page)
  render_vcf(slug)       -> {"ok", "vcf", "filename"}

Sab user-text HTML-escaped; vcf values comma/semicolon-escaped. Kabhi raise
nahi — error pe {"ok": False, "error": ...}.
"""

from __future__ import annotations

import os
import re
from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _base_url() -> str:
    for k in ("PUBLIC_BASE_URL", "SITE_BASE", "PUBLIC_SITE_BASE"):
        v = (os.environ.get(k) or "").strip().rstrip("/")
        if v.startswith("http"):
            return v
    return "https://leadsgenai.in"


def _wa_number(phone: str) -> str:
    """Phone → wa.me digits (91-prefixed 10-digit Indian mobile)."""
    d = re.sub(r"\D", "", str(phone or ""))
    if len(d) == 10:
        return "91" + d
    if len(d) == 12 and d.startswith("91"):
        return d
    if len(d) == 11 and d.startswith("0"):
        return "91" + d[1:]
    return d


def _safe_color(c: Any, default: str) -> str:
    s = str(c or "").strip()
    return s if _HEX_RE.match(s) else default


def _niche_label(niche: str) -> str:
    try:
        from app.marketing.post_generator import _niche_name  # reuse, import-safe

        return _niche_name(niche)
    except Exception:
        return (niche or "general").replace("_", " ").title()


def card_data(slug: str) -> dict[str, Any]:
    """Card ke saare fields (client + brand merge). Client na mile to
    {"ok": False, "error": ...}. Kabhi raise nahi."""
    try:
        from app.marketing import brand_frames, clients_store

        key = str(slug or "").strip()
        client = clients_store.get_by_slug(key) or clients_store.get_client(key)
        if not client:
            return {"ok": False, "error": "client nahi mila — pehle onboard karo."}
        brand = brand_frames.resolve_brand(client.get("slug") or key)
        the_slug = str(client.get("slug") or key)
        phone = str(client.get("phone") or "").strip()
        base = _base_url()
        return {
            "ok": True,
            "slug": the_slug,
            "client_id": str(client.get("id") or ""),
            "business_name": str(client.get("business_name") or "Aapka Business"),
            "niche": str(client.get("niche") or "general"),
            "services": _niche_label(client.get("niche") or "general"),
            "city": str(client.get("city") or ""),
            "phone": phone,
            "wa_number": _wa_number(phone),
            "tagline": str(brand.get("tagline") or ""),
            "primary": _safe_color(brand.get("primary"), "#0b5fff"),
            "accent": _safe_color(brand.get("accent"), "#ffd56b"),
            "logo_data_uri": str(brand.get("logo_data_uri") or ""),
            "minisite_url": f"{base}/b/{the_slug}",
            "card_url": f"{base}/api/brand/card/{the_slug}",
            "vcf_url": f"/api/brand/card/{the_slug}.vcf",
        }
    except Exception as e:
        logger.warning(f"[business_card] card_data failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def _vcf_escape(v: str) -> str:
    return (
        str(v or "")
        .replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def render_vcf(slug: str) -> dict[str, Any]:
    """vCard 3.0 text — phone me 'Save Contact' 1-tap. Kabhi raise nahi."""
    try:
        d = card_data(slug)
        if not d.get("ok"):
            return d
        name = _vcf_escape(d["business_name"])
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"N:;{name};;;",
            f"FN:{name}",
            f"ORG:{name}",
        ]
        if d.get("phone"):
            lines.append(f"TEL;TYPE=CELL,VOICE:{_vcf_escape(d['phone'])}")
        lines.append(f"URL:{d['minisite_url']}")
        if d.get("city"):
            lines.append(f"ADR;TYPE=WORK:;;{_vcf_escape(d['city'])};;;;India")
        note = d.get("tagline") or d.get("services") or ""
        if note:
            lines.append(f"NOTE:{_vcf_escape(note)}")
        lines.append("END:VCARD")
        return {
            "ok": True,
            "vcf": "\r\n".join(lines) + "\r\n",
            "filename": f"{d['slug']}.vcf",
        }
    except Exception as e:
        logger.warning(f"[business_card] render_vcf failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def render_card_html(slug: str) -> dict[str, Any]:
    """Standalone mobile-first digital card HTML. Kabhi raise nahi."""
    try:
        d = card_data(slug)
        if not d.get("ok"):
            return d

        name = escape(d["business_name"], quote=True)
        services = escape(d["services"], quote=True)
        city = escape(d["city"], quote=True)
        tagline = escape(d["tagline"], quote=True)
        phone = escape(d["phone"], quote=True)
        primary = d["primary"]
        accent = d["accent"]
        tel_href = escape("tel:" + re.sub(r"[^\d+]", "", d["phone"] or ""), quote=True)
        wa_href = escape(
            f"https://wa.me/{d['wa_number']}?text=Namaste! Aapka card dekha.", quote=True
        )
        site_href = escape(d["minisite_url"], quote=True)
        vcf_href = escape(d["vcf_url"], quote=True)

        # QR — review_kit ka pure-python encoder (kabhi raise nahi, fallback "")
        qr = ""
        try:
            from app.marketing.review_kit import qr_svg

            qr = qr_svg(d["minisite_url"], size=180)
        except Exception as e:  # pragma: no cover
            logger.debug(f"[business_card] qr skip: {e}")

        logo_html = ""
        if d["logo_data_uri"].startswith("data:image/"):
            logo_html = f'<img class="logo" src="{d["logo_data_uri"]}" alt="logo"/>'
        else:
            initials = escape("".join(w[0] for w in d["business_name"].split()[:2]).upper() or "B")
            logo_html = f'<div class="logo initials">{initials}</div>'

        call_btn = (
            f'<a class="btn call" href="{tel_href}">\U0001f4de Call karein</a>'
            if d["phone"]
            else ""
        )
        wa_btn = (
            f'<a class="btn wa" href="{wa_href}">\U0001f4ac WhatsApp</a>' if d["wa_number"] else ""
        )
        city_line = f'<p class="city">\U0001f4cd {city}</p>' if city else ""
        tagline_line = f'<p class="tag">{tagline}</p>' if tagline else ""

        html_doc = f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{name} — Digital Card</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:#f1f5f9;display:flex;
    justify-content:center;padding:16px;min-height:100vh}}
  .card{{width:100%;max-width:420px;background:#fff;border-radius:20px;overflow:hidden;
    box-shadow:0 10px 30px rgba(0,0,0,.12)}}
  .hero{{background:linear-gradient(135deg,{primary},{primary}cc);padding:34px 22px 26px;
    text-align:center;color:#fff}}
  .logo{{width:84px;height:84px;border-radius:50%;background:#fff;object-fit:contain;
    margin:0 auto 12px;display:flex;align-items:center;justify-content:center;
    border:3px solid {accent}}}
  .initials{{font-size:34px;font-weight:800;color:{primary}}}
  h1{{font-size:24px;line-height:1.2}}
  .services{{margin-top:6px;font-size:14px;color:{accent};font-weight:600}}
  .tag{{margin-top:8px;font-size:13px;opacity:.92}}
  .city{{margin-top:6px;font-size:13px;opacity:.85}}
  .body{{padding:20px 22px 26px}}
  .btn{{display:block;text-align:center;padding:14px;border-radius:12px;margin-bottom:12px;
    text-decoration:none;font-weight:700;font-size:16px}}
  .call{{background:{primary};color:#fff}}
  .wa{{background:#25d366;color:#fff}}
  .save{{background:#111827;color:#fff}}
  .site{{background:#fff;color:{primary};border:2px solid {primary}}}
  .qr{{text-align:center;margin:18px 0 6px}}
  .qr p{{font-size:12px;color:#6b7280;margin-top:6px}}
  footer{{text-align:center;font-size:11px;color:#9ca3af;padding-bottom:18px}}
  footer a{{color:{primary};text-decoration:none}}
</style>
</head>
<body>
<div class="card">
  <div class="hero">
    {logo_html}
    <h1>{name}</h1>
    <div class="services">{services}</div>
    {tagline_line}
    {city_line}
  </div>
  <div class="body">
    {call_btn}
    {wa_btn}
    <a class="btn save" href="{vcf_href}">\U0001f4c7 Contact save karein</a>
    <a class="btn site" href="{site_href}">\U0001f310 Hamari website dekhein</a>
    <div class="qr">{qr}<p>QR scan karke website kholo / aage share karo</p></div>
  </div>
  <footer>Phone: {phone or "—"} · Powered by <a href="https://leadsgenai.in">LeadGen AI</a></footer>
</div>
</body>
</html>"""
        return {"ok": True, "html": html_doc, "slug": d["slug"]}
    except Exception as e:
        logger.warning(f"[business_card] render_card_html failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["card_data", "render_card_html", "render_vcf"]
