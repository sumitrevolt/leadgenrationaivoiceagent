"""app.platform.delivery_ledger — customer-facing delivery event log.
Offline (no DB required): _db() returns None when no engine is configured,
so log_event must no-op safely and get_timeline must return []."""

from app.platform import delivery_ledger as dl


def test_event_types_include_all_14_mission_types():
    expected = {
        "customer_created", "plan_activated", "onboarding_started",
        "onboarding_completed", "marketing_calendar_generated",
        "post_draft_created", "post_approved", "post_published",
        "post_failed", "lead_captured", "followup_sent",
        "weekly_report_generated", "automation_failed", "admin_manual_action",
    }
    assert expected.issubset(dl.EVENT_TYPES)


def test_log_event_never_raises_without_db(monkeypatch):
    monkeypatch.setattr(dl, "_db", lambda: None)
    # Must not raise even though there is no DB session.
    dl.log_event("client_x", "plan_activated", detail="starter plan")


def test_log_event_writes_row_via_fake_session(monkeypatch):
    added = []

    class _FakeSession:
        def add(self, row):
            added.append(row)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())
    dl.log_event("client_x", "plan_activated", detail="starter plan", meta={"plan": "starter"})
    assert len(added) == 1
    row = added[0]
    assert row.client_id == "client_x"
    assert row.event_type == "plan_activated"
    assert row.detail == "starter plan"
    assert "starter" in row.meta_json


def test_log_event_unknown_type_still_logs_never_raises(monkeypatch):
    added = []

    class _FakeSession:
        def add(self, row):
            added.append(row)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())
    dl.log_event("client_x", "totally_unknown_type")
    assert len(added) == 1
    assert added[0].event_type == "totally_unknown_type"


def test_get_timeline_empty_without_db(monkeypatch):
    monkeypatch.setattr(dl, "_db", lambda: None)
    assert dl.get_timeline("client_x") == []


def test_get_timeline_renders_customer_vs_admin_labels(monkeypatch):
    from datetime import datetime

    class _Row:
        def __init__(self):
            self.client_id = "client_x"
            self.event_type = "plan_activated"
            self.detail = "starter plan via upi_screenshot"
            self.status = "ok"
            self.meta_json = "{}"
            self.created_at = datetime(2026, 7, 6, 9, 0, 0)

    class _Query:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return [_Row()]

    class _FakeSession:
        def query(self, *a, **k):
            return _Query()

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())

    customer_view = dl.get_timeline("client_x", audience="customer")
    admin_view = dl.get_timeline("client_x", audience="admin")
    assert len(customer_view) == 1 and len(admin_view) == 1
    # Customer label must be the friendly Hinglish line, not the raw event_type.
    assert customer_view[0]["label"] != "plan_activated"
    assert "plan_activated" not in customer_view[0]["label"]
    # Admin label may include the technical detail.
    assert "plan_activated" in admin_view[0]["label"] or "starter plan" in admin_view[0]["label"]
    assert customer_view[0]["event_type"] == "plan_activated"


def test_get_timeline_unknown_type_has_safe_fallback_label(monkeypatch):
    from datetime import datetime

    class _Row:
        client_id = "client_x"
        event_type = "some_future_type"
        detail = "n/a"
        status = "ok"
        meta_json = "{}"
        created_at = datetime(2026, 7, 6, 9, 0, 0)

    class _Query:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return [_Row()]

    class _FakeSession:
        def query(self, *a, **k):
            return _Query()

        def close(self):
            pass

    monkeypatch.setattr(dl, "_db", lambda: _FakeSession())
    out = dl.get_timeline("client_x")
    assert len(out) == 1
    assert out[0]["label"]  # non-empty fallback, never raises/blank
