"""Edge-reconciliation completeness gate.

Locks the accounting rules for folding the legacy Explorer edges into the one
canonical registry:

* every legacy edge is accounted for — none silently discarded,
* no edge is promoted on adjacency alone (a legacy ``{f,t}`` literal proves the
  two boxes were drawn connected; it proves nothing about queues, retries,
  tenancy, idempotency or runtime activation),
* collapsed duplicates go to review rather than creating a duplicate canonical
  edge,
* and the L0 overview projection is untouched by this analysis.
"""

from __future__ import annotations

from scripts import blueprint_edge_reconcile as ber


def _m():
    return ber.reconcile_edges()


def test_every_legacy_edge_is_accounted_for():
    m = _m()
    assert m["legacy_edges_total"] > 0
    assert sum(m["counts"].values()) == m["legacy_edges_total"]
    assert len(m["entries"]) == m["legacy_edges_total"]


def test_classification_vocabulary_is_closed():
    for e in _m()["entries"]:
        assert e["classification"] in ber.EDGE_CLASSIFICATIONS, e


def test_deterministic_and_sorted():
    a, b = _m(), _m()
    assert a["entries"] == b["entries"]
    keys = [(e["legacy_source"], e["legacy_target"]) for e in a["entries"]]
    assert keys == sorted(keys)


def test_no_edge_is_silently_dropped():
    """Unresolvable endpoints must be reported, not omitted."""
    m = _m()
    missing = [e for e in m["entries"] if e["classification"] == "ENDPOINT_MISSING"]
    for e in missing:
        assert e["reason"], e
        assert e["canonical_source"] is None or e["canonical_target"] is None or \
            e["source_node_classification"] in ("MISSING_RUNTIME",) or \
            e["target_node_classification"] in ("MISSING_RUNTIME",)


def test_migrate_verified_requires_both_endpoints_canonical():
    for e in _m()["entries"]:
        if e["classification"] == "MIGRATE_VERIFIED":
            assert e["canonical_source"] and e["canonical_target"], e
            assert e["canonical_source"] != e["canonical_target"], e


def test_no_duplicate_canonical_pair_is_migratable():
    """Collapsed duplicates must not become two identical canonical edges."""
    seen: set[tuple[str, str]] = set()
    for e in _m()["entries"]:
        if e["classification"] in ("MIGRATE_VERIFIED", "MERGE_WITH_CANONICAL_EDGE"):
            pair = (e["canonical_source"], e["canonical_target"])
            assert pair not in seen, f"duplicate canonical edge {pair}"
            seen.add(pair)


def test_self_edges_are_not_migrated():
    for e in _m()["entries"]:
        if e["self_edge"]:
            assert e["classification"] != "MIGRATE_VERIFIED", e


def test_runtime_fields_are_never_fabricated_from_adjacency():
    """Adjacency proves nothing about queues/retries/tenancy/idempotency."""
    for e in _m()["entries"]:
        for f in ("kind", "condition", "mode", "queue", "data_contract",
                  "on_success", "on_failure", "on_retry", "audit_event",
                  "propagates_tenant", "propagates_idempotency"):
            assert e[f] is None, (e["legacy_source"], f)


def test_l0_projection_untouched_by_edge_analysis():
    from app.platform import blueprint_graph as bg

    c = bg.build_graph()["counts"]
    assert c["l0"] == 48
    assert c["edges"] == 52 and c["flows"] == 11
    assert c["domains"] == 18 and c["layers"] == 9


def test_no_sys_path_mutation_at_import_time():
    """Regression: a module-level sys.path insert segfaulted CI (PR #131)."""
    src = (ber.ROOT / "scripts" / "blueprint_edge_reconcile.py").read_text(
        encoding="utf-8", errors="replace")
    head = src.split('if __name__ == "__main__"', 1)[0]
    assert "sys.path.insert" not in head.replace(
        "        sys.path.insert(0, str(ROOT))", "")


def test_check_mode_exit_zero():
    assert ber.main(["--check"]) == 0


def test_manifest_carries_no_secrets():
    import json
    import re

    blob = json.dumps(_m())
    for pat in (r"sk_[A-Za-z0-9]{8,}", r"AIza[0-9A-Za-z_\-]{20,}"):
        assert not re.search(pat, blob), pat
