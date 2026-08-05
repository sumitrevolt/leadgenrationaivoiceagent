"""Campaign Offer Policy — immutable versioning + fail-closed qualification (#240).

The whole point is that a package is never GUESSED. These tests are written
adversarially: every path that could produce a wrong price must instead produce a
question or an exception.

Pure python: store monkeypatched to tmp_path, no network/LLM.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def pol(tmp_path, monkeypatch):
    from app.marketing import campaign_offer_policy as mod

    monkeypatch.setattr(mod, "_store", lambda: str(tmp_path / "policies.jsonl"))
    return mod


# ----------------------------------------------------------------- versioning


def test_edit_appends_a_new_immutable_version(pol):
    v1 = pol.put_policy("p1", product_family="marketing", allowed_package_codes=["starter"])
    v2 = pol.put_policy("p1", product_family="marketing", allowed_package_codes=["advanced"])

    assert v1["policy_version"] == 1
    assert v2["policy_version"] == 2
    # v1's commercial meaning is untouched — a message already in flight keeps it
    stored_v1 = [r for r in pol.list_policies("p1") if r["policy_version"] == 1][0]
    assert stored_v1["allowed_package_codes"] == ["starter"]


def test_resolution_prefers_newest_active_version(pol):
    pol.put_policy("p1", product_family="marketing", allowed_package_codes=["starter"])
    pol.put_policy("p1", product_family="marketing", allowed_package_codes=["advanced"])

    assert pol.resolve_policy(policy_id="p1")["policy_version"] == 2


def test_retired_policy_cannot_be_resolved(pol):
    pol.put_policy("p1", product_family="marketing", allowed_package_codes=["starter"])
    pol.retire_policy("p1")

    assert pol.resolve_policy(policy_id="p1") is None


def test_default_package_must_be_in_the_allowed_list(pol):
    """Prevents a policy that authorises a price it never allowed."""
    bad = pol.put_policy(
        "p1",
        product_family="marketing",
        allowed_package_codes=["starter"],
        default_package_code="advanced",
    )

    assert bad is None
    assert pol.list_policies("p1") == []


# ------------------------------------------------------------ live provenance


def test_prospect_without_send_stamp_resolves_to_none(pol):
    """All historical generic cold email — must NOT license a quote."""
    assert pol.resolve_for_prospect({"business_name": "X"}) is None
    assert pol.resolve_for_prospect(None) is None


def test_prospect_resolves_through_campaign_variant_id(pol):
    """`campaign_variant_id` is what auto_outreach actually stamps at send time."""
    pol.put_policy(
        "combo-q3",
        product_family="marketing",
        allowed_package_codes=["advanced"],
        message_variant="var-77",
    )

    got = pol.resolve_for_prospect({"campaign_variant_id": "var-77"})

    assert got is not None
    assert got["policy_id"] == "combo-q3"


# ----------------------------------------------------------- fail-closed rules


def test_missing_policy_asks_instead_of_quoting(pol):
    out = pol.qualify(None, {})

    assert out["outcome"] == pol.NEEDS_QUALIFICATION
    assert out["reason"] == "POLICY_NOT_FOUND"
    assert out["amount"] is None


def test_discovery_campaign_never_quotes(pol):
    """The historical generic campaign pitched nothing — it must qualify."""
    p = pol.put_policy("legacy-cold", product_family=pol.FAMILY_DISCOVERY)

    out = pol.qualify(p, {"intent": "interested"})

    assert out["outcome"] == pol.NEEDS_QUALIFICATION
    assert out["amount"] is None
    assert out["package_code"] == ""


def test_intent_alone_never_selects_a_package(pol):
    """Reply intent is not a commercial fact."""
    p = pol.put_policy(
        "multi", product_family="marketing", allowed_package_codes=["starter", "advanced"]
    )

    out = pol.qualify(p, {"intent": "interested", "niche": "salon", "business_name": "X"})

    assert out["outcome"] == pol.NEEDS_QUALIFICATION
    assert out["reason"] == "PACKAGE_UNRESOLVED"


def test_package_outside_the_allowed_list_is_an_exception(pol):
    p = pol.put_policy(
        "marketing-only", product_family="marketing", allowed_package_codes=["starter"]
    )

    out = pol.qualify(p, {"requested_package": "advanced"})

    assert out["outcome"] == pol.EXCEPTION_REQUIRED
    assert out["reason"] == "PACKAGE_NOT_ALLOWED"
    assert out["amount"] is None


def test_unknown_package_fails_closed(pol):
    p = pol.put_policy("p", product_family="marketing", allowed_package_codes=["no_such_plan"])

    out = pol.qualify(p, {"requested_package": "no_such_plan"})

    assert out["outcome"] == pol.EXCEPTION_REQUIRED
    assert out["reason"] == "PRICE_UNAVAILABLE"


def test_retired_policy_qualification_is_an_exception(pol):
    p = pol.put_policy("p", product_family="marketing", allowed_package_codes=["starter"])
    pol.retire_policy("p")
    retired = pol.list_policies("p")[0]

    out = pol.qualify(retired, {"requested_package": "starter"})

    assert out["outcome"] == pol.EXCEPTION_REQUIRED
    assert out["reason"] == "POLICY_RETIRED"


# --------------------------------------------------------- correct selections


def test_single_allowed_package_is_deterministic(pol):
    from app.marketing.packages import get_starter_price_inr

    p = pol.put_policy(
        "starter-camp", product_family="marketing", allowed_package_codes=["starter"]
    )

    out = pol.qualify(p, {})

    assert out["outcome"] == pol.PACKAGE_SELECTED
    assert out["package_code"] == "starter"
    assert out["amount"] == get_starter_price_inr()
    assert out["currency"] == "INR"


def test_combo_is_never_priced_as_starter(pol):
    """The exact bug this whole authority exists to prevent."""
    from app.marketing.packages import get_starter_price_inr

    p = pol.put_policy("combo-camp", product_family="marketing", allowed_package_codes=["advanced"])

    out = pol.qualify(p, {})

    assert out["outcome"] == pol.PACKAGE_SELECTED
    assert out["package_code"] == "advanced"
    assert out["amount"] == 5999
    assert out["amount"] != get_starter_price_inr()


def test_price_comes_from_the_catalogue_not_the_policy(pol):
    """Policies must not duplicate price truth."""
    p = pol.put_policy("p", product_family="marketing", allowed_package_codes=["starter"])

    assert "price" not in p
    assert "amount" not in p


def test_qualify_never_raises_on_garbage(pol):
    for bad in ({}, {"product_family": None}, {"status": "active"}):
        out = pol.qualify(bad, {"requested_package": "starter"})
        assert out["outcome"] in (
            pol.NEEDS_QUALIFICATION,
            pol.EXCEPTION_REQUIRED,
            pol.PACKAGE_SELECTED,
            pol.NOT_ELIGIBLE,
        )
