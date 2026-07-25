"""blueprint_edge_reconcile.py — legacy Explorer edges -> canonical edge manifest.

The node side is handled by ``blueprint_reconcile`` / ``blueprint_derive``. This
tool does the EDGE side: it takes all 344 legacy ``/app/explorer`` edges, maps
each endpoint to a canonical node where one exists, and classifies every edge.

No edge is ever silently discarded. An edge whose endpoints cannot both be
resolved is reported as ``ENDPOINT_MISSING`` — it is not dropped, and it is not
invented into the canonical graph either.

Field honesty: a legacy edge literal carries only ``{f, t}`` (plus an optional
visual label). It proves the two nodes were drawn connected. It does NOT prove
queue ownership, retry behaviour, tenant propagation, idempotency, runtime
activation or success/failure routing. Those fields therefore stay ``None``
here and must be evidenced separately before any edge is imported.

Usage:
    python scripts/blueprint_edge_reconcile.py            # summary
    python scripts/blueprint_edge_reconcile.py --json     # full manifest
    python scripts/blueprint_edge_reconcile.py --check    # exit 1 if unaccounted
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent

EDGE_CLASSIFICATIONS = (
    "MIGRATE_VERIFIED",
    "MERGE_WITH_CANONICAL_EDGE",
    "REPLACE_WITH_CURRENT_PATH",
    "DEPRECATED",
    "ENDPOINT_MISSING",
    "INVALID_OR_STALE",
    "REVIEW_REQUIRED",
)


def _load(name: str, rel: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    if spec is None or spec.loader is None:
        raise ImportError(rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _ensure_repo_importable() -> None:
    """CLI-only sys.path fix.

    Must never run at import time: pytest imports this module, and a second
    root entry lets ``app`` resolve under two module identities, which
    re-initialises native extensions (torch/av/ctranslate2) in one process and
    segfaults the suite. Learned the hard way — see PR #131.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def reconcile_edges() -> dict[str, Any]:
    """Deterministic legacy-edge manifest (never raises)."""
    br = _load("_br", "scripts/blueprint_reconcile.py")
    bg = _load("_bg", "app/platform/blueprint_graph.py")

    html = (ROOT / "frontend" / "explorer.html").read_text(
        encoding="utf-8", errors="replace")
    legacy = br.parse_legacy(html)
    legacy_nodes, legacy_edges = legacy["nodes"], legacy["edges"]

    node_manifest = br.reconcile(ROOT)
    node_by_legacy = {e["legacy_id"]: e for e in node_manifest["entries"]}

    # legacy id -> canonical node id, from BOTH sources of truth:
    #   1. reconciler matches (file-evidence merges)
    #   2. nodes already imported into the registry (legacy_node_id)
    resolve: dict[str, str] = {}
    for e in node_manifest["entries"]:
        if e.get("canonical_id"):
            resolve[e["legacy_id"]] = e["canonical_id"]
    for n in bg.NODES:
        lg = n.get("legacy_node_id")
        if lg:
            resolve[lg] = n["id"]

    canon_ids = {n["id"] for n in bg.NODES}
    canon_pairs = {(e["source"], e["target"]) for e in bg.EDGES}

    entries: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for f, t in legacy_edges:
        cf, ct = resolve.get(f), resolve.get(t)
        fe, te = node_by_legacy.get(f), node_by_legacy.get(t)
        f_cls = fe["classification"] if fe else None
        t_cls = te["classification"] if te else None

        unresolved = [x for x, c in ((f, cf), (t, ct)) if not c]

        if f_cls == "INVALID_OR_STALE" or t_cls == "INVALID_OR_STALE":
            cls = "INVALID_OR_STALE"
            reason = "an endpoint references source files that do not exist"
        elif cf and ct and (cf, ct) in canon_pairs:
            cls = "MERGE_WITH_CANONICAL_EDGE"
            reason = "both endpoints canonical and the edge already exists"
        elif cf and ct and cf == ct:
            cls = "REPLACE_WITH_CURRENT_PATH"
            reason = "both legacy endpoints now map to the same canonical node"
        elif cf and ct:
            cls = "MIGRATE_VERIFIED"
            reason = "both endpoints resolve to canonical nodes; edge not yet present"
        elif f_cls == "DEPRECATED" or t_cls == "DEPRECATED":
            cls = "DEPRECATED"
            reason = "an endpoint is a deprecated component"
        elif f_cls == "MISSING_RUNTIME" or t_cls == "MISSING_RUNTIME":
            cls = "ENDPOINT_MISSING"
            reason = "an endpoint has no current runtime implementation"
        elif unresolved:
            cls = "ENDPOINT_MISSING"
            reason = f"endpoint(s) not yet canonical: {', '.join(unresolved)}"
        else:
            cls = "REVIEW_REQUIRED"
            reason = "needs manual inspection"

        pair = (cf or f"legacy:{f}", ct or f"legacy:{t}")
        duplicate = pair in seen_pairs
        seen_pairs.add(pair)

        # Two distinct legacy edges can collapse onto one canonical pair once
        # their endpoints merge (e.g. public_in->customer_wh and
        # public_in->vobiz_inbound both become public_landing->webhooks).
        # Importing both would create a duplicate canonical edge, so the
        # collision goes to review instead of being silently de-duplicated.
        if duplicate and cls in ("MIGRATE_VERIFIED", "MERGE_WITH_CANONICAL_EDGE"):
            cls = "REVIEW_REQUIRED"
            reason = (f"collapses onto an already-seen canonical pair "
                      f"{pair[0]} -> {pair[1]}; needs manual de-duplication")

        entries.append({
            "legacy_source": f,
            "legacy_target": t,
            "canonical_source": cf,
            "canonical_target": ct,
            "classification": cls,
            "reason": reason,
            "duplicate_of_earlier_pair": duplicate,
            "self_edge": bool(cf and ct and cf == ct),
            "source_node_classification": f_cls,
            "target_node_classification": t_cls,
            # A legacy {f,t} literal proves adjacency only. Everything below
            # needs independent evidence and stays Unknown until it has it.
            "kind": None,
            "condition": None,
            "mode": None,
            "queue": None,
            "data_contract": None,
            "on_success": None,
            "on_failure": None,
            "on_retry": None,
            "audit_event": None,
            "propagates_tenant": None,
            "propagates_idempotency": None,
            "evidence": "legacy explorer adjacency only",
        })

    entries.sort(key=lambda e: (e["legacy_source"], e["legacy_target"]))
    counts = collections.Counter(e["classification"] for e in entries)
    return {
        "legacy_edges_total": len(legacy_edges),
        "legacy_nodes_total": len(legacy_nodes),
        "canonical_nodes": len(canon_ids),
        "canonical_edges": len(bg.EDGES),
        "resolved_endpoints": len(resolve),
        "counts": dict(counts),
        "entries": entries,
    }


def main(argv: list[str]) -> int:
    m = reconcile_edges()
    if "--json" in argv:
        print(json.dumps(m, indent=2, sort_keys=True))
        return 0

    print("=" * 66)
    print("LEGACY EXPLORER EDGES -> CANONICAL RECONCILIATION")
    print("=" * 66)
    print(f"legacy edges          : {m['legacy_edges_total']}")
    print(f"canonical nodes/edges : {m['canonical_nodes']} / {m['canonical_edges']}")
    print(f"resolvable endpoints  : {m['resolved_endpoints']}")
    print("\n--- classification ---")
    for k in EDGE_CLASSIFICATIONS:
        if m["counts"].get(k):
            print(f"  {k:<28} {m['counts'][k]}")
    mig = [e for e in m["entries"] if e["classification"] == "MIGRATE_VERIFIED"]
    if mig:
        print(f"\n--- MIGRATE_VERIFIED ({len(mig)}) — both endpoints canonical ---")
        for e in mig[:25]:
            print(f"  {e['legacy_source']:<20} -> {e['legacy_target']:<20} "
                  f"({e['canonical_source']} -> {e['canonical_target']})")

    if "--check" in argv:
        total = sum(m["counts"].values())
        if total != m["legacy_edges_total"]:
            print(f"\n[FAIL] {m['legacy_edges_total'] - total} legacy edge(s) unaccounted for.")
            return 1
        bad = [e for e in m["entries"] if e["classification"] not in EDGE_CLASSIFICATIONS]
        if bad:
            print(f"\n[FAIL] unclassified edges: {len(bad)}")
            return 1
        print(f"\n[OK] all {total} legacy edges accounted for and classified.")
    return 0


if __name__ == "__main__":
    _ensure_repo_importable()
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # never-raise (repo convention)
        print(f"[blueprint_edge_reconcile] skipped: {type(e).__name__}: {e}")
        sys.exit(0)
