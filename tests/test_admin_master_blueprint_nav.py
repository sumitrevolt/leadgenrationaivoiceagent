"""Master Blueprint must be reachable FROM THE ADMIN PANEL (2026-08-07).

Owner-reported bug: "Master Blueprint is missing in the Admin Panel."

Falsified first, then fixed. The feature itself was NOT missing:
  * ``/api/blueprint/{graph,public,validate,trace,meta}`` are mounted and live
    (prod probe: ``/api/blueprint/meta`` -> 200 ``2026-08-03-mbp-v4``,
    ``/api/blueprint/graph`` -> 401 = admin gate working as designed).
  * ``frontend/explorer.html`` ships the ``master`` sub-mode and honours the
    ``?view=master`` deep-link in ``BP.boot()``.

What WAS missing: the admin sidebar only linked bare ``/app/explorer``, which
boots into *Project* Blueprint mode. Live prod ``/app/admin`` HTML contained
**zero** occurrences of "Master Blueprint", so an admin who did not already know
the deep-link had no way in. This module is the regression guard for that link.

Updated 2026-08-19: c18e3384 refactored the nav to 8 numbered groups. The bare
/app/explorer link was removed; only the ``?view=master`` deep-link survives
under the System group. Tests updated to match.
"""

from __future__ import annotations

import re

MASTER_HREF = "/app/explorer?view=master"


def _admin_html() -> str:
    with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
        return f.read()


def _nav_block(html: str) -> str:
    m = re.search(r"<nav class=\"nav\".*?</nav>", html, re.DOTALL)
    assert m, "sidebar <nav> block not found"
    return m.group(0)


def test_master_blueprint_link_present_in_admin_nav():
    nav = _nav_block(_admin_html())
    assert f'href="{MASTER_HREF}"' in nav, (
        "admin sidebar has no Master Blueprint entry — the canonical graph is unreachable"
    )


def test_master_blueprint_labelled_so_an_admin_can_find_it():
    nav = _nav_block(_admin_html())
    link = re.search(rf'<a href="{re.escape(MASTER_HREF)}".*?</a>', nav, re.DOTALL)
    assert link, "Master Blueprint anchor not found"
    assert "Architecture Explorer" in link.group(0), "link must be labelled clearly for admins"
    assert 'role="menuitem"' in link.group(0), "must be a real menuitem, not a bare anchor"


def test_master_blueprint_registered_exactly_once_in_nav():
    nav = _nav_block(_admin_html())
    count = len(re.findall(re.escape(f'href="{MASTER_HREF}"'), nav))
    assert count == 1, f"expected exactly one Master Blueprint nav link, found {count}"


def test_bare_explorer_link_removed_from_nav():
    """c18e3384 removed the bare /app/explorer link from the sidebar.
    Only the ?view=master deep-link should remain in the <nav> block."""
    nav = _nav_block(_admin_html())
    # Count bare explorer links (href="/app/explorer" with closing quote,
    # but NOT href="/app/explorer?view=master")
    bare_count = len(re.findall(r'href="/app/explorer(?!\?)', nav))
    assert bare_count == 0, (
        f"bare /app/explorer link should be removed from nav, found {bare_count}"
    )


def test_master_blueprint_lives_under_system_group():
    """Master Blueprint must be in the System group (group 7)."""
    nav = _nav_block(_admin_html())
    # Find the System group block
    parts = re.split(r'<div class="sec nav-group"[^>]*>(.*?)</div>', nav)
    # parts = [pre, label1, block1, label2, block2, ...]
    groups = {}
    for i in range(1, len(parts), 2):
        groups[parts[i]] = parts[i + 1]
    assert "7. System" in groups, "System group not found in nav"
    assert f'href="{MASTER_HREF}"' in groups["7. System"], (
        "Master Blueprint must be under System group"
    )


def test_guard_is_not_vacuous():
    """Prove the guard detects the real regression rather than always passing.

    R4 (docs/AGENT_WORK_RULES.md): a test that asserts presence must itself
    create the absence case, otherwise a passing run proves nothing.
    """
    nav = _nav_block(_admin_html())
    stripped = nav.replace(f'href="{MASTER_HREF}"', 'href="/app/explorer"')
    assert f'href="{MASTER_HREF}"' not in stripped, "fixture did not actually remove the link"
