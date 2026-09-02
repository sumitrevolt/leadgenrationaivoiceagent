"""Phase-1 derivation gate: evidence-backed L1/L2 parent proposals.

These tests lock the *honesty* of the derivation rather than a target import
count. The failure mode we are defending against is a heuristic that emits
confident-but-wrong parents. Real examples caught during design and pinned here
as negative regressions:

    admin_ui     -> public_landing   (broad `frontend/` directory ownership)
    celery       -> app_fastapi      (broad `app/` directory ownership)
    brand_frames -> public_landing   (broad `app/api/` directory ownership)
    s_gbp        -> public_landing   (a single Graphify vote read as "dominant")
"""

from __future__ import annotations

from scripts import blueprint_derive as bd


def _rows():
    return bd.derive()["entries"]


def test_every_candidate_is_classified():
    m = bd.derive()
    assert m["total_candidates"] > 0
    for r in m["entries"]:
        assert r["classification"] in bd.CLASSIFICATIONS, r
    assert sum(m["classification_counts"].values()) == m["total_candidates"]


def test_no_candidate_is_silently_dropped():
    """Reconciler's MIGRATE_VERIFIED count must equal the derivation input."""
    m = bd.derive()
    assert m["total_candidates"] == m["reconcile_counts"]["MIGRATE_VERIFIED"]


def test_deterministic():
    a, b = bd.derive(), bd.derive()
    assert [r["legacy_id"] for r in a["entries"]] == [r["legacy_id"] for r in b["entries"]]
    assert [r["classification"] for r in a["entries"]] == [
        r["classification"] for r in b["entries"]
    ]
    assert [r["parent_domain_id"] for r in a["entries"]] == [
        r["parent_domain_id"] for r in b["entries"]
    ]


def test_entries_sorted_by_legacy_id():
    ids = [r["legacy_id"] for r in _rows()]
    assert ids == sorted(ids)


def test_proposed_domains_are_real_domains():
    from app.platform import blueprint_graph as bg

    keys = {d["key"] for d in bg.DOMAINS}
    for r in _rows():
        if r["parent_domain_id"] is not None:
            assert r["parent_domain_id"] in keys, r["legacy_id"]


def test_proposed_parent_nodes_are_real_nodes():
    from app.platform import blueprint_graph as bg

    ids = {n["id"] for n in bg.NODES}
    for r in _rows():
        if r["parent_node_id"] is not None:
            assert r["parent_node_id"] in ids, r["legacy_id"]


# ---------------------- the actual honesty gates ---------------------------
def test_high_confidence_requires_evidence_and_corroboration():
    """HIGH may never rest on AST votes alone."""
    for r in _rows():
        if r["confidence"] == "HIGH":
            assert r["evidence_files"], r["legacy_id"]
            assert r["graphify_edges_used"] >= bd.MIN_DISTINCT_EDGES, r["legacy_id"]
            assert r["corroboration"]["count"] >= 1, r["legacy_id"]
            assert max(r["domain_votes"].values()) >= bd.MIN_DOMAIN_VOTES, r["legacy_id"]


def test_structural_parent_requires_reviewed_ownership():
    """A specific parent_node_id may not be claimed from AST votes alone.

    "A uses B" is not "A belongs to B". Caught live: `s_council`
    (app/agents/llm_council.py) scored kb_rag 4-2 only because the LLM council
    READS the knowledge base, and would have been parented under the RAG node.
    """
    for r in _rows():
        if r["confidence"] == "HIGH" and r["parent_node_id"]:
            assert r["ownership_domain"], (
                r["legacy_id"],
                "structural parent without reviewed ownership",
            )


def test_council_is_not_parented_under_rag():
    """Named regression for the specific false placement that was caught."""
    for r in _rows():
        if r["legacy_id"] == "s_council":
            assert r["classification"] != "IMPORTED_CANONICAL", r
            assert r["confidence"] != "HIGH", r


def test_critical_domains_never_auto_accept_on_ast_alone():
    for r in _rows():
        if r["confidence"] == "HIGH" and r["critical_domain"]:
            assert r["corroboration"]["count"] >= 2, r["legacy_id"]


def test_only_high_confidence_is_imported():
    """Anything not HIGH must land in a review//missing bucket, never imported."""
    for r in _rows():
        if r["classification"] == "IMPORTED_CANONICAL":
            assert r["confidence"] == "HIGH", r["legacy_id"]


def test_no_candidate_without_source_evidence_is_imported():
    for r in _rows():
        if not r["evidence_files"]:
            assert r["classification"] != "IMPORTED_CANONICAL", r["legacy_id"]


def test_absolute_floor_beats_bare_ratio():
    """A single weak vote must never satisfy the auto-accept floor.

    Regression for `s_gbp -> public_landing` accepted on one Graphify vote
    because "1 vs 0" trivially satisfied a top >= 2*second ratio rule.
    """
    assert bd.MIN_DOMAIN_VOTES >= 4
    assert bd.MIN_DISTINCT_EDGES >= 2
    for r in _rows():
        if r["confidence"] == "HIGH":
            votes = max(r["domain_votes"].values())
            assert votes >= bd.MIN_DOMAIN_VOTES, (r["legacy_id"], votes)


def test_broad_directory_ownership_is_not_a_signal():
    """The derivation must not reintroduce directory-proximity mapping."""
    src = (bd.ROOT / "scripts" / "blueprint_derive.py").read_text(encoding="utf-8")
    assert "DEP_RELATIONS" in src
    # `contains` is structural nesting, not a dependency — must stay excluded
    assert "contains" not in bd.DEP_RELATIONS
    assert "rationale_for" not in bd.DEP_RELATIONS


def test_graphify_provenance_is_reported():
    p = bd.derive()["graphify"]
    for k in ("available", "built_at_commit", "repo_head", "fresh", "nodes", "links"):
        assert k in p


def test_stale_graph_cannot_be_silently_trusted():
    """If the graph is missing/stale the report must say so (no fake freshness)."""
    p = bd.derive()["graphify"]
    if p["available"] and p["built_at_commit"] and p["repo_head"]:
        assert p["fresh"] == (p["built_at_commit"][:8] == p["repo_head"][:8])
    else:
        assert p["fresh"] is False


def test_manifest_carries_no_secrets():
    import json
    import re

    blob = json.dumps(bd.derive())
    for pat in (r"sk_[A-Za-z0-9]{8,}", r"AIza[0-9A-Za-z_\-]{20,}"):
        assert not re.search(pat, blob), pat


def test_check_mode_exit_zero():
    assert bd.main(["--check"]) == 0
