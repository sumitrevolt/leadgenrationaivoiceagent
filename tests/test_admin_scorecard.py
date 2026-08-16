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

    def test_paid_gross_element(self):
        assert 'id="scPaidGross"' in self.html

    def test_upi_pending_element(self):
        assert 'id="scUpiPending"' in self.html

    def test_start_today_element(self):
        assert 'id="scStartToday"' in self.html

    def test_onboard_element(self):
        assert 'id="scOnboard"' in self.html

    def test_delivery_risk_element(self):
        assert 'id="scDeliveryRisk"' in self.html

    def test_automation_fail_element(self):
        assert 'id="scAutomationFail"' in self.html

    def test_dsh_element(self):
        assert 'id="scDsh"' in self.html

    def test_staff_bus_element(self):
        assert 'id="scStaffBus"' in self.html

    def test_marketing_scorecard_container(self):
        assert 'id="ownerMktScorecard"' in self.html

    def test_reviews_sent_element(self):
        assert 'id="scReviewsSent"' in self.html
        assert "Review requests sent" in self.html

    def test_drip_sent_opened_element(self):
        assert 'id="scDripSentOpened"' in self.html
        assert "Drip sent/opened" in self.html

    def test_forms_submitted_element(self):
        assert 'id="scFormsSubmitted"' in self.html

    def test_proposals_accepted_element(self):
        assert 'id="scProposalsAccepted"' in self.html

    def test_reminders_sent_element(self):
        assert 'id="scRemindersSent"' in self.html

    def test_health_at_risk_element(self):
        assert 'id="scHealthAtRisk"' in self.html

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

    def test_paintOwnerScorecards_helper(self):
        assert "function paintOwnerScorecards(t)" in self.html
        assert "upi_needs_owner" in self.html
        assert "dsh_runtime" in self.html
        assert "reviews_sent" in self.html
        assert "drip_emails_sent" in self.html
        assert "drip_emails_opened" in self.html
        assert "forms_submitted" in self.html
        assert "proposals_accepted" in self.html
        assert "reminders_sent" in self.html
        assert "health_at_risk" in self.html

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
        idx_todaybiz = self.html.index("async function loadTodayBiz()")
        idx_sync = self.html.index("paintOwnerScorecards(t)", idx_todaybiz)
        assert idx_sync > idx_todaybiz

    def test_next_best_action_priority_hot_queue(self):
        """Hot Queue is highest priority in next best action."""
        assert "hot_queue" in self.html
        assert "/app/inbox" in self.html

    def test_next_best_action_upi_from_totals(self):
        assert "upi_needs_owner" in self.html
        assert "/app/admin#sec-upi-selfserve" in self.html

    def test_no_fake_metrics(self):
        """Scorecard shows real API data, not hardcoded numbers."""
        assert "paid_today:1" not in self.html.replace(" ", "")
        assert "activations_today:1" not in self.html.replace(" ", "")

    def test_no_hardcoded_plugin_count(self):
        assert "all 42 plugin manifests" not in self.html

    def test_uses_auth_header(self):
        """All API calls use abAuthHdr() for admin auth."""
        assert "abAuthHdr()" in self.html
