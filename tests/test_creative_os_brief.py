"""Creative OS Customer Video Brief — entitlement, brand provenance, anti-fabrication.

Pure unit tests: stores are monkeypatched, no FFmpeg, no queue, no network.
"""

from __future__ import annotations

import pytest

from app.marketing.creative_os import brief as B


def _client(**over):
    rec = {
        "id": "acme01",
        "business_name": "Acme Salon",
        "niche": "salon",
        "city": "Mumbai",
        "plan": "main",
        "status": "active",
        "brand": {"primary": "#101820", "accent": "#f2aa4c", "tagline": "Look sharp"},
        "socials": {"instagram": "acme"},
        "services": [{"name": "Haircut", "price_inr": 499}],
    }
    rec.update(over)
    return rec


@pytest.fixture
def store(monkeypatch):
    """Single seam for both store reads; catalog always knows 'main'."""
    state = {"rec": _client(), "kit": {}}
    monkeypatch.setattr(B, "_client_record", lambda tid: state["rec"])
    monkeypatch.setattr(B, "_plan_catalog", lambda: {"main": {"price_inr": 1999}})
    monkeypatch.setattr(
        "app.marketing.brand_kit.get_brand", lambda cid: state["kit"], raising=False
    )
    return state


# --- entitlement gate: fail-CLOSED --------------------------------------


def test_entitlement_allows_active_known_plan(store):
    assert B.entitlement_gate("acme01")["ok"] is True


@pytest.mark.parametrize(
    "over,reason",
    [
        ({"status": "cancelled"}, "inactive_subscription"),
        ({"status": ""}, "inactive_subscription"),
        ({"plan": ""}, "no_plan"),
        ({"plan": "ghost_plan"}, "unknown_plan"),
    ],
)
def test_entitlement_refuses(store, over, reason):
    store["rec"] = _client(**over)
    out = B.entitlement_gate("acme01")
    assert out["ok"] is False and out["reason"] == reason


def test_entitlement_refuses_unknown_tenant(store):
    store["rec"] = None
    assert B.entitlement_gate("nope")["reason"] == "unknown_tenant"


def test_entitlement_refuses_empty_tenant(store):
    assert B.entitlement_gate("")["ok"] is False


def test_lookup_failure_is_a_refusal_not_a_pass(monkeypatch):
    """A store that raises must not read as 'entitled'."""

    def boom(_tid):
        raise RuntimeError("store down")

    monkeypatch.setattr("app.marketing.clients_store.resolve_client", boom, raising=False)
    monkeypatch.setattr("app.marketing.clients_store.get_client", boom, raising=False)
    assert B.entitlement_gate("acme01")["ok"] is False


# --- brand resolution: provenance, no invented defaults ------------------


def test_brand_carries_provenance(store):
    prof = B.resolve_brand_profile("acme01")
    assert prof.primary_color == "#101820"
    assert prof.sources["primary_color"] == "clients_store.brand"
    assert prof.sources["business_name"] == "clients_store"
    assert prof.missing == []


def test_brand_kit_fills_gaps_but_never_overwrites(store):
    store["rec"] = _client(brand={"primary": "#101820"})
    store["kit"] = {"primary": "#ffffff", "accent": "#00ff00"}
    prof = B.resolve_brand_profile("acme01")
    assert prof.primary_color == "#101820"  # store wins
    assert prof.accent_color == "#00ff00"
    assert prof.sources["accent_color"] == "brand_kit"


def test_missing_brand_fields_are_reported_not_defaulted(store):
    store["rec"] = _client(brand={})
    prof = B.resolve_brand_profile("acme01")
    assert prof.primary_color == "" and prof.accent_color == ""
    assert set(prof.missing) == {"primary_color", "accent_color"}


def test_verified_prices_from_services(store):
    assert B.resolve_brand_profile("acme01").verified_prices() == {"499"}


# --- resolve_brief outcomes ---------------------------------------------


def test_ready_brief(store):
    out = B.resolve_brief(tenant_id="acme01", objective="monsoon offer", offer="Flat 20% off")
    assert out["ok"] and out["outcome"] == B.OUTCOME_READY
    assert out["brief"].brand.business_name == "Acme Salon"
    assert out["brief"].to_dict()["brand"]["sources"]


def test_blocked_when_not_entitled(store):
    store["rec"] = _client(status="cancelled")
    out = B.resolve_brief(tenant_id="acme01", objective="offer")
    assert out["outcome"] == B.OUTCOME_BLOCKED and out["brief"] is None


def test_needs_input_when_brand_incomplete(store):
    store["rec"] = _client(brand={"primary": "#101820"})
    out = B.resolve_brief(tenant_id="acme01", objective="offer")
    assert out["outcome"] == B.OUTCOME_NEEDS_INPUT
    assert out["missing"] == ["accent_color"]


def test_needs_input_when_objective_missing(store):
    out = B.resolve_brief(tenant_id="acme01", objective="   ")
    assert out["outcome"] == B.OUTCOME_NEEDS_INPUT and "objective" in out["missing"]


# --- anti-fabrication ----------------------------------------------------


@pytest.mark.parametrize("copy", ["Haircut at just Rs 199", "Only ₹1,299 today", "INR 899 offer"])
def test_unverified_price_in_copy_is_refused(store, copy):
    out = B.resolve_brief(tenant_id="acme01", objective="offer", offer=copy)
    assert out["outcome"] == B.OUTCOME_NEEDS_INPUT
    assert out["reason"] == "unverified_price"


def test_unverified_price_in_business_name_is_refused(store):
    out = B.resolve_brief(
        tenant_id="acme01",
        objective="general",
        business_name="Acme — sirf ₹1,299",
        niche="general",
    )
    assert out["outcome"] == B.OUTCOME_NEEDS_INPUT
    assert out["reason"] == "unverified_price"


def test_unverified_price_in_niche_is_refused(store):
    out = B.resolve_brief(
        tenant_id="acme01",
        objective="general",
        niche="salon from ₹999",
    )
    assert out["outcome"] == B.OUTCOME_NEEDS_INPUT
    assert out["reason"] == "unverified_price"


def test_unverified_price_in_store_business_name_is_refused(store):
    store["rec"] = _client(business_name="Jiya Makeover — only ₹1,299")
    out = B.resolve_brief(
        tenant_id="acme01",
        objective="general",
        business_name="",
        niche="general",
    )
    assert out["outcome"] == B.OUTCOME_NEEDS_INPUT
    assert out["reason"] == "unverified_price"


def test_unverified_price_in_store_niche_is_refused(store):
    store["rec"] = _client(niche="salon from ₹999")
    out = B.resolve_brief(tenant_id="acme01", objective="general")
    assert out["outcome"] == B.OUTCOME_NEEDS_INPUT
    assert out["reason"] == "unverified_price"


def test_entitlement_refuses_empty_plan_catalog(store, monkeypatch):
    monkeypatch.setattr(B, "_plan_catalog", lambda: {})
    out = B.entitlement_gate("acme01")
    assert out["ok"] is False and out["reason"] == "catalog_unavailable"


def test_verified_price_in_copy_passes(store):
    out = B.resolve_brief(tenant_id="acme01", objective="offer", offer="Haircut ₹499 only")
    assert out["ok"] is True


def test_unverified_price_detected_in_cta_too(store):
    out = B.resolve_brief(tenant_id="acme01", objective="offer", cta="Book now for Rs 99")
    assert out["reason"] == "unverified_price"


def test_no_price_in_copy_is_fine(store):
    assert B.resolve_brief(tenant_id="acme01", objective="brand awareness")["ok"] is True
