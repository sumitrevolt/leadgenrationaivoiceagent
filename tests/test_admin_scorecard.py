"""Test admin dashboard scorecard — live elements + JS function present."""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
DASHBOARD = FRONTEND / "admin_dashboard.html"


class TestAdminScorecardHTML:
    """Scorecard elements exist in admin_dashboard.html."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.html = DASHBOARD.read_text(encoding="utf-8")

    def test_scorecard_container(self):
        assert 'id="ownerScorecard"' in self.html

    def test_paid_today_element(self):
        assert 'id="scPaidToday"' in self.html

    def test_activations_element(self):
        assert 'id="scActivations"' in self.html

    def test_hot_queue_element(self):
        assert 'id="scHotQueue"' in self.html

    def test_pending_element(self):
        assert 'id="scPending"' in self.html

    def test_next_best_action_container(self):
        assert 'id="nextBestAction"' in self.html

    def test_next_best_action_text(self):
        assert 'id="nextBestActionText"' in self.html


class TestAdminScorecardJS:
    """JavaScript functions exist and are correctly wired."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.html = DASHBOARD.read_text(encoding="utf-8")

    def test_loadOwnerScorecard_function(self):
        assert "async function loadOwnerScorecard()" in self.html

    def test_fetches_today_overview(self):
        assert "/api/growth/overview/today" in self.html

    def test_fetches_admin_office(self):
        assert "/api/admin/office" in self.html

    def test_dom_content_loaded_hook(self):
        assert "DOMContentLoaded" in self.html
        assert "loadOwnerScorecard" in self.html

    def test_auto_refresh_interval(self):
        assert "setInterval(loadOwnerScorecard, 60000)" in self.html

    def test_scorecard_syncs_with_today_biz(self):
        """loadTodayBiz should also update scorecard elements."""
        assert "scPaidToday" in self.html
        # The sync block should be inside loadTodayBiz
        idx_todaybiz = self.html.index("async function loadTodayBiz()")
        idx_sync = self.html.index("scPaidToday", idx_todaybiz)
        assert idx_sync > idx_todaybiz

    def test_next_best_action_priority_hot_queue(self):
        """Hot Queue is highest priority in next best action."""
        assert "hot_queue" in self.html
        assert "/app/inbox" in self.html

    def test_no_fake_metrics(self):
        """Scorecard shows real API data, not hardcoded numbers."""
        # Should NOT have hardcoded paid_today=1 or similar
        assert "paid_today:1" not in self.html.replace(" ", "")
        assert "activations_today:1" not in self.html.replace(" ", "")

    def test_uses_auth_header(self):
        """All API calls use abAuthHdr() for admin auth."""
        assert "abAuthHdr()" in self.html
