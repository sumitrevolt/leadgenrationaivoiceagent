"""Billing-store test isolation contract (2026-07-18 prod-ledger contamination fix).

Root cause proven on prod: `tests/test_upi_payments.py` et al patch `upi_payments._STORE`
but `submit_payment` -> `_fire_gst_invoice` -> `gst_invoice.create_invoice` wrote to the
REAL relative `data/invoices.jsonl` of whatever cwd pytest ran in. On the VPS (closure run
2026-07-18 10:22 UTC) that was /opt/leadgen -> 11 synthetic `cli_*` invoices INV/0003..0013
landed in the production Rule-46 ledger. The autouse `_isolate_billing_stores` fixture in
conftest.py must keep EVERY test's billing writes inside tmp_path.
"""

from __future__ import annotations

import os


def test_gst_invoice_store_is_redirected_away_from_repo_data():
    from app.billing import gst_invoice

    p = os.path.abspath(gst_invoice._STORE())
    assert os.path.abspath(os.path.join("data", "invoices.jsonl")) != p
    assert not p.startswith(os.path.abspath("data"))


def test_upi_payments_store_is_redirected_away_from_repo_data():
    from app.platform import upi_payments

    p = os.path.abspath(upi_payments._STORE())
    assert not p.startswith(os.path.abspath("data"))


def test_invoice_write_lands_in_tmp_not_repo(tmp_path):
    """Functional proof: creating an invoice in a test must not touch data/invoices.jsonl."""
    from app.billing import gst_invoice

    before_mtime = None
    real = os.path.join("data", "invoices.jsonl")
    if os.path.exists(real):
        before_mtime = os.path.getmtime(real)

    rec = gst_invoice.create_invoice("iso_test_client", "starter", amount_inr=1999)
    assert rec.get("number")
    assert os.path.exists(gst_invoice._STORE())

    if before_mtime is not None:
        assert os.path.getmtime(real) == before_mtime
    # And the synthetic client id must not appear in the real ledger.
    if os.path.exists(real):
        assert "iso_test_client" not in open(real, encoding="utf-8").read()


def test_upi_auto_activate_full_path_stays_isolated(monkeypatch):
    """The exact contamination path: UPI_AUTO_ACTIVATE=1 submit -> _fire_gst_invoice.
    With the autouse fixture, the resulting invoice must land in the isolated store."""
    from app.billing import gst_invoice, usage
    from app.platform import upi_payments as up

    monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
    monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")
    monkeypatch.setattr(up, "_notify_admin", lambda rec: None)
    monkeypatch.setattr(up, "_trigger_onboarding", lambda *a, **k: None)
    monkeypatch.setattr(up, "_mark_deal_won", lambda *a, **k: None)
    monkeypatch.setattr(usage, "activate_plan", lambda cid, plan, **kw: True)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)

    out = up.submit_payment("iso_cli_contain", "starter", "TXNISO1", amount=1999)
    assert out.get("auto_activated") is True

    real = os.path.join("data", "invoices.jsonl")
    if os.path.exists(real):
        assert "iso_cli_contain" not in open(real, encoding="utf-8").read()
    rows = gst_invoice.list_invoices(20)
    assert any(r.get("client_id") == "iso_cli_contain" for r in rows)
