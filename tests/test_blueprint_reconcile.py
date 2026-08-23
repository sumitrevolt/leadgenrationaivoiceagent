"""Legacy Explorer -> canonical Blueprint reconciliation gate.

Evidence artifact for the migration step: the legacy `/app/explorer` graph is
being folded into the ONE canonical registry (`app/platform/blueprint_graph`).
These tests lock the reconciliation contract so the migration stays honest:
deterministic output, a closed classification vocabulary, evidence-backed
"verified" labels, and no legacy node smuggled in while naming a file that does
not exist.
"""

from __future__ import annotations

from scripts import blueprint_reconcile as br


def test_manifest_shape():
    m = br.reconcile()
    for k in (
        "legacy_view_nodes",
        "legacy_subnodes",
        "legacy_edges",
        "canonical_nodes",
        "counts",
        "entries",
    ):
        assert k in m, f"manifest missing {k}"
    assert m["legacy_view_nodes"] > 0
    assert m["legacy_edges"] > 0
    assert m["canonical_nodes"] > 0
    assert len(m["entries"]) == m["legacy_view_nodes"] + m["legacy_subnodes"]


def test_classification_vocabulary_is_closed():
    m = br.reconcile()
    for e in m["entries"]:
        assert e["classification"] in br.CLASSIFICATIONS, e


def test_deterministic_output():
    """Same input -> byte-identical manifest (no set-ordering leakage)."""
    a, b = br.reconcile(), br.reconcile()
    assert a["entries"] == b["entries"]
    assert [e["legacy_id"] for e in a["entries"]] == sorted(e["legacy_id"] for e in a["entries"])


def test_no_legacy_node_references_a_missing_file():
    """Drift gate: a legacy node claiming `files:'x.py'` must resolve on disk."""
    m = br.reconcile()
    stale = [
        (e["legacy_id"], e["files_unresolved"])
        for e in m["entries"]
        if e["classification"] == "INVALID_OR_STALE"
    ]
    assert not stale, f"legacy nodes reference missing files: {stale}"


def test_merged_entries_name_a_canonical_node():
    m = br.reconcile()
    for e in m["entries"]:
        if e["classification"] in ("MERGE_WITH_CANONICAL_NODE", "DEPRECATED"):
            assert e["canonical_id"], f"{e['legacy_id']} merged but no canonical_id"


def test_migrate_verified_is_evidence_backed():
    """ "Verified" is never granted on a description — only on a real file."""
    m = br.reconcile()
    for e in m["entries"]:
        if e["classification"] == "MIGRATE_VERIFIED":
            assert e["files_resolved"], f"{e['legacy_id']} verified without file evidence"
            assert e["evidence"].startswith("disk:")


def test_missing_runtime_has_no_file_claim():
    m = br.reconcile()
    for e in m["entries"]:
        if e["classification"] == "MISSING_RUNTIME":
            assert not e["files_declared"], e["legacy_id"]


def test_subnodes_carry_their_parent():
    m = br.reconcile()
    subs = [e for e in m["entries"] if e["kind"] == "subnode"]
    assert subs, "no SUBNODES parsed — parser regression"
    for e in subs:
        assert e["parent_legacy_id"], f"subnode {e['legacy_id']} lost its parent"


def test_check_mode_exit_zero():
    assert br.main(["--check"]) == 0


def test_manifest_carries_no_secrets():
    import json
    import re

    blob = json.dumps(br.reconcile())
    for pat in (
        r"sk_[A-Za-z0-9]{8,}",
        r"AIza[0-9A-Za-z_\-]{20,}",
        r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"]{8,}",
    ):
        assert not re.search(pat, blob), f"secret-shaped literal in manifest: {pat}"
