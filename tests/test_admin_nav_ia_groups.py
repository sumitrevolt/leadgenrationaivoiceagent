"""Admin navigation contract for the current 4-group delivery-first IA.

Follow-up to Loop-7's narrow cleanup (test_admin_nav_ia_cleanup.py): the user
explicitly asked to continue the IA consolidation the audit flagged as the biggest
remaining gap ("no more than 6 main admin nav items" + "no duplicate dashboards").

This loop regrouped the sidebar's ~40 links (previously scattered across 6 loosely
named groups Overview/Sales/Operations/Business/Advanced/Account) into exactly 6
MISSION-ALIGNED groups, demoting the overlapping ops/infra cockpit pages
(control-center, ops, dashboards, brain, team, office, explorer) out of the
primary nav into ONE "System (Internal)" group.

Purely additive/reversible: every link + badge id + onclick handler preserved,
no /app route or feature removed — so nothing becomes unreachable, only reordered.
"""

from __future__ import annotations

import re


def _admin_html() -> str:
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        return f.read()


# The current 4 mission-aligned groups, in the exact rendered order.
EXPECTED_GROUPS = [
    "Delivery",
    "Automation",
    "Customers",
    "System",
]

# Overlapping ops/infra cockpit pages that MUST live under System (Internal),
# not in any customer-value primary group.
DEMOTED_DASHBOARDS = [
    "/app/control-center",
    "/app/ops",
    "/app/dashboards",
    "/app/brain",
    "/app/team",
    "/app/office",
    "/app/explorer",
]

# Every /app page link that must remain reachable from the sidebar after the
# regroup (reachability guarantee — regroup must not drop any page).
REQUIRED_PAGE_LINKS = [
    "/app/delivery-command-center",
    "/app/onboard",
    "/app/clients",
    "/app/impersonate",
    "/app/automation",
    "/app/outreach",
    "/app/analytics",
    "/app/battlecard",
    "/app/control-center",
    "/app/ops",
    "/app/dashboards",
    "/app/brain",
    "/app/team",
    "/app/office",
    "/app/explorer",
    "/app/agent-tools",
    "/app/team-access",
    "/app/admin-login",
]

# JS-referenced badge ids that must survive the reorder untouched.
REQUIRED_BADGE_IDS = ["nav-clients", "nav-auto-appr", "nav-camp", "nav-niche", "nav-ag"]


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


def test_exactly_six_nav_groups_in_order():
    nav = _nav_block(_admin_html())
    labels = _group_labels(nav)
    assert len(labels) == 4, f"expected 4 nav groups, got {len(labels)}: {labels}"
    assert labels == EXPECTED_GROUPS, labels


def test_no_more_than_six_groups_rule():
    assert len(_group_labels(_nav_block(_admin_html()))) <= 4


def test_duplicate_dashboards_demoted_into_system_group():
    nav = _nav_block(_admin_html())
    system_block = nav.split(">System</div>", 1)[1]
    for href in DEMOTED_DASHBOARDS:
        assert (
            f'href="{href}"' in system_block
        ), f"{href} must be under System (Internal), found elsewhere or missing"


def test_demoted_dashboards_not_in_primary_groups():
    groups = _parse_groups(_nav_block(_admin_html()))
    primary = ("Delivery", "Automation", "Customers")
    primary_block = "".join(groups[g] for g in primary)
    for href in DEMOTED_DASHBOARDS:
        assert (
            f'href="{href}"' not in primary_block
        ), f"{href} is a duplicate/infra cockpit — must not sit in a primary nav group"


def test_command_center_is_front_door_in_overview():
    groups = _parse_groups(_nav_block(_admin_html()))
    assert 'href="/app/delivery-command-center"' in groups["Delivery"]


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
    assert 'class="active"' in nav
    assert "openOnboard();return false;" in nav  # Add Customer handler intact
    assert 'onclick="expandAdvTech()"' in nav  # God Mode handler intact
    assert 'id="navAdminLogin"' in nav  # login link id intact


# ---------------------------------------------------------------------------
# Orphan-page MERGE step (2026-07-07): previously-orphaned but UNIQUE working
# feature pages surfaced back into nav so no feature is lost. "Merge before
# delete" — these are NOT delete candidates (nothing to merge them into).
# ---------------------------------------------------------------------------
SURFACED_ORPHANS = {
    "/app/calendar": "Automation",
    "/app/whatsapp": "System",
    "/app/studio": "System",
    "/app/deals": "System",
    "/app/segments": "System",
    "/app/growth-tools": "System",
}


def test_surfaced_orphans_present_exactly_once_in_correct_group():
    groups = _parse_groups(_nav_block(_admin_html()))
    nav = _nav_block(_admin_html())
    for href, group in SURFACED_ORPHANS.items():
        assert nav.count(f'href="{href}"') == 1, f"{href} should be linked exactly once"
        block = groups[group]
        if group == "System":
            block = nav.split('id="nav-system-extra"', 1)[1]
        assert f'href="{href}"' in block, f"{href} expected under {group}"


def test_command_center_duplicate_stays_unlinked():
    # /app/command-center (old Ops cockpit) was MERGED→DELETED (route now
    # redirects to /app/control-center). Its redirect route must stay UNLINKED
    # from nav — re-linking it would re-introduce the duplicate entry point.
    nav = _nav_block(_admin_html())
    assert 'href="/app/command-center"' not in nav
