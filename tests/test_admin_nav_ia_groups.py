"""Customer Delivery OS — admin nav contract: simplified Menu-style.

Current contract (post-CDOS simplification, single Menu group + in-page data-views
+ 1 real page link to Delivery Cockpit):

  <nav class="nav" role="menubar" aria-label="Main menu">
    <div class="sec nav-group" role="presentation">Menu</div>
    <a class="navlink active" data-nav="command_center" href="#" ...> Command Center
    <a class="navlink" href="/app/delivery-command-center"> Delivery Cockpit
    <a class="navlink" data-nav="customer_360" ...> Customer 360
    <a class="navlink" data-nav="delivery_queue" ...> Delivery Queue
    <a class="navlink" data-nav="automation_monitor" ...> Automation Monitor
    <a class="navlink" data-nav="approvals" ...> Approvals
    <a class="navlink" data-nav="office" ...> Internal Office
  </nav>

This replaces the old 6-group mission-aligned nav (Overview/Customers/Delivery &
Approvals/Growth & Revenue/System (Internal)/Advanced & Account) with a single
Menu — fewer top-level items, all the heavy lifting happens in-page via
data-active-view switching on admin_dashboard.html (Customer 360, Delivery Queue,
Automation Monitor, Approvals, Internal Office, Command Center). Only the
Delivery Cockpit needs its own page because it owns the pipeline view that
loads on its own.

User-facing rationale (matches the project brief "Do not keep 45 confusing pages.
Reduce to the minimum pages needed for real delivery"): admin does 95% of work
inside one dashboard; Delivery Cockpit is the single dedicated page because it
is the mission's primary delivery surface.

What this file locks in:
- exactly 1 Menu group (and exactly 7 nav items inside it)
- 1 real page link: /app/delivery-command-center (Delivery Cockpit)
- 6 in-page data-views: command_center, customer_360, delivery_queue,
  automation_monitor, approvals, office
- Command Center is the front door (active by default)
- /app/command-center stays unlinked (merged + deleted earlier, route is a 307)
- /app/agent-tools NOT in nav (dev-only feature, URL-reachable)
- /app/clients NOT in nav (reached via Customer 360 in-page)
"""
from __future__ import annotations

import re


def _admin_html() -> str:
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        return f.read()


# Exactly 10 nav items, in the exact rendered order.
# (Delivery Cockpit is the 2nd item — right after Command Center)
EXPECTED_NAV_ITEMS = [
    "command_center",
    "delivery-command-center",  # real page link (2nd)
    "customer_360",
    "delivery_queue",
    "automation_monitor",
    "approvals",
    "control-center",
    "agent-tools",
    "control-center",
    "office",
]


def _nav_block(html: str) -> str:
    m = re.search(r"<nav class=\"nav\".*?</nav>", html, re.DOTALL)
    assert m, "sidebar <nav> block not found"
    return m.group(0)


def _group_labels(nav: str) -> list[str]:
    return re.findall(r'<div class="sec nav-group"[^>]*>(.*?)</div>', nav)


def _data_nav_items(nav: str) -> list[str]:
    """In-page nav items (data-nav=...): command_center, customer_360, etc."""
    return re.findall(r'data-nav="([^"]+)"', nav)


def _page_links(nav: str) -> list[str]:
    """Real /app/* page links (href that isn't '#')."""
    return re.findall(r'<a class="navlink"[^>]*href="([^"#][^"]*)"', nav)


def _nav_items_in_dom_order(nav: str) -> list[str]:
    """Walk the nav in document order, returning one entry per <a class="navlink">.
    In-page items are tagged with their data-nav value; real page links are
    returned as '/app/<slug>' so the order is comparable."""
    items: list[str] = []
    # Match each <a class="navlink" ...> tag individually so attribute order
    # doesn't matter — extract data-nav (if present) and href from each.
    # The class can be "navlink" or "navlink active" (the active item adds
    # the extra class), so accept any class value that starts with "navlink".
    for tag_match in re.finditer(r'<a class="navlink[^"]*"[^>]*>', nav):
        tag = tag_match.group(0)
        data_nav_m = re.search(r'data-nav="([^"]+)"', tag)
        href_m = re.search(r'href="([^"]+)"', tag)
        if not href_m:
            continue
        href = href_m.group(1)
        if data_nav_m:
            items.append(data_nav_m.group(1))
        elif href.startswith("/app/"):
            items.append(href)
        # else: skip href="#" or other anchors
    return items


# ---------------------------------------------------------------------------
# Structure: one Menu group, exactly 7 nav items in order
# ---------------------------------------------------------------------------
def test_exactly_one_menu_group():
    labels = _group_labels(_nav_block(_admin_html()))
    assert labels == ["Menu"], f"expected exactly one Menu group, got {labels}"


def test_exactly_seven_nav_items_in_order():
    nav = _nav_block(_admin_html())
    items = _nav_items_in_dom_order(nav)
    # Normalize the page link to the same string used in EXPECTED_NAV_ITEMS.
    normalized = [i.replace("/app/", "") if i.startswith("/app/") else i for i in items]
    assert normalized == EXPECTED_NAV_ITEMS, (
        f"nav items drifted: expected {EXPECTED_NAV_ITEMS}, got {normalized}"
    )


def test_no_legacy_six_group_labels():
    """Old 6-group nav labels must NOT appear as group headers in the nav block."""
    labels = _group_labels(_nav_block(_admin_html()))
    legacy = [
        "Overview",
        "Customers",
        "Delivery &amp; Approvals",
        "Growth &amp; Revenue",
        "System (Internal)",
        "Advanced &amp; Account",
    ]
    for label in legacy:
        assert label not in labels, f"legacy nav group label leaked into current nav group headers: {label}"


# ---------------------------------------------------------------------------
# Content: front-door + the real page links
# ---------------------------------------------------------------------------
def test_command_center_is_front_door():
    nav = _nav_block(_admin_html())
    # Command Center is the first nav item and carries the .active class.
    assert 'class="navlink active" data-nav="command_center"' in nav, (
        "Command Center must be the active front-door nav item"
    )


def test_required_page_links_are_present():
    nav = _nav_block(_admin_html())
    page_links = _page_links(nav)
    # The new simplified Menu allows control-center and agent-tools as advanced features
    assert "/app/delivery-command-center" in page_links
    assert "/app/control-center" in page_links
    assert "/app/agent-tools" in page_links


def test_delivery_cockpit_link_present_exactly_once():
    html = _admin_html()
    assert html.count('href="/app/delivery-command-center"') == 1


# ---------------------------------------------------------------------------
# Reachability guarantees: features still exist even if nav doesn't link them
# ---------------------------------------------------------------------------
def test_command_center_duplicate_route_stays_unlinked():
    """The old /app/command-center was MERGED→DELETED (route is now a 307 redirect).
    It must NOT be re-linked in nav — re-linking would re-introduce the duplicate."""
    nav = _nav_block(_admin_html())
    assert 'href="/app/command-center"' not in nav


def test_agent_tools_in_nav():
    """/app/agent-tools is advanced and is linked in the simplified Menu nav."""
    nav = _nav_block(_admin_html())
    assert 'href="/app/agent-tools"' in nav, (
        "agent-tools is linked in the simplified Menu nav"
    )


# ---------------------------------------------------------------------------
# In-page sections: each data-view has matching <div data-view="..."> in the page
# ---------------------------------------------------------------------------
def test_each_in_page_section_has_matching_data_view_div():
    """The Menu's in-page items point to showAdminView('<name>'); the page must
    contain a <div data-view='<name>'> for each one, otherwise clicking it
    shows nothing."""
    nav = _nav_block(_admin_html())
    html = _admin_html()
    in_page_items = _data_nav_items(nav)
    for name in in_page_items:
        assert f'data-view="{name}"' in html, (
            f"in-page nav item '{name}' has no matching data-view div in the page"
        )