"""Automation dashboard loaders must always resolve to an actionable state."""

import re
from pathlib import Path

HTML = Path("frontend/automation.html")


def test_today_overview_auth_failure_clears_every_loading_placeholder():
    html = HTML.read_text(encoding="utf-8")
    start = html.index("async function tdLoad()")
    end = html.index("/* ---------------- Loyalty", start)
    snippet = html[start:end]
    error_branch = snippet[snippet.rindex("}catch(e)") :]

    assert "$('tdHead').textContent=" in error_branch
    assert "warnBox('tdProblems'" in error_branch
    assert "$('tdStaff').innerHTML=" in error_branch
    assert "$('tdJobs').innerHTML=" in error_branch
    assert "$('tdFlags').innerHTML=" in error_branch
    assert "load ho raha" not in error_branch.lower()


# --------------------------------------------------------------------------- #
# 2026-07-19 regression guards — "Automation main content empty" + token UX.
# --------------------------------------------------------------------------- #


def test_no_read_tool_line_number_artifacts_in_script():
    """A stray `  3150|    $('tdFlags')...` line (Read-tool line-number paste from
    an earlier edit) was a JS SyntaxError that killed the ENTIRE main script —
    `.tabsec{display:none}` default meant every section stayed hidden = the
    reported 'main content empty' bug. Guard against any recurrence."""
    html = HTML.read_text(encoding="utf-8")
    artifacts = re.findall(r"^\s+\d{2,6}\|.*$", html, re.M)
    assert not artifacts, f"line-number paste artifacts found: {artifacts[:3]}"


def test_admin_token_prefills_from_localstorage():
    """The token field promises 'login se auto' — /app/admin-login stores
    `accessToken` in localStorage, so the page must prefill it on load."""
    html = HTML.read_text(encoding="utf-8")
    assert "var t=tok();if(t)$('tokin').value=t" in html


def test_empty_save_does_not_wipe_login_token():
    html = HTML.read_text(encoding="utf-8")
    start = html.index("function saveTok()")
    snippet = html[start : start + 400]
    assert "if(!v)" in snippet, "empty Save must not overwrite the login token with ''"


def test_boot_valid_tabs_derived_from_sidebar_dom():
    """The old hard-coded hash whitelist drifted (growthlab/clientops/rl missing)
    so their deep links bounced to 'today'. It must be DOM-derived now."""
    html = HTML.read_text(encoding="utf-8")
    assert "querySelectorAll('#sidebar button[id^=\"tab-\"]')" in html


def test_every_sidebar_tab_has_a_section():
    """show(tab) does `$('sec-'+tab).style.display` — a button without a matching
    section throws mid-boot and can blank the page."""
    html = HTML.read_text(encoding="utf-8")
    tabs = set(re.findall(r"show\('([a-z0-9]+)'\)", html))
    secs = set(re.findall(r'id="sec-([a-z0-9]+)"', html))
    assert tabs <= secs, f"tabs without a section: {sorted(tabs - secs)}"
