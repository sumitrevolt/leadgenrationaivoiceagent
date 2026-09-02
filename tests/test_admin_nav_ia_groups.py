"""Admin navigation contract for the current 8-group mission-aligned IA.

Commit c18e3384 refactored the sidebar from 4 mission-aligned groups into 8
numbered, task-oriented groups:
  1. Today  2. Sales  3. Customers  4. Content & Delivery
  5. Automations  6. Agents  7. System  8. Owner Controls

This is a streamlined "daily workflow" layout — an admin opens the panel and
scans top-to-bottom through their workday: morning overview → sales outreach →
client management → content/delivery → automations → agents → system health →
owner-only controls.

Links that were previously in the sidebar were consolidated or moved to
section-based anchors.  Only primary daily-action links remain in the nav.
"""

from __future__ import annotations

import re


def _admin_html() -> str:
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        return f.read()


# The current 8 numbered groups, in the exact rendered order.
EXPECTED_GROUPS = [
    "1. Today",
    "2. Sales",
    "3. Customers",
    "4. Content & Delivery",
    "5. Automations",
    "6. Agents",
    "7. System",
    "8. Owner Controls",
]

# Every /app page link that must remain reachable from the sidebar.
# The refactored nav keeps only primary daily-action external links.
REQUIRED_PAGE_LINKS = [
    "/app/delivery-command-center",
    "/app/clients",
    "/app/automation",
    "/app/outreach",
    "/app/control-center",
    "/app/team-access",
    "/app/admin-login",
    "/app/inbox",
    "/app/studio",
]

# JS-referenced badge ids that must survive the reorder untouched.
REQUIRED_BADGE_IDS = ["nav-clients", "nav-auto-appr", "nav-camp", "nav-ag"]


def _nav_block(html: str) -> str:
    m = re.search(r"<nav class=\"nav\".*?</nav>", html, re.DOTALL)
    assert m, "sidebar <nav> block not found"
    return m.group(0)


_GROUP_DIV = r'<div class="sec nav-group"[^>]*>(.*?)</div>'


def _group_labels(nav: str) -> list[str]:
    return re.findall(_GROUP_DIV, nav)


def _parse_groups(nav: str) -> dict[str, str]:
    """Split the nav into {group_label: block_of_links_under_it}.

    Splits on the real group-<div> markers only, so the leading HTML comment
    (which happens to mention several group words) is discarded and can never
    pollute a membership slice.
    """
    parts = re.split(_GROUP_DIV, nav)
    # parts = [pre-first-group, label1, block1, label2, block2, ...]
    groups: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        groups[parts[i]] = parts[i + 1]
    return groups


def test_exactly_eight_nav_groups_in_order():
    nav = _nav_block(_admin_html())
    labels = _group_labels(nav)
    assert len(labels) == 8, f"expected 8 nav groups, got {len(labels)}: {labels}"
    assert labels == EXPECTED_GROUPS, labels


def test_no_more_than_ten_groups_rule():
    """Practical ceiling: allow small future growth but catch runaway sprawl."""
    assert len(_group_labels(_nav_block(_admin_html()))) <= 10


def test_control_center_lives_in_system_group():
    nav = _nav_block(_admin_html())
    groups = _parse_groups(nav)
    assert 'href="/app/control-center"' in groups["7. System"], (
        "/app/control-center must be under System group"
    )


def test_delivery_command_center_in_content_group():
    groups = _parse_groups(_nav_block(_admin_html()))
    assert 'href="/app/delivery-command-center"' in groups["4. Content & Delivery"]


def test_all_page_links_still_reachable():
    nav = _nav_block(_admin_html())
    for href in REQUIRED_PAGE_LINKS:
        assert f'href="{href}"' in nav, f"regroup dropped a page link: {href}"


def test_each_page_link_registered_exactly_once():
    nav = _nav_block(_admin_html())
    for href in REQUIRED_PAGE_LINKS:
        count = len(re.findall(rf'href="{re.escape(href)}"', nav))
        assert count == 1, f"{href} should appear once in nav, found {count}"


def test_badge_ids_preserved():
    nav = _nav_block(_admin_html())
    for bid in REQUIRED_BADGE_IDS:
        assert f'id="{bid}"' in nav, f"badge id lost in reorder: {bid}"


def test_active_dashboard_link_and_handlers_preserved():
    nav = _nav_block(_admin_html())
    assert 'onclick="expandAdvTech()"' in nav  # God Mode handler intact
    assert 'id="navAdminLogin"' in nav  # login link id intact


def test_command_center_duplicate_stays_unlinked():
    # /app/command-center (old Ops cockpit) was MERGED→DELETED (route now
    # redirects to /app/control-center). Its redirect route must stay UNLINKED
    # from nav — re-linking it would re-introduce the duplicate entry point.
    nav = _nav_block(_admin_html())
    assert 'href="/app/command-center"' not in nav


def test_master_blueprint_link_in_system_group():
    """Master Blueprint deep-link must live under System, not a primary group."""
    nav = _nav_block(_admin_html())
    groups = _parse_groups(nav)
    assert 'href="/app/explorer?view=master"' in groups["7. System"]


def test_hot_queue_is_prominent_in_sales():
    """Hot Queue must be in the Sales group as the primary outreach action."""
    nav = _nav_block(_admin_html())
    groups = _parse_groups(nav)
    assert 'href="/app/inbox"' in groups["2. Sales"]
    assert 'id="navHotQueue"' in groups["2. Sales"]


def test_team_access_and_admin_login_in_owner_controls():
    groups = _parse_groups(_nav_block(_admin_html()))
    assert 'href="/app/team-access"' in groups["8. Owner Controls"]
    assert 'href="/app/admin-login"' in groups["8. Owner Controls"]
