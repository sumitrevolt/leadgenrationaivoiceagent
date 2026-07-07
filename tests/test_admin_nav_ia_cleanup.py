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
"""
from __future__ import annotations


def _admin_html():
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        return f.read()


def _ops_cc_html():
    with open("frontend/command_center.html", encoding="utf-8") as f:
        return f.read()


def _delivery_cc_html():
    with open("frontend/delivery_command_center.html", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. Distinct titles/badges for the two Command Center pages
# ---------------------------------------------------------------------------
def test_ops_and_delivery_command_center_titles_are_distinct():
    ops_html = _ops_cc_html()
    delivery_html = _delivery_cc_html()

    import re

    ops_title = re.search(r"<title>(.*?)</title>", ops_html).group(1)
    delivery_title = re.search(r"<title>(.*?)</title>", delivery_html).group(1)

    assert ops_title != delivery_title
    assert "Ops" in ops_title


def test_ops_command_center_badge_also_disambiguated():
    """The <title> isn't the only user-visible label — the page header shows
    a .badge div with the same text. Both must be updated for the fix to be
    real (a title-only fix would still show "Command Center" on the page
    itself, defeating the disambiguation)."""
    html = _ops_cc_html()
    assert '<div class="badge">Ops Command Center</div>' in html
    assert '<div class="badge">Command Center</div>' not in html


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
    assert html.count('href="/app/clients"') == 1


def test_clients_nav_link_is_in_menubar_nav():
    """Confirm the new link lives inside the actual <nav role="menubar">
    sidebar block, not some unrelated part of the page."""
    html = _admin_html()
    nav_start = html.index('<nav class="nav" role="menubar"')
    nav_end = html.index("</nav>", nav_start)
    nav_block = html[nav_start:nav_end]
    assert 'href="/app/clients"' in nav_block


# ---------------------------------------------------------------------------
# 3. agent-tools regrouped under "Advanced", not deleted
# ---------------------------------------------------------------------------
def test_agent_tools_link_still_present_exactly_once():
    """Regrouping must not delete the feature or duplicate the link."""
    html = _admin_html()
    assert html.count('href="/app/agent-tools"') == 1


def test_agent_tools_moved_out_of_operations_into_advanced_group():
    html = _admin_html()
    advanced_idx = html.index('<div class="sec nav-group" role="presentation">Advanced</div>')
    account_idx = html.index('<div class="sec nav-group" role="presentation">Account</div>')
    operations_idx = html.index('<div class="sec nav-group" role="presentation">Operations</div>')
    business_idx = html.index('<div class="sec nav-group" role="presentation">Business</div>')
    agent_tools_idx = html.index('href="/app/agent-tools"')

    # Advanced group sits between Business and Account (the last two groups).
    assert business_idx < advanced_idx < account_idx
    # The agent-tools link is inside the Advanced group, not Operations/Business.
    assert advanced_idx < agent_tools_idx < account_idx
    assert not (operations_idx < agent_tools_idx < business_idx)


def test_agent_tools_label_signals_dev_only():
    html = _admin_html()
    idx = html.index('href="/app/agent-tools"')
    snippet = html[idx : idx + 200]
    assert "Dev" in snippet
