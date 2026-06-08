"""
mini_site.py — free per-client MINI WEBSITE + booking page (NowFloats/Durable-lite).
=====================================================================================

Har marketing client ko ek simple, mobile-first web-presence milti hai jo
/b/{slug} par live hoti hai. Yahi ₹2,999 plan ka tangible deliverable hai:
chhote local business ke paas turant ek share-karne-layak page + "enquiry/book"
button — aur har enquiry hamare lead-funnel me capture hoti hai.

  render_site(client) -> str   (complete self-contained HTML page)

Page sections (brand colors client.brand se):
  - Hero        : business name + tagline + niche badge + Call/WhatsApp buttons
  - About       : template blurb (niche-aware) — pure SYNC, no LLM/await
  - Services    : niche content_focus / client-provided list → chips
  - Booking form: name/phone/message/preferred-time → POST /api/public/inquiry
                  (hidden source_slug) — submit ke baad thank-you
  - Reviews     : Google-review QR (review_kit) + GBP map link (optional)
  - Socials     : Instagram / Facebook / Google links (jo diye hon)
  - Footer      : "Powered by LeadGen AI — leadsgenai.in"

Pure stdlib string template — XML/HTML escaped (injection-safe), KABHI raise
nahi karta (har lookup try/except + fallback). Koi network/DB/await nahi.
"""

from __future__ import annotations

from html import escape
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FONT = "'Inter',system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif"
_HEAD_FONT = "'Plus Jakarta Sans',system-ui,sans-serif"

# Safe brand defaults (clients.html ke violet/indigo se match).
_DEF_PRIMARY = "#6d28d9"
_DEF_ACCENT = "#f59e0b"

_HEX_OK = set("0123456789abcdefABCDEF")


def _e(value: Any) -> str:
    """HTML-attribute-safe escape (quotes bhi). None → ''."""
    return escape(str(value if value is not None else ""), quote=True)


def _color(value: Any, fallback: str) -> str:
    """Strict #RGB / #RRGGBB validate — warna fallback (CSS injection block)."""
    c = str(value or "").strip()
    if (len(c) in (4, 7)) and c.startswith("#") and all(ch in _HEX_OK for ch in c[1:]):
        return c
    return fallback


def _digits_intl(phone: Any) -> str:
    """Phone → sirf digits, wa.me ke liye country-code ke saath (default 91)."""
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not d:
        return ""
    if len(d) == 10:  # bare Indian mobile → prefix 91
        d = "91" + d
    elif d.startswith("0") and len(d) == 11:
        d = "91" + d[1:]
    return d


def _niche_label(niche: Any) -> str:
    """Niche key → display name (NICHES se, warna title-cased key)."""
    key = str(niche or "").strip().lower()
    if not key or key == "general":
        return ""
    try:
        from app.niches import NICHES

        info = NICHES.get(key)
        if info and info.get("name"):
            return str(info["name"])
    except Exception:
        pass
    return key.replace("_", " ").title()


def _niche_services(niche: Any) -> list[str]:
    """content_focus list (display-friendly) — fallback generic offerings."""
    key = str(niche or "").strip().lower()
    try:
        from app.niches import NICHES

        info = NICHES.get(key) or {}
        focus = info.get("content_focus") or []
        out = [str(x).strip().title() for x in focus if str(x).strip()]
        if out:
            return out[:6]
    except Exception:
        pass
    return ["Quality Service", "Best Prices", "Trusted by Locals", "Quick Response"]


def _about_blurb(name: str, niche_label: str, city: str, tagline: str) -> str:
    """Template About paragraph (SYNC, no LLM). Hinglish, never-empty."""
    bits = [f"{name} aapki seva ke liye hai"]
    if niche_label:
        bits[0] = f"{name} — {niche_label}"
    if city:
        bits.append(f"{city} me trusted naam")
    body = ". ".join(bits) + "."
    if tagline:
        body += f" {tagline}."
    body += (
        " Quality, bharosa aur customer-first approach hamari pehchaan hai. "
        "Niche diye form se abhi enquiry karein ya seedha call/WhatsApp karein — "
        "hum jaldi se aapse connect karenge."
    )
    return body


# --------------------------------------------------------------------------- #
# Section builders (har ek pure string; escape andar hi)
# --------------------------------------------------------------------------- #
def _btn_row(phone_disp: str, wa: str) -> str:
    parts: list[str] = []
    if phone_disp:
        parts.append(
            f'<a class="cta call" href="tel:{_e(phone_disp)}">📞 Call karein</a>'
        )
    if wa:
        parts.append(
            f'<a class="cta wa" href="https://wa.me/{_e(wa)}" '
            f'target="_blank" rel="noopener">💬 WhatsApp</a>'
        )
    parts.append('<a class="cta book" href="#book">📅 Enquiry / Booking</a>')
    return '<div class="ctas">' + "".join(parts) + "</div>"


def _services_section(services: list[str]) -> str:
    if not services:
        return ""
    chips = "".join(f'<span class="chip">{_e(s)}</span>' for s in services)
    return (
        '<section class="sec"><h2>Hamari Services</h2>'
        f'<div class="chips">{chips}</div></section>'
    )


def _booking_section(slug: str, name: str) -> str:
    """Enquiry/booking form → POST /api/public/inquiry (hidden source_slug)."""
    return (
        '<section class="sec book" id="book"><h2>Enquiry / Booking</h2>'
        f'<p class="bsub">{_e(name)} se baat karni hai? Neeche detail bhar do — '
        "hum aapko call karenge.</p>"
        '<form id="bform" class="bform" novalidate>'
        # honeypot — insaan ise kabhi nahi bharta (bot trap; public_site ignore karta)
        '<input type="text" name="website" class="hp" tabindex="-1" '
        'autocomplete="off" aria-hidden="true" />'
        '<label>Aapka naam *<input name="name" type="text" '
        'placeholder="Pura naam" maxlength="120" required /></label>'
        '<label>Phone *<input name="phone" type="tel" '
        'placeholder="10-digit mobile" maxlength="14" required /></label>'
        '<label>Pasand ka time<input name="preferred_time" type="text" '
        'placeholder="e.g. kal shaam 5 baje" maxlength="80" /></label>'
        '<label>Message<textarea name="message" rows="3" '
        'placeholder="Aapko kya chahiye?" maxlength="600"></textarea></label>'
        '<button type="submit" class="cta submit">📩 Bhej do</button>'
        '<div class="bmsg" id="bmsg" role="status"></div>'
        "</form></section>"
    )


def _reviews_section(name: str, gbp: str, place_query: str) -> str:
    """Google-review QR (pure-python encoder) + GBP map link (optional)."""
    inner: list[str] = []
    try:
        from app.marketing.review_kit import qr_svg, review_link

        url = ""
        if gbp.startswith("http"):
            url = gbp
        else:
            url = review_link(place_query or name).get("maps_search_url", "")
        if url:
            svg = qr_svg(url, 200)
            inner.append(
                '<div class="qrbox">' + svg + "</div>"
                '<p class="qrcap">📱 Scan karke Google par review dein</p>'
            )
    except Exception as e:  # QR optional — fail ho to bas skip
        logger.debug(f"[mini_site] review QR skip: {e}")

    if gbp.startswith("http"):
        inner.append(
            f'<a class="maplink" href="{_e(gbp)}" target="_blank" '
            'rel="noopener">📍 Google par dekho / location</a>'
        )
    if not inner:
        return ""
    return '<section class="sec reviews"><h2>Reviews & Location</h2>' + "".join(inner) + "</section>"


def _socials_section(socials: dict[str, Any]) -> str:
    s = socials if isinstance(socials, dict) else {}
    links: list[str] = []

    def _url(raw: str, base: str) -> str:
        raw = str(raw or "").strip()
        if not raw:
            return ""
        if raw.startswith("http"):
            return raw
        return base + raw.lstrip("@/")

    ig = _url(s.get("instagram"), "https://instagram.com/")
    fb = _url(s.get("facebook"), "https://facebook.com/")
    gb = str(s.get("gbp") or "").strip()
    if ig:
        links.append(f'<a class="soc ig" href="{_e(ig)}" target="_blank" rel="noopener">📸 Instagram</a>')
    if fb:
        links.append(f'<a class="soc fb" href="{_e(fb)}" target="_blank" rel="noopener">👍 Facebook</a>')
    if gb.startswith("http"):
        links.append(f'<a class="soc gb" href="{_e(gb)}" target="_blank" rel="noopener">🔎 Google</a>')
    if not links:
        return ""
    return '<section class="sec socials"><h2>Follow karein</h2><div class="soclist">' + "".join(links) + "</div></section>"


# --------------------------------------------------------------------------- #
# CSS + booking JS (templated with brand colors)
# --------------------------------------------------------------------------- #
def _css(primary: str, accent: str) -> str:
    return (
        ":root{--p:%s;--a:%s;--ink:#1e1b2e;--muted:#6b7280;--line:#e9e7f2;"
        "--bg:#f7f6fb;--card:#fff}"
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:%s;color:var(--ink);background:var(--bg);line-height:1.6;"
        "-webkit-font-smoothing:antialiased}"
        "img,svg{max-width:100%%;height:auto}"
        ".wrap{max-width:560px;margin:0 auto;background:var(--card);min-height:100vh;"
        "box-shadow:0 0 60px rgba(24,16,55,.06)}"
        ".hero{background:linear-gradient(135deg,var(--p),var(--a));color:#fff;"
        "padding:54px 24px 46px;text-align:center}"
        ".hero .logo{width:64px;height:64px;border-radius:18px;background:rgba(255,255,255,.22);"
        "display:grid;place-items:center;font-weight:800;font-size:26px;margin:0 auto 16px;"
        "backdrop-filter:blur(6px)}"
        ".hero h1{font-family:%s;font-size:clamp(1.6rem,6vw,2.2rem);font-weight:800;"
        "letter-spacing:-.02em;line-height:1.15}"
        ".hero .nb{display:inline-block;margin-top:10px;font-size:.78rem;font-weight:700;"
        "background:rgba(255,255,255,.2);padding:5px 13px;border-radius:999px}"
        ".hero .tag{margin-top:12px;font-size:1.02rem;opacity:.95;max-width:420px;"
        "margin-left:auto;margin-right:auto}"
        ".ctas{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:24px}"
        ".cta{display:inline-flex;align-items:center;gap:7px;font-weight:700;font-size:.95rem;"
        "padding:13px 20px;border-radius:13px;text-decoration:none;cursor:pointer;border:none;"
        "transition:transform .12s,filter .12s}"
        ".cta:active{transform:scale(.97)}"
        ".cta.call{background:#fff;color:var(--p)}"
        ".cta.wa{background:#25d366;color:#fff}"
        ".cta.book{background:rgba(255,255,255,.18);color:#fff;border:1.5px solid rgba(255,255,255,.5)}"
        ".sec{padding:30px 24px;border-bottom:1px solid var(--line)}"
        ".sec h2{font-family:%s;font-size:1.25rem;font-weight:800;margin-bottom:14px;color:var(--ink)}"
        ".about p{color:#33324a;font-size:1rem}"
        ".chips{display:flex;flex-wrap:wrap;gap:9px}"
        ".chip{background:#f3f0fd;color:var(--p);font-weight:600;font-size:.9rem;"
        "padding:8px 14px;border-radius:11px;border:1px solid var(--line)}"
        ".book .bsub{color:var(--muted);margin-bottom:16px}"
        ".bform{display:flex;flex-direction:column;gap:13px}"
        ".bform label{font-size:.82rem;font-weight:700;color:var(--muted);display:flex;"
        "flex-direction:column;gap:6px}"
        ".bform input,.bform textarea{font-family:inherit;font-size:1rem;color:var(--ink);"
        "border:1.5px solid var(--line);border-radius:12px;padding:13px 14px;background:#fff;width:100%%}"
        ".bform input:focus,.bform textarea:focus{outline:none;border-color:var(--p);"
        "box-shadow:0 0 0 3px rgba(109,40,217,.13)}"
        ".bform .hp{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}"
        ".cta.submit{background:linear-gradient(135deg,var(--p),var(--a));color:#fff;"
        "justify-content:center;margin-top:4px;font-size:1.02rem}"
        ".cta.submit:disabled{opacity:.6;cursor:not-allowed}"
        ".bmsg{font-size:.92rem;font-weight:600;text-align:center;min-height:1px}"
        ".bmsg.ok{color:#15803d}.bmsg.err{color:#dc2626}"
        ".reviews{text-align:center}"
        ".qrbox{display:inline-block;padding:12px;background:#fff;border:1px solid var(--line);"
        "border-radius:16px;max-width:220px}"
        ".qrcap{color:var(--muted);font-size:.9rem;margin-top:10px}"
        ".maplink,.soc{display:inline-flex;align-items:center;gap:7px;font-weight:700;"
        "color:var(--p);text-decoration:none;margin-top:14px}"
        ".soclist{display:flex;flex-wrap:wrap;gap:14px}"
        ".soc{background:#f3f0fd;padding:11px 16px;border-radius:12px;margin-top:0}"
        "footer{padding:26px 24px;text-align:center;color:var(--muted);font-size:.82rem}"
        "footer a{color:var(--p);font-weight:700;text-decoration:none}"
        % (primary, accent, _FONT, _HEAD_FONT, _HEAD_FONT)
    )


def _booking_js(slug: str) -> str:
    """Booking form ko /api/public/inquiry par POST karta hai (business_name +
    source_slug auto). Pure vanilla JS; slug JSON-safe inject."""
    import json

    slug_js = json.dumps(str(slug or ""))
    biz_js = json.dumps("")  # business_name page se nahi — server slug se resolve karta; safe default
    return (
        "<script>(function(){"
        "var f=document.getElementById('bform');if(!f)return;"
        "var msg=document.getElementById('bmsg');"
        "var SLUG=%s;var BIZ=%s;"
        "f.addEventListener('submit',function(ev){ev.preventDefault();"
        "if(f.website&&f.website.value){return;}"  # honeypot filled → bot, no-op
        "var name=(f.name.value||'').trim();var phone=(f.phone.value||'').trim();"
        "if(!name||!phone){msg.className='bmsg err';msg.textContent='Naam aur phone zaroori hain.';return;}"
        "var btn=f.querySelector('button[type=submit]');btn.disabled=true;"
        "var payload={name:name,business_name:(BIZ||name),phone:phone,"
        "message:(f.message.value||'').trim(),"
        "preferred_time:(f.preferred_time.value||'').trim(),"
        "source_slug:SLUG,package:'Mini-site enquiry'};"
        "fetch('/api/public/inquiry',{method:'POST',"
        "headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})"
        ".then(function(r){return r.json().catch(function(){return{};});})"
        ".then(function(d){"
        "if(d&&d.ok){msg.className='bmsg ok';"
        "msg.textContent=d.message||'Dhanyawad! Hum jaldi call karenge.';f.reset();}"
        "else{msg.className='bmsg err';"
        "msg.textContent=(d&&d.detail)?d.detail:'Kuch galat hua — dobara try karein.';"
        "btn.disabled=false;}})"
        ".catch(function(){msg.className='bmsg err';"
        "msg.textContent='Network issue — dobara try karein.';btn.disabled=false;});"
        "});})();</script>"
        % (slug_js, biz_js)
    )


# --------------------------------------------------------------------------- #
# Main entry
# --------------------------------------------------------------------------- #
def render_site(client: dict[str, Any] | None) -> str:
    """client dict → complete mobile-first mini-site HTML. KABHI raise nahi.

    client: clients_store record (id, business_name, slug, niche, city, phone,
    brand{primary,accent,tagline,logo_text}, socials{instagram,facebook,gbp}).
    Missing/None ho to bhi safe minimal page deta hai.
    """
    try:
        c = client if isinstance(client, dict) else {}
        name = str(c.get("business_name") or "").strip() or "Aapka Business"
        slug = str(c.get("slug") or "").strip() or "business"
        niche = c.get("niche") or "general"
        city = str(c.get("city") or "").strip()
        brand = c.get("brand") if isinstance(c.get("brand"), dict) else {}
        socials = c.get("socials") if isinstance(c.get("socials"), dict) else {}

        primary = _color(brand.get("primary"), _DEF_PRIMARY)
        accent = _color(brand.get("accent"), _DEF_ACCENT)
        tagline = str(brand.get("tagline") or "").strip()
        logo_text = str(brand.get("logo_text") or "").strip() or (name[:1].upper() if name else "B")

        niche_label = _niche_label(niche)
        services = _niche_services(niche)
        phone_raw = str(c.get("phone") or "").strip()
        wa = _digits_intl(phone_raw)
        gbp = str(socials.get("gbp") or "").strip()
        place_query = f"{name} {city}".strip()

        # ----- HEAD ----- #
        title = f"{name}" + (f" — {niche_label}" if niche_label else "")
        desc = tagline or f"{name}" + (f" in {city}" if city else "") + " — abhi enquiry karein."
        fonts = (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<link href="https://fonts.googleapis.com/css2?'
            "family=Plus+Jakarta+Sans:wght@700;800&family=Inter:wght@400;600;700&"
            'display=swap" rel="stylesheet">'
        )

        # ----- HERO ----- #
        nb = f'<span class="nb">{_e(niche_label)}{(" · " + _e(city)) if city else ""}</span>' if (niche_label or city) else (
            f'<span class="nb">📍 {_e(city)}</span>' if city else ""
        )
        tag_html = f'<p class="tag">{_e(tagline)}</p>' if tagline else ""
        hero = (
            '<div class="hero">'
            f'<div class="logo">{_e(logo_text[:3])}</div>'
            f"<h1>{_e(name)}</h1>"
            f"{nb}{tag_html}"
            f"{_btn_row(phone_raw, wa)}"
            "</div>"
        )

        about = (
            '<section class="sec about"><h2>Hamare Baare Me</h2>'
            f"<p>{_e(_about_blurb(name, niche_label, city, tagline))}</p></section>"
        )

        footer = (
            '<footer>Powered by <a href="https://leadsgenai.in" target="_blank" '
            'rel="noopener">LeadGen AI</a> — leadsgenai.in</footer>'
        )

        body = (
            '<div class="wrap">'
            + hero
            + about
            + _services_section(services)
            + _booking_section(slug, name)
            + _reviews_section(name, gbp, place_query)
            + _socials_section(socials)
            + footer
            + "</div>"
        )

        return (
            '<!DOCTYPE html><html lang="en-IN"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">'
            f"<title>{_e(title)}</title>"
            f'<meta name="description" content="{_e(desc[:160])}">'
            f'<meta property="og:title" content="{_e(title)}">'
            f'<meta property="og:description" content="{_e(desc[:160])}">'
            f'<link rel="canonical" href="/b/{_e(slug)}">'
            f'<meta name="theme-color" content="{_e(primary)}">'
            f"{fonts}<style>{_css(primary, accent)}</style></head><body>"
            f"{body}{_booking_js(slug)}</body></html>"
        )
    except Exception as e:  # absolute guard — page kabhi 500 na de
        logger.warning(f"[mini_site] render failed, minimal fallback: {e}")
        safe = _e((client or {}).get("business_name") if isinstance(client, dict) else "Business")
        return (
            '<!DOCTYPE html><html lang="en-IN"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f"<title>{safe}</title></head><body style='font-family:sans-serif;"
            "text-align:center;padding:60px 20px'>"
            f"<h1>{safe}</h1><p>Enquiry ke liye call karein.</p>"
            '<p style="color:#888;font-size:13px;margin-top:40px">'
            'Powered by <a href="https://leadsgenai.in">LeadGen AI</a></p>'
            "</body></html>"
        )


__all__ = ["render_site"]
