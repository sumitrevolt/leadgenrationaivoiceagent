"""Campaign Offer Policy — immutable commercial provenance (#240, release review).

Every test here is adversarial: a path that could produce a WRONG PRICE must
instead produce a question, an exception, or a refusal.

The five release-blocking findings this locks:
  A. variant -> newest-active resolution retroactively repriced sent messages;
  B. an empty allowlist behaved as allow-any-priced-package;
  C. an ambiguous variant silently picked the highest version;
  D. malformed rows were skipped, so versioning ran on partial data;
  E. retirement mutated historical rows despite an append-only claim.

Pure python: store monkeypatched to tmp_path, no network/LLM.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def pol(tmp_path, monkeypatch):
    from app.marketing import campaign_offer_policy as mod

    store = tmp_path / "policies.jsonl"
    monkeypatch.setattr(mod, "_store", lambda: str(store))
    mod._STORE_FILE = store  # test convenience handle
    return mod


def _good_row(**over):
    row = {
        "kind": "policy",
        "policy_id": "p",
        "policy_version": 1,
        "product_family": "marketing",
        "allowed_package_codes": ["starter"],
        "default_package_code": "",
        "currency": "INR",
        "offer_validity_days": 30,
        "message_variant": "",
        "outreach_sequence_id": "",
        "template_id": "",
        "effective_from": "2026-08-05T00:00:00+00:00",
        "created_by": "test",
    }
    row.update(over)
    return row


# ============================ A. version pinning (retroactive repricing) =====


def test_pinned_prospect_keeps_its_original_version(pol):
    """THE finding: a later version must not reprice a message already sent."""
    v1 = pol.put_policy(
        "camp", product_family="marketing", allowed_package_codes=["starter"], message_variant="v"
    )
    prospect = {
        "campaign_offer_policy_id": "camp",
        "campaign_offer_policy_version": v1["policy_version"],
        "campaign_variant_id": "v",
    }

    pol.put_policy(
        "camp", product_family="combo", allowed_package_codes=["advanced"], message_variant="v"
    )

    got, reason = pol.resolve_for_prospect(prospect)

    assert reason == "ok"
    assert got["policy_version"] == 1
    assert got["allowed_package_codes"] == ["starter"]  # NOT advanced


def test_variant_alone_is_not_reply_authority(pol):
    """A prospect with only a variant stamp must qualify, never resolve a policy."""
    pol.put_policy(
        "camp", product_family="marketing", allowed_package_codes=["starter"], message_variant="v"
    )

    got, reason = pol.resolve_for_prospect({"campaign_variant_id": "v"})

    assert got is None
    assert reason == pol.HISTORICAL_DISCOVERY


def test_unstamped_historical_prospect_enters_qualification(pol):
    got, reason = pol.resolve_for_prospect({"business_name": "X"})

    assert got is None
    assert reason == pol.HISTORICAL_DISCOVERY
    assert pol.qualify(got, {})["outcome"] == pol.NEEDS_QUALIFICATION


def test_retirement_blocks_new_sends_but_not_historical_resolution(pol):
    v1 = pol.put_policy("camp", product_family="marketing", allowed_package_codes=["starter"])
    assert pol.retire_policy("camp") is True

    historical = pol.resolve_exact("camp", v1["policy_version"])
    assert historical is not None
    assert historical["allowed_package_codes"] == ["starter"]
    assert historical["status"] == pol.STATUS_RETIRED

    fresh, reason = pol.resolve_for_send(policy_id="camp")
    assert fresh is None
    assert reason == "POLICY_NOT_FOUND"


# ============================ B. empty allowlist is not allow-all ============


def test_sellable_policy_requires_a_non_empty_allowlist(pol):
    assert pol.put_policy("p", product_family="marketing", allowed_package_codes=[]) is None
    assert pol.list_policies("p") == []


def test_empty_allowlist_selects_nothing(pol):
    """Even if such a row existed, empty must mean NONE, never ANY."""
    out = pol.qualify(
        {"product_family": "marketing", "allowed_package_codes": [], "currency": "INR"},
        {"requested_package": "advanced"},
    )

    assert out["outcome"] == pol.EXCEPTION_REQUIRED
    assert out["reason"] == "PACKAGE_NOT_ALLOWED"
    assert out["amount"] is None


def test_discovery_cannot_sell_a_requested_package(pol):
    """A prospect naming a package is a fact to qualify, not authorisation."""
    p = pol.put_policy("legacy", product_family=pol.FAMILY_DISCOVERY)

    out = pol.qualify(p, {"requested_package": "advanced"})

    assert out["outcome"] == pol.NEEDS_QUALIFICATION
    assert out["package_code"] == ""
    assert out["amount"] is None


def test_policy_creation_rejects_unknown_packages(pol):
    assert pol.put_policy("p", product_family="marketing", allowed_package_codes=["nope"]) is None


def test_non_inr_currency_is_refused_on_the_upi_path(pol):
    assert (
        pol.put_policy(
            "p", product_family="marketing", allowed_package_codes=["starter"], currency="USD"
        )
        is None
    )


# ============================ C. ambiguity fails closed =====================


def test_same_variant_under_two_policies_is_refused_at_creation(pol):
    pol.put_policy(
        "p1", product_family="marketing", allowed_package_codes=["starter"], message_variant="dup"
    )

    assert (
        pol.put_policy(
            "p2",
            product_family="combo",
            allowed_package_codes=["advanced"],
            message_variant="dup",
        )
        is None
    )


def test_ambiguous_variant_resolution_returns_ambiguous(pol, tmp_path):
    """Hand-craft the clash the creation guard prevents, and prove resolution refuses."""
    rows = [
        {
            "kind": "policy",
            "policy_id": "p1",
            "policy_version": 1,
            "product_family": "marketing",
            "allowed_package_codes": ["starter"],
            "currency": "INR",
            "default_package_code": "",
            "offer_validity_days": 30,
            "message_variant": "dup",
            "outreach_sequence_id": "",
            "template_id": "",
            "effective_from": "2026-08-05T00:00:00+00:00",
            "created_by": "test",
        },
        {
            "kind": "policy",
            "policy_id": "p2",
            "policy_version": 9,
            "product_family": "marketing",
            "allowed_package_codes": ["advanced"],
            "currency": "INR",
            "default_package_code": "",
            "offer_validity_days": 30,
            "message_variant": "dup",
            "outreach_sequence_id": "",
            "template_id": "",
            "effective_from": "2026-08-05T00:00:00+00:00",
            "created_by": "test",
        },
    ]
    (tmp_path / "policies.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )

    got, reason = pol.resolve_for_send(message_variant="dup")

    assert got is None
    assert reason == pol.POLICY_AMBIGUOUS  # NOT "highest version wins"


# ============================ D. corrupt store fails closed =================


@pytest.mark.parametrize(
    "content",
    [
        "{not json}\n",
        '{"kind":"policy","policy_id":"p","policy_version":1}\n{oops}\n',
        '{"kind":"policy","policy_id":"p","policy_version":1}\n{"kind":"policy","policy',
        '{"kind":"policy","policy_id":"p","policy_version":1,"product_family":"marketing"}\n'
        '{"kind":"policy","policy_id":"p","policy_version":1,"product_family":"marketing"}\n',
    ],
    ids=["first-row", "middle-row", "truncated-tail", "duplicate-version"],
)
def test_corrupt_store_refuses_every_money_path_action(pol, tmp_path, content):
    (tmp_path / "policies.jsonl").write_text(content, encoding="utf-8")

    assert pol.store_health()["ok"] is False
    assert pol.resolve_exact("p", 1) is None
    got, reason = pol.resolve_for_send(policy_id="p")
    assert got is None and reason == pol.POLICY_STORE_CORRUPT
    # and it must not write a "repaired" store from a partial view
    assert (
        pol.put_policy("p2", product_family="marketing", allowed_package_codes=["starter"]) is None
    )
    assert (tmp_path / "policies.jsonl").read_text(encoding="utf-8") == content


def test_store_recovers_once_valid_data_is_restored(pol, tmp_path):
    (tmp_path / "policies.jsonl").write_text("{broken}\n", encoding="utf-8")
    assert pol.store_health()["ok"] is False

    (tmp_path / "policies.jsonl").write_text("", encoding="utf-8")

    assert pol.store_health()["ok"] is True
    assert pol.put_policy("p", product_family="marketing", allowed_package_codes=["starter"])


# ============================ E. append-only history ========================


def test_retirement_does_not_mutate_the_definition_row(pol, tmp_path):
    pol.put_policy("camp", product_family="marketing", allowed_package_codes=["starter"])
    before = (tmp_path / "policies.jsonl").read_text(encoding="utf-8")

    pol.retire_policy("camp", reason="season over")
    after = (tmp_path / "policies.jsonl").read_text(encoding="utf-8")

    assert after.startswith(before), "historical definition row was rewritten"
    assert '"kind": "policy_retired"' in after


def test_retirement_is_idempotent(pol):
    pol.put_policy("camp", product_family="marketing", allowed_package_codes=["starter"])

    assert pol.retire_policy("camp") is True
    assert pol.retire_policy("camp") is True
    assert len(pol.list_policies("camp")) == 1


def test_version_uses_max_plus_one_not_row_count(pol, tmp_path):
    """Row-count numbering reuses a version after any gap."""
    rows = [_good_row(policy_id="p", policy_version=5)]
    (tmp_path / "policies.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )

    nxt = pol.put_policy("p", product_family="combo", allowed_package_codes=["advanced"])

    assert nxt["policy_version"] == 6  # not 2


# ============================ correct selections ============================


def test_single_allowed_package_is_deterministic(pol):
    from app.marketing.packages import get_starter_price_inr

    p = pol.put_policy("s", product_family="marketing", allowed_package_codes=["starter"])

    out = pol.qualify(p, {})

    assert out["outcome"] == pol.PACKAGE_SELECTED
    assert out["package_code"] == "starter"
    assert out["amount"] == get_starter_price_inr()


def test_combo_is_never_priced_as_starter(pol):
    from app.marketing.packages import get_starter_price_inr

    p = pol.put_policy("c", product_family="combo", allowed_package_codes=["advanced"])

    out = pol.qualify(p, {})

    assert out["package_code"] == "advanced"
    assert out["amount"] == 5999
    assert out["amount"] != get_starter_price_inr()


def test_intent_alone_never_selects_a_package(pol):
    p = pol.put_policy("m", product_family="marketing", allowed_package_codes=["starter", "growth"])

    out = pol.qualify(p, {"intent": "interested", "niche": "salon"})

    assert out["outcome"] == pol.NEEDS_QUALIFICATION
    assert out["reason"] == "PACKAGE_UNRESOLVED"


def test_price_is_not_duplicated_into_the_policy_row(pol):
    p = pol.put_policy("p", product_family="marketing", allowed_package_codes=["starter"])

    assert "price" not in p and "amount" not in p


def test_qualify_never_raises_on_garbage(pol):
    for bad in ({}, {"product_family": None}, {"allowed_package_codes": None}):
        out = pol.qualify(bad, {"requested_package": "starter"})
        assert out["outcome"] in (
            pol.NEEDS_QUALIFICATION,
            pol.EXCEPTION_REQUIRED,
            pol.PACKAGE_SELECTED,
            pol.NOT_ELIGIBLE,
        )


# ============ P1 round 2: schema-strict, reason propagation, retired id ======


@pytest.mark.parametrize(
    "over",
    [
        {"allowed_package_codes": "starter"},
        {"allowed_package_codes": ["starter", "starter"]},
        {"currency": "USD"},
        {"product_family": "markting"},
        {"product_family": "nonsense"},
        {"offer_validity_days": 0},
        {"offer_validity_days": "30"},
        {"effective_from": "2026-08-05T00:00:00"},
        {"created_by": ""},
        {"default_package_code": "advanced"},
        {"policy_version": 0},
        {"policy_id": ""},
        {"message_variant": 7},
    ],
    ids=[
        "allowlist-is-string",
        "duplicate-codes",
        "bad-currency",
        "misspelled-family",
        "unknown-family",
        "validity-zero",
        "validity-string",
        "naive-timestamp",
        "empty-actor",
        "default-outside-allowlist",
        "version-zero",
        "empty-id",
        "variant-wrong-type",
    ],
)
def test_valid_json_but_malformed_policy_row_is_corruption(pol, tmp_path, over):
    """Valid JSON is not valid AUTHORITY. Each of these must refuse, not resolve."""
    (tmp_path / "policies.jsonl").write_text(json.dumps(_good_row(**over)) + "\n", encoding="utf-8")

    assert pol.store_health()["ok"] is False
    got, reason = pol.resolve_exact_with_reason("p", 1)
    assert got is None and reason == pol.POLICY_STORE_CORRUPT


def test_unknown_row_kind_is_corruption(pol, tmp_path):
    (tmp_path / "policies.jsonl").write_text(
        json.dumps({"kind": "policy_reactivated", "policy_id": "p"}) + "\n", encoding="utf-8"
    )

    assert pol.store_health()["ok"] is False


@pytest.mark.parametrize(
    "evt",
    [
        {"kind": "policy_retired", "policy_id": "p"},
        {
            "kind": "policy_retired",
            "policy_id": "p",
            "retired_at": "2026-08-05T00:00:00",
            "retired_by": "x",
        },
        {
            "kind": "policy_retired",
            "policy_id": "p",
            "retired_at": "2026-08-05T00:00:00+00:00",
            "retired_by": "",
        },
        {
            "kind": "policy_retired",
            "policy_id": "ghost",
            "retired_at": "2026-08-05T00:00:00+00:00",
            "retired_by": "x",
        },
    ],
    ids=["missing-fields", "naive-timestamp", "empty-actor", "dangling-reference"],
)
def test_malformed_retirement_event_is_corruption(pol, tmp_path, evt):
    (tmp_path / "policies.jsonl").write_text(
        json.dumps(_good_row()) + "\n" + json.dumps(evt) + "\n", encoding="utf-8"
    )

    assert pol.store_health()["ok"] is False


def test_corruption_is_not_reported_as_missing_policy(pol, tmp_path):
    """Owner OS must not be told to create a policy when authority is unreadable."""
    (tmp_path / "policies.jsonl").write_text("{broken}\n", encoding="utf-8")

    _, reason = pol.resolve_for_prospect(
        {"campaign_offer_policy_id": "p", "campaign_offer_policy_version": 1}
    )

    assert reason == pol.POLICY_STORE_CORRUPT


def test_genuinely_missing_version_is_still_not_found(pol):
    pol.put_policy("p", product_family="marketing", allowed_package_codes=["starter"])

    _, reason = pol.resolve_for_prospect(
        {"campaign_offer_policy_id": "p", "campaign_offer_policy_version": 99}
    )

    assert reason == "POLICY_NOT_FOUND"


def test_retired_policy_id_refuses_a_new_version(pol, tmp_path):
    """Otherwise the write succeeds but the row is permanently unreachable."""
    pol.put_policy("camp", product_family="marketing", allowed_package_codes=["starter"])
    pol.retire_policy("camp")
    before = (tmp_path / "policies.jsonl").read_text(encoding="utf-8")

    assert (
        pol.put_policy("camp", product_family="combo", allowed_package_codes=["advanced"]) is None
    )
    assert (tmp_path / "policies.jsonl").read_text(encoding="utf-8") == before
    assert pol.resolve_exact("camp", 1)["allowed_package_codes"] == ["starter"]


def test_replacement_policy_id_works_after_retirement(pol):
    pol.put_policy("camp", product_family="marketing", allowed_package_codes=["starter"])
    pol.retire_policy("camp")

    fresh = pol.put_policy("camp-v2", product_family="combo", allowed_package_codes=["advanced"])

    assert fresh is not None
    got, reason = pol.resolve_for_send(policy_id="camp-v2")
    assert reason == "ok" and got["policy_id"] == "camp-v2"


def test_creation_rejects_unknown_product_family(pol):
    assert pol.put_policy("p", product_family="nonsense", allowed_package_codes=["starter"]) is None


# ============ P0: package family / exact payable amount =====================


def test_voice_annual_is_refused_rather_than_undercharged(pol):
    """voice_plan_price() returns the MONTHLY equivalent for annual plans.

    Freezing it would quote ~Rs 4,999 for a ~Rs 49,990 annual commitment. Until a
    descriptor carries price_inr_year as the payable amount, annual must refuse.
    """
    from app.marketing import voice_packages as vp

    annual = next((c for c in vp.VOICE_PLAN_IDS if c.endswith("_annual")), None)
    assert annual, "no annual voice plan in catalogue"

    assert pol.put_policy("v", product_family="voice", allowed_package_codes=[annual]) is None


def test_cross_family_packages_are_refused(pol):
    """A code existing 'somewhere' is not authorisation to sell it."""
    assert pol.put_policy("a", product_family="voice", allowed_package_codes=["starter"]) is None
    assert pol.put_policy("b", product_family="topup", allowed_package_codes=["advanced"]) is None
    assert (
        pol.put_policy("c", product_family="marketing", allowed_package_codes=["voice_a_monthly"])
        is None
    )


def test_advanced_is_combo_not_marketing(pol):
    """`advanced` is Marketing + AI Voice — the family must say so."""
    assert (
        pol.put_policy("m", product_family="marketing", allowed_package_codes=["advanced"]) is None
    )

    combo = pol.put_policy("c", product_family="combo", allowed_package_codes=["advanced"])
    assert combo is not None
    assert pol.qualify(combo, {})["amount"] == 5999


def test_topup_pack_prices_as_a_one_time_charge(pol):
    p = pol.put_policy("t", product_family="topup", allowed_package_codes=["topup_100"])

    assert p is not None
    assert pol.qualify(p, {})["amount"] == 1499  # TOPUP_PACKS.price_inr


def test_free_pilot_cannot_enter_the_paid_upi_path(pol):
    assert (
        pol.put_policy("f", product_family="voice", allowed_package_codes=["voice_pilot"]) is None
    )


def test_marketing_starter_still_prices_correctly(pol):
    from app.marketing.packages import get_starter_price_inr

    p = pol.put_policy("s", product_family="marketing", allowed_package_codes=["starter"])

    assert pol.qualify(p, {})["amount"] == get_starter_price_inr()
