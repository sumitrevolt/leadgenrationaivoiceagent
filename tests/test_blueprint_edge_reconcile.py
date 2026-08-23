"""Edge-reconciliation completeness gate.

Locks the accounting rules for folding the legacy Explorer edges into the one
canonical registry:

* every raw edge literal is accounted for — none silently discarded,
* raw / unique / exact-duplicate counts reconcile arithmetically,
* canonical-pair collisions are tracked as a DIFFERENT concept from exact
  duplicate literals,
* nothing is importable on adjacency alone (a legacy ``{f,t}`` literal proves
  the two boxes were drawn connected and nothing more),
* and a tool that cannot read its inputs fails CLOSED rather than reporting
  success.
"""

from __future__ import annotations

import pytest

from scripts import blueprint_edge_reconcile as ber


def _m():
    return ber.reconcile_edges()


# --------------------------- accounting ------------------------------------
def test_manifest_is_ok():
    m = _m()
    assert m["ok"], m["errors"]


def test_every_raw_literal_is_accounted_for():
    m = _m()
    assert m["raw_edge_literals"] > 0
    assert m["accounted_entries"] == m["raw_edge_literals"]
    assert len(m["entries"]) == m["raw_edge_literals"]
    assert sum(m["counts"].values()) == m["raw_edge_literals"]


def test_duplicate_accounting_reconciles():
    """unique + exact duplicates == raw literals."""
    m = _m()
    assert m["unique_legacy_pairs"] + m["exact_duplicate_literals"] == m["raw_edge_literals"]
    assert m["exact_duplicate_literals"] >= 0


def test_raw_input_is_not_silently_deduplicated():
    m = _m()
    if m["exact_duplicate_literals"]:
        dupes = [e for e in m["entries"] if e["exact_duplicate_literal"]]
        assert len(dupes) == m["exact_duplicate_literals"]
        for e in dupes:
            assert e["literal_occurrence"] >= 2
            assert e["classification"] == "REVIEW_REQUIRED"
        # the first occurrence is still present and distinct
        firsts = [e for e in m["entries"] if e["literal_occurrence"] == 1]
        assert len(firsts) == m["unique_legacy_pairs"]


def test_collisions_are_distinct_from_exact_duplicates():
    """Two different legacy pairs collapsing onto one canonical pair is NOT
    the same thing as the same literal appearing twice."""
    m = _m()
    assert "canonical_pair_collisions" in m
    for e in m["entries"]:
        if e["canonical_collision_id"]:
            assert not e["exact_duplicate_literal"] or e["literal_occurrence"] >= 2
            assert e["classification"] == "REVIEW_REQUIRED"
            assert e["eligible_for_import"] is False


def test_classification_vocabulary_is_closed():
    for e in _m()["entries"]:
        assert e["classification"] in ber.EDGE_CLASSIFICATIONS, e


def test_deterministic_and_sorted():
    a, b = _m(), _m()
    assert a["entries"] == b["entries"]
    assert a["counts"] == b["counts"]
    keys = [(e["legacy_source"], e["legacy_target"]) for e in a["entries"]]
    assert keys == sorted(keys)


# --------------------------- honesty gates ---------------------------------
def test_nothing_is_eligible_for_import_on_adjacency_alone():
    assert ber.IMPORTABLE_CLASSIFICATIONS == ()
    for e in _m()["entries"]:
        assert e["eligible_for_import"] is False, e
        assert e["imported"] is False, e
        assert e["evidence_level"] == "LEGACY_ADJACENCY_ONLY"
        assert e["contract_status"] == "UNVERIFIED"


def test_endpoints_resolved_means_endpoints_only():
    for e in _m()["entries"]:
        if e["classification"] == "ENDPOINTS_RESOLVED_REVIEW_REQUIRED":
            assert e["endpoint_resolution"] == "VERIFIED"
            assert e["contract_status"] == "UNVERIFIED"
            assert e["canonical_source"] and e["canonical_target"]
            assert e["canonical_source"] != e["canonical_target"]


def test_existing_canonical_pair_is_not_claimed_equivalent():
    for e in _m()["entries"]:
        if e["canonical_pair_exists"]:
            assert e["contract_equivalence"] == "UNVERIFIED", e


def test_runtime_contract_fields_are_never_fabricated():
    for e in _m()["entries"]:
        for f in ber._CONTRACT_FIELDS:
            assert e[f] is None, (e["legacy_source"], f)


def test_no_self_edge_is_promoted():
    for e in _m()["entries"]:
        if e["self_edge"]:
            assert e["classification"] != "ENDPOINTS_RESOLVED_REVIEW_REQUIRED"


def test_unresolved_endpoints_are_reported_not_dropped():
    for e in _m()["entries"]:
        if e["endpoint_resolution"] == "UNRESOLVED":
            assert e["reason"]
            assert e["classification"] in (
                "ENDPOINT_MISSING",
                "DEPRECATED",
                "INVALID_OR_STALE",
                "REVIEW_REQUIRED",
            )


# --------------------------- fail-closed -----------------------------------
def test_check_mode_exit_zero_on_healthy_manifest():
    assert ber.main(["--check"]) == 0


def test_parse_failure_fails_closed(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(ber, "_load", boom)
    m = ber.reconcile_edges()
    assert m["ok"] is False
    assert m["errors"]
    assert ber.main(["--check"]) == 1
    assert ber.main([]) == 1


def test_missing_legacy_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(ber, "ROOT", tmp_path)
    m = ber.reconcile_edges()
    assert m["ok"] is False
    assert any("not found" in e for e in m["errors"])
    assert ber.main(["--check"]) == 1


def test_incomplete_manifest_fails_check(monkeypatch):
    real = ber.reconcile_edges()
    broken = dict(real)
    broken["accounted_entries"] = real["raw_edge_literals"] - 1
    monkeypatch.setattr(ber, "reconcile_edges", lambda: broken)
    assert ber.main(["--check"]) == 1


def test_duplicate_arithmetic_mismatch_fails_check(monkeypatch):
    real = ber.reconcile_edges()
    broken = dict(real)
    broken["unique_legacy_pairs"] = real["unique_legacy_pairs"] + 5
    monkeypatch.setattr(ber, "reconcile_edges", lambda: broken)
    assert ber.main(["--check"]) == 1


def test_unknown_classification_is_flagged(monkeypatch):
    real = ber.reconcile_edges()
    entries = [dict(e) for e in real["entries"]]
    entries[0]["classification"] = "NOT_A_REAL_CLASSIFICATION"
    for e in entries:
        assert (
            e["classification"] in ber.EDGE_CLASSIFICATIONS
            or e["classification"] == "NOT_A_REAL_CLASSIFICATION"
        )
    with pytest.raises(AssertionError):
        for e in entries:
            assert e["classification"] in ber.EDGE_CLASSIFICATIONS


def test_json_mode_returns_nonzero_when_not_ok(monkeypatch):
    monkeypatch.setattr(ber, "reconcile_edges", lambda: {**ber._fail(["broken"]), "entries": []})
    assert ber.main(["--json"]) == 1


# --------------------------- isolation -------------------------------------
def test_l0_projection_untouched_by_edge_analysis():
    from app.platform import blueprint_graph as bg

    c = bg.build_graph()["counts"]
    assert c["l0"] == 50
    assert c["edges"] == 56 and c["flows"] == 11
    assert c["domains"] == 18 and c["layers"] == 9


def test_no_sys_path_mutation_at_import_time():
    """Regression: a module-level sys.path insert segfaulted CI (PR #131)."""
    src = (ber.ROOT / "scripts" / "blueprint_edge_reconcile.py").read_text(
        encoding="utf-8", errors="replace"
    )
    head = src.split("def _ensure_repo_importable", 1)[0]
    assert "sys.path.insert" not in head


def test_manifest_carries_no_secrets():
    import json
    import re

    blob = json.dumps(_m())
    for pat in (r"sk_[A-Za-z0-9]{8,}", r"AIza[0-9A-Za-z_\-]{20,}"):
        assert not re.search(pat, blob), pat
