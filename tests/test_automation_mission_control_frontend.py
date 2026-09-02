"""Automation Mission Control loader resilience contracts."""

from pathlib import Path

HTML = Path("frontend/automation.html")


def test_today_tab_autoloads_launch_status_and_has_error_fallbacks():
    html = HTML.read_text(encoding="utf-8")
    assert "var AUTOLOAD={today:tdLoad,launch:launchLoad" in html
    assert "if(tab==='today')setTimeout(function(){launchLoad().catch(function(){})" in html
    assert "Production readiness load nahi hua" in html
    assert "Wizard load nahi hua" in html


def test_today_loader_replaces_team_and_schedule_placeholders_on_fail():
    html = HTML.read_text(encoding="utf-8")
    assert "Team data abhi available nahi." in html
    assert "Schedule data abhi available nahi." in html
    assert "Automation flags abhi available nahi." in html
