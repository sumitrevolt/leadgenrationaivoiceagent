"""
mini_site.py — free per-client MINI WEBSITE + booking page (NowFloats/Durable-lite).
=====================================================================================

Har marketing client ko ek simple, mobile-first web-presence milti hai jo
/b/{slug} par live hoti hai. Yahi ₹2,999 plan ka tangible deliverable hai:
chhote local business ke paas turant ek share-karne-layak page + "enquiry/book"
button — aur har enquiry hamare lead-funnel me capture hoti hai.

  render_site(client) -> str   (complete self-contained HTML page)

Builder-aware: palette/layout/logo `minisite_builder.get_config(slug)` se aata
hai (lazy import, defensive). Booking-calendar + reviews-feed sections bhi
shamil hain (calendar -> /api/booking/*, reviews -> /api/minisite/reviews/*).

Page sections (brand colors client.brand se):
  - Hero        : business name + tagline + niche badge + Call/WhatsApp buttons
  - About       : template blurb (niche-aware) — pure SYNC, no LLM/await
  - Services    : niche content_focus / client-provided list → chips
  - Booking form: name/phone/message/preferred-time → POST /api/public/inquiry
                  (hidden source_slug) — submit ke baad thank-you
  - Calendar    : interactive date/slot picker -> /api/booking/slots + /book
  - Reviews     : customer-feedback feed + submit + Google-review QR (optional)
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


def _load_config(slug: str) -> dict[str, Any]:
    """Mini-site builder config (palette/layout/logo) for a slug. Lazy import so
    there is no circular dependency at module load; never raises. Returns safe
    defaults if the builder module / store is unavailable."""
    try:
        from app.api.minisite_builder import get_config  # lazy (avoid cycle)

        cfg = get_config(slug)
        if isinstance(cfg, dict):
            return cfg
    except Exception as e:  # pragma: no cover - builder optional
        logger.debug(f"[mini_site] config load skip: {e}")
    return {"palette": "violet", "layout": "classic", "logo_url": "", "primary": "", "accent": ""}


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
        parts.append(f'<a class="cta call" href="tel:{_e(phone_disp)}">📞 Call karein</a>')
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
        f'<section class="sec"><h2>Hamari Services</h2><div class="chips">{chips}</div></section>'
    )


def _catalog_section(slug: str, name: str, wa: str) -> str:
    """Product catalog grid (WhatsApp-store style) — product_catalog store se.

    Catalog empty/missing/error => '' (page me ZERO change). Har product pe
    'WhatsApp pe order karein' = wa.me 1-click prefilled link (auto-send nahi).
    """
    try:
        from urllib.parse import quote as _q

        from app.marketing import product_catalog  # lazy (optional store)

        items = product_catalog.list_products(slug, include_out_of_stock=False)
    except Exception as e:  # store/module issue => section hi nahi
        logger.debug(f"[mini_site] catalog skip: {e}")
        return ""
    if not items:
        return ""

    cards: list[str] = []
    for p in items[:24]:
        try:
            pname = str(p.get("name") or "").strip()
            if not pname:
                continue
            price = product_catalog.fmt_price(p.get("price_inr"))
            desc = str(p.get("desc") or "").strip()
            photo = str(p.get("photo_url") or "").strip()
            img = (
                f'<img class="pimg" src="{_e(photo)}" alt="{_e(pname)}" loading="lazy" '
                "onerror=\"this.style.display='none'\" />"
                if photo.startswith(("https://", "http://", "/"))
                else '<div class="pimg ph">🛍️</div>'
            )
            order_btn = ""
            if wa:
                msg = (
                    f"Mujhe {pname}"
                    + (f" ({price})" if price else "")
                    + f" order karna hai — {name}"
                )
                order_btn = (
                    f'<a class="porder" href="https://wa.me/{_e(wa)}?text={_e(_q(msg))}" '
                    'target="_blank" rel="noopener">💬 WhatsApp pe order karein</a>'
                )
            cards.append(
                '<div class="pcard">'
                + img
                + f'<div class="pname">{_e(pname)}</div>'
                + (f'<div class="pprice">{_e(price)}</div>' if price else "")
                + (f'<div class="pdesc">{_e(desc[:120])}</div>' if desc else "")
                + order_btn
                + "</div>"
            )
        except Exception:
            continue
    if not cards:
        return ""
    return (
        '<section class="sec catalog" id="catalog"><h2>Hamare Products</h2>'
        '<div class="pgrid">' + "".join(cards) + "</div></section>"
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


def _calendar_section() -> str:
    """Interactive date/slot picker. Static markup; JS (`_calendar_js`) fetches
    GET /api/booking/slots and submits POST /api/booking/book."""
    return (
        '<section class="sec calsec" id="calendar"><h2>Appointment Book Karein</h2>'
        '<p class="csub">Apna pasand ka din aur time chuniye — turant slot lock ho jayega.</p>'
        '<div class="cal">'
        '<div class="days" id="calDays"></div>'
        '<div class="slots" id="calSlots"></div>'
        '<div class="bform" id="calBook" style="display:none">'
        '<label>Aapka naam *<input id="calName" type="text" placeholder="Pura naam" '
        'maxlength="120" /></label>'
        '<label>Phone *<input id="calPhone" type="tel" placeholder="10-digit mobile" '
        'maxlength="14" /></label>'
        '<button type="button" class="cta submit" id="calConfirm">✅ Slot confirm karein</button>'
        "</div>"
        '<div class="calmsg" id="calMsg" role="status">Loading available days…</div>'
        "</div></section>"
    )


def _reviews_section(name: str, gbp: str, place_query: str, slug: str = "") -> str:
    """Customer-feedback reviews FEED (approved reviews + submit form) PLUS the
    existing Google-review QR + GBP map link (optional). Feed data is fetched
    client-side from /api/minisite/reviews/public; submit posts (rate-limited,
    moderated) to /api/minisite/reviews/submit."""
    feed = (
        '<div class="rvavg" id="rvAvg"></div>'
        '<div class="rvlist" id="rvList"></div>'
        '<form class="rvform" id="rvForm" novalidate>'
        '<input type="text" id="rvHp" name="website" class="hp" tabindex="-1" '
        'autocomplete="off" aria-hidden="true" />'
        '<div class="rvrow">'
        '<input id="rvName" type="text" placeholder="Aapka naam" maxlength="80" />'
        '<select id="rvRating" aria-label="Rating">'
        '<option value="5">★★★★★</option><option value="4">★★★★</option>'
        '<option value="3">★★★</option><option value="2">★★</option>'
        '<option value="1">★</option></select>'
        "</div>"
        '<textarea id="rvText" rows="2" placeholder="Apna experience likhiye…" '
        'maxlength="600"></textarea>'
        '<button type="submit" class="cta submit" id="rvBtn">⭐ Review do</button>'
        '<div class="bmsg" id="rvMsg" role="status"></div>'
        "</form>"
    )

    extra: list[str] = []
    try:
        from app.marketing.review_kit import qr_svg, review_link

        url = ""
        if gbp.startswith("http"):
            url = gbp
        else:
            url = review_link(place_query or name).get("maps_search_url", "")
        if url:
            svg = qr_svg(url, 200)
            extra.append(
                '<div class="qrbox">' + svg + "</div>"
                '<p class="qrcap">📱 Scan karke Google par review dein</p>'
            )
    except Exception as e:  # QR optional — fail ho to bas skip
        logger.debug(f"[mini_site] review QR skip: {e}")

    if gbp.startswith("http"):
        extra.append(
            f'<a class="maplink" href="{_e(gbp)}" target="_blank" '
            'rel="noopener">📍 Google par dekho / location</a>'
        )

    return (
        '<section class="sec reviews" id="reviews"><h2>Customer Reviews</h2>'
        + feed
        + "".join(extra)
        + "</section>"
    )


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
        links.append(
            f'<a class="soc ig" href="{_e(ig)}" target="_blank" rel="noopener">📸 Instagram</a>'
        )
    if fb:
        links.append(
            f'<a class="soc fb" href="{_e(fb)}" target="_blank" rel="noopener">👍 Facebook</a>'
        )
    if gb.startswith("http"):
        links.append(
            f'<a class="soc gb" href="{_e(gb)}" target="_blank" rel="noopener">🔎 Google</a>'
        )
    if not links:
        return ""
    return (
        '<section class="sec socials"><h2>Follow karein</h2><div class="soclist">'
        + "".join(links)
        + "</div></section>"
    )


# --------------------------------------------------------------------------- #
# CSS + booking JS (templated with brand colors)
# --------------------------------------------------------------------------- #
def _layout_css(layout: str) -> str:
    """Layout-specific CSS overrides (3 visually-distinct templates) appended
    after the base CSS. 'classic' = base (no override)."""
    lay = (layout or "classic").strip().lower()
    if lay == "bold":
        # Big solid hero band, heavier type, dark alternating sections, square-ish.
        return (
            ".hero{background:var(--p);padding:70px 22px 56px}"
            ".hero h1{font-size:clamp(2rem,8vw,2.8rem);letter-spacing:-.03em}"
            ".hero .logo{border-radius:8px;width:72px;height:72px;font-size:30px;"
            "background:rgba(255,255,255,.16)}"
            ".sec{padding:38px 22px}"
            ".sec h2{font-size:1.5rem;text-transform:uppercase;letter-spacing:.04em}"
            ".sec.reviews,.sec.socials{background:#15131f;color:#fff}"
            ".sec.reviews h2,.sec.socials h2{color:#fff}"
            ".chip{border-radius:6px;background:#efe9fb}"
            ".cta{border-radius:8px;padding:15px 22px;font-size:1rem}"
            ".bform input,.bform textarea{border-radius:8px;border-width:2px}"
            ".rvcard{border-radius:8px}"
        )
    if lay == "minimal":
        # Clean white hero, thin accents, airy spacing, hairline borders.
        return (
            ".hero{background:#fff;color:var(--ink);padding:60px 24px 30px;"
            "border-bottom:1px solid var(--line)}"
            ".hero h1{color:var(--ink);font-weight:700}"
            ".hero .tag{color:var(--muted);opacity:1}"
            ".hero .logo{background:var(--bg);color:var(--p);border:1px solid var(--line);"
            "backdrop-filter:none}"
            ".hero .nb{background:var(--bg);color:var(--p);border:1px solid var(--line)}"
            ".hero .logoimg{box-shadow:none;border:1px solid var(--line)}"
            ".cta.call{background:var(--p);color:#fff;border:1px solid var(--p)}"
            ".cta.book{background:#fff;color:var(--p);border:1.5px solid var(--p)}"
            ".sec{padding:34px 24px}"
            ".sec h2{font-weight:700;font-size:1.15rem}"
            ".chip{background:#fff;border:1px solid var(--line);color:var(--ink)}"
            ".cta.submit{background:var(--p)}"
            ".rvcard{box-shadow:none;border:1px solid var(--line)}"
        )
    return ""  # classic


def _css(primary: str, accent: str, layout: str = "classic") -> str:
    base = (
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
        ".hero .logoimg{width:84px;height:84px;border-radius:18px;object-fit:cover;margin:0 auto 16px;"
        "display:block;background:#fff;box-shadow:0 6px 20px rgba(0,0,0,.18)}"
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
        # --- booking calendar component --- #
        ".cal{display:flex;flex-direction:column;gap:14px}"
        ".cal .csub{color:var(--muted);margin-bottom:2px}"
        ".days{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;-webkit-overflow-scrolling:touch}"
        ".day{flex:0 0 auto;min-width:58px;text-align:center;border:1.5px solid var(--line);"
        "border-radius:12px;padding:9px 8px;background:#fff;cursor:pointer;font-weight:700;"
        "color:var(--ink);transition:border-color .12s,background .12s}"
        ".day small{display:block;font-size:.66rem;font-weight:600;color:var(--muted)}"
        ".day b{display:block;font-size:1.15rem;line-height:1.1}"
        ".day.sel{background:var(--p);color:#fff;border-color:var(--p)}"
        ".day.sel small{color:rgba(255,255,255,.85)}"
        ".slots{display:flex;flex-wrap:wrap;gap:8px;min-height:8px}"
        ".slot{border:1.5px solid var(--line);background:#fff;border-radius:10px;padding:9px 13px;"
        "font-size:.92rem;font-weight:700;color:var(--p);cursor:pointer}"
        ".slot.sel{background:var(--p);color:#fff;border-color:var(--p)}"
        ".calmsg{font-size:.9rem;color:var(--muted);min-height:1px}"
        ".calmsg.ok{color:#15803d}.calmsg.err{color:#dc2626}"
        # --- reviews feed --- #
        ".reviews{text-align:center}"
        ".rvavg{font-size:1.05rem;font-weight:700;color:var(--ink);margin-bottom:12px}"
        ".rvavg .stars{color:#f59e0b;letter-spacing:1px}"
        ".rvlist{display:flex;flex-direction:column;gap:12px;text-align:left;margin-bottom:18px}"
        ".rvcard{background:#faf9ff;border:1px solid var(--line);border-radius:14px;padding:14px 16px}"
        ".rvcard .rvtop{display:flex;justify-content:space-between;align-items:center;gap:8px}"
        ".rvcard .rvname{font-weight:800;font-size:.95rem;color:var(--ink)}"
        ".rvcard .rvstars{color:#f59e0b;font-size:.9rem;letter-spacing:1px}"
        ".rvcard .rvtext{color:#44425c;font-size:.92rem;margin-top:6px}"
        ".rvform{display:flex;flex-direction:column;gap:10px;text-align:left;"
        "border-top:1px dashed var(--line);padding-top:16px}"
        ".rvform .rvrow{display:flex;gap:10px}"
        ".rvform input,.rvform textarea,.rvform select{font-family:inherit;font-size:.95rem;"
        "border:1.5px solid var(--line);border-radius:10px;padding:10px 12px;width:100%%;color:var(--ink)}"
        ".rvform .hp{position:absolute;left:-9999px;width:1px;height:1px;opacity:0}"
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
    return base + _CATALOG_CSS + _layout_css(layout)


# Product-catalog grid (plain string — no %-format, safe append after base CSS).
_CATALOG_CSS = (
    ".pgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}"
    "@media(max-width:380px){.pgrid{grid-template-columns:1fr}}"
    ".pcard{background:#faf9ff;border:1px solid var(--line);border-radius:14px;"
    "padding:12px;display:flex;flex-direction:column;gap:7px}"
    ".pimg{width:100%;height:120px;object-fit:cover;border-radius:10px;background:#f3f0fd}"
    ".pimg.ph{display:grid;place-items:center;font-size:38px;color:var(--p)}"
    ".pname{font-weight:800;font-size:.95rem;color:var(--ink);line-height:1.3}"
    ".pprice{font-weight:800;font-size:1.02rem;color:var(--p)}"
    ".pdesc{font-size:.82rem;color:var(--muted);line-height:1.45}"
    ".porder{margin-top:auto;display:inline-flex;align-items:center;justify-content:center;"
    "gap:6px;background:#25d366;color:#fff;font-weight:700;font-size:.82rem;"
    "padding:9px 10px;border-radius:10px;text-decoration:none;text-align:center}"
    ".porder:active{transform:scale(.97)}"
)


def _booking_js(slug: str) -> str:
    """Booking form ko /api/public/inquiry par POST karta hai (business_name +
    source_slug auto). Pure vanilla JS; slug JSON-safe inject."""
    import json

    slug_js = json.dumps(str(slug or ""))
    biz_js = json.dumps(
        ""
    )  # business_name page se nahi — server slug se resolve karta; safe default
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
        "});})();</script>" % (slug_js, biz_js)
    )


def _calendar_js(slug: str = "") -> str:
    """Booking-calendar widget: next-7-day strip → GET /api/booking/slots per day
    → pick slot → POST /api/booking/book. Pure vanilla JS, reuses existing API.

    `slug` is threaded into both API calls so availability + booking are scoped to
    THIS business (per-client slot pool — no cross-client slot blocking)."""
    import json

    slug_js = json.dumps(str(slug or ""))
    return (
        "<script>(function(){"
        "var SLUG=" + slug_js + ";"
        "var SLUGQ=SLUG?('&slug='+encodeURIComponent(SLUG)):'';"
        "var daysEl=document.getElementById('calDays');"
        "var slotsEl=document.getElementById('calSlots');"
        "var bookEl=document.getElementById('calBook');"
        "var msg=document.getElementById('calMsg');"
        "if(!daysEl||!slotsEl||!msg)return;"
        "var selSlot=null,selDay=null;"
        "var DOW=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];"
        "function pad(n){return(n<10?'0':'')+n;}"
        "function fmtTime(iso){var t=iso.split('T')[1]||'';var hm=t.slice(0,5).split(':');"
        "if(hm.length<2)return iso;var h=parseInt(hm[0],10),m=hm[1];"
        "var ap=h>=12?'PM':'AM';var h12=((h+11)%12)+1;return h12+':'+m+' '+ap;}"
        "function buildDays(){var today=new Date();var html='';"
        "for(var i=0;i<7;i++){var d=new Date(today.getTime()+i*86400000);"
        "var ds=d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());"
        "html+='<div class=\"day\" data-d=\"'+ds+'\"><small>'+DOW[d.getDay()]+'</small>'"
        "+'<b>'+d.getDate()+'</b></div>';}"
        "daysEl.innerHTML=html;"
        "var nodes=daysEl.querySelectorAll('.day');"
        "for(var j=0;j<nodes.length;j++){nodes[j].addEventListener('click',function(){"
        "for(var k=0;k<nodes.length;k++)nodes[k].classList.remove('sel');"
        "this.classList.add('sel');selDay=this.getAttribute('data-d');loadSlots(selDay);});}"
        "if(nodes[0])nodes[0].click();}"
        "function loadSlots(day){slotsEl.innerHTML='';selSlot=null;bookEl.style.display='none';"
        "msg.className='calmsg';msg.textContent='Slots dekh rahe hain…';"
        "fetch('/api/booking/slots?date='+encodeURIComponent(day)+'&duration_min=30'+SLUGQ)"
        ".then(function(r){return r.json();}).then(function(d){"
        "var arr=(d&&d.slots)?d.slots:[];"
        "if(!arr.length){msg.textContent='Is din koi slot free nahi — doosra din chuniye.';return;}"
        "msg.textContent='';var html='';"
        "for(var i=0;i<arr.length;i++){var s=arr[i];var iso=(typeof s==='string')?s:(s&&(s.when||s.start||s.iso||s.slot));"
        'if(!iso)continue;html+=\'<button type="button" class="slot" data-iso="\''
        "+encodeURIComponent(iso)+'\">'+fmtTime(iso)+'</button>';}"
        "slotsEl.innerHTML=html;"
        "var sn=slotsEl.querySelectorAll('.slot');"
        "for(var j=0;j<sn.length;j++){sn[j].addEventListener('click',function(){"
        "for(var k=0;k<sn.length;k++)sn[k].classList.remove('sel');this.classList.add('sel');"
        "selSlot=decodeURIComponent(this.getAttribute('data-iso'));bookEl.style.display='flex';"
        "msg.className='calmsg';msg.textContent='Naam aur phone bhar ke confirm karein.';});}"
        "}).catch(function(){msg.className='calmsg err';msg.textContent='Slots load nahi hue — dobara try karein.';});}"
        "var cb=document.getElementById('calConfirm');"
        "if(cb)cb.addEventListener('click',function(){"
        "var nm=(document.getElementById('calName').value||'').trim();"
        "var ph=(document.getElementById('calPhone').value||'').trim();"
        "if(!selSlot){msg.className='calmsg err';msg.textContent='Pehle ek slot chuniye.';return;}"
        "if(!nm||ph.replace(/\\D/g,'').length<10){msg.className='calmsg err';"
        "msg.textContent='Naam aur sahi 10-digit phone daaliye.';return;}"
        "cb.disabled=true;cb.textContent='Book ho raha hai…';"
        "fetch('/api/booking/book',{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({slot:selSlot,name:nm,phone:ph,notes:'Mini-site booking',slug:SLUG})})"
        ".then(function(r){return r.json().catch(function(){return{};});}).then(function(d){"
        "if(d&&d.ok){msg.className='calmsg ok';"
        "msg.textContent=d.confirmation_text||'Aapki appointment book ho gayi!';"
        "bookEl.style.display='none';slotsEl.innerHTML='';}"
        "else{msg.className='calmsg err';msg.textContent=(d&&(d.error||d.detail))||'Book nahi ho payi — doosra slot try karein.';"
        "cb.disabled=false;cb.textContent='✅ Slot confirm karein';}})"
        ".catch(function(){msg.className='calmsg err';msg.textContent='Network issue — dobara try karein.';"
        "cb.disabled=false;cb.textContent='✅ Slot confirm karein';});});"
        "buildDays();"
        "})();</script>"
    )


def _reviews_js(slug: str) -> str:
    """Reviews feed: load approved reviews (GET /api/minisite/reviews/public) +
    submit (POST /api/minisite/reviews/submit, rate-limited+moderated). slug JSON-safe."""
    import json

    slug_js = json.dumps(str(slug or ""))
    return (
        "<script>(function(){"
        "var SLUG=%s;"
        "var listEl=document.getElementById('rvList');"
        "var avgEl=document.getElementById('rvAvg');"
        "var form=document.getElementById('rvForm');"
        "var msg=document.getElementById('rvMsg');"
        "function esc(s){var d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}"
        "function stars(n){n=Math.max(0,Math.min(5,parseInt(n,10)||0));"
        "return '★★★★★'.slice(0,n)+'☆☆☆☆☆'.slice(0,5-n);}"
        "function load(){fetch('/api/minisite/reviews/public?slug='+encodeURIComponent(SLUG))"
        ".then(function(r){return r.json();}).then(function(d){"
        "var arr=(d&&d.reviews)?d.reviews:[];"
        "if(avgEl){avgEl.innerHTML=arr.length?('<span class=\"stars\">'+stars(Math.round(d.avg_rating))"
        "+'</span> '+d.avg_rating+' / 5 · '+arr.length+' reviews'):'';}"
        "if(!listEl)return;if(!arr.length){listEl.innerHTML='';return;}"
        "var html='';for(var i=0;i<arr.length;i++){var rv=arr[i];"
        'html+=\'<div class="rvcard"><div class="rvtop"><span class="rvname">\'+esc(rv.name)'
        "+'</span><span class=\"rvstars\">'+stars(rv.rating)+'</span></div>'"
        "+(rv.text?'<div class=\"rvtext\">'+esc(rv.text)+'</div>':'')+'</div>';}"
        "listEl.innerHTML=html;}).catch(function(){});}"
        "if(form){form.addEventListener('submit',function(ev){ev.preventDefault();"
        "var hp=document.getElementById('rvHp');if(hp&&hp.value){return;}"
        "var nm=(document.getElementById('rvName').value||'').trim()||'Anonymous';"
        "var rt=parseInt(document.getElementById('rvRating').value,10)||5;"
        "var tx=(document.getElementById('rvText').value||'').trim();"
        "var btn=document.getElementById('rvBtn');btn.disabled=true;"
        "fetch('/api/minisite/reviews/submit',{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({slug:SLUG,name:nm,rating:rt,text:tx,website:''})})"
        ".then(function(r){return r.json().catch(function(){return{};});}).then(function(d){"
        "if(d&&d.ok){msg.className='bmsg ok';msg.textContent=d.message||'Shukriya!';form.reset();}"
        "else{msg.className='bmsg err';msg.textContent=(d&&d.detail)||'Submit nahi hua — dobara try karein.';}"
        "btn.disabled=false;}).catch(function(){msg.className='bmsg err';"
        "msg.textContent='Network issue — dobara try karein.';btn.disabled=false;});});}"
        "load();"
        "})();</script>" % (slug_js,)
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

        # Mini-site builder config (palette/layout/logo). Palette colors WIN over
        # the legacy brand colors when set; brand still used as the fallback.
        cfg = _load_config(slug)
        layout = str(cfg.get("layout") or "classic").strip().lower()
        logo_url = str(cfg.get("logo_url") or "").strip()
        primary = _color(cfg.get("primary"), _color(brand.get("primary"), _DEF_PRIMARY))
        accent = _color(cfg.get("accent"), _color(brand.get("accent"), _DEF_ACCENT))
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
        nb = (
            f'<span class="nb">{_e(niche_label)}{(" · " + _e(city)) if city else ""}</span>'
            if (niche_label or city)
            else (f'<span class="nb">📍 {_e(city)}</span>' if city else "")
        )
        tag_html = f'<p class="tag">{_e(tagline)}</p>' if tagline else ""
        # Logo: real uploaded/linked image if configured (validated upstream),
        # else the text-initial badge fallback.
        if logo_url:
            logo_html = f'<img class="logoimg" src="{_e(logo_url)}" alt="{_e(name)} logo" />'
        else:
            logo_html = f'<div class="logo">{_e(logo_text[:3])}</div>'
        hero = (
            '<div class="hero">'
            f"{logo_html}"
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
            + _catalog_section(slug, name, wa)
            + _booking_section(slug, name)
            + _calendar_section()
            + _reviews_section(name, gbp, place_query, slug)
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
            f"{fonts}<style>{_css(primary, accent, layout)}</style>"
            '<script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness",'
            f'"name":"{_e(name)}","description":"{_e(desc[:160])}",'
            f'"url":"https://leadsgenai.in/b/{_e(slug)}"'
            + (f',"telephone":"{_e(phone_raw)}"' if phone_raw else "")
            + (
                f',"address":{{"@type":"PostalAddress","addressLocality":"{_e(city)}","addressCountry":"IN"}}'
                if city
                else ""
            )
            + "}</script>"
            "</head><body>"
            f"{body}{_booking_js(slug)}{_calendar_js(slug)}{_reviews_js(slug)}</body></html>"
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
# Builder-aware mini-site: palette/layout/logo + booking-calendar + reviews-feed.
