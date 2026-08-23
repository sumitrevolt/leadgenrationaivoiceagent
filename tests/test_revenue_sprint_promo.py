"""Revenue-sprint batch (2026-08-23) — promo engine + custom offers + referral flip.

Contract coverage:
* promo_codes.create_code fail-closed validation (kind/value/expiry/code)
* validate_code: expiry, plan restriction, once-per-customer, max_redemptions,
  discount floor (₹99) — Lago-style definitions vs applied ledger
* apply_promo_to_order: original offer IMMUTABLE (supersede chain), stacking
  refused, derived offer carries discounted frozen amount
* offers.issue_custom_offer bounds + guaranteed-new identity (reuse_live=False)
* affiliate.mark_referral_paid_by_contact idempotent lead→paid flip
* active_launch_offer returns only LIVE launch-tagged codes

Pure python: stores monkeypatched to tmp_path, no network/LLM.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def pc(tmp_path, monkeypatch):
    from app.billing import promo_codes as mod

    monkeypatch.setattr(mod, "_STORE", str(tmp_path / "promo_codes.jsonl"))
    return mod


@pytest.fixture
def off(tmp_path, monkeypatch):
    from app.marketing import offers as mod

    store = str(tmp_path / "offers.jsonl")
    monkeypatch.setattr(mod, "_store", lambda: store)
    return mod


@pytest.fixture
def aff(tmp_path, monkeypatch):
    from app.marketing import affiliate as mod

    monkeypatch.setattr(mod, "_REFERRALS", str(tmp_path / "affiliate_referrals.jsonl"))
    return mod


# ------------------------------------------------------------- create_code gates


def test_create_rejects_unknown_kind(pc):
    assert pc.create_code("X1", "mystery", 100)["ok"] is False


def test_create_rejects_bad_values(pc):
    assert pc.create_code("X2", "fixed_inr", 0)["ok"] is False
    assert pc.create_code("X3", "pct", 95)["ok"] is False
    assert pc.create_code("X4", "fixed_inr", 99_999)["ok"] is False
    assert pc.create_code("X5", "pct", -5)["ok"] is False


def test_create_normalizes_code_and_upserts(pc):
    a = pc.create_code(" launch500 ", "fixed_inr", 500)
    assert a["ok"] is True and a["code"] == "LAUNCH500"
    b = pc.create_code("LAUNCH500", "fixed_inr", 700)
    assert b["ok"] is True
    defs = pc.list_definitions()
    assert len(defs) == 1 and defs[0]["value"] == 700


def test_create_rejects_invalid_expiry(pc):
    assert pc.create_code("X6", "fixed_inr", 100, expires_at="not-a-date")["ok"] is False


# --------------------------------------------------------------- validate gates


def test_validate_unknown_code(pc):
    r = pc.validate_code("NOPE", "starter", 1999)
    assert r["ok"] is False and r["reason"] == "unknown"


def test_validate_expired(pc, off):
    off.issue_offer("d1", "starter")
    pc.create_code("OLD", "fixed_inr", 200, expires_at="2020-01-01T00:00:00+00:00")
    assert pc.validate_code("OLD", "starter", 1999)["reason"] == "expired"


def test_validate_plan_restriction(pc):
    pc.create_code("COMBOONLY", "fixed_inr", 500, plan_ids=["advanced"])
    assert pc.validate_code("COMBOONLY", "starter", 1999)["reason"] == "plan_not_eligible"
    assert pc.validate_code("COMBOONLY", "ADVANCED", 5999)["ok"] is True


def test_validate_pct_math_and_cap(pc):
    pc.create_code("P10", "pct", 10)
    r = pc.validate_code("P10", "starter", 1999)
    assert r["ok"] is True and r["discount_inr"] == 200 and r["effective_inr"] == 1799
    pc.create_code("P90", "pct", 90)
    r2 = pc.validate_code("P90", "starter", 100)
    # effective would be ₹10 < ₹99 floor → refuse, never sell at ~zero
    assert r2["ok"] is False and r2["reason"] == "discount_exceeds_floor"


def test_validate_fixed_capped_at_amount(pc):
    pc.create_code("BIG", "fixed_inr", 5000)
    r = pc.validate_code("BIG", "starter", 1999)
    # ₹5000-off on a ₹1999 plan would be ₹0 effective — below the ₹99 sale
    # floor, so fail-closed refuse (kabhi zero/negative UPI order nahi).
    assert r["ok"] is False and r["reason"] == "discount_exceeds_floor"


# ------------------------------------------------------------------- apply flow


def _seed_order(off, pkg="starter"):
    o = off.issue_offer(f"deal-{pkg}", pkg)
    assert o is not None
    return o


def test_apply_creates_discounted_supersede_original_immutable(pc, off):
    orig = _seed_order(off)
    pc.create_code("L500", "fixed_inr", 500)

    res = pc.apply_promo_to_order(orig["order_ref"], "L500", customer_contact="9876500001")
    assert res["ok"] is True
    assert res["order_ref"] != orig["order_ref"]
    assert res["quoted_amount"] == 1999 - 500

    # ORIGINAL untouched — billing-truth invariant
    old = off.get_offer(orig["order_ref"])
    assert old["status"] == "superseded"
    assert old["quoted_amount"] == 1999

    new = off.get_offer(res["order_ref"])
    assert new["status"] == "issued"
    assert new["quoted_amount"] == 1499
    assert new["promo_code"] == "L500"
    assert new["supersedes_order_ref"] == orig["order_ref"]

    # submit-side plan-match still works on the derived offer
    payable, reason = off.resolve_payable(res["order_ref"])
    assert reason == "ok" and payable["package_code"] == "starter"


def test_apply_stacking_refused(pc, off):
    orig = _seed_order(off)
    pc.create_code("A1", "fixed_inr", 100)
    pc.create_code("A2", "fixed_inr", 100)
    first = pc.apply_promo_to_order(orig["order_ref"], "A1")
    assert first["ok"] is True
    second = pc.apply_promo_to_order(first["order_ref"], "A2")
    assert second["ok"] is False and second["reason"] == "promo_already_applied"


def test_apply_once_per_customer_enforced_via_ledger(pc, off):
    pc.create_code("ONE", "fixed_inr", 300, once_per_customer=True)
    o1 = off.issue_offer("deal-a", "starter")
    o2 = off.issue_offer("deal-b", "starter")
    r1 = pc.apply_promo_to_order(o1["order_ref"], "ONE", customer_contact="user@x.com")
    assert r1["ok"] is True
    chk = pc.validate_code("ONE", "starter", 1999, customer_key="USER@X.COM")
    assert chk["ok"] is False and chk["reason"] == "already_used"
    # different customer still fine
    r2 = pc.apply_promo_to_order(o2["order_ref"], "ONE", customer_contact="other@y.com")
    assert r2["ok"] is True


def test_apply_max_redemptions_exhausted(pc, off):
    pc.create_code("TEN", "fixed_inr", 100, once_per_customer=False, max_redemptions=2)
    for i in range(2):
        o = off.issue_offer(f"d{i}", "starter")
        assert pc.apply_promo_to_order(o["order_ref"], "TEN")["ok"] is True
    o3 = off.issue_offer("d-last", "starter")
    assert pc.apply_promo_to_order(o3["order_ref"], "TEN")["reason"] == "exhausted"


def test_apply_fail_closed_on_unpayable_order(pc, off):
    pc.create_code("Z1", "fixed_inr", 100)
    assert pc.apply_promo_to_order("", "Z1")["ok"] is False
    assert pc.apply_promo_to_order("LG-nonexistent", "Z1")["reason"].startswith("order_not_payable")


# --------------------------------------------------------- issue_custom_offer


def test_custom_offer_bounds(off):
    assert off.issue_custom_offer("d", "dfy_setup", 50) is None  # < ₹99 floor
    assert off.issue_custom_offer("d", "dfy_setup", 2_000_000) is None  # > max
    assert off.issue_custom_offer("", "dfy_setup", 4999) is None
    ok = off.issue_custom_offer("d", "dfy_setup", 4999, label="Done-for-you setup")
    assert ok is not None and ok["quoted_amount"] == 4999 and ok["label"]


def test_custom_offer_guaranteed_new_identity(off):
    """reuse_live=False must NOT collide with an identical live catalogue offer."""
    base = off.issue_offer("deal-c", "starter")
    custom = off.issue_custom_offer("deal-c", "starter", 1799, reuse_live=False)
    assert custom is not None
    assert custom["order_ref"] != base["order_ref"]
    assert custom["offer_version"] == 2


# ------------------------------------------------------------- referral flip


def test_referral_flip_by_phone_idempotent(aff):
    from datetime import datetime, timezone

    aff.record_referral(
        "jiya1234",
        {"business_name": "Salon X", "phone": "9876500001", "email": ""},
        status="lead",
    )
    n = aff.mark_referral_paid_by_contact(contact="+91 98765 00001", amount=1999)
    assert n == 1
    # idempotent — already paid rows skipped
    assert aff.mark_referral_paid_by_contact(contact="9876500001", amount=1999) == 0
    s = aff.stats("jiya1234")
    assert s["paid_conversions"] == 1 and s["commission_earned"] == 400


def test_referral_flip_no_match_returns_zero(aff):
    aff.record_referral("c1", {"phone": "1111122222"}, status="lead")
    assert aff.mark_referral_paid_by_contact(contact="9999977777") == 0


def test_referral_flip_requires_real_contact(aff):
    assert aff.mark_referral_paid_by_contact(contact="") == 0
    assert aff.mark_referral_paid_by_contact(contact="12") == 0  # not a phone


# ------------------------------------------------------------ launch offer


def test_launch_offer_only_live_returned(pc):
    assert pc.active_launch_offer() is None
    pc.create_code(
        "LAUNCH7",
        "pct",
        15,
        tags=["launch"],
        label="Launch Week",
        expires_at="2099-01-01T00:00:00+00:00",
        max_redemptions=5,
    )
    live = pc.active_launch_offer()
    assert live is not None and live["code"] == "LAUNCH7"

    # expired launch code → nothing
    pc.create_code("DEAD", "pct", 10, tags=["launch"], expires_at="2020-01-01T00:00:00+00:00")
    assert pc.active_launch_offer()["code"] == "LAUNCH7"


def test_promo_store_is_append_ledger_with_definitions(pc, off):
    """Ledger rows survive alongside definitions; applied history queryable."""
    pc.create_code("H1", "fixed_inr", 150)
    o = _seed_order(off, "advanced")
    pc.apply_promo_to_order(o["order_ref"], "H1")
    applied = pc.list_applied()
    assert len(applied) == 1
    assert applied[0]["order_ref_old"] == o["order_ref"]
    assert applied[0]["discount_inr"] == 150
