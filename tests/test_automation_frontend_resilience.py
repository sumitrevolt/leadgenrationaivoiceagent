"""Automation dashboard loaders must always resolve to an actionable state."""

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
