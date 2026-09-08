"""Offer pricing must resolve the EXACT payable amount, per family and cadence.

Confirmed against the deployed production image (SHA 9f2ab9f8) before writing:

    voice_a_annual -> offers._price_for: (4999, 'INR')
    BAND A price_month: 4999   price_year: 49990

`offers.issue_offer` is the canonical order-creation path (merged in #241, live).
It resolves annual voice through `voice_packages.voice_plan_price()`, whose own
docstring says it returns the MONTHLY equivalent even for annual plans. So an
annual order freezes ~Rs 4,999 against a ~Rs 49,990 commitment — a ~90%
undercharge, and `voice_a_annual` is indistinguishable from `voice_a_monthly`.

No customer has been undercharged: zero offers have ever been issued and
`issue_offer` has no caller yet. This is a latent live defect, and it must be
closed before anything wires the offer path.

The deeper fault is that a bare price lookup cannot express commercial truth. A
package code alone does not say which family it belongs to, whether the amount
is monthly / annual / one-time, or whether it may be sold at all. These tests
pin that contract.

Pure logic: no network, no store writes, no provider calls.
"""

from __future__ import annotations

import pytest

from app.marketing import offers, packages, voice_packages


def _band(letter: str) -> dict:
    return voice_packages.BANDS[letter]


# ------------------------------------------------------- exact payable amounts


@pytest.mark.parametrize("letter", ["A", "B", "C"])
def test_annual_voice_uses_the_annual_payable_amount(letter):
    """THE production defect: annual must charge price_year, not price_month."""
    band = _band(letter)
    code = band["plan_annual"]

    got = offers._price_for(code)

    assert got is not None, f"{code} must be priceable"
    assert got[0] == band["price_year"], (
        f"{code} priced at {got[0]} but the annual payable amount is "
        f"{band['price_year']} (monthly equivalent is {band['price_month']})"
    )


@pytest.mark.parametrize("letter", ["A", "B", "C"])
def test_annual_charge_differs_from_the_monthly_equivalent(letter):
    """Guards the specific confusion: annual != monthly, always."""
    band = _band(letter)

    annual = offers._price_for(band["plan_annual"])
    monthly = offers._price_for(band["plan_monthly"])

    assert annual is not None and monthly is not None
    assert annual[0] != monthly[0], "annual and monthly resolved to the same amount"
    assert annual[0] > monthly[0]


@pytest.mark.parametrize("letter", ["A", "B", "C"])
def test_monthly_voice_still_prices_correctly(letter):
    band = _band(letter)

    got = offers._price_for(band["plan_monthly"])

    assert got == (band["price_month"], "INR")


def test_marketing_starter_prices_from_the_catalogue():
    assert offers._price_for("starter") == (packages.get_starter_price_inr(), "INR")


def test_combo_advanced_is_not_priced_as_starter():
    got = offers._price_for("advanced")

    assert got == (5999, "INR")
    assert got[0] != packages.get_starter_price_inr()


# ------------------------------------------------------------- must fail closed


def test_free_pilot_cannot_produce_a_paid_order():
    """A zero-amount UPI order is not a sale."""
    assert offers._price_for("voice_pilot") is None


def test_unknown_package_fails_closed():
    assert offers._price_for("no_such_plan") is None
    assert offers._price_for("") is None


def test_internal_only_package_cannot_become_a_customer_offer():
    """`growth` is legacy/internal (public: False) but priced at Rs 2,999.

    A bare-code lookup returned that price, so it could become a customer-paid
    offer. Driven by the catalogue's own `public` flag rather than a hardcoded
    code, so a future internal package inherits the protection.
    """
    internal = [p for p in packages.PACKAGES if not p.get("public", True)]
    assert internal, "expected at least one non-public package in the catalogue"

    for pkg in internal:
        code = str(pkg["key"])
        assert offers._price_for(code) is None, f"{code} is non-public but priced"
        assert int(pkg.get("price_inr_month") or 0) > 0, (
            f"{code} must actually carry a price, else this test proves nothing"
        )


def test_topup_packs_are_not_sellable_through_this_resolver():
    """Top-up support is a separate commercial change, not a pricing fix.

    Enabling a previously impossible order type inside an undercharge
    correction would be an unrelated behaviour change. Top-ups return through
    the descriptor with explicit one-time cadence and entitlement semantics.
    """
    packs = list(getattr(packages, "TOPUP_PACKS", []))
    assert packs, "expected top-up packs in the catalogue"

    for pack in packs:
        assert offers._price_for(str(pack["key"])) is None


# ----------------------------------------------- issued offers freeze the truth


def test_issued_annual_offer_freezes_the_annual_amount(tmp_path, monkeypatch):
    """End-to-end through the real canonical order path."""
    monkeypatch.setattr(offers, "_store", lambda: str(tmp_path / "offers.jsonl"))
    band = _band("A")

    order = offers.issue_offer("deal-annual", band["plan_annual"])

    assert order is not None, "annual voice must be sellable"
    assert order["quoted_amount"] == band["price_year"]
    assert order["currency"] == "INR"
