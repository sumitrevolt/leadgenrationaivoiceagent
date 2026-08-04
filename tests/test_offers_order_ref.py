"""Immutable offer/order entity — identity, pricing truth, idempotency (#240).

Cardinality note (why this is a separate entity, not deal fields):
``sales_pipeline.upsert_deal`` dedupes by phone/email and returns the EXISTING
deal, so a deal is long-lived. A prospect can be quoted Main today, Combo on
upgrade, and top-up packs repeatedly. Deal 1..N offer — a single mutable
``order_ref`` on the deal would let a second quote silently overwrite a link the
prospect is already holding.

Pure python: store path monkeypatched to tmp_path, no network/LLM.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def off(tmp_path, monkeypatch):
    from app.marketing import offers as mod

    store = str(tmp_path / "offers.jsonl")
    monkeypatch.setattr(mod, "_store", lambda: store)
    return mod


# --------------------------------------------------------------- order identity


def test_reference_is_full_entropy_not_truncated(off):
    o = off.issue_offer("deal123", "starter")

    assert o is not None
    assert o["order_ref"].startswith("LG-")
    # 32 hex chars = full uuid4. Truncating would stack birthday risk on a deal
    # id that is ALREADY uuid4().hex[:12].
    assert len(o["order_ref"]) == 3 + 32


def test_references_are_unique_across_offers(off):
    refs = {off.issue_offer(f"deal{i}", "starter")["order_ref"] for i in range(50)}

    assert len(refs) == 50


def test_same_deal_same_package_reuses_reference(off):
    """Idempotency: a retried triage run must not mint a second quote."""
    a = off.issue_offer("deal1", "starter")
    b = off.issue_offer("deal1", "starter")

    assert a["order_ref"] == b["order_ref"]
    assert len(off.list_offers("deal1")) == 1


def test_different_package_on_same_deal_creates_new_order(off):
    """The upgrade case that makes a deal-level order_ref untenable."""
    main = off.issue_offer("deal1", "starter")
    combo = off.issue_offer("deal1", "advanced")

    assert main["order_ref"] != combo["order_ref"]
    assert combo["offer_version"] > main["offer_version"]
    assert len(off.list_offers("deal1")) == 2


def test_supersede_preserves_original_and_links(off):
    first = off.issue_offer("deal1", "starter")
    second = off.issue_offer("deal1", "advanced", supersedes=first["order_ref"])

    assert second["supersedes_order_ref"] == first["order_ref"]
    assert off.get_offer(first["order_ref"])["status"] == off.STATUS_SUPERSEDED
    # original row still exists and keeps its quoted amount — audit intact
    assert off.get_offer(first["order_ref"])["quoted_amount"] == first["quoted_amount"]


# ------------------------------------------------------------- pricing truth


def test_starter_price_comes_from_catalogue(off):
    from app.marketing.packages import get_starter_price_inr

    o = off.issue_offer("deal1", "starter")

    assert o["quoted_amount"] == get_starter_price_inr()
    assert o["currency"] == "INR"


def test_combo_is_not_priced_as_starter(off):
    """The exact regression #236 avoided by shipping no amount at all."""
    from app.marketing.packages import get_starter_price_inr

    combo = off.issue_offer("deal1", "advanced")

    assert combo is not None
    assert combo["quoted_amount"] != get_starter_price_inr()
    assert combo["quoted_amount"] == 5999


def test_unknown_package_fails_closed(off):
    assert off.issue_offer("deal1", "no_such_plan") is None
    assert off.issue_offer("deal1", "") is None
    assert off.list_offers("deal1") == []


def test_missing_deal_id_fails_closed(off):
    assert off.issue_offer("", "starter") is None


def test_catalogue_price_change_does_not_mutate_issued_offer(off, monkeypatch):
    """Billing truth: an issued quote is frozen at issuance."""
    issued = off.issue_offer("deal1", "starter")
    original = issued["quoted_amount"]

    monkeypatch.setattr(off, "_price_for", lambda code: (99999, "INR"))

    assert off.get_offer(issued["order_ref"])["quoted_amount"] == original


# --------------------------------------------------------- payability gating


def test_resolve_payable_happy_path(off):
    o = off.issue_offer("deal1", "starter")

    got, reason = off.resolve_payable(o["order_ref"])

    assert reason == "ok"
    assert got["order_ref"] == o["order_ref"]


def test_unknown_reference_is_rejected(off):
    got, reason = off.resolve_payable("LG-deadbeef")

    assert got is None
    assert reason == "unknown"


def test_superseded_order_is_not_payable(off):
    first = off.issue_offer("deal1", "starter")
    off.issue_offer("deal1", "advanced", supersedes=first["order_ref"])

    got, reason = off.resolve_payable(first["order_ref"])

    assert got is None
    assert reason == "superseded"


def test_paid_order_is_not_payable_again(off):
    o = off.issue_offer("deal1", "starter")
    off.mark_status(o["order_ref"], off.STATUS_PAID)

    got, reason = off.resolve_payable(o["order_ref"])

    assert got is None
    assert reason == "already_paid"


def test_expired_order_is_not_payable(off):
    o = off.issue_offer("deal1", "starter", ttl_days=1)

    # age the row past its TTL
    import json
    from datetime import datetime, timedelta, timezone

    rows = off._read()
    rows[0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    off._write_all(rows)

    got, reason = off.resolve_payable(o["order_ref"])

    assert got is None
    assert reason == "expired"
    assert json  # keep import meaningful for lint


def test_expired_offer_is_not_reused_as_idempotent_hit(off):
    """An expired quote must produce a NEW order, not silently resurrect."""
    from datetime import datetime, timedelta, timezone

    first = off.issue_offer("deal1", "starter")
    rows = off._read()
    rows[0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    off._write_all(rows)

    second = off.issue_offer("deal1", "starter")

    assert second["order_ref"] != first["order_ref"]


def test_mark_status_is_idempotent(off):
    o = off.issue_offer("deal1", "starter")

    assert off.mark_status(o["order_ref"], off.STATUS_PAID) is True
    assert off.mark_status(o["order_ref"], off.STATUS_PAID) is True
    assert off.get_offer(o["order_ref"])["status"] == off.STATUS_PAID


def test_mark_status_rejects_unknown_status(off):
    o = off.issue_offer("deal1", "starter")

    assert off.mark_status(o["order_ref"], "banana") is False


def test_reference_is_safe_in_urls_and_upi_fields(off):
    from urllib.parse import quote

    ref = off.issue_offer("deal1", "starter")["order_ref"]

    assert quote(ref, safe="") == ref  # nothing to escape
    assert " " not in ref and "&" not in ref and "?" not in ref


def test_listing_is_scoped_to_the_deal(off):
    off.issue_offer("deal1", "starter")
    off.issue_offer("deal2", "starter")

    assert len(off.list_offers("deal1")) == 1
    assert len(off.list_offers()) == 2


def test_store_failure_never_raises(off, monkeypatch):
    monkeypatch.setattr(off, "_write_all", lambda rows: False)

    assert off.issue_offer("deal1", "starter") is None
