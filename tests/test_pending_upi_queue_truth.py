"""ADR-114: pending UPI queue = real submissions, not every trial client."""

from __future__ import annotations


def test_pending_upi_queue_uses_upi_payments_not_trial_clients(monkeypatch):
    from app.api import admin_ops

    trials = [
        {"id": "t1", "business_name": "Trial One", "plan": "trial", "phone": "91"},
        {"id": "t2", "business_name": "Trial Two", "plan": "free", "phone": "92"},
    ]

    def fake_list_clients():
        return trials

    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients", fake_list_clients, raising=False
    )

    monkeypatch.setattr(
        "app.platform.upi_payments.list_payments",
        lambda status=None: [],
    )
    assert admin_ops._pending_upi_queue(20) == []

    monkeypatch.setattr(
        "app.platform.upi_payments.list_payments",
        lambda status=None: (
            [
                {
                    "id": "pay1",
                    "client_id": "t1",
                    "plan": "starter",
                    "amount": 1999,
                    "upi_ref": "UTR1",
                    "status": "pending",
                    "created_at": "2026-07-16T10:00:00+00:00",
                }
            ]
            if status == "pending"
            else []
        ),
    )
    rows = admin_ops._pending_upi_queue(20)
    assert len(rows) == 1
    assert rows[0]["payment_id"] == "pay1"
    assert rows[0]["client_id"] == "t1"
    assert rows[0]["upi_ref"] == "UTR1"
    assert rows[0]["business_name"] == "Trial One"


def test_daily_check_json_verdict_not_hardcoded_green(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "automation_health_audit.py"
    spec = importlib.util.spec_from_file_location("aha_verdict_test", path)
    aha = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(aha)

    monkeypatch.setattr(aha, "check_alive", lambda: {"status": "green"})
    monkeypatch.setattr(aha, "check_budget", lambda: {"status": "red", "detail": "over"})
    monkeypatch.setattr(aha, "check_anomalies", lambda: {"status": "green"})
    monkeypatch.setattr(aha, "check_approvals", lambda: {"enabled": False, "status": "green"})
    monkeypatch.setattr(aha, "check_next_action", lambda: {"status": "green"})
    monkeypatch.setattr(aha, "check_compliance", lambda: {"status": "green"})

    import json

    body = json.loads(aha.format_daily_check_json())
    assert body["verdict"] == "red"
