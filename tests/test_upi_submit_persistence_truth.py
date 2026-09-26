"""A UPI claim is acknowledged only after its payment record is durable."""

from __future__ import annotations

from app.platform import upi_payments


def test_store_write_failure_refuses_success_or_side_effects(monkeypatch, tmp_path):
    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(tmp_path / "upi.json"))
    monkeypatch.setattr(upi_payments, "_write_store", lambda rows: False)
    events = []
    monkeypatch.setattr(upi_payments, "_notify_admin", lambda record: events.append("alert"))
    monkeypatch.setattr(
        upi_payments, "_try_activate", lambda *args, **kwargs: events.append("activate")
    )
    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")

    result = upi_payments.submit_payment("client-a", "starter", "TXN-STORE-FAIL", 1999)

    assert result == {"ok": False, "error": "Payment record unavailable — retry later"}
    assert events == []
    assert upi_payments.list_payments() == []


def test_real_store_error_refuses_ack_and_operator_alert(monkeypatch, tmp_path):
    # A directory at the target pathname makes the actual JSON write fail.
    bad_path = tmp_path / "upi.json"
    bad_path.mkdir()
    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(bad_path))
    alerts = []
    monkeypatch.setattr(upi_payments, "_notify_admin", lambda rec: alerts.append(rec))

    result = upi_payments.submit_payment("client-a", "starter", "TXN-BAD-FS", 1999)

    assert result["ok"] is False
    assert alerts == []
