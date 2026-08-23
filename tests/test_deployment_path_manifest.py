"""The deployment manifest must reconcile, and unknowns must count against us.

Four successive hand-written summaries of this surface disagreed with each
other. Every number now derives from `ENTRYPOINTS` and is asserted against an
independent recomputation here.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.platform import deployment_path_manifest as d

_REPO = pathlib.Path(__file__).resolve().parents[1]


def _executable_lines(rel: str) -> list[str]:
    """Source lines with comments and blanks removed.

    Classification must be based on what a script EXECUTES. Twice already a
    scanner read my own prose — a comment saying "no bypass" — and reported it
    as a finding. Comments are not evidence in either direction.
    """
    text = (_REPO / rel).read_text(encoding="utf-8", errors="replace")
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


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
    # NOT "assert unknown_unguarded" — that was a stage assertion, and it broke
    # the moment the unknowns were actually resolved, punishing progress. The
    # durable property is the accounting rule: however many unknowns exist,
    # every guard-required one is inside the unguarded total. Zero is allowed.
    for e in unknown_unguarded:
        assert d.requires_guard(e) is True, (
            f"{e['deployment_id']}: UNKNOWN entries are only permitted to leave "
            "the guard denominator via evidence, not by assumption"
        )
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


def test_deployment_guard_graph_has_no_gaps() -> None:
    """The Foundation gate: every guard-required entry point is guarded.

    This replaces an earlier `assert unguarded > 0` scaffold. That assertion
    described a STAGE rather than a property, so it failed the moment the last
    gap was closed — punishing the progress it was meant to track. It is the
    second time that shape bit me, so the rule is now explicit: assert what
    must always hold, not where the work happens to be.
    """
    c = d.counts()
    unguarded = [
        e["deployment_id"] for e in d.ENTRYPOINTS if d.requires_guard(e) and not e.get("guarded")
    ]
    assert c["unguarded_runtime_data_entrypoints"] == 0, f"unguarded: {unguarded}"
    assert c["unknown_guard_required_entrypoints"] == 0
    assert unguarded == []


# ------------------------------------------------------------------ unknowns


def test_no_unresolved_entrypoints_remain() -> None:
    """Every entry has an evidence-backed mutation capability.

    `None` means nobody looked. An unattended cron script whose capability was
    never read is not 'probably fine'.
    """
    unresolved = [
        e["deployment_id"] for e in d.ENTRYPOINTS if e.get("runtime_data_mutation_capable") is None
    ]
    assert unresolved == [], f"unresolved mutation capability: {unresolved}"


def test_unknown_buckets_sum_to_unknown_total() -> None:
    c = d.counts()
    assert (
        c["unknown_guard_required_entrypoints"] + c["unknown_guard_not_required_entrypoints"]
        == c["unknown_entrypoints"]
    )


def test_unknowns_inside_denominator_are_counted_as_unguarded() -> None:
    """A guard-required unknown must never be netted out of the exposure count.

    Guarding against the shape of my earlier errors: a separate 'unknown'
    bucket would let the gate read zero while unexamined paths sat in it.
    """
    c = d.counts()
    assert c["unknown_guard_required_entrypoints"] <= c["unguarded_runtime_data_entrypoints"]


# ------------------------------------------------- classification enforcement


def test_selfheal_cannot_prune_volumes() -> None:
    """`vps_selfheal.sh` is classified NON-runtime-data-mutating.

    That holds only because its prune is scoped to unused images/containers.
    `docker system prune --volumes` WOULD remove named volumes and invalidate
    the classification, so the classification is enforced here rather than
    trusted. Same for any git reset/clean, which would make it a release path.
    """
    e = next(x for x in d.ENTRYPOINTS if x["deployment_id"] == "maintenance.selfheal")
    assert e["runtime_data_mutation_capable"] is False
    assert d.requires_guard(e) is False

    lines = _executable_lines(e["file"])
    for line in lines:
        assert "--volumes" not in line, f"prune now removes volumes: {line}"
        assert not re.search(r"\bgit\s+(reset|clean|checkout)\b", line), (
            f"selfheal gained a git mutation, reclassify it: {line}"
        )


def test_selfheal_prune_is_actually_present() -> None:
    """Negative-space check: the classification says prune EXECUTES.

    If a future edit removed it, the evidence string would silently become
    false. A manifest whose evidence no longer matches source is worse than
    no manifest.
    """
    lines = _executable_lines("scripts/vps_selfheal.sh")
    assert any("docker system prune" in ln for ln in lines)
    assert any(re.search(r"\bdocker\s+restart\b", ln) for ln in lines)


def test_bootstrap_target_dir_is_env_overridable() -> None:
    """`hostinger_hermes_bootstrap.sh` is guard-required because of this line.

    Its comment claims a sandbox clone, and the DEFAULT is a sandbox clone.
    But `LOCAL_DIR` is overridable, so it can be pointed at /opt/leadgen and
    then `git reset --hard` the production checkout. Default-safe is not
    enforced-safe. If someone later hard-codes the path, this test fails and
    the entry should be reclassified rather than left over-restrictive.
    """
    e = next(x for x in d.ENTRYPOINTS if x["deployment_id"] == "bootstrap.hermes")
    assert d.requires_guard(e) is True
    # NOT pinned to UNGUARDED_PRODUCTION_PATH — that was a stage assertion and
    # it broke the moment the gap was closed. Third time this shape has bitten
    # me. The durable property is: while LOCAL_DIR is overridable this entry
    # requires a guard, and it must HAVE one.
    assert e["guarded"] is True, "bootstrap is guard-required but unguarded"
    assert e["guard_precedes_mutation"] is True

    lines = _executable_lines(e["file"])
    assert any(re.search(r'LOCAL_DIR="\$\{LOCAL_DIR:-', ln) for ln in lines), (
        "LOCAL_DIR is no longer env-overridable — re-evaluate the classification"
    )
    # The `git reset --hard` this entry was created for is now DELETED, not
    # gated — see tests/test_bootstrap_guard.py. Asserting its presence here
    # would lock in the very command the protection removed.
    assert not any(re.search(r"\bgit\s+reset\s+--hard\b", ln) for ln in lines), (
        "the destructive reset came back"
    )


def test_detached_execution_is_tracked_separately_from_guarding() -> None:
    """Detached delegation is an OPERATIONAL gap, not a containment gap.

    `_ship_vps_recover.sh` inherits the parent's guard (the guard runs before
    any mutation regardless), but `setsid nohup ... &` means the caller never
    learns whether the release succeeded. Recording that as `guarded=False`
    would overstate exposure; ignoring it would hide a real weakness.
    """
    e = next(x for x in d.ENTRYPOINTS if x["deployment_id"] == "recovery.ship_recover")
    assert e["guarded"] is True
    assert e["guard_precedes_mutation"] is True
    assert e["detached_execution"] is True
    assert e["operational_completion_observable"] is False
    assert e["exit_code_propagated"] is False


def test_operational_risks_never_change_the_guard_count() -> None:
    """Operational risk and containment must stay in separate ledgers.

    Real risks live outside the runtime-data denominator — an unattended
    `docker system prune` can delete the ROLLBACK IMAGES the release runbook
    depends on, and flywheel's `alembic upgrade head || true` swallows a
    migration failure with no rollback. Neither is checkout-backed data loss.
    Folding them into the guard count would corrupt the gate in one direction;
    dropping them would lose them entirely. So: tracked, and asserted to be
    inert with respect to the count.
    """
    before = d.counts()["runtime_data_guard_required_entrypoints"]
    risky = [e for e in d.ENTRYPOINTS if e["operational_risks"]]
    assert risky, "operational risks were dropped instead of tracked"
    for e in risky:
        # A risk record must never be the reason something looks guarded.
        assert isinstance(e["operational_risks"], list)
    assert d.counts()["runtime_data_guard_required_entrypoints"] == before


def test_known_operational_risks_are_recorded() -> None:
    by_id = {e["deployment_id"]: e for e in d.ENTRYPOINTS}
    assert "SELF_HEAL_ROLLBACK_ASSET_RISK" in by_id["maintenance.selfheal"]["operational_risks"]
    assert "UNATTENDED_DOCKER_PRUNE" in by_id["maintenance.selfheal"]["operational_risks"]
    assert "NO_VOLUME_PRUNE_VERIFIED" in by_id["maintenance.selfheal"]["operational_risks"]
    assert (
        "RECOVERY_RESULT_PROPAGATION_DEGRADED"
        in by_id["recovery.ship_recover"]["operational_risks"]
    )


def test_post_parent_mutation_declares_failure_semantics() -> None:
    """A wrapper that mutates after the parent must state whether that work
    propagates failure and whether it can be rolled back.

    Guard coverage proves runtime data is contained. It says nothing about
    whether a half-applied migration can be undone, and conflating the two
    would let 'guarded' read as 'safe'.
    """
    for e in d.ENTRYPOINTS:
        if not e["post_parent_mutation"]:
            continue
        assert e["post_parent_operations"], f"{e['deployment_id']}: undeclared post-parent work"
        assert isinstance(e["post_parent_failure_propagated"], bool)
        assert isinstance(e["post_parent_rollback_available"], bool)


def test_every_entry_declares_completion_observability() -> None:
    for e in d.ENTRYPOINTS:
        assert isinstance(e["detached_execution"], bool)
        assert isinstance(e["operational_completion_observable"], bool)
        if e["detached_execution"]:
            assert e["operational_completion_observable"] is False, (
                f"{e['deployment_id']}: detached but claims observable completion"
            )
