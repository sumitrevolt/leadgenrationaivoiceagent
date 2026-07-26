"""The deployment manifest must reconcile, and unknowns must count against us.

Four successive hand-written summaries of this surface disagreed with each
other. Every number now derives from `ENTRYPOINTS` and is asserted against an
independent recomputation here.
"""

from __future__ import annotations

import pytest

from app.platform import deployment_path_manifest as d


def test_manifest_validates() -> None:
    problems = d.validate()
    assert problems == [], "manifest problems:\n  " + "\n  ".join(problems)


def test_unique_ids() -> None:
    ids = [e["deployment_id"] for e in d.ENTRYPOINTS]
    assert len(ids) == len(set(ids))
    assert d.counts()["unique_logical_entrypoints"] == len(ids)


def test_guard_denominator_invariant() -> None:
    """direct + parent + unguarded == runtime_data_guard_required."""
    c = d.counts()
    assert (
        c["directly_guarded_entrypoints"]
        + c["parent_guarded_entrypoints"]
        + c["unguarded_runtime_data_entrypoints"]
        == c["runtime_data_guard_required_entrypoints"]
    )


def test_scope_invariant() -> None:
    c = d.counts()
    assert (
        c["runtime_data_guard_required_entrypoints"]
        + c["production_non_runtime_mutation_entrypoints"]
        <= c["production_capable_entrypoints"]
    )


def test_unknown_counts_as_unguarded() -> None:
    """ "We have not checked" must never read as "safe".

    An UNKNOWN entry that is production-capable and not proven non-mutating is
    included in the unguarded total, so the release gate cannot reach zero
    before someone has actually looked.
    """
    c = d.counts()
    unknown_unguarded = [
        e
        for e in d.ENTRYPOINTS
        if e["status"] == d.UNKNOWN_REQUIRES_REVIEW and not e.get("guarded")
    ]
    assert unknown_unguarded, "expected unresolved entries at this stage"
    assert c["unguarded_runtime_data_entrypoints"] >= len(unknown_unguarded)


def test_unresolved_mutation_capability_requires_guard() -> None:
    """`runtime_data_mutation_capable=None` means unresolved, not False."""
    for e in d.ENTRYPOINTS:
        if e.get("production_capable") and e.get("runtime_data_mutation_capable") is None:
            assert d.requires_guard(e) is True, e["deployment_id"]


# ------------------------------------------- classification correctness
def test_non_runtime_mutation_is_excluded_from_denominator() -> None:
    """Config prep is production-scoped but cannot revert the checkout.

    Counting it as an unguarded deployment path would inflate the denominator
    and hide the real gap.
    """
    sops = next(e for e in d.ENTRYPOINTS if e["deployment_id"] == "config.sops_decrypt")
    assert sops["production_capable"] is True
    assert sops["runtime_data_mutation_capable"] is False
    assert d.requires_guard(sops) is False
    assert sops["status"] == d.PRODUCTION_NON_RUNTIME_MUTATION


def test_ci_workflow_is_not_production() -> None:
    ci = next(e for e in d.ENTRYPOINTS if e["deployment_id"] == "ci.tests_workflow")
    assert ci["production_capable"] is False
    assert d.requires_guard(ci) is False
    assert "ubuntu-latest" in ci["evidence"]


def test_restore_drill_is_diagnostic_not_release() -> None:
    drill = next(e for e in d.ENTRYPOINTS if e["deployment_id"] == "restore.pg_drill")
    assert drill["runtime_data_mutation_capable"] is False
    assert drill["status"] == d.DIAGNOSTIC_ONLY
    assert d.requires_guard(drill) is False


def test_parent_guarded_entry_cites_its_delegation() -> None:
    """A parent-guard claim needs the delegating line, not a filename guess."""
    rec = next(e for e in d.ENTRYPOINTS if e["status"] == d.GUARDED_BY_CANONICAL_PARENT)
    assert rec["canonical_parent"] == d.CANONICAL_RELEASE_PARENT
    assert "deploy_vps.sh" in rec["evidence"]
    # Honest weakness recorded rather than glossed.
    assert rec["exit_code_propagated"] is False


def test_canonical_release_parent_is_directly_guarded() -> None:
    parent = next(e for e in d.ENTRYPOINTS if e["file"] == d.CANONICAL_RELEASE_PARENT)
    assert parent["status"] == d.GUARDED_DIRECTLY
    assert parent["guard_precedes_mutation"] is True


@pytest.mark.parametrize(
    "deployment_id",
    ["release.canonical", "release.mcp_remote", "release.pitch", "release.force_pull"],
)
def test_guarded_entries_precede_mutation(deployment_id: str) -> None:
    e = next(x for x in d.ENTRYPOINTS if x["deployment_id"] == deployment_id)
    assert e["guarded"] is True
    assert e["guard_precedes_mutation"] is True
    assert e["fallback_after_denial"] is False


def test_gate_is_not_yet_met() -> None:
    """The Foundation gate requires zero unguarded. It is not zero today."""
    c = d.counts()
    assert (
        c["unguarded_runtime_data_entrypoints"] > 0
    ), "if this passes, either the work is done or the manifest is lying"
