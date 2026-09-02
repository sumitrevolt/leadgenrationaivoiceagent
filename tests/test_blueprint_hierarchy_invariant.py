"""Master Blueprint hierarchy invariant — how detail nodes are ROOTED.

WHY THIS EXISTS (2026-08-03): an agent audit reported the nine ``detail_*`` nodes
as "orphans needing wiring" because they carry no graph EDGE. That reading was
wrong, and acting on it would have corrupted the blueprint.

The hierarchy is not expressed by edges. It is expressed by two fields:

* ``depth_level == 1`` -> the node is rooted on its DOMAIN. It must carry a real
  domain and must NOT carry a parent. ``blueprint_detail_nodes.py`` states the
  reason explicitly for ``detail_stt_tts``: parenting an L1 onto an L0 curated
  aggregate would skip the domain/flow layer, and inventing an L1 group purely
  to satisfy a validator "would be fabrication".
* ``depth_level == 2`` -> the node hangs off a real L1 parent in the SAME domain
  (today: ``detail_agentic_rag`` -> ``detail_kb_rag``).

So "no parent" on an L1 node is the RULE, not a defect. This test pins that rule
so the next reader — human or agent — cannot quietly "fix" it by fabricating
parents, and so a genuine violation (an L2 with no parent, or a parent in the
wrong domain) fails loudly instead.
"""

from __future__ import annotations

from app.platform import blueprint_graph as B


def _nodes():
    return B.build_graph()["nodes"]


def _by_id():
    return {str(n.get("id")): n for n in _nodes()}


def test_graph_validates_against_the_real_checkout():
    """The canonical registry itself must be coherent."""
    v = B.validate_graph(strict_files=True)
    assert v.get("ok") is True, v.get("errors")
    assert not v.get("errors"), v.get("errors")


def test_depth_level_1_is_domain_rooted_and_never_parented():
    """L1 = rooted on its domain. A parent here would skip the domain layer."""
    index = _by_id()
    offenders_parent = []
    offenders_domain = []
    for n in _nodes():
        if n.get("depth_level") != 1:
            continue
        nid = str(n.get("id"))
        if n.get("parent_node_id"):
            offenders_parent.append(nid)
        if not str(n.get("domain") or "").strip():
            offenders_domain.append(nid)
    assert not offenders_parent, f"L1 nodes must not be parented: {offenders_parent}"
    assert not offenders_domain, f"L1 nodes must carry a domain: {offenders_domain}"
    assert index, "graph must not be empty"


def test_depth_level_2_hangs_off_a_real_parent_in_the_same_domain():
    """L2 = parented. The parent must exist AND share the domain."""
    index = _by_id()
    missing = []
    unknown = []
    cross_domain = []
    for n in _nodes():
        if n.get("depth_level") != 2:
            continue
        nid = str(n.get("id"))
        pid = str(n.get("parent_node_id") or "")
        if not pid:
            missing.append(nid)
            continue
        parent = index.get(pid)
        if parent is None:
            unknown.append((nid, pid))
            continue
        if str(parent.get("domain")) != str(n.get("domain")):
            cross_domain.append((nid, pid))
    assert not missing, f"L2 nodes must declare a parent: {missing}"
    assert not unknown, f"L2 parent must be a real node: {unknown}"
    assert not cross_domain, f"L2 parent must share the domain: {cross_domain}"


def test_every_edge_endpoint_is_a_declared_node():
    """Edges may not point at nodes that do not exist."""
    ids = set(_by_id())
    dangling = set()
    for e in B.build_graph()["edges"]:
        ne = B.normalize_edge(e)
        for key in ("source", "from", "target", "to"):
            val = str(ne.get(key) or "")
            if val and val not in ids:
                dangling.add(val)
    assert not dangling, f"edges reference unknown nodes: {sorted(dangling)}"


def test_detail_domains_are_real_not_invented():
    """A domain-rooted node is only rooted if the domain actually exists.

    Guards the failure mode this file was written against: parking a node on a
    private one-off domain looks structured but roots it on nothing.
    """
    nodes = _nodes()
    by_domain: dict[str, list[str]] = {}
    for n in nodes:
        by_domain.setdefault(str(n.get("domain")), []).append(str(n.get("id")))

    lonely = []
    for n in nodes:
        nid = str(n.get("id"))
        if not nid.startswith("detail_"):
            continue
        siblings = [x for x in by_domain.get(str(n.get("domain")), []) if x != nid]
        if not siblings:
            lonely.append((nid, n.get("domain")))
    assert not lonely, f"detail nodes rooted on a domain with no other member: {lonely}"
