"""Customer dashboard view-engine consistency guard.

2026-07-07 regression: nav links + CSS were migrated to the
home/setup/calendar/leads/reports/billing view taxonomy, par showView()/
viewForHash() purane [home,leads,content,account] whitelist pe reh gaye —
Setup/Calendar/Reports/Billing nav clicks 'home' pe collapse ho jaate the aur
un views ke cards CSS se permanently hidden rehte the (paid customer Billing
tak nahi pahunch sakta tha). Yeh tests EK hi template ki teeno layers (nav
data-nav, CSS [data-active-view] rules, JS whitelists) ko aapas me consistent
assert karte hain, taaki future taxonomy-drift CI me faile — silently ship na ho.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "frontend" / "customer_dashboard.html"

# viewForHash ke map me yeh keys element-id nahi, purani taxonomy ke hash-alias hain
_LEGACY_HASH_ALIASES = {"content", "account"}


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _showview_whitelist(html: str) -> set[str]:
    m = re.search(r"function showView\(name\)\{\s*name=\[([^\]]+)\]", html)
    assert m, "showView() whitelist array template me nahi mila"
    return set(re.findall(r'"([a-z]+)"', m.group(1)))


def _viewforhash_whitelist(html: str) -> set[str]:
    m = re.search(r"return \[([^\]]+)\]\.indexOf\(h\)", html)
    assert m, "viewForHash() whitelist array template me nahi mila"
    return set(re.findall(r'"([a-z]+)"', m.group(1)))


def _viewforhash_map(html: str) -> dict[str, str]:
    m = re.search(r"var map=\{([^}]+)\}", html)
    assert m, "viewForHash() ka card-id map template me nahi mila"
    return dict(re.findall(r'([A-Za-z]+):"([a-z]+)"', m.group(1)))


def test_every_card_view_is_reachable_via_showview():
    """Har data-view card ka view showView() whitelist me hona chahiye —
    warna woh view select hi nahi ho sakta aur uske cards hamesha hidden."""
    html = _html()
    whitelist = _showview_whitelist(html)
    card_views = set(re.findall(r'data-view="([a-z]+)"', html))
    missing = card_views - whitelist
    assert not missing, (
        f"data-view views {sorted(missing)} showView() whitelist {sorted(whitelist)} "
        "me nahi — in views ke cards kabhi visible nahi honge (2026-07-07 bug class)"
    )


def test_every_nav_link_view_is_reachable():
    html = _html()
    whitelist = _showview_whitelist(html)
    nav_views = set(re.findall(r'data-nav="([a-z]+)"', html))
    missing = nav_views - whitelist
    assert not missing, (
        f"nav data-nav views {sorted(missing)} showView() whitelist me nahi — "
        "in nav links ka click 'home' pe collapse ho jayega"
    )


def test_css_view_engine_matches_js_whitelist_exactly():
    """CSS [data-active-view=X] hide-rules aur JS whitelist EXACT same set ho —
    JS me extra view (bina CSS rule) = us view pe SAB cards ek saath dikhte;
    CSS me extra view (JS me nahi) = woh view kabhi activate nahi hota."""
    html = _html()
    whitelist = _showview_whitelist(html)
    css_views = set(re.findall(r'\[data-active-view="([a-z]+)"\]', html))
    assert css_views == whitelist, (
        f"CSS view-rules {sorted(css_views)} != JS whitelist {sorted(whitelist)}"
    )


def test_viewforhash_and_showview_whitelists_agree():
    html = _html()
    assert _viewforhash_whitelist(html) == _showview_whitelist(html)


def test_viewforhash_map_targets_valid_views_and_real_ids():
    """Map ki har value whitelist ka view ho; har key ya to legacy alias ho ya
    template me sach me id ke roop me exist kare (dangling scroll target nahi)."""
    html = _html()
    whitelist = _showview_whitelist(html)
    mapping = _viewforhash_map(html)
    assert mapping, "viewForHash map khali parse hua"
    for key, view in mapping.items():
        assert view in whitelist, f"map {key}->{view}: '{view}' whitelist me nahi"
        if key not in _LEGACY_HASH_ALIASES:
            assert f'id="{key}"' in html, f"map key '{key}' ka element id template me nahi"


def test_mapped_card_view_matches_cards_actual_data_view():
    """viewForHash map jo view bolta hai, card ka data-view wahi ho — warna
    scrollToId sahi view khol ke galat card dhoondega (hidden card pe scroll)."""
    html = _html()
    mapping = _viewforhash_map(html)
    for key, view in mapping.items():
        if key in _LEGACY_HASH_ALIASES:
            continue
        # card ka opening tag dhoondo aur uska data-view attribute nikalo
        m = re.search(r'<[a-z]+ [^>]*data-view="([a-z]+)"[^>]*id="%s"' % key, html) or re.search(
            r'<[a-z]+ [^>]*id="%s"[^>]*data-view="([a-z]+)"' % key, html
        )
        if not m:
            # kuch ids (jaise nested cards) ke wrapper pe data-view parent div me hota
            # hai — unke liye sirf id-existence kaafi hai (upar wale test me covered)
            continue
        assert m.group(1) == view, (
            f"card '{key}' ka data-view='{m.group(1)}' hai par viewForHash use "
            f"'{view}' view me bhejta hai — click par card hidden reh jayega"
        )
