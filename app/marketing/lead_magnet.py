"""
lead_magnet.py — niche guide generator (Beacon.by-style branded lead magnet).
==============================================================================

Client ke liye ek branded HTML guide ("<Niche> business <City> me grow karne
ki 10-point checklist") — free_ai se 8-10 points (static NICHES content_focus
fallback hamesha) + brand-color cover + CTA (mini-site /b/{slug} + WhatsApp +
free audit). File: data/lead_magnets/<slug>-<niche>.html (regex-safe name,
public serve route ke liye).

Capture/gating: NAYA form NAHI banaya — EXISTING embed widget
(`/b/{slug}/widget.js`) hi capture form hai; guide me uska note + link daala
jata hai (reuse, rebuild nahi).

PDF: agar `weasyprint` ya `pdfkit` installed ho to PDF bhi banti hai
(`available()` pattern) — warna HTML-only, koi nayi dependency NAHI.

Public API (never-raise):
  - available()                                    -> {"weasyprint": bool, "pdfkit": bool}
  - generate(niche, city, business_name, slug="")  -> async; {ok, name, file, url, pdf, points}
  - safe_file_path(name)                           -> serve helper (regex-locked, traversal-proof)
"""

from __future__ import annotations

import html as _html
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = os.path.join("data", "lead_magnets")
_SITE_URL = "https://leadsgenai.in"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,78}\.(html|pdf)$")
_DEFAULT_PRIMARY = "#4f46e5"

# Generic local-marketing checklist (universal fallback tail)
_GENERIC_POINTS = [
    "Google Business Profile 100% complete karo — photos, timing, services, sab.",
    "Har khush customer se Google review maango (QR code counter pe rakho).",
    "Hafte me kam se kam 3 social media posts — festival, offer, behind-the-scenes.",
    "Har inquiry ka jawab 5 minute ke andar do — late reply = gaya customer.",
    "WhatsApp Business use karo — catalog, auto-greeting, quick replies set karo.",
    "Apne top 3 competitors ke reviews padho — jo unke customers complain karte hain, wahi aap better karo.",
    "Purane customers ko mahine me ek baar yaad karo — repeat business sabse sasta business hai.",
    "Apni website/mini-site pe clear phone number + booking button rakho.",
]


def _safe_part(s: str) -> str:
    out = re.sub(r"[^a-z0-9_-]+", "-", str(s or "").strip().lower()).strip("-")[:40]
    return out or "guide"


def available() -> dict[str, bool]:
    """Optional PDF deps check (no new dep — jo installed ho wahi use)."""
    out = {"weasyprint": False, "pdfkit": False}
    try:
        import weasyprint  # noqa: F401

        out["weasyprint"] = True
    except Exception:
        pass
    try:
        import pdfkit  # noqa: F401

        out["pdfkit"] = True
    except Exception:
        pass
    return out


def safe_file_path(name: str) -> str | None:
    """Public-serve helper: filename regex-locked + dir-locked. None = reject."""
    try:
        n = os.path.basename(str(name or "").strip())
        if not _NAME_RE.match(n):
            return None
        p = os.path.join(_DIR, n)
        if os.path.isfile(p):
            return p
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------- #
# Points (free-LLM + static NICHES fallback)
# --------------------------------------------------------------------------- #
def _static_points(niche: str, city: str) -> list[str]:
    """NICHES content_focus se niche-specific points + generic tail. Never raises."""
    points: list[str] = []
    try:
        from app.niches import NICHES

        cfg = NICHES.get(str(niche or "").strip().lower()) or {}
        for focus in cfg.get("content_focus") or []:
            points.append(
                f"{str(focus).strip().capitalize()} pe regular kaam karo — "
                f"{city or 'aapke area'} ke customers yahi dekh ke decide karte hain."
            )
        hook = str(cfg.get("pitch_hook") or "").strip()
        if hook:
            points.append(f"Pro tip: {hook}.")
    except Exception as e:
        logger.debug(f"[lead_magnet] static points skip: {e}")
    for g in _GENERIC_POINTS:
        if len(points) >= 10:
            break
        points.append(g)
    return points[:10]


async def _llm_points(niche: str, city: str, business_name: str) -> list[str]:
    """Free-LLM 8-10 checklist points — fail par [] (caller static use kare)."""
    try:
        from app.voice_agent import free_ai

        system = (
            "Tu ek Indian local-business marketing expert hai. Hinglish (Roman "
            "script) me EK numbered checklist de — 8 se 10 practical, specific "
            "points. Har point ek line (max 25 shabd). Sirf points, koi intro/"
            "outro/heading nahi. Format: har line '1. ...' jaisi."
        )
        user = (
            f"Business type: {(niche or 'local business').replace('_', ' ')}\n"
            f"City: {city or 'India'}\nBusiness: {business_name or 'local business'}\n"
            "Topic: naye customers laane ki checklist"
        )
        text, _provider = await free_ai.chat(
            system, [{"role": "user", "content": user}], max_tokens=600, temperature=0.6
        )
        points: list[str] = []
        for line in (text or "").splitlines():
            ln = re.sub(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)", "", line).strip()
            if 12 <= len(ln) <= 300:
                points.append(ln)
        if len(points) >= 6:
            return points[:10]
    except Exception as e:
        logger.debug(f"[lead_magnet] llm points skip: {e}")
    return []


# --------------------------------------------------------------------------- #
# HTML render + optional PDF
# --------------------------------------------------------------------------- #
def _brand_primary(slug: str) -> str:
    try:
        from app.marketing import brand_kit, clients_store

        c = clients_store.get_by_slug(slug) if slug else None
        if c:
            brand = brand_kit.get_brand(str(c.get("id") or "")) or {}
            p = str((brand.get("colors") or {}).get("primary") or "").strip()
            if p:
                return p
    except Exception:
        pass
    return _DEFAULT_PRIMARY


def _render_html(
    title: str,
    business_name: str,
    city: str,
    points: list[str],
    slug: str,
    primary: str,
    phone: str = "",
) -> str:
    e = _html.escape
    minisite = f"{_SITE_URL}/b/{quote(slug)}?utm_source=lead_magnet" if slug else ""
    wa_digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(wa_digits) == 10:
        wa_digits = "91" + wa_digits
    wa_url = f"https://wa.me/{wa_digits}" if wa_digits else ""
    items = "".join(f"<li style='margin:0 0 14px;padding-left:6px;'>{e(p)}</li>" for p in points)
    ctas = []
    if minisite:
        ctas.append(
            f"<a href='{e(minisite)}' style='background:{e(primary)};color:#fff;padding:12px 22px;"
            "border-radius:8px;text-decoration:none;display:inline-block;margin:4px;'>"
            "🌐 Book / Visit karein</a>"
        )
    if wa_url:
        ctas.append(
            f"<a href='{e(wa_url)}' style='background:#25D366;color:#fff;padding:12px 22px;"
            "border-radius:8px;text-decoration:none;display:inline-block;margin:4px;'>"
            "💬 WhatsApp karein</a>"
        )
    ctas.append(
        f"<a href='{e(_SITE_URL)}/audit?utm_source=lead_magnet' style='background:#222;color:#fff;"
        "padding:12px 22px;border-radius:8px;text-decoration:none;display:inline-block;margin:4px;'>"
        "🔍 Free Google Audit</a>"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{e(title)}</title></head>"
        "<body style='font-family:Arial,Helvetica,sans-serif;margin:0;background:#f7f7fb;color:#222;'>"
        # cover
        f"<div style='background:{e(primary)};color:#fff;padding:56px 24px;text-align:center;'>"
        f"<div style='font-size:13px;letter-spacing:2px;opacity:.85;'>FREE GUIDE</div>"
        f"<h1 style='margin:10px 0 6px;font-size:28px;line-height:1.25;'>{e(title)}</h1>"
        f"<div style='font-size:15px;opacity:.9;'>by {e(business_name)}"
        f"{(' · ' + e(city)) if city else ''}</div></div>"
        # checklist
        "<div style='max-width:640px;margin:0 auto;padding:30px 22px;'>"
        "<div style='background:#fff;border-radius:12px;padding:26px 28px;"
        "box-shadow:0 2px 10px rgba(0,0,0,.05);'>"
        f"<ol style='margin:0;padding-left:22px;font-size:15px;line-height:1.55;'>{items}</ol>"
        "</div>"
        # CTA
        f"<div style='text-align:center;margin:26px 0;'>{''.join(ctas)}</div>"
        f"<p style='text-align:center;color:#888;font-size:12px;'>Guide by {e(business_name)} "
        f"· Powered by <a href='{e(_SITE_URL)}' style='color:#888;'>LeadGen AI</a></p>"
        "</div></body></html>"
    )


def _try_pdf(html_path: str, html_content: str) -> str:
    """HTML -> PDF agar weasyprint/pdfkit ho (best-effort). Returns pdf path ya ''."""
    pdf_path = html_path[:-5] + ".pdf" if html_path.endswith(".html") else html_path + ".pdf"
    deps = available()
    try:
        if deps.get("weasyprint"):
            from weasyprint import HTML as _WHTML

            _WHTML(string=html_content).write_pdf(pdf_path)
            return pdf_path
        if deps.get("pdfkit"):
            import pdfkit as _pdfkit

            _pdfkit.from_string(html_content, pdf_path)
            return pdf_path
    except Exception as e:
        logger.debug(f"[lead_magnet] pdf skip: {e}")
    return ""


async def generate(niche: str, city: str, business_name: str, slug: str = "") -> dict[str, Any]:
    """Branded lead-magnet guide banao + save karo. Never raises.
    Returns {ok, name, file, url, pdf, points, capture_note}."""
    try:
        niche = str(niche or "").strip().lower()
        city = str(city or "").strip()[:60]
        business_name = str(business_name or "").strip()[:120] or "Aapka Business"
        slug = str(slug or "").strip().lower()

        niche_label = (niche or "local business").replace("_", " ").title()
        title = f"{niche_label} {('in ' + city) if city else ''} — naye customers laane ki checklist".strip()

        points = await _llm_points(niche, city, business_name)
        source = "llm"
        if not points:
            points = _static_points(niche, city)
            source = "static"

        phone = ""
        try:
            from app.marketing import clients_store

            c = clients_store.get_by_slug(slug) if slug else None
            if c:
                phone = str(c.get("phone") or "")
        except Exception:
            pass

        primary = _brand_primary(slug)
        html_content = _render_html(title, business_name, city, points, slug, primary, phone)

        name = f"{_safe_part(slug or business_name)}-{_safe_part(niche)}.html"
        if not _NAME_RE.match(name):  # paranoid double-check
            name = f"guide-{_safe_part(niche)}.html"
        os.makedirs(_DIR, exist_ok=True)
        path = os.path.join(_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)

        pdf_path = _try_pdf(path, html_content)

        capture_note = (
            "Capture/gating ke liye NAYA form nahi chahiye — apni website pe EXISTING "
            f"embed widget lagao (script: {_SITE_URL}/b/{slug or '<slug>'}/widget.js) "
            "aur 'Free guide chahiye? Enquiry karo' CTA me yeh guide link do — "
            "lead aate hi dashboard me dikhegi."
        )
        return {
            "ok": True,
            "name": name,
            "file": path,
            "url": f"/api/lifecycle/lead-magnet-file/{name}",
            "pdf": os.path.basename(pdf_path) if pdf_path else "",
            "pdf_url": (
                f"/api/lifecycle/lead-magnet-file/{os.path.basename(pdf_path)}" if pdf_path else ""
            ),
            "title": title,
            "points": points,
            "points_source": source,
            "capture_note": capture_note,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"[lead_magnet] generate failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["available", "generate", "safe_file_path"]
