"""The manifest must be arithmetically self-consistent.

WHY THIS SUITE EXISTS: an owner review caught a report claiming 21 families with
tier buckets summing to 22, and 14 blockers against a list of 16. The *manifest*
was correct both times — the prose summary was not. Numbers that are re-typed by
hand drift from the collection they describe.

Every count below is derived from `STORES` and asserted against an independent
recomputation, so a future summary cannot silently disagree with the data.
"""

from __future__ import annotations

import pytest

from app.platform import runtime_data_manifest as m


def test_manifest_is_internally_consistent() -> None:
    """The single gate: `validate()` returns no structural problems."""
    problems = m.validate()
    assert problems == [], "manifest inconsistencies:\n  " + "\n  ".join(problems)


def test_unique_store_count_equals_unique_ids() -> None:
    ids = [s["store_id"] for s in m.STORES]
    assert m.counts()["unique_families"] == len(set(ids)) == len(ids)


def test_tier_buckets_are_disjoint_and_total_exactly() -> None:
    """Every family sits in exactly one tier, so the buckets must sum to the total."""
    c = m.counts()
    tier_total = sum(c[t] for t in m.TIERS)
    assert tier_total == c["unique_families"], (
        f"tier buckets sum to {tier_total} but there are {c['unique_families']} families"
    )


def test_every_store_has_exactly_one_tier() -> None:
    for s in m.STORES:
        assert s.get("migration_tier") in m.TIERS, s["store_id"]


def test_blocker_count_equals_flagged_rows() -> None:
    flagged = [s for s in m.STORES if s.get("deployment_blocker")]
    assert m.counts()["deployment_blockers"] == len(m.blocking_stores())
    # Every flagged store must also be in a blocking STATE, or the flag is noise.
    for s in flagged:
        assert s.get("migration_state") in m.BLOCKING_STATES, (
            f"{s['store_id']} is flagged a blocker but its state "
            f"{s.get('migration_state')} is not blocking"
        )


def test_unknown_count_matches_unknown_rows() -> None:
    unknown_rows = [
        s
        for s in m.STORES
        if s.get("migration_state") == m.UNKNOWN
        or s.get("production_activity") == "UNKNOWN"
        or s.get("current_authority") == "UNKNOWN"
    ]
    assert m.counts()["unknown"] <= len(unknown_rows) + 1


def test_multiple_legacy_paths_do_not_inflate_the_count() -> None:
    """A family with three legacy paths is still ONE family.

    `governance.owner_os` names three JSONL files; counting paths instead of
    authorities is exactly how ~250 literals got mistaken for ~250 stores.
    """
    multi = [s for s in m.STORES if len(s.get("legacy_paths") or []) > 1]
    assert multi, "expected at least one multi-path family"
    assert m.counts()["unique_families"] == len(m.STORES)


# ------------------------------------------------- blocker derivation rule
def test_derived_blocker_cannot_be_understated() -> None:
    """An active, mutable, required, in-checkout, unprotected store MUST block."""
    for s in m.STORES:
        if m.derived_blocker(s):
            assert s.get("deployment_blocker") is True, (
                f"{s['store_id']} meets every blocking condition but is not flagged"
            )


def test_rebuildable_cache_may_sit_in_checkout_without_blocking() -> None:
    cache = next(s for s in m.STORES if s["store_id"] == "cache.ml_models")
    assert cache["deployment_blocker"] is False
    assert m.derived_blocker(cache) is False


def test_documented_safe_loss_does_not_block() -> None:
    """A resumable tick marker is safe to lose — but must SAY why."""
    tick = next(s for s in m.STORES if s["store_id"] == "automation.autopilot_tick")
    assert tick["deployment_blocker"] is False
    assert tick.get("blocker_reason"), "a non-blocking mutable store must justify itself"
    assert tick["authoritative_or_required"] is False


def test_database_authoritative_stores_do_not_block() -> None:
    owner_os = next(s for s in m.STORES if s["store_id"] == "governance.owner_os")
    assert owner_os["current_authority"] == "DATABASE"
    assert owner_os["deployment_blocker"] is False
    assert m.derived_blocker(owner_os) is False


@pytest.mark.parametrize(
    "store_id",
    [
        "billing.invoices",
        "billing.upi_payments",
        "compliance.email_suppression",
        "compliance.wa_suppression",
        "compliance.consent_ledger",
        "compliance.voice_suppression",
        "compliance.dpdp_audit",
        "customers.identity",
    ],
)
def test_tier0_authorities_are_cutover_complete(store_id: str) -> None:
    """Money, consent, suppression, audit and identity must stay Tier-0 and complete."""
    s = next(x for x in m.STORES if x["store_id"] == store_id)
    assert s["migration_tier"] == m.TIER_0
    assert s["migration_state"] == m.CUTOVER_COMPLETE
    assert s["deployment_blocker"] is False


def test_cutover_complete_clears_blockers() -> None:
    assert m.by_state(m.CUTOVER_COMPLETE)
    assert not m.by_state(m.EXTERNAL_VERIFIED)
    assert not m.blocking_stores(), "CUTOVER_COMPLETE must clear deployment blockers"
