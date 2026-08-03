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
    # Orphan rule is an L0 rule. L1/L2 detail nodes are reached by hierarchy
    # (domain / flow / group expansion), not by overview edges — demanding an
    # edge here would force fabricated connections. Their reachability is
    # proven by the depth gates in validate_graph().
    depth = {n["id"]: n.get("depth_level", 0) for n in bg.NODES}
    orphans = [i for i, d in deg.items() if d == 0 and depth.get(i, 0) == 0]
    assert not orphans, f"orphan L0 nodes present: {orphans}"


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


def test_platform_dial_full_campaign_live_invariant():
    pd = next(n for n in bg.NODES if n["id"] == "platform_dial")
    assert pd["disabled"] is False
    assert pd["status"] == "PRODUCTION-PROVEN"
    assert "FULL CAMPAIGN LIVE" in pd["desc"]


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
    assert "/api/blueprint/public" in paths
    assert "/api/blueprint/trace" in paths
    main = (REPO / "app" / "main.py").read_text(encoding="utf-8")
    assert main.count("from app.api.blueprint import router") == 1


# --- P0: workforce truth (registry-derived, no drift) ---------------------
def test_workforce_matches_canonical_registry_not_hardcoded():
    from app.platform.team import STAFF

    wf = bg._workforce()
    assert wf["source"] == "registry"
    assert wf["count"] == len(STAFF)  # fails on drift — the whole point
    g = bg.build_graph()
    assert g["workforce"]["count"] == len(STAFF)
    assert g["counts"]["workforce"] == len(STAFF)
    roster = next(n for n in g["nodes"] if n["id"] == "team_roster")
    assert roster["workforce"]["count"] == len(STAFF)
    assert wf["includes_manager"] is True  # Boss/manager is IN the 31, not a 32nd


def test_no_stale_18_ai_staff_anywhere():
    import json

    blob = json.dumps(bg.build_graph()) + json.dumps(bg.build_public_graph())
    assert "18 AI staff" not in blob
    # validator also refuses it
    assert bg.validate_graph()["ok"]


# --- P1: multi-hop traversal (cycle-safe, deterministic) ------------------
def test_shortest_path_linear_and_edges():
    p = bg.shortest_path("prospector", "hot_queue")
    assert p and p[0] == "prospector" and p[-1] == "hot_queue"
    # every consecutive pair is a real directed edge
    edges = {(e["source"], e["target"]) for e in bg.EDGES}
    assert all((p[i], p[i + 1]) in edges for i in range(len(p) - 1))


def test_shortest_path_same_missing_and_none():
    assert bg.shortest_path("subscription", "subscription") == ["subscription"]
    assert bg.shortest_path("nope_missing", "subscription") == []
    assert bg.shortest_path("qdrant", "prospector") == []  # no directed path back


def test_traverse_deterministic_bounded_cycle_safe():
    a = bg.traverse("scheduler", "down", 3)
    b = bg.traverse("scheduler", "down", 3)
    assert a == b  # deterministic
    assert "scheduler" not in a  # excludes start
    assert bg.traverse("app_fastapi", "both", 0) == []  # depth 0
    # bounded even with generous depth (no runaway on cycles)
    assert len(bg.traverse("app_fastapi", "both", 99)) <= len(bg.NODES)


def test_impact_is_downstream_only():
    imp = bg.impact("scheduler", 3)
    assert "staff_jobs" in imp and "auto_outreach" in imp


# --- P0: sanitized public contract (no internal leakage) ------------------
def test_public_graph_has_no_sensitive_metadata():
    import json

    pub = bg.build_public_graph()
    assert pub["visibility"] == "public"
    for n in pub["nodes"]:
        assert set(n.keys()) == {"id", "title", "layer", "domain", "state", "disabled"}
        assert n["state"] in {"live", "building", "planned", "off"}
    blob = json.dumps(pub)
    for leak_key in ('"files"', '"flags"', '"runtime"', '"tech_refs"', '"desc"', '"io"'):
        assert leak_key not in blob, f"public payload leaks field: {leak_key}"
    # sensitive = file paths, module refs, infra addresses/ports (NOT display
    # product names in titles, which a public architecture overview may show).
    for infra in ("app/", ".py", ".yml", "127.0.0.1", ":6432", ":6333", "8080", "docker-compose"):
        assert infra not in blob, f"public payload leaks infra: {infra}"
    # FULL CAMPAIGN LIVE node surfaces as live, not a granular DEPRECATED label
    pd = next(n for n in pub["nodes"] if n["id"] == "platform_dial")
    assert pd["state"] == "live"


# --- P1: schema expansion present -----------------------------------------
def test_schema_expansion_fields_present():
    for k in ("routes_to", "triggers", "depends_on"):
        assert k in bg.EDGE_KINDS
    g = bg.build_graph()
    assert "node_fields" in g and "edge_types" in g and "workforce" in g
    roster = next(n for n in g["nodes"] if n["id"] == "team_roster")
    for f in ("io", "process", "triggers", "feedback_loop", "tech_refs"):
        assert f in roster


# --- workforce degraded mode (Unknown-stays-Unknown, no fabrication) -------
def test_workforce_degraded_is_unknown_not_fabricated(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "app.platform.team", None)  # force ImportError
    wf = bg._workforce()
    assert wf["count"] is None  # NOT 31
    assert wf["includes_manager"] is None
    assert wf["by_product"] == {}
    assert wf["source"] == "unavailable"


def test_validate_degraded_workforce_warns_not_crash(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "app.platform.team", None)
    v = bg.validate_graph(strict_files=False)
    assert v["ok"], v["errors"]  # structural integrity independent of registry
    assert v["counts"]["workforce"] is None  # no fabricated number
    assert any("workforce truth degraded" in w for w in v["warnings"])


def test_no_fabricated_fallback_constant():
    # the old _CANONICAL_STAFF_FALLBACK=31 must be gone
    assert not hasattr(bg, "_CANONICAL_STAFF_FALLBACK")


# --- v3 semantic schema (roles + edge semantics + field contract) ----------
def test_all_nodes_have_valid_semantic_role():
    g = bg.build_graph()
    assert "node_roles" in g
    for n in bg.NODES:
        assert n["role"] in bg.NODE_ROLES, f"{n['id']} bad role {n['role']}"


def test_edge_kinds_cover_agreed_semantics():
    agreed = (
        "calls",
        "routes_to",
        "queues",
        "consumes",
        "produces",
        "reads",
        "writes",
        "stores",
        "publishes",
        "approves",
        "rejects",
        "blocks",
        "retries",
        "monitors",
        "alerts",
        "authenticates",
        "authorizes",
        "provisions",
        "invoices",
        "deploys",
        "rolls_back",
        "synchronizes",
        "resolves_identity",
        "emits",
        "triggers",
    )
    for k in agreed:
        assert k in bg.EDGE_KINDS, f"missing edge semantic {k}"
    for e in bg.EDGES:
        assert e["kind"] in bg.EDGE_KINDS


def test_v3_contract_fields_present_and_honest():
    required_fields = {
        "role",
        "implementation_status",
        "runtime_status",
        "lifecycle_status",
        "module",
        "service",
        "route",
        "job",
        "queue",
        "datastore",
        "provider",
        "feature_flags",
        "inputs",
        "outputs",
        "guards",
        "approvals",
        "tenant_scope",
        "retry_policy",
        "failure_path",
        "source_evidence",
        "admin_links",
        "customer_links",
        "documentation_links",
        "production_evidence",
        "last_verified_at",
        "tags",
    }
    g = bg.build_graph()
    for n in g["nodes"]:
        assert required_fields.issubset(n.keys()), f"{n['id']} missing v3 fields"
        assert n["runtime_status"] is None  # runtime NEVER fabricated in the static graph
        assert n["lifecycle_status"] in (None, "active", "preview", "deprecated")
        assert n["implementation_status"] == n["status"]
    # visual type preserved (FE not broken)
    for n in bg.NODES:
        assert n["type"] in bg.NODE_TYPES
    # active lifecycle for the FULL CAMPAIGN LIVE node
    pd = next(n for n in bg.NODES if n["id"] == "platform_dial")
    assert pd["lifecycle_status"] == "active"
