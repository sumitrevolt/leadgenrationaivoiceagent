"""Contract tests for the customer activation nudge."""

from app.api.customer_dashboard_builders import _approval_banner


def test_approval_banner_is_hidden_when_queue_is_empty(monkeypatch):
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda _cid: [], raising=False)
    banner = _approval_banner("client-a")
    assert banner.show is False
    assert banner.count == 0
    assert banner.target == "approvalCard"


def test_approval_banner_is_customer_safe_and_counts_pending_items(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.content_approval.pending",
        lambda _cid: [
            {"id": "secret-1", "content": {"phone": "+919999999999"}},
            {"id": "secret-2", "content": {"email": "owner@example.com"}},
        ],
        raising=False,
    )
    banner = _approval_banner("client-a")
    assert banner.show is True
    assert banner.count == 2
    assert banner.urgency == "normal"
    assert banner.target == "approvalCard"
    assert "secret-" not in banner.message
    assert "+919999999999" not in banner.message
    assert "owner@example.com" not in banner.message


def test_approval_banner_escalates_without_exposing_item_data(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.content_approval.pending",
        lambda _cid: [{"id": str(i), "content": {}} for i in range(3)],
        raising=False,
    )
    banner = _approval_banner("client-a")
    assert banner.urgency == "high"
