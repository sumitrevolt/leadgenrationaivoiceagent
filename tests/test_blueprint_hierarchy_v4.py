"""v4 hierarchy + agent-harness contract tests for the Master Blueprint graph.

The blueprint is ONE canonical registry rendered at MULTIPLE depths (L0 curated
overview -> L1 domain/flow detail -> L2 implementation). These tests lock:

* the hierarchy fields exist and default safely (every pre-v4 node stays L0),
* progressive disclosure can always reach a deeper node (no unreachable detail),
* the harness control surface is present on every node and honestly Unknown
  rather than fabricated,
* edges expose the full v4 contract shape,
* none of it leaks into the sanitized public graph,
* and the new gates actually FAIL on violation (negative tests — a gate that
  cannot fail is not a gate).
"""

from __future__ import annotations

from app.platform import blueprint_graph as bg


# --------------------------- hierarchy shape ------------------------------
def test_every_node_has_valid_depth_level():
    for n in bg.NODES:
        assert n["depth_level"] in bg.DEPTH_LEVELS, (n["id"], n["depth_level"])


def test_existing_nodes_default_to_l0_visible():
    """Backward compatibility: the curated overview still loads by default."""
    for n in bg.NODES:
        if n["depth_level"] == 0:
            assert n["default_visibility"] == "visible", n["id"]
        else:
            assert n["default_visibility"] == "collapsed", n["id"]


def test_parent_domain_id_is_a_real_domain():
    keys = {d["key"] for d in bg.DOMAINS}
    for n in bg.NODES:
        assert n["parent_domain_id"] in keys, (n["id"], n["parent_domain_id"])


def test_deeper_nodes_are_reachable():
    """Reachability, per depth.

    L1 is domain/flow internals — expanding its DOMAIN reaches it, so a
    domain-rooted L1 node must NOT be forced under an L0 aggregate (inventing
    that parent is how `admin_ui -> public_landing` happened).
    L2 is concrete detail — it must resolve through a real L1/L2 group or flow.
    """
    domains = {d["key"] for d in bg.DOMAINS}
    for n in bg.NODES:
        d = n["depth_level"]
        if d == 1:
            assert (
                n.get("parent_domain_id") in domains
                or n.get("parent_flow_id")
                or n.get("parent_node_id")
            ), n["id"]
        elif d >= 2:
            assert n.get("parent_node_id") or n.get("parent_flow_id"), n["id"]


def test_source_provenance_vocabulary():
    for n in bg.NODES:
        assert n["source_provenance"] in ("canonical", "legacy-migrated", "derived")


def test_legacy_node_id_maps_at_most_one_canonical_node():
    seen: dict[str, str] = {}
    for n in bg.NODES:
        lg = n.get("legacy_node_id")
        if lg:
            assert lg not in seen, f"{lg} mapped to {seen[lg]} and {n['id']}"
            seen[lg] = n["id"]


# --------------------------- harness surface ------------------------------
def test_every_node_exposes_the_harness_control_surface():
    for n in bg.NODES:
        for f in bg.HARNESS_CONTROL_FIELDS:
            assert f in n, f"{n['id']} missing harness field {f}"


def test_harness_controls_are_unknown_not_fabricated():
    """A control we have not represented yet must be None — never a default
    'True'/'yes' that would read as "this control exists"."""
    for n in bg.NODES:
        for f in bg.HARNESS_CONTROL_FIELDS:
            v = n[f]
            assert v is None or isinstance(v, (str, int, list, dict)), (n["id"], f, v)
            assert v is not True, f"{n['id']}.{f} fabricates a control"


def test_safety_lane_vocabulary():
    for n in bg.NODES:
        assert n.get("safety_lane") in (None, "GREEN", "AMBER", "RED")


# --------------------------- edge contract --------------------------------
def test_normalized_edges_carry_full_contract():
    g = bg.build_graph()
    for e in g["edges"]:
        assert e["source"] and e["target"] and e["kind"]
        for f in bg.EDGE_CONTRACT_FIELDS:
            assert f in e, f"edge {e['source']}->{e['target']} missing {f}"


def test_normalize_edge_is_backward_compatible():
    raw = {"source": "a", "target": "b", "kind": "flow"}
    out = bg.normalize_edge(raw)
    assert out["source"] == "a" and out["target"] == "b" and out["kind"] == "flow"
    assert out["condition"] is None and out["on_failure"] is None


# --------------------------- payload + isolation --------------------------
def test_build_graph_advertises_the_new_contract():
    g = bg.build_graph()
    assert g["harness_fields"] == list(bg.HARNESS_CONTROL_FIELDS)
    assert g["edge_fields"] == list(bg.EDGE_CONTRACT_FIELDS)
    assert g["depth_levels"] == list(bg.DEPTH_LEVELS)


def test_public_graph_leaks_no_hierarchy_or_harness_internals():
    pub = bg.build_public_graph()
    forbidden = set(bg.HARNESS_CONTROL_FIELDS) | {
        "legacy_node_id",
        "parent_node_id",
        "source_provenance",
        "files",
        "flags",
    }
    for n in pub["nodes"]:
        assert not (set(n) & forbidden), f"public node leaks {set(n) & forbidden}"


def test_build_graph_is_deterministic():
    a, b = bg.build_graph(), bg.build_graph()
    assert [n["id"] for n in a["nodes"]] == [n["id"] for n in b["nodes"]]
    assert a["edges"] == b["edges"]


def test_v4_did_not_change_the_curated_overview():
    """One Fix, Zero Regressions: the owner-facing L0 map is untouched."""
    c = bg.build_graph()["counts"]
    # Total may grow as verified detail is migrated; the DEFAULT projection
    # (L0) must stay exactly the curated owner-facing map.
    assert c["l0"] == 50 and c["edges"] == 56
    assert c["nodes"] == c["l0"] + c["l1"] + c["l2"]
    assert c["layers"] == 9 and c["domains"] == 18 and c["flows"] == 11
    assert bg.validate_graph(strict_files=False)["ok"]


# --------------------------- negative gates -------------------------------
def _base_node(**extra):
    return bg._n(
        "tmp_probe",
        "Probe",
        1,
        "observability_ops",
        "platform",
        "CODE-PRESENT",
        ["app/platform/blueprint_graph.py"],
        "probe",
        **extra,
    )


def _errors(monkeypatch, nodes):
    monkeypatch.setattr(bg, "NODES", nodes)
    monkeypatch.setattr(bg, "EDGES", [])
    monkeypatch.setattr(bg, "FLOWS", [])
    return bg.validate_graph(strict_files=False)["errors"]


def test_gate_rejects_unparented_l2_detail(monkeypatch):
    """L2 detail with no group/flow parent is unreachable — must fail."""
    errs = _errors(monkeypatch, [_base_node(depth_level=2)])
    assert any("L2 detail" in e and "unreachable" in e for e in errs), errs


def test_gate_allows_domain_rooted_l1(monkeypatch):
    """An L1 node rooted on its DOMAIN is legitimate — no fabricated L0 parent.

    Regression for the false-mapping class (`admin_ui -> public_landing`) that
    a "must have parent_node_id" rule would have forced us to invent.
    """
    n = _base_node(depth_level=1)
    assert n["parent_domain_id"] == "observability_ops"
    assert n["parent_node_id"] is None
    errs = _errors(monkeypatch, [n])
    assert not any("unreachable" in e for e in errs), errs


def test_gate_still_rejects_l1_with_bogus_domain(monkeypatch):
    bad = _base_node(depth_level=1)
    bad["parent_domain_id"] = "not_a_domain"
    errs = _errors(monkeypatch, [bad])
    assert any("bad parent_domain_id" in e for e in errs), errs


def test_gate_rejects_self_parent(monkeypatch):
    errs = _errors(monkeypatch, [_base_node(parent_node_id="tmp_probe")])
    assert any("points at itself" in e for e in errs), errs


def test_gate_rejects_duplicate_legacy_mapping(monkeypatch):
    a = _base_node(legacy_node_id="crm_sync")
    b = dict(a)
    b["id"] = "tmp_probe_2"
    errs = _errors(monkeypatch, [a, b])
    assert any("already mapped to" in e for e in errs), errs


def test_gate_rejects_bad_depth_and_visibility(monkeypatch):
    bad = _base_node()
    bad["depth_level"] = 9
    bad["default_visibility"] = "sometimes"
    errs = _errors(monkeypatch, [bad])
    assert any("bad depth_level" in e for e in errs), errs
    assert any("bad default_visibility" in e for e in errs), errs


def test_gate_rejects_parent_cycle(monkeypatch):
    a = _base_node(parent_node_id="tmp_probe_2")
    b = dict(a)
    b["id"] = "tmp_probe_2"
    b["parent_node_id"] = "tmp_probe"
    errs = _errors(monkeypatch, [a, b])
    assert any("cycle" in e for e in errs), errs


def test_gate_rejects_unknown_parent_node(monkeypatch):
    errs = _errors(monkeypatch, [_base_node(depth_level=1, parent_node_id="nope")])
    assert any("parent_node_id nope is not a node" in e for e in errs), errs
