"""blueprint_edge_reconcile.py — legacy Explorer edges -> canonical edge manifest.

The node side is handled by ``blueprint_reconcile`` / ``blueprint_derive``. This
tool does the EDGE side: it takes every legacy ``/app/explorer`` edge literal,
maps each endpoint to a canonical node where one exists, and classifies the edge.
No edge is ever silently discarded or silently de-duplicated.

EDGE ACCOUNTING (measured on the current explorer.html, not assumed)
--------------------------------------------------------------------
``raw_edge_literals``        every ``{f:'..',t:'..'}`` literal            = 345
``unique_legacy_pairs``      distinct (source, target) pairs              = 341
``exact_duplicate_literals`` repeated literals of an identical pair       =   4
                             (worker->prospect, worker->self_improve,
                              ops->launch, pipeline_ops->events)
Invariants: ``unique_legacy_pairs + exact_duplicate_literals == raw_edge_literals``
and ``accounted_entries == raw_edge_literals``.

``canonical_pair_collisions`` is a DIFFERENT thing: distinct legacy pairs that
collapse onto one canonical pair once their endpoints merge. It is counted and
reported separately and never conflated with exact duplicate literals.

WHAT A LEGACY EDGE PROVES
-------------------------
A legacy literal is ``{f, t}``. It proves the two boxes were drawn connected.
It proves NOTHING about kind, routing condition, sync/async, queue/topic, data
contract, success/failure/retry path, audit event, tenant propagation,
idempotency propagation or runtime activation. Hence
``ENDPOINTS_RESOLVED_REVIEW_REQUIRED``: the endpoint mapping is verified, the
edge contract is not. Nothing here is eligible for import.

FAIL-CLOSED
-----------
A dev tool that cannot read its own inputs must never report success. Parser or
canonical-graph failures produce ``ok=False`` with errors, and the CLI exits
non-zero in both ``--check`` and summary mode.

Usage:
    python scripts/blueprint_edge_reconcile.py            # summary
    python scripts/blueprint_edge_reconcile.py --json     # full manifest
    python scripts/blueprint_edge_reconcile.py --check    # exit 1 if unaccounted
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent

EDGE_CLASSIFICATIONS = (
    "ENDPOINTS_RESOLVED_REVIEW_REQUIRED",
    "MERGE_WITH_CANONICAL_EDGE",
    "REPLACE_WITH_CURRENT_PATH",
    "DEPRECATED",
    "ENDPOINT_MISSING",
    "INVALID_OR_STALE",
    "REVIEW_REQUIRED",
)

# No classification is importable yet: none of them carries edge-contract
# evidence. Kept explicit so a future slice must consciously change it.
IMPORTABLE_CLASSIFICATIONS: tuple[str, ...] = ()

_CONTRACT_FIELDS = (
    "kind",
    "condition",
    "mode",
    "queue",
    "data_contract",
    "on_success",
    "on_failure",
    "on_retry",
    "audit_event",
    "propagates_tenant",
    "propagates_idempotency",
)


def _load(name: str, rel: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {rel}")
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


def _fail(errors: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "errors": errors,
        "raw_edge_literals": 0,
        "unique_legacy_pairs": 0,
        "exact_duplicate_literals": 0,
        "canonical_pair_collisions": 0,
        "accounted_entries": 0,
        "counts": {},
        "entries": [],
    }


def reconcile_edges() -> dict[str, Any]:
    """Deterministic legacy-edge manifest. Returns ok=False on fatal input errors."""
    errors: list[str] = []

    explorer = ROOT / "frontend" / "explorer.html"
    if not explorer.exists():
        return _fail([f"legacy explorer not found: {explorer}"])

    try:
        br = _load("_br", "scripts/blueprint_reconcile.py")
        bg = _load("_bg", "app/platform/blueprint_graph.py")
    except Exception as e:
        return _fail([f"canonical graph/reconciler import failed: {type(e).__name__}: {e}"])

    try:
        html = explorer.read_text(encoding="utf-8", errors="replace")
        legacy = br.parse_legacy(html)
        legacy_edges = list(legacy["edges"])
        node_manifest = br.reconcile(ROOT)
    except Exception as e:
        return _fail([f"legacy parse/reconcile failed: {type(e).__name__}: {e}"])

    # Independent recount straight from the source text — if the structured
    # parser ever drifts from the raw literals we want that to be loud.
    raw_literals = len(re.findall(r"\{f:'[\w]+',\s*t:'[\w]+'", html))
    if raw_literals != len(legacy_edges):
        errors.append(
            f"parser drift: {len(legacy_edges)} parsed edges vs {raw_literals} raw literals"
        )

    pair_counts = collections.Counter(legacy_edges)
    unique_pairs = len(pair_counts)
    exact_dupes = len(legacy_edges) - unique_pairs
    if unique_pairs + exact_dupes != len(legacy_edges):
        errors.append("duplicate accounting invariant violated")

    node_by_legacy = {e["legacy_id"]: e for e in node_manifest["entries"]}

    # legacy id -> canonical node id, from BOTH sources of truth:
    #   1. reconciler file-evidence matches
    #   2. nodes already imported into the registry (legacy_node_id)
    resolve: dict[str, str] = {}
    for e in node_manifest["entries"]:
        if e.get("canonical_id"):
            resolve[e["legacy_id"]] = e["canonical_id"]
    for n in bg.NODES:
        lg = n.get("legacy_node_id")
        if lg:
            resolve[lg] = n["id"]

    canon_pairs = {(e["source"], e["target"]) for e in bg.EDGES}

    # Pre-compute canonical collapse groups so collisions get a deterministic
    # identifier rather than "whichever we saw first wins".
    canon_group: dict[tuple[str, str], list[tuple[str, str]]] = collections.defaultdict(list)
    for f, t in sorted(set(legacy_edges)):
        cf, ct = resolve.get(f), resolve.get(t)
        if cf and ct:
            canon_group[(cf, ct)].append((f, t))
    collisions = {k: v for k, v in canon_group.items() if len(v) > 1}

    seen_literal: collections.Counter = collections.Counter()
    entries: list[dict[str, Any]] = []

    for f, t in sorted(legacy_edges):
        seen_literal[(f, t)] += 1
        occurrence = seen_literal[(f, t)]
        is_exact_duplicate = occurrence > 1

        cf, ct = resolve.get(f), resolve.get(t)
        fe, te = node_by_legacy.get(f), node_by_legacy.get(t)
        f_cls = fe["classification"] if fe else None
        t_cls = te["classification"] if te else None
        unresolved = [x for x, c in ((f, cf), (t, ct)) if not c]

        canonical_pair = (cf, ct) if (cf and ct) else None
        pair_exists = bool(canonical_pair and canonical_pair in canon_pairs)
        collision_id = (
            (f"{cf}->{ct}" if canonical_pair in collisions else None) if canonical_pair else None
        )

        if f_cls == "INVALID_OR_STALE" or t_cls == "INVALID_OR_STALE":
            cls = "INVALID_OR_STALE"
            reason = "an endpoint references source files that do not exist"
        elif is_exact_duplicate:
            cls = "REVIEW_REQUIRED"
            reason = (
                f"exact duplicate legacy literal (occurrence {occurrence}); "
                "first occurrence retained for accounting"
            )
        elif collision_id:
            cls = "REVIEW_REQUIRED"
            reason = (
                f"canonical collapse collision {collision_id}: "
                f"{len(collisions[canonical_pair])} distinct legacy pairs map here"
            )
        elif pair_exists:
            cls = "MERGE_WITH_CANONICAL_EDGE"
            reason = "canonical pair already present (contract equivalence unverified)"
        elif cf and ct and cf == ct:
            cls = "REPLACE_WITH_CURRENT_PATH"
            reason = "both legacy endpoints now map to the same canonical node"
        elif cf and ct:
            cls = "ENDPOINTS_RESOLVED_REVIEW_REQUIRED"
            reason = "endpoint mapping verified; edge runtime contract NOT verified"
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

        entry: dict[str, Any] = {
            "legacy_source": f,
            "legacy_target": t,
            "literal_occurrence": occurrence,
            "exact_duplicate_literal": is_exact_duplicate,
            "canonical_source": cf,
            "canonical_target": ct,
            "canonical_pair_exists": pair_exists,
            "contract_equivalence": "UNVERIFIED" if pair_exists else None,
            "canonical_collision_id": collision_id,
            "classification": cls,
            "reason": reason,
            "self_edge": bool(cf and ct and cf == ct),
            "source_node_classification": f_cls,
            "target_node_classification": t_cls,
            # explicit honesty about what IS and IS NOT verified
            "endpoint_resolution": "VERIFIED" if (cf and ct) else "UNRESOLVED",
            "contract_status": "UNVERIFIED",
            "evidence_level": "LEGACY_ADJACENCY_ONLY",
            "eligible_for_import": False,
            "imported": False,
        }
        for cfield in _CONTRACT_FIELDS:
            entry[cfield] = None
        entries.append(entry)

    counts = collections.Counter(e["classification"] for e in entries)
    accounted = len(entries)

    if accounted != len(legacy_edges):
        errors.append(f"accounted {accounted} != raw literals {len(legacy_edges)}")
    if sum(counts.values()) != accounted:
        errors.append("classification counts do not sum to accounted entries")
    for e in entries:
        if e["classification"] not in EDGE_CLASSIFICATIONS:
            errors.append(f"unknown classification {e['classification']}")
            break

    return {
        "ok": not errors,
        "errors": errors,
        "raw_edge_literals": len(legacy_edges),
        "unique_legacy_pairs": unique_pairs,
        "exact_duplicate_literals": exact_dupes,
        "canonical_pair_collisions": len(collisions),
        "accounted_entries": accounted,
        "canonical_nodes": len(bg.NODES),
        "canonical_edges": len(bg.EDGES),
        "resolved_endpoints": len(resolve),
        "counts": dict(counts),
        "entries": entries,
    }


def main(argv: list[str]) -> int:
    m = reconcile_edges()

    if "--json" in argv:
        print(json.dumps(m, indent=2, sort_keys=True))
        return 0 if m["ok"] else 1

    print("=" * 68)
    print("LEGACY EXPLORER EDGES -> CANONICAL RECONCILIATION")
    print("=" * 68)
    if not m["ok"]:
        print("[FAIL] reconciliation could not complete:")
        for e in m["errors"]:
            print(f"   - {e}")
        return 1

    print(f"raw_edge_literals        : {m['raw_edge_literals']}")
    print(f"unique_legacy_pairs      : {m['unique_legacy_pairs']}")
    print(f"exact_duplicate_literals : {m['exact_duplicate_literals']}")
    print(f"canonical_pair_collisions: {m['canonical_pair_collisions']}  (distinct concept)")
    print(f"accounted_entries        : {m['accounted_entries']}")
    print(f"canonical nodes/edges    : {m['canonical_nodes']} / {m['canonical_edges']}")
    print("\n--- classification ---")
    for k in EDGE_CLASSIFICATIONS:
        if m["counts"].get(k):
            print(f"  {k:<36} {m['counts'][k]}")
    print(
        f"\nedges eligible for import: "
        f"{sum(1 for e in m['entries'] if e['eligible_for_import'])} "
        "(adjacency alone is not an edge contract)"
    )

    if "--check" in argv:
        if m["unique_legacy_pairs"] + m["exact_duplicate_literals"] != m["raw_edge_literals"]:
            print("\n[FAIL] duplicate accounting does not reconcile.")
            return 1
        if m["accounted_entries"] != m["raw_edge_literals"]:
            print("\n[FAIL] not every raw edge literal is accounted for.")
            return 1
        print(
            f"\n[OK] all {m['raw_edge_literals']} raw edge literals accounted "
            f"({m['unique_legacy_pairs']} unique + {m['exact_duplicate_literals']} duplicates)."
        )
    return 0


if __name__ == "__main__":
    _ensure_repo_importable()
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # fail CLOSED, with context
        print(f"[blueprint_edge_reconcile] FATAL {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)
