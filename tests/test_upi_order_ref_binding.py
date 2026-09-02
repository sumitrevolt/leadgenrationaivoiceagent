"""UPI submission binds to an immutable offer, fail-closed (#240).

`order_ref` is never trusted as submitted — it is re-resolved server-side. The
offer owns the commercial truth, so a client cannot substitute another deal's
reference, replay a paid order, or override the quoted package.

Omitting order_ref must behave exactly as before #240 (backward compatible with
the historical payment store).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.marketing import offers
    from app.platform import upi_payments

    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(tmp_path / "upi.json"))
    monkeypatch.setattr(offers, "_store", lambda: str(tmp_path / "offers.jsonl"))
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    monkeypatch.delenv("UPI_AUTO_ACTIVATE_CLIENTS", raising=False)
    return upi_payments, offers


def test_valid_order_ref_is_bound_to_the_payment(env):
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")

    out = upi.submit_payment("cli1", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])

    assert out["ok"] is True
    rec = upi.list_payments("pending")[-1]
    assert rec["order_ref"] == o["order_ref"]
    assert rec["deal_id"] == "deal1"
    assert rec["package_code"] == "starter"
    assert rec["expected_amount"] == o["quoted_amount"]
    assert rec["amount_mismatch"] is False


def test_unknown_order_ref_is_rejected(env):
    upi, _ = env

    out = upi.submit_payment("cli1", "starter", "TXN1", order_ref="LG-doesnotexist")

    assert out["ok"] is False
    assert "unknown" in out["error"]
    assert upi.list_payments("pending") == []


def test_superseded_order_is_rejected(env):
    upi, offers = env
    first = offers.issue_offer("deal1", "starter")
    offers.issue_offer("deal1", "advanced", supersedes=first["order_ref"])

    out = upi.submit_payment("cli1", "starter", "TXN1", order_ref=first["order_ref"])

    assert out["ok"] is False
    assert "superseded" in out["error"]


def test_already_paid_order_cannot_be_replayed(env):
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")
    offers.mark_status(o["order_ref"], offers.STATUS_PAID)

    out = upi.submit_payment("cli1", "starter", "TXN2", order_ref=o["order_ref"])

    assert out["ok"] is False
    assert "already_paid" in out["error"]


def test_plan_mismatch_is_rejected_not_overridden(env):
    """A client cannot pay Starter prices against a Combo order (or vice versa)."""
    upi, offers = env
    combo = offers.issue_offer("deal1", "advanced")

    out = upi.submit_payment("cli1", "starter", "TXN1", order_ref=combo["order_ref"])

    assert out["ok"] is False
    assert "does not match" in out["error"]


def test_amount_mismatch_is_flagged_for_review_not_silently_accepted(env):
    upi, offers = env
    o = offers.issue_offer("deal1", "advanced")  # 5999

    out = upi.submit_payment("cli1", "advanced", "TXN1", amount=1999, order_ref=o["order_ref"])

    assert out["ok"] is True  # recorded, but visibly wrong
    assert upi.list_payments("pending")[-1]["amount_mismatch"] is True


def test_expected_amount_survives_a_catalogue_price_change(env, monkeypatch):
    """Billing truth: the ISSUED quote is persisted, not re-looked-up."""
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")
    original = o["quoted_amount"]

    monkeypatch.setattr(offers, "_price_for", lambda code: (99999, "INR"))
    upi.submit_payment("cli1", "starter", "TXN1", amount=original, order_ref=o["order_ref"])

    assert upi.list_payments("pending")[-1]["expected_amount"] == original


def test_offer_store_failure_refuses_rather_than_recording_unverified(env, monkeypatch):
    upi, offers = env

    def boom(_ref):
        raise RuntimeError("store down")

    monkeypatch.setattr(offers, "resolve_payable", boom)

    out = upi.submit_payment("cli1", "starter", "TXN1", order_ref="LG-whatever")

    assert out["ok"] is False
    assert upi.list_payments("pending") == []


# ------------------------------------------------------- backward compatibility


def test_submission_without_order_ref_is_unchanged(env):
    """Pre-#240 behaviour preserved — historical records have no order fields."""
    upi, _ = env

    out = upi.submit_payment("cli1", "starter", "TXN1", amount=1999)

    assert out["ok"] is True
    rec = upi.list_payments("pending")[-1]
    assert "order_ref" not in rec
    assert "expected_amount" not in rec


def test_idempotent_resubmit_still_works_with_order_ref(env):
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")

    first = upi.submit_payment("cli1", "starter", "TXN9", amount=1999, order_ref=o["order_ref"])
    second = upi.submit_payment("cli1", "starter", "TXN9", amount=1999, order_ref=o["order_ref"])

    assert first["ok"] is True
    assert second.get("duplicate") is True
    assert len(upi.list_payments("pending")) == 1


def test_retry_after_offer_leaves_issued_still_returns_duplicate(env):
    """Post-merge review of #241 — retry safety must survive approval/expiry.

    Gating the order BEFORE the duplicate check meant that once the owner
    approved (offer -> paid) or the quote expired, a legitimate resubmit of an
    ALREADY-RECORDED payment started returning
    "Order reference not payable (already_paid)". A payer who genuinely paid
    would see a failure. Only genuinely NEW submissions need a payable order.
    """
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")
    upi.submit_payment("cli1", "starter", "TXN9", amount=1999, order_ref=o["order_ref"])

    offers.mark_status(o["order_ref"], offers.STATUS_PAID)  # owner approved
    retry = upi.submit_payment("cli1", "starter", "TXN9", amount=1999, order_ref=o["order_ref"])

    assert retry["ok"] is True
    assert retry.get("duplicate") is True
    assert len(upi.list_payments("pending")) == 1


def test_new_submission_against_a_paid_offer_is_still_refused(env):
    """The gate must still bite for a genuinely new payment — no replay hole."""
    upi, offers = env
    o = offers.issue_offer("deal1", "starter")
    upi.submit_payment("cli1", "starter", "TXN9", amount=1999, order_ref=o["order_ref"])
    offers.mark_status(o["order_ref"], offers.STATUS_PAID)

    fresh = upi.submit_payment("cli1", "starter", "TXN_DIFFERENT", order_ref=o["order_ref"])

    assert fresh["ok"] is False
    assert "already_paid" in fresh["error"]
