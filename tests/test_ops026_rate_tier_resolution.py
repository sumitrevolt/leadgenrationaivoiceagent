"""OPS-026 — rate-limit tier resolution: guard the OPS-024 bug class, change nothing.

Cycle 12 found OPS-024: `_classify` matched intent labels by SUBSTRING over an ordered
constant, so `"not_interested"` always resolved to `"interested"`. Cycle 13 swept the
codebase for the same shape — "first constant that appears inside the input wins" — and
found it in exactly one more place: `app/api/ratelimit.py::_client_tier`, which decides
the budget for the whole `/ai` router (`tier_rate_limit("ai", 30, 60)`).

    for key in _TIER_MULT:      # free, trial, starter, growth, advanced, voice, admin
        if key in t:
            return key

**Deliberately NOT changed.** Unlike OPS-024 this is not an active defect:
  - the tenant plan is server-derived (the spoofable client header was removed
    2026-07-01), so an attacker cannot set it, and
  - no real plan string (`free/trial/starter/growth/advanced/voice/admin`) contains
    another tier key, so today substring == exact.
Any "cleanup" here can only do harm: making matching exact would drop a plan like
`"voice_4999"` from 8x to 1x, i.e. throttle paying customers 8x harder. That is a
revenue-visible behaviour change, not a safety fix — it belongs to the owner.

What this file DOES pin (all green today, all fail loudly the moment the situation
changes):
  1. every real plan string still resolves to itself;
  2. no tier key is a substring of another (the OPS-024 class invariant);
  3. the real plan vocabulary is collision-free;
  4. unknown / missing / broken tenant state still falls back to `"free"` (fail-safe);
  5. a tripwire documenting the latent over-grant, so fixing it is a visible event.

See docs/OPS_026_RATE_TIER_SUBSTRING_2026-09-07.md.
"""

import types

import pytest

from app.api.ratelimit import _TIER_MULT, _client_tier


def _req(tenant):
    """Minimal stand-in for a Starlette Request carrying server-derived tenant state."""
    return types.SimpleNamespace(state=types.SimpleNamespace(tenant=tenant))


def _tier(plan):
    return _client_tier(_req({"plan": plan}))


# The plan values this codebase actually produces (see app/api/customer_auth.py,
# customer_onboard.py, billing/subscription.py, billing/usage.py).
REAL_PLANS = ("free", "trial", "starter", "growth", "advanced", "voice", "admin")


# --------------------------------------------------------------------------- #
# 1. Today's behaviour: every real plan resolves to itself
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("plan", REAL_PLANS)
def test_every_real_plan_resolves_to_itself(plan):
    assert _tier(plan) == plan


def test_tier_multiplier_is_actually_applied():
    """Sanity: the resolved tier is what scales the budget (not decoration)."""
    assert _TIER_MULT["free"] == 1.0
    assert _TIER_MULT["admin"] > _TIER_MULT["growth"]


# --------------------------------------------------------------------------- #
# 2. The OPS-024 class invariant: no key may contain another key
# --------------------------------------------------------------------------- #
def test_no_tier_key_is_a_substring_of_another():
    """If this ever fails, dict insertion order has started deciding budgets."""
    for a in _TIER_MULT:
        for b in _TIER_MULT:
            if a is b or a == b:
                continue
            assert a not in b, (
                f"tier key {a!r} is a substring of {b!r} — resolution is order-dependent"
            )


def test_resolution_is_independent_of_dict_order_for_real_plans():
    """Reversing the iteration order must not change any real plan's tier."""
    original = dict(_TIER_MULT)
    try:
        _TIER_MULT.clear()
        for k in reversed(list(original)):
            _TIER_MULT[k] = original[k]
        for plan in REAL_PLANS:
            assert _tier(plan) == plan
    finally:
        _TIER_MULT.clear()
        _TIER_MULT.update(original)


# --------------------------------------------------------------------------- #
# 3. The real plan vocabulary must stay collision-free
# --------------------------------------------------------------------------- #
def test_real_plan_vocabulary_has_no_cross_tier_collision():
    """A plan string must not contain a DIFFERENT tier key, or its tier is ambiguous."""
    for plan in REAL_PLANS:
        for key in _TIER_MULT:
            if key == plan:
                continue
            assert key not in plan, (
                f"plan {plan!r} contains tier key {key!r} — tier is ambiguous "
                f"(resolved: {_tier(plan)!r})"
            )


# --------------------------------------------------------------------------- #
# 4. Fail-safe preserved
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("plan", ["", "   ", "MAIN", "combo", "₹1999"])
def test_unknown_plan_falls_back_to_free(plan):
    assert _tier(plan) == "free"


def test_missing_or_broken_tenant_state_falls_back_to_free():
    assert _client_tier(_req(None)) == "free"
    assert _client_tier(_req({})) == "free"  # dict without "plan"
    assert _client_tier(types.SimpleNamespace(state=types.SimpleNamespace())) == "free"
    assert _client_tier(types.SimpleNamespace()) == "free"  # no .state at all


def test_tenant_object_plan_is_read_too():
    """Non-dict tenants expose `.plan`; that path must keep working."""
    assert _client_tier(_req(types.SimpleNamespace(plan="growth"))) == "growth"


# --------------------------------------------------------------------------- #
# 5. TRIPWIRE — the latent over-grant, documented, not fixed
# --------------------------------------------------------------------------- #
def test_ops026_tripwire_admin_budget_can_be_reached_by_substring():
    """TRIPWIRE for OPS-026 — this asserts CURRENT (latent-defect) behaviour.

    A plan string that merely CONTAINS "admin" inherits the largest budget (20x),
    because the scan is substring-based and `admin` is the last key. Unreachable
    from today's plan vocabulary (test 3 proves that), so it is not an active
    exploit — but it becomes one the moment a plan like "super_admin",
    "admin_lite" or "voice_admin" is introduced.

    If this test FAILS, someone fixed OPS-026: update this test and close the
    ADR. Do not "fix" it by deleting the test.
    """
    assert _tier("not_admin") == "admin"
    assert _TIER_MULT[_tier("not_admin")] == _TIER_MULT["admin"]
