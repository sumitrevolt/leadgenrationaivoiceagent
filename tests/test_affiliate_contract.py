"""Affiliate/referral program contract tests (B1: referral launch).

affiliate.py is the money path (commission on first month) — public register
route + admin stats + referral-kit builder must keep their shapes. Pure-file
stores (data/affiliates.jsonl + data/affiliate_referrals.jsonl), tmp_path
monkeypatched, no network.
"""

from __future__ import annotations

import json
import os

import pytest

from app.marketing import affiliate as af


@pytest.fixture(autouse=True)
def _tmp_stores(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(af, "_AFFILIATES", str(tmp_path / "affiliates.jsonl"))
    monkeypatch.setattr(af, "_REFERRALS", str(tmp_path / "affiliate_referrals.jsonl"))


# --------------------------------------------------------------------------- #
# register_affiliate
# --------------------------------------------------------------------------- #
def test_register_new_affiliate() -> None:
    r = af.register_affiliate("Jiya Makeover", "jiya@example.com", "9876543210")
    assert r["ok"] is True
    assert r["existing"] is False
    assert r["code"] and r["code"].isalnum()
    assert r["link"] == f"{af.BASE_URL}/?ref={r['code']}"
    assert "20%" in r["commission"]


def test_register_dedupes_by_email() -> None:
    af.register_affiliate("Jiya", "jiya@example.com", "9876543210")
    r2 = af.register_affiliate("Jiya Again", "jiya@example.com", "1111111111")
    assert r2["existing"] is True
    assert r2["code"]  # same code, same link
    assert len(af.list_affiliates()) == 1


def test_register_dedupes_by_phone() -> None:
    af.register_affiliate("Jiya", "jiya@example.com", "9876543210")
    r2 = af.register_affiliate("Other", "other@example.com", "9876543210")
    assert r2["existing"] is True


# --------------------------------------------------------------------------- #
# referral_kit — owner ko ek-tap shareable kit
# --------------------------------------------------------------------------- #
def test_referral_kit_shape() -> None:
    kit = af.referral_kit("Jiya Makeover", "jiya@example.com", "9876543210")
    assert kit["ok"] is True
    assert kit["link"].startswith("https://")
    assert af.BASE_URL in kit["whatsapp_text"]
    assert kit["link"] in kit["whatsapp_text"]
    assert "₹" in kit["whatsapp_text"] or "reward" in kit["whatsapp_text"].lower()
    assert kit["code"]


def test_referral_kit_reuses_existing_affiliate() -> None:
    k1 = af.referral_kit("Jiya", "jiya@example.com", "9876543210")
    k2 = af.referral_kit("Jiya", "jiya@example.com", "9876543210")
    assert k1["code"] == k2["code"]


# --------------------------------------------------------------------------- #
# referral tracking + admin detail
# --------------------------------------------------------------------------- #
def test_record_referral_unknown_code() -> None:
    r = af.record_referral("", {"name": "x"})
    assert r["ok"] is False


def test_affiliate_detail_per_affiliate_earned() -> None:
    a = af.register_affiliate("Jiya", "jiya@example.com", "9876543210")
    af.record_referral(a["code"], {"business_name": "Shop A", "email": "a@a.in"}, status="lead")
    af.record_referral(
        a["code"],
        {"business_name": "Shop B", "email": "b@b.in", "amount": 1999},
        status="paid",
    )
    detail = af.affiliate_detail()
    assert len(detail) == 1
    row = detail[0]
    assert row["name"] == "Jiya"
    assert row["code"] == a["code"]
    assert row["referrals"] == 2
    assert row["paid_conversions"] == 1
    assert row["earned"] == round(1999 * af.COMMISSION_PCT / 100)


def test_stats_includes_detail() -> None:
    a = af.register_affiliate("Jiya", "jiya@example.com", "9876543210")
    af.record_referral(a["code"], {"amount": 1999, "name": "Shop"}, status="paid")
    s = af.stats()
    assert s["affiliates"] == 1
    assert s["paid_conversions"] == 1
    assert s["commission_earned"] == round(1999 * af.COMMISSION_PCT / 100)
    assert len(s["detail"]) == 1


def test_stats_code_filter() -> None:
    a1 = af.register_affiliate("Jiya", "jiya@example.com", "9876543210")
    a2 = af.register_affiliate("Rohan", "rohan@example.com", "9876543211")
    af.record_referral(a1["code"], {"amount": 1999, "name": "Shop"}, status="paid")
    s = af.stats(a2["code"])
    assert s["referrals"] == 0
    assert s["paid_conversions"] == 0


def test_affiliate_files_are_append_only_jsonl(tmp_path) -> None:
    af.register_affiliate("Jiya", "jiya@example.com", "9876543210")
    with open(af._AFFILIATES, encoding="utf-8") as f:
        assert len(f.readlines()) == 1
    assert os.path.exists(af._REFERRALS) is False  # no referrals yet = no file
