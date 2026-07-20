"""Regression guard for the /app/customer* product-routing bug (2026-07-07, commit 8359d1c).

customer_dashboard.html is intentionally served (via plain FileResponse, no templating)
at all 3 routes — /app/customer (combo), /app/customer/marketing, /app/customer/voice —
gated purely by CSS on a `prod-marketing`/`prod-voice` body class (see the file's own
comment above the per-product CSS block). commit 8359d1c pointed all 3 routes at this
one file but never updated the inline script to actually SET that class, so every visit
read a permanently-classless <body>, always resolved to "combo", and for a logged-in
non-combo customer triggered an infinite location.replace() reload loop (traced via
`/api/customer/auth/me`'s `product` mismatching the always-"combo" page reading).

This test hits the live routes (not just the static file) and asserts the shipped
script derives product from the URL path — the actual fix — so a future edit can't
silently regress back to reading a DOM class that nothing ever sets.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _script_block(body: str) -> str:
    """Prefer the product-routing script, not an earlier CDN bootstrap <script>."""
    for m in re.finditer(r"<script>(.*?)</script>", body, re.S):
        block = m.group(1)
        if "pageProduct" in block or "location.pathname" in block:
            return block
    raise AssertionError("no product-routing inline <script> block found in served page")


def test_all_three_product_routes_serve_200():
    from app.main import app

    client = TestClient(app)
    for path in ("/app/customer", "/app/customer/marketing", "/app/customer/voice"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_all_three_routes_serve_the_same_unified_file():
    """Confirms the intentional single-file consolidation — not a stale duplicate mismatch."""
    from app.main import app

    client = TestClient(app)
    bodies = [
        client.get(p).text
        for p in ("/app/customer", "/app/customer/marketing", "/app/customer/voice")
    ]
    assert bodies[0] == bodies[1] == bodies[2]


def test_page_product_derived_from_url_path_not_dom_class():
    """The regression: pageProduct must NOT be read off document.body.classList alone —
    nothing ever sets that class server-side, so that read always resolved to "combo"."""
    from app.main import app

    client = TestClient(app)
    js = _script_block(client.get("/app/customer/marketing").text)

    assert "location.pathname" in js, (
        "pageProduct must be derived from the URL path — reading it purely from "
        "document.body.classList (the pre-fix bug) always resolves to 'combo' "
        "since nothing sets that class server-side."
    )
    assert '"/customer/marketing"' in js and '"/customer/voice"' in js


def test_body_class_is_set_unconditionally_not_only_after_login():
    """The class must be set before the token/login check — otherwise a logged-out
    demo visitor on /marketing or /voice still gets the wrong (combo) CSS gating."""
    from app.main import app

    client = TestClient(app)
    js = _script_block(client.get("/app/customer/voice").text)

    add_pos = js.find("classList.add(")
    token_pos = js.find('getItem("lgai_token")')
    assert add_pos != -1 and token_pos != -1
    assert add_pos < token_pos, (
        "body class must be added based on the URL path BEFORE the token/login "
        "check, so logged-out demo visitors also get correct product gating."
    )


# --------------------------------------------------------------------------- #
# 2026-07-19 regression guards — customer-reported dashboard bugs:
#   (1) "Billing page — 404": views are hash-based (#view-billing), so the
#       path-style URLs customers naturally type (/app/customer/billing) were
#       a hard 404. Static aliases now 307-redirect to /app/customer#view-<x>.
#   (2) "Leads tab — blank": prod-marketing CSS hides EVERY card of the leads
#       view but the mobile bottom-nav Leads button (and #view-leads deep links)
#       still switched to it -> fully blank main content.
# --------------------------------------------------------------------------- #


def test_path_style_view_aliases_redirect_to_hash_views():
    from app.main import app

    client = TestClient(app)
    for view in ("billing", "leads", "reports", "calendar", "support", "delivery", "setup"):
        r = client.get(f"/app/customer/{view}", follow_redirects=False)
        assert r.status_code == 307, f"/app/customer/{view} -> {r.status_code} (expected 307)"
        assert r.headers["location"] == f"/app/customer#view-{view}"


def test_view_aliases_do_not_shadow_product_and_feature_routes():
    """First-route-wins safety: the aliases must not swallow the real sibling pages."""
    from app.main import app

    client = TestClient(app)
    for path in ("/app/customer/marketing", "/app/customer/voice", "/app/customer/flows"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 200, f"{path} -> {r.status_code} (expected 200 file serve)"


def test_showview_guards_other_products_hidden_views():
    """A marketing customer navigating to the (voice-only) leads view — or a voice
    customer to the (marketing-only) calendar view — must fall back to home, not
    render a blank page with every card display:none."""
    from app.main import app

    client = TestClient(app)
    body = client.get("/app/customer/marketing").text

    assert (
        'if(name==="leads" && document.body.classList.contains("prod-marketing")) name="home";'
        in body
    )
    assert (
        'if(name==="calendar" && document.body.classList.contains("prod-voice")) name="home";'
        in body
    )


def test_mobile_bottom_nav_is_product_gated():
    """The mobile bottom-nav Leads/Posts buttons must be hidden for the product
    that has no such view (the desktop sidebar already was via voice-only /
    marketing-only classes)."""
    from app.main import app

    client = TestClient(app)
    body = client.get("/app/customer").text

    assert '.prod-marketing .mobile-app-nav [data-mobile-view="leads"]' in body
    assert '.prod-voice .mobile-app-nav [data-mobile-view="calendar"]' in body


def test_product_redirect_preserves_view_hash():
    """The product-correction redirect must carry location.hash along, otherwise
    /app/customer/billing -> #view-billing would be dropped for marketing/voice
    customers when they get bounced to their product page."""
    from app.main import app

    client = TestClient(app)
    js = _script_block(client.get("/app/customer").text)

    assert '(location.hash||"")' in js
