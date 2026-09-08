"""Customer Delivery OS — Loop 7 (final sub-project): narrow, additive IA cleanup.

Discovery (background research agent) found a much larger admin-nav sprawl than
the mission brief assumed (13 fully-orphaned admin pages, 5 overlapping ops
cockpits, 3 overlapping staff-roster views, 3 overlapping inbox views) — all of
that is PRE-EXISTING and admin-side, out of scope for a customer-value-delivery
mission (parked in memory/backlog.md with the evidence). Only 3 narrow, additive
items were actually in scope:

  1. The two "Command Center" pages shared an identical <title> and on-page
     badge text ("Command Center") — disambiguated the OLDER ops/infra page to
     "Ops Command Center" (the NEW business-outcome page keeps the plain name,
     since it's the one linked from nav). No merge — discovery found the old
     page already has zero nav links (de-facto hidden already), so there was
     nothing to reconcile beyond the naming collision.
  2. /app/clients (this mission's own Loop-2 "Deliver Now" deliverable) had NO
     direct sidebar nav link — reachable only via a link buried inside the new
     Command Center page. Added a direct link.
  3. /app/agent-tools exposes raw code-review/diagnostics/code-exec/browser-
     fetch tools — confirmed dev-only, not a normal business feature a local
     shop-owner admin would use day to day (matches memory/backlog.md's
     hide-from-default-nav candidate note). Regrouped (not deleted) under a new
     "Advanced" nav section with an explicit "(Dev)" label, reversible.

Updated 2026-08-19: c18e3384 refactored the nav to 8 numbered groups. Many
links (agent-tools, onboard, calendar, etc.) were removed from the sidebar
as part of the daily-workflow streamlining. Tests updated to match.
"""

from __future__ import annotations


def _admin_html():
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        return f.read()


import os


def _main_py():
    with open("app/main.py", encoding="utf-8") as f:
        return f.read()


def _delivery_cc_html():
    with open("frontend/delivery_command_center.html", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. Distinct titles/badges for the two Command Center pages
# ---------------------------------------------------------------------------
def test_ops_command_center_merged_and_deleted():
    # ADR-034 follow-up (2026-07-07, LLM-council decision): the old Ops Command
    # Center duplicated /app/control-center + /app/ops. It was MERGED (route now
    # redirects) and the template DELETED (merge-before-delete). File must be gone.
    assert not os.path.exists("frontend/command_center.html")


def test_command_center_route_redirects_to_control_center():
    # The /app/command-center route is kept as a permanent redirect so old
    # bookmarks still resolve to the canonical ops cockpit instead of 404-ing.
    main = _main_py()
    assert 'RedirectResponse(url="/app/control-center"' in main


def test_delivery_command_center_title_unchanged():
    """The NEW business-outcome page is the one linked from nav under the
    plain "Command Center" label — its title should NOT have been touched by
    this loop's disambiguation fix."""
    html = _delivery_cc_html()
    assert "<title>LeadGen AI — Command Center</title>" in html


# ---------------------------------------------------------------------------
# 2. /app/clients direct nav link
# ---------------------------------------------------------------------------
def test_admin_nav_links_directly_to_clients_page():
    html = _admin_html()
    assert 'href="/app/clients"' in html
    assert html.count('href="/app/clients"') >= 1


def test_clients_nav_link_is_in_menubar_nav():
    """Confirm the new link lives inside the actual <nav role="menubar">
    sidebar block, not some unrelated part of the page."""
    html = _admin_html()
    nav_start = html.index('<nav class="nav" role="menubar"')
    nav_end = html.index("</nav>", nav_start)
    nav_block = html[nav_start:nav_end]
    assert 'href="/app/clients"' in nav_block


# ---------------------------------------------------------------------------
# 3. agent-tools removed from sidebar (c18e3384 refactored to 8-group layout)
# ---------------------------------------------------------------------------
def test_agent_tools_not_in_nav_sidebar():
    """agent-tools was removed from the sidebar as part of the 8-group
    daily-workflow refactoring.  It should NOT appear in the <nav> block."""
    html = _admin_html()
    nav_start = html.index('<nav class="nav" role="menubar"')
    nav_end = html.index("</nav>", nav_start)
    nav_block = html[nav_start:nav_end]
    assert 'href="/app/agent-tools"' not in nav_block


# ---------------------------------------------------------------------------
# 4. Hot Queue must be prominent in Sales group
# ---------------------------------------------------------------------------
def test_admin_nav_hot_queue_in_sales_group():
    html = _admin_html()
    nav_start = html.index('<nav class="nav" role="menubar"')
    nav_end = html.index("</nav>", nav_start)
    nav_block = html[nav_start:nav_end]
    assert 'href="/app/inbox"' in nav_block
    assert 'id="navHotQueue"' in nav_block
    # Hot Queue must appear under "Sales" group (group 2)
    sales_idx = nav_block.index("2. Sales")
    inbox_idx = nav_block.index('href="/app/inbox"')
    assert sales_idx < inbox_idx
