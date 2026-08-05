"""Loop 5 (2026-07-10): UPI submit_payment idempotency (revenue-critical).

`decide()` was already idempotent (guards on `activated` flag) but `submit_payment`
appended duplicates on customer double-click / retry, and with UPI_AUTO_ACTIVATE=1
that could double-activate a plan → free minutes / duplicate GST invoice.

Fix: dedupe on (upi_ref, plan, client_id) at submit time. Same ref for same client
returns the existing record with `duplicate: True` — never a new row, never a
second `_try_activate` call.

RED-first: fails against the pre-fix code (two rows), passes after (one row).
"""

from __future__ import annotations

import json
import os

import pytest


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Point the module store at a fresh file per test — no cross-test bleed."""
    import app.platform.upi_payments as upi_mod

    monkeypatch.setattr(upi_mod, "_STORE", lambda: str(tmp_path / "upi_payments.json"))
    # Disable auto-activate + notify side-effects so we can isolate submit logic.
    monkeypatch.setattr(upi_mod, "_notify_admin", lambda rec: None)
    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "0")
    yield


def test_submit_payment_dedupes_on_upi_ref(monkeypatch):
    """Two submits with the same (upi_ref, plan, client_id) → exactly ONE row."""
    from app.platform import upi_payments

    r1 = upi_payments.submit_payment(
        client_id="c_pay1", plan="starter", upi_ref="UPI2026070001", amount=1999
    )
    assert r1.get("ok") is True
    assert not r1.get("duplicate"), "first submit is not a duplicate"

    r2 = upi_payments.submit_payment(
        client_id="c_pay1", plan="starter", upi_ref="UPI2026070001", amount=1999
    )
    assert r2.get("ok") is True
    assert r2.get("duplicate") is True, "second submit MUST be flagged duplicate"
    assert r2.get("id") == r1.get("id"), "same record returned on replay"

    rows = upi_payments.list_payments()
    assert len(rows) == 1, f"expected exactly 1 stored row, got {len(rows)}"


def test_submit_payment_different_ref_creates_new_row(monkeypatch):
    """Different upi_ref for same client + plan → separate rows (two real payments)."""
    from app.platform import upi_payments

    r1 = upi_payments.submit_payment(
        client_id="c_pay2", plan="starter", upi_ref="UPI111", amount=1999
    )
    r2 = upi_payments.submit_payment(
        client_id="c_pay2", plan="starter", upi_ref="UPI222", amount=1999
    )
    assert r1.get("id") != r2.get("id")
    assert not r2.get("duplicate")
    assert len(upi_payments.list_payments()) == 2


def test_submit_payment_different_plan_creates_new_row(monkeypatch):
    """Same ref but different plan → new row (rare but possible for admin scenarios).
    We dedupe on the (ref, plan, client_id) triple, not ref alone, so an upgrade
    payment is not silently swallowed by a prior starter submit."""
    from app.platform import upi_payments

    r1 = upi_payments.submit_payment(
        client_id="c_pay3", plan="starter", upi_ref="UPI333", amount=1999
    )
    r2 = upi_payments.submit_payment(
        client_id="c_pay3", plan="growth", upi_ref="UPI333", amount=2999
    )
    assert r1.get("id") != r2.get("id")
    assert not r2.get("duplicate")


def test_submit_payment_auto_activate_dedupe_prevents_double_activation(monkeypatch):
    """Critical: with UPI_AUTO_ACTIVATE=1, dedupe MUST prevent a second
    `_try_activate` call from a replay — that would reset the usage period twice."""
    import app.platform.upi_payments as upi_mod

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")

    activations: list[tuple] = []

    def _fake_activate(cid, plan, amount):
        activations.append((cid, plan, amount))
        return True

    monkeypatch.setattr(upi_mod, "_try_activate", _fake_activate)
    monkeypatch.setattr(upi_mod, "_trigger_onboarding", lambda *_a, **_k: None)
    monkeypatch.setattr(upi_mod, "_mark_deal_won", lambda *_a: None)
    monkeypatch.setattr(upi_mod, "_fire_gst_invoice", lambda *_a: None)

    r1 = upi_mod.submit_payment(
        client_id="c_pay_auto", plan="starter", upi_ref="UPIAUTO1", amount=1999
    )
    r2 = upi_mod.submit_payment(
        client_id="c_pay_auto", plan="starter", upi_ref="UPIAUTO1", amount=1999
    )

    assert r1.get("auto_activated") is True
    assert r2.get("duplicate") is True
    assert len(activations) == 1, (
        f"MUST call _try_activate exactly once — dedupe prevents double activation, "
        f"got {len(activations)}: {activations}"
    )
    assert len(upi_mod.list_payments()) == 1
