"""Testimonial/reviews embed widget — client apni website pe APPROVED reviews
(social proof) ek script line se dikhaye. embed_widget (lead-capture) ka sibling:
wahi CORS-free iframe pattern, par yeh READ-only social-proof feed hai.

Data source: minisite_builder ka reviews store (data/reviews/<slug>.jsonl) —
SIRF `approved=True` (admin-moderated) reviews render hote hain. Rebuild NAHI:
list_reviews() reuse.

  reviews_widget_html(slug) -> self-contained iframe-able HTML (stars + brand color)
  widget_js(slug)           -> JS injector (inline iframe jahan script paste hua)
  snippet(slug)             -> copy-paste <script> one-liner

Pure-string module, lazy imports, NEVER raises.
"""

from __future__ import annotations

import html
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _site_base() -> str:
    try:
        from app.marketing.embed_widget import site_base

        return site_base()
    except Exception:
        return "https://leadsgenai.in"


def _client(slug: str) -> dict[str, Any]:
    try:
        from app.marketing import clients_store

        return clients_store.get_by_slug(slug) or {}
    except Exception:
        return {}


def _brand_color(client: dict[str, Any]) -> str:
    """Brand color — pehle brand.primary (clients_store ka norm), fir flat keys."""
    try:
        b = client.get("brand") or {}
        if isinstance(b, dict):
            v = str(b.get("primary") or "").strip()
            if v.startswith("#") and 4 <= len(v) <= 9:
                return v
        for k in ("brand_color", "primary_color", "color", "theme_color"):
            v = str(client.get(k) or "").strip()
            if v.startswith("#") and 4 <= len(v) <= 9:
                return v
    except Exception:
        pass
    return "#2563eb"


def _approved_reviews(slug: str, limit: int = 12) -> list[dict[str, Any]]:
    """Sirf admin-approved reviews (minisite_builder store reuse)."""
    try:
        from app.api.minisite_builder import list_reviews

        return list_reviews(slug, approved_only=True, limit=limit)
    except Exception as e:
        logger.warning(f"reviews_widget feed failed: {e}")
        return []


def _stars(rating: Any) -> str:
    try:
        r = max(1, min(5, int(rating)))
    except Exception:
        r = 5
    return "★" * r + "☆" * (5 - r)


def _card(rec: dict[str, Any], color: str) -> str:
    name = html.escape(str(rec.get("name") or "Customer").strip()[:60])
    text = html.escape(str(rec.get("text") or "").strip()[:400])
    stars = _stars(rec.get("rating"))
    return (
        '<div class="rv">'
        f'<div class="st" style="color:{color}">{stars}</div>'
        f'<div class="tx">"{text}"</div>'
        f'<div class="nm">— {name}</div>'
        "</div>"
    )


def reviews_widget_html(slug: str) -> str:
    """Self-contained branded reviews page (iframe content). Approved-only."""
    try:
        slug = (slug or "").strip().lower()
        client = _client(slug)
        biz = html.escape(str(client.get("business_name") or "Hamare customers"))
        color = _brand_color(client)
        rows = _approved_reviews(slug)
        if rows:
            try:
                avg = round(sum(int(r.get("rating") or 5) for r in rows) / len(rows), 1)
            except Exception:
                avg = 5.0
            head = (
                f'<div class="hd"><b>{biz}</b> — customers kya kehte hain '
                f'<span class="avg" style="color:{color}">{_stars(round(avg))} {avg}/5</span></div>'
            )
            cards = "".join(_card(r, color) for r in rows)
        else:
            head = f'<div class="hd"><b>{biz}</b></div>'
            cards = '<div class="rv"><div class="tx">Reviews jald aa rahe hain — pehla review aap dijiye! 🙏</div></div>'
        base = _site_base()
        return f"""<!doctype html><html lang="hi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{biz} — Reviews</title>
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:transparent;color:#111}}
 .wrap{{padding:10px 6px}}
 .hd{{font-size:15px;margin:0 4px 10px}}
 .avg{{font-weight:700;margin-left:6px}}
 .row{{display:flex;gap:10px;overflow-x:auto;padding-bottom:8px;scroll-snap-type:x mandatory}}
 .rv{{flex:0 0 240px;scroll-snap-align:start;background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px;box-shadow:0 2px 8px rgba(0,0,0,.05)}}
 .st{{font-size:15px;letter-spacing:2px}}
 .tx{{font-size:13.5px;line-height:1.45;margin:8px 0;color:#374151}}
 .nm{{font-size:12.5px;font-weight:600;color:#6b7280}}
 .pw{{text-align:center;font-size:11px;color:#9ca3af;margin-top:8px}}
 .pw a{{color:#9ca3af}}
</style></head><body>
<div class="wrap">
  {head}
  <div class="row">{cards}</div>
  <div class="pw">Powered by <a href="{base}" target="_blank" rel="noopener">LeadsGenAI</a></div>
</div>
</body></html>"""
    except Exception as e:  # pragma: no cover - sab defensive hai
        logger.warning(f"reviews_widget_html failed: {e}")
        return "<!doctype html><html><body></body></html>"


def widget_js(slug: str) -> str:
    """Inline iframe injector — jahan <script> paste hua wahi reviews strip aati
    (lead-widget ke floating-button se alag: social proof content-flow me hota)."""
    slug = (slug or "").strip().lower()
    src = f"{_site_base()}/api/engage/reviews-widget/{slug}"
    return f"""/* LeadsGenAI reviews widget */
(function(){{
  try{{
    var cs=document.currentScript;
    var f=document.createElement("iframe");
    f.src="{src}";
    f.loading="lazy"; f.title="Customer reviews";
    f.style.cssText="border:0;width:100%;height:230px;display:block;overflow:hidden";
    if(cs&&cs.parentNode){{ cs.parentNode.insertBefore(f,cs.nextSibling); }}
    else{{ document.body&&document.body.appendChild(f); }}
  }}catch(e){{}}
}})();"""


def snippet(slug: str) -> str:
    """Client ko dene ke liye copy-paste one-liner."""
    slug = (slug or "").strip().lower()
    return f'<!-- LeadsGenAI Reviews --><script src="{_site_base()}/api/engage/reviews-widget.js/{slug}" async></script>'


__all__ = ["reviews_widget_html", "widget_js", "snippet"]
