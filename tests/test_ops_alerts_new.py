"""Tests for the two new ops_alerts helpers (payment-failed + SMTP-disabled).

Mirrors the existing module contract:
- No-op (never raises, no fire) when ntfy unconfigured / OPS_ALERTS unset.
- Fires the underlying `_ntfy` when OPS_ALERTS=1 (cooldown bypassed via
  monkeypatch so the disk state ledger doesn't suppress the second test).
"""

from __future__ import annotations

import pytest

from app.platform import ops_alerts


# --------------------------------------------------------------------------- #
# (a) No-op when ntfy / OPS_ALERTS unconfigured — must never raise, must not fire.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "helper",
    [
        ops_alerts.maybe_alert_payment_failed,
        ops_alerts.maybe_alert_smtp_disabled,
        lambda detail: ops_alerts.alert_paid_customer_stuck("c1", "jiya makeover", detail),
    ],
)
def test_helper_noop_when_unconfigured(helper, monkeypatch):
    # OPS_ALERTS unset -> enabled() is False -> inert.
    monkeypatch.delenv("OPS_ALERTS", raising=False)

    # If anything tried to push, fail loudly — it must NOT in the disabled path.
    def _boom(*_a, **_kw):  # pragma: no cover - asserts non-call
        raise AssertionError("_ntfy must not be called when OPS_ALERTS is unset")

    monkeypatch.setattr(ops_alerts, "_ntfy", _boom)

    # Never raises, returns the disabled sentinel.
    res = helper("some detail")
    assert res == {"alerted": False, "reason": "disabled"}


def test_helpers_noop_even_with_ntfy_env_but_flag_off(monkeypatch):
    """Even if NTFY_* are set, the OPS_ALERTS master gate keeps it inert."""
    monkeypatch.delenv("OPS_ALERTS", raising=False)
    monkeypatch.setenv("NTFY_URL", "http://ntfy:80")
    monkeypatch.setenv("NTFY_TOPIC", "leadgen")

    monkeypatch.setattr(
        ops_alerts,
        "_ntfy",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fire")),
    )

    assert ops_alerts.maybe_alert_payment_failed("x")["alerted"] is False
    assert ops_alerts.maybe_alert_smtp_disabled("x")["alerted"] is False


# --------------------------------------------------------------------------- #
# (b) Fires _ntfy when configured (OPS_ALERTS=1) + cooldown bypassed.
# --------------------------------------------------------------------------- #
def _recorder(monkeypatch):
    """Enable OPS_ALERTS, bypass cooldown + disk writes, capture _ntfy calls."""
    monkeypatch.setenv("OPS_ALERTS", "1")
    monkeypatch.setattr(ops_alerts, "_cooldown_active", lambda *a, **k: False)
    monkeypatch.setattr(ops_alerts, "_record_fire", lambda *a, **k: None)
    calls: list[tuple] = []
    monkeypatch.setattr(
        ops_alerts,
        "_ntfy",
        lambda title, message, **kw: calls.append((title, message, kw)),
    )
    return calls


def test_payment_failed_fires_ntfy_when_enabled(monkeypatch):
    calls = _recorder(monkeypatch)

    res = ops_alerts.maybe_alert_payment_failed("card declined 4001")

    assert res == {"alerted": True}
    assert len(calls) == 1
    title, message, _kw = calls[0]
    assert "Payment failed" in title
    assert "card declined 4001" in message


def test_smtp_disabled_fires_ntfy_when_enabled(monkeypatch):
    calls = _recorder(monkeypatch)

    res = ops_alerts.maybe_alert_smtp_disabled("554 Disabled by user")

    assert res == {"alerted": True}
    assert len(calls) == 1
    title, message, _kw = calls[0]
    assert "SMTP" in title
    assert "554 Disabled by user" in message


def test_helpers_respect_cooldown(monkeypatch):
    """When cooldown is active, no fire even with OPS_ALERTS=1."""
    monkeypatch.setenv("OPS_ALERTS", "1")
    monkeypatch.setattr(ops_alerts, "_cooldown_active", lambda *a, **k: True)
    monkeypatch.setattr(ops_alerts, "_record_fire", lambda *a, **k: None)

    def _boom(*_a, **_kw):  # pragma: no cover - asserts non-call
        raise AssertionError("_ntfy must not fire while cooldown active")

    monkeypatch.setattr(ops_alerts, "_ntfy", _boom)

    assert ops_alerts.maybe_alert_payment_failed("x") == {
        "alerted": False,
        "reason": "cooldown",
    }
    assert ops_alerts.maybe_alert_smtp_disabled("x") == {
        "alerted": False,
        "reason": "cooldown",
    }
    assert ops_alerts.alert_paid_customer_stuck("c1", "jiya makeover", "x") == {
        "alerted": False,
        "reason": "cooldown",
    }


# --------------------------------------------------------------------------- #
# UPI auto-activate spot-check nudge (council decision 2026-07-03: ship
# UPI_AUTO_ACTIVATE's speed, pair it with a reconciliation signal not a gate).
# --------------------------------------------------------------------------- #
def test_upi_auto_activated_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("OPS_ALERTS", raising=False)

    def _boom(*_a, **_kw):  # pragma: no cover - asserts non-call
        raise AssertionError("_ntfy must not be called when OPS_ALERTS is unset")

    monkeypatch.setattr(ops_alerts, "_ntfy", _boom)

    res = ops_alerts.maybe_alert_upi_auto_activated("upi_1", "cli_1", "advanced", 5999)
    assert res == {"alerted": False, "reason": "disabled"}


def test_upi_auto_activated_fires_ntfy_when_enabled(monkeypatch):
    calls = _recorder(monkeypatch)

    res = ops_alerts.maybe_alert_upi_auto_activated("upi_42", "cli_9", "advanced", 5999)

    assert res == {"alerted": True}
    assert len(calls) == 1
    title, message, _kw = calls[0]
    assert "auto-activated" in title.lower()
    assert "cli_9" in message and "advanced" in message and "5999" in message


def test_upi_auto_activated_keys_cooldown_per_payment(monkeypatch):
    """Two DIFFERENT payments must both alert — this is per-event, not a
    shared-key alert like payment_failed/smtp_disabled (real cooldown ledger,
    not bypassed here, to prove the per-payment_id keying actually works)."""
    monkeypatch.setenv("OPS_ALERTS", "1")
    monkeypatch.setattr(ops_alerts, "_record_fire", lambda *a, **k: None)
    monkeypatch.setattr(
        ops_alerts, "_read_state", lambda: {}
    )  # empty ledger, real _cooldown_active logic
    calls: list[tuple] = []
    monkeypatch.setattr(
        ops_alerts, "_ntfy", lambda title, message, **kw: calls.append((title, message))
    )

    r1 = ops_alerts.maybe_alert_upi_auto_activated("upi_a", "cli_a", "starter", 1999)
    r2 = ops_alerts.maybe_alert_upi_auto_activated("upi_b", "cli_b", "starter", 1999)

    assert r1 == {"alerted": True}
    assert r2 == {"alerted": True}
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# Paid-customer-stuck page (the jiya-makeover-class ghosting bug, closed) —
# this is the alert that was MISSING when customer_delivery._record_stuck only
# wrote a jsonl line + a log WARNING nobody was watching.
# --------------------------------------------------------------------------- #
def test_paid_customer_stuck_fires_urgent_ntfy_when_enabled(monkeypatch):
    calls = _recorder(monkeypatch)

    res = ops_alerts.alert_paid_customer_stuck("c1", "jiya makeover", "send_failed")

    assert res == {"alerted": True}
    assert len(calls) == 1
    title, message, kw = calls[0]
    assert "jiya makeover" in title
    assert "c1" in message and "send_failed" in message
    assert kw.get("priority") == "urgent"


def test_paid_customer_stuck_keyed_per_client_not_shared(monkeypatch):
    """Two different stuck customers must each get their own cooldown key —
    one ghosted customer's alert must never suppress another's."""
    monkeypatch.setenv("OPS_ALERTS", "1")
    monkeypatch.setattr(ops_alerts, "_record_fire", lambda *a, **k: None)
    fired_keys: list[str] = []

    def _spy(key, kind):
        fired_keys.append(key)
        return False  # never suppress in this test

    monkeypatch.setattr(ops_alerts, "_cooldown_active", _spy)
    monkeypatch.setattr(ops_alerts, "_ntfy", lambda *a, **k: None)

    ops_alerts.alert_paid_customer_stuck("client-a", "biz a", "no_phone")
    ops_alerts.alert_paid_customer_stuck("client-b", "biz b", "no_phone")

    assert fired_keys == [
        "paid_customer_stuck:client-a",
        "paid_customer_stuck:client-b",
    ]
