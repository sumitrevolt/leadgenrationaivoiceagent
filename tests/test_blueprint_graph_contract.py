"""Contract + schema-integrity tests for the Master Project Blueprint graph.

These are the pass/fail evidence artifacts for the canonical graph (the
Agent Harness Engineering Standard's §5/§6 control-matrix + eval-gate analogue):
they lock the schema, the 9-layer / 18-domain / 11-flow shape, the honesty
rules, and the HARD-OFF cold-outbound invariant. Static — no live server.
"""

from __future__ import annotations

from pathlib import Path

from app.platform import blueprint_graph as bg

REPO = Path(__file__).resolve().parent.parent


def test_validate_graph_is_green():
    r = bg.validate_graph(strict_files=True)
    assert r["ok"], f"blueprint graph integrity errors: {r['errors']}"
    assert not r["errors"]


def test_schema_version_present():
    assert bg.SCHEMA_VERSION
    assert bg.build_graph()["schema_version"] == bg.SCHEMA_VERSION


def test_nine_layers_ids_1_to_9():
    ids = sorted(l["id"] for l in bg.LAYERS)
    assert ids == list(range(1, 10)), ids
    for l in bg.LAYERS:
        assert l["key"] and l["title"] and l["desc"]


def test_eighteen_domains():
    assert len(bg.DOMAINS) == 18
    keys = {d["key"] for d in bg.DOMAINS}
    assert len(keys) == 18  # unique
    for d in bg.DOMAINS:
        assert d["layer"] in {l["id"] for l in bg.LAYERS}


def test_flows_9_1_through_9_11():
    ids = [f["id"] for f in bg.FLOWS]
    assert ids == [f"9.{i}" for i in range(1, 12)], ids
    node_ids = {n["id"] for n in bg.NODES}
    for f in bg.FLOWS:
        assert f["steps"], f"flow {f['id']} has no steps"
        for s in f["steps"]:
            assert s in node_ids, f"flow {f['id']} step {s} not a node"


def test_no_duplicate_node_ids():
    ids = [n["id"] for n in bg.NODES]
    assert len(ids) == len(set(ids))


def test_edges_resolve_and_no_orphans():
    idset = {n["id"] for n in bg.NODES}
    deg = {i: 0 for i in idset}
    for e in bg.EDGES:
        assert e["source"] in idset and e["target"] in idset, e
        assert e["kind"] in bg.EDGE_KINDS
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    assert not [i for i, d in deg.items() if d == 0], "orphan nodes present"


def test_implemented_nodes_carry_real_file_evidence():
    implemented = {"PRODUCTION-PROVEN", "TEST-PROVEN", "CODE-PRESENT"}
    for n in bg.NODES:
        assert n["status"] in bg.EVIDENCE_LABELS, n
        if n["status"] in implemented:
            assert n["files"], f"{n['id']} implemented but no file evidence"
            for f in n["files"]:
                assert (REPO / f).exists(), f"{n['id']} file ref missing: {f}"


def test_all_layers_and_domains_have_at_least_one_node():
    covered_layers = {n["layer"] for n in bg.NODES}
    assert covered_layers == {l["id"] for l in bg.LAYERS}
    covered_domains = {n["domain"] for n in bg.NODES}
    assert covered_domains == {d["key"] for d in bg.DOMAINS}


def test_platform_dial_hard_off_invariant():
    pd = next(n for n in bg.NODES if n["id"] == "platform_dial")
    assert pd["disabled"] is True
    assert pd["status"] in ("DEPRECATED", "LEGACY")
    assert "HARD OFF" in pd["desc"]


def test_no_secret_shaped_literals_in_payload():
    import json

    blob = json.dumps(bg.build_graph())
    assert not bg._SECRET_RE.search(blob), "secret-shaped literal in graph payload"


def test_api_router_prefix_and_single_registration():
    from app.api.blueprint import router

    assert router.prefix == "/api/blueprint"
    paths = {r.path for r in router.routes}
    assert "/api/blueprint/graph" in paths
    assert "/api/blueprint/validate" in paths
    assert "/api/blueprint/meta" in paths
    main = (REPO / "app" / "main.py").read_text(encoding="utf-8")
    assert main.count("from app.api.blueprint import router") == 1
