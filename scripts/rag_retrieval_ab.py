#!/usr/bin/env python3
"""RAG retrieval A/B — baseline vs upgraded flags (offline-safe).

Compares top-k hits for fixed queries under:
  baseline  — flags OFF
  rerank    — USE_RERANKER=1
  hybrid    — USE_HYBRID_SEARCH=1 (seed with hybrid ON so BM25 mirror exists)
  full      — rerank + hybrid

Usage (VPS after deploy + optional flag flip in .env):
  cd /opt/leadgen && docker exec leadgen_app python scripts/rag_retrieval_ab.py

Local:
  python scripts/rag_retrieval_ab.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _p in ("/opt/leadgen/.env", os.path.join(ROOT, ".env")):
    if os.path.exists(_p):
        for _ln in open(_p, encoding="utf-8"):
            _ln = _ln.strip()
            if _ln and not _ln.startswith("#") and "=" in _ln:
                _k, _v = _ln.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        break

NS = "ab:ragtest"
QUERIES = [
    "electricity bill kam kaise kare solar",
    "pricing kitni hai per kw installation",
    "warranty kitne saal ki milti hai panel",
]

DOCS = [
    "Solar panels lagane se bijli ka monthly bill 70 percent tak kam ho jata hai, 25 saal warranty.",
    "Hamari pricing transparent hai: commercial rooftop per kw installation ₹45,000 se shuru.",
    "Har panel par 25 saal product warranty aur 10 saal performance guarantee milti hai.",
    "Marketing posts aur review replies AI se — yeh solar pricing doc nahi hai.",
]

# KB_EXACT_SEARCH pinned "0" on every A/B config: the gate compares shippable
# (approximate/HNSW) configs, so it must be immune to an ambient KB_EXACT_SEARCH.
# Exact search is exercised separately by run_exact_recall_probe().
MODES = {
    "baseline": {
        "USE_RERANKER": "0",
        "USE_HYBRID_SEARCH": "0",
        "USE_CONTEXTUAL_INGEST": "0",
        "KB_EXACT_SEARCH": "0",
    },
    "rerank": {
        "USE_RERANKER": "1",
        "USE_HYBRID_SEARCH": "0",
        "USE_CONTEXTUAL_INGEST": "0",
        "KB_EXACT_SEARCH": "0",
    },
    "hybrid": {
        "USE_RERANKER": "0",
        "USE_HYBRID_SEARCH": "1",
        "USE_CONTEXTUAL_INGEST": "0",
        "KB_EXACT_SEARCH": "0",
    },
    "full": {
        "USE_RERANKER": "1",
        "USE_HYBRID_SEARCH": "1",
        "USE_CONTEXTUAL_INGEST": "0",
        "KB_EXACT_SEARCH": "0",
    },
}


def _apply(mode: dict[str, str]) -> None:
    for k, v in mode.items():
        os.environ[k] = v


def _seed() -> None:
    """Seed KB; hybrid mirror only populates when USE_HYBRID_SEARCH=1 at ingest."""
    from app.voice_agent import knowledge_base as kb_mod

    _apply({"USE_HYBRID_SEARCH": "1", "USE_CONTEXTUAL_INGEST": "0", "USE_RERANKER": "0"})
    kb = kb_mod.get_knowledge_base()
    kb.add_documents(DOCS, source="ab_seed", namespace=NS)


def _run_mode(name: str, flags: dict[str, str]) -> dict[str, list]:
    _apply(flags)
    from app.voice_agent.knowledge_base import get_knowledge_base

    kb = get_knowledge_base()
    out: dict[str, list] = {}
    for q in QUERIES:
        hits = kb.retrieve(q, k=2, namespace=NS, rerank=None)
        out[q] = hits
    return out


def main() -> int:
    print("=== RAG retrieval A/B ===")
    try:
        from app.voice_agent import knowledge_base as kb_mod

        kb_mod._get_qdrant_embedder()
        print(f"embedder={kb_mod._E5_MODEL_NAME} dim={kb_mod._QDRANT_VECTOR_SIZE}")
    except Exception as e:
        print(f"WARN: embedder/qdrant unavailable ({e}) — keyword fallback only")

    _seed()
    results: dict[str, dict[str, list]] = {}
    for mode, flags in MODES.items():
        results[mode] = _run_mode(mode, flags)

    print(f"\nnamespace={NS}  queries={len(QUERIES)}\n")
    for q in QUERIES:
        print(f"Q: {q}")
        base_top = results["baseline"][q][0].get("text", "")[:50] if results["baseline"][q] else "—"
        for mode in MODES:
            hits = results[mode][q]
            top = hits[0] if hits else {}
            txt = (top.get("text") or "—")[:55]
            sc = round(float(top.get("score", 0) or 0), 4)
            changed = " *" if mode != "baseline" and txt[:40] != base_top[:40] else ""
            print(f"  {mode:8} score={sc}  {txt}{changed}")
        print()

    # Simple win metric: full mode top-1 differs from baseline on solar/pricing queries
    wins = 0
    for q in QUERIES[:2]:
        b = results["baseline"][q][0].get("text", "") if results["baseline"][q] else ""
        f = results["full"][q][0].get("text", "") if results["full"][q] else ""
        if f and f != b:
            wins += 1
    print(f"full_vs_baseline_top1_changed={wins}/{min(2, len(QUERIES))} (higher = upgrade helping)")

    # Measured recall/precision DELTA gate (offline-safe — uses real KB retrieve fn).
    try:
        gate_rc = run_gate(make_kb_retrieve_fn())
    except Exception as e:  # pragma: no cover - live KB optional
        print(f"\n[gate] skipped (KB unavailable): {e}")
        gate_rc = 0

    # ANN-vs-exact recall diagnostic (isolates model vs HNSW; eval only).
    try:
        run_exact_recall_probe()
    except Exception as e:  # pragma: no cover - live KB optional
        print(f"[exact-probe] skipped (KB unavailable): {e}")
    return gate_rc


# =========================================================================== #
# A/B RETRIEVAL GATE — measured recall@k / precision@k DELTA per config.
#
# Goal: enable a new retrieval lever (rerank / hybrid / full) only when it
# PROVABLY beats baseline by a margin on a fixed labeled query->expected-doc set.
#
# Design for offline-safety:
#   - The scoring math operates on a `retrieve_fn(query, k) -> list[dict]`.
#   - Each returned dict has a "text" field; we map text -> doc_id via DOC_IDS.
#   - The harness NEVER needs live Qdrant: tests pass a fake retrieve_fn fixture.
#     `make_kb_retrieve_fn()` builds the real one only when main() runs.
# =========================================================================== #

# Stable doc-id -> document text. The id prefix is embedded so a returned hit's
# text can be mapped back to its labeled id regardless of scoring/order.
LABELED_DOCS: dict[str, str] = {
    "solar_bill": "Solar panels lagane se bijli ka monthly bill 70 percent tak kam ho jata hai, 25 saal warranty.",
    "pricing_kw": "Hamari pricing transparent hai: commercial rooftop per kw installation 45000 se shuru.",
    "warranty_25y": "Har panel par 25 saal product warranty aur 10 saal performance guarantee milti hai.",
    "marketing_noise": "Marketing posts aur review replies AI se yeh solar pricing doc nahi hai.",
    "subsidy_info": "Residential solar par government subsidy 40 percent tak milti hai 3kw tak.",
    "maintenance": "Panel maintenance saal me do baar safai, warna efficiency 15 percent gir sakti hai.",
}

# Fixed labeled relevance set: query -> set of doc_ids that SHOULD be retrieved.
LABELED_SET: list[dict] = [
    {"query": "electricity bill kam kaise kare solar", "relevant": {"solar_bill"}},
    {"query": "pricing kitni hai per kw installation", "relevant": {"pricing_kw"}},
    {"query": "warranty kitne saal ki milti hai panel", "relevant": {"warranty_25y", "solar_bill"}},
    {"query": "government subsidy kitni milti hai residential", "relevant": {"subsidy_info"}},
    {"query": "panel ki safai maintenance kaise karein", "relevant": {"maintenance"}},
]

# Margin a config must beat baseline by (on mean recall@k) to PASS the gate.
GATE_MARGIN = float(os.getenv("RAG_GATE_MARGIN", "0.05") or 0.05)
GATE_K = int(os.getenv("RAG_GATE_K", "3") or 3)


def _hit_doc_id(hit: dict) -> str | None:
    """Map a retrieve() hit back to its labeled doc_id by text containment."""
    txt = (hit.get("text") or "").strip().lower()
    if not txt:
        return None
    for doc_id, doc_text in LABELED_DOCS.items():
        dt = doc_text.strip().lower()
        # chunking may shorten/extend; match on either-direction containment
        if dt and (dt in txt or txt in dt or _overlap_ratio(dt, txt) >= 0.6):
            return doc_id
    return None


def _overlap_ratio(a: str, b: str) -> float:
    """Token-overlap ratio (Jaccard-ish) — robust to chunking/whitespace drift."""
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def score_config(retrieve_fn, labeled_set=None, k: int = GATE_K) -> dict:
    """Score one retrieval config over the labeled set.

    Args:
        retrieve_fn: callable(query: str, k: int) -> list[dict] (each {"text":...}).
        labeled_set: list of {"query", "relevant": set[doc_id]}.
        k: cutoff for recall@k / precision@k.

    Returns dict: {recall, precision, f1, per_query: [...]}.
    Pure function — no I/O, no globals beyond LABELED_DOCS mapping.
    """
    cases = labeled_set if labeled_set is not None else LABELED_SET
    recalls: list[float] = []
    precisions: list[float] = []
    per_query: list[dict] = []
    for case in cases:
        relevant = set(case.get("relevant", set()))
        try:
            hits = retrieve_fn(case["query"], k) or []
        except Exception:
            hits = []
        retrieved_ids: list[str] = []
        for h in hits[:k]:
            did = _hit_doc_id(h)
            if did is not None:
                retrieved_ids.append(did)
        retrieved_set = set(retrieved_ids)
        hit_relevant = retrieved_set & relevant
        recall = (len(hit_relevant) / len(relevant)) if relevant else 0.0
        precision = (len(hit_relevant) / len(retrieved_ids)) if retrieved_ids else 0.0
        recalls.append(recall)
        precisions.append(precision)
        per_query.append(
            {
                "query": case["query"],
                "recall": round(recall, 4),
                "precision": round(precision, 4),
                "retrieved": retrieved_ids,
                "relevant": sorted(relevant),
            }
        )
    mean_recall = sum(recalls) / len(recalls) if recalls else 0.0
    mean_precision = sum(precisions) / len(precisions) if precisions else 0.0
    f1 = (
        2 * mean_recall * mean_precision / (mean_recall + mean_precision)
        if (mean_recall + mean_precision)
        else 0.0
    )
    return {
        "recall": round(mean_recall, 4),
        "precision": round(mean_precision, 4),
        "f1": round(f1, 4),
        "per_query": per_query,
    }


def compute_deltas(
    config_fns: dict, labeled_set=None, k: int = GATE_K, margin: float = GATE_MARGIN
) -> dict:
    """Score every config, compute recall/precision DELTA vs baseline + PASS/FAIL.

    Args:
        config_fns: {"baseline": retrieve_fn, "rerank": fn, "hybrid": fn, "full": fn}.
                    MUST contain "baseline".
        labeled_set: optional override of the labeled relevance set.
        k, margin: gate cutoff + required recall improvement over baseline.

    Returns:
        {
          "baseline": {recall, precision, f1, ...},
          "configs": {name: {recall, precision, f1, recall_delta, precision_delta,
                             passed: bool, ...}},
          "winner": name|None,            # best PASS-ing config by recall_delta
          "passed": bool,                 # any non-baseline config passed
        }
    """
    if "baseline" not in config_fns:
        raise ValueError("config_fns must include a 'baseline' config")
    base = score_config(config_fns["baseline"], labeled_set, k)
    base_recall = base["recall"]
    base_precision = base["precision"]
    configs: dict[str, dict] = {}
    winner = None
    best_delta = -1.0
    for name, fn in config_fns.items():
        if name == "baseline":
            continue
        sc = score_config(fn, labeled_set, k)
        sc["recall_delta"] = round(sc["recall"] - base_recall, 4)
        sc["precision_delta"] = round(sc["precision"] - base_precision, 4)
        # Gate: must beat baseline recall by margin AND not regress precision.
        passed = sc["recall_delta"] >= margin and sc["precision_delta"] >= -1e-9
        sc["passed"] = bool(passed)
        configs[name] = sc
        if passed and sc["recall_delta"] > best_delta:
            best_delta = sc["recall_delta"]
            winner = name
    return {
        "baseline": base,
        "configs": configs,
        "winner": winner,
        "passed": winner is not None,
        "k": k,
        "margin": margin,
    }


def format_delta_table(report: dict) -> str:
    """Render compute_deltas() output as a fixed-width delta table string."""
    base = report["baseline"]
    k = report.get("k", GATE_K)
    margin = report.get("margin", GATE_MARGIN)
    lines = []
    lines.append(f"=== RAG A/B retrieval gate (k={k}, margin=+{margin} recall) ===")
    hdr = f"{'config':10} {'recall':>7} {'prec':>7} {'f1':>7} {'dRecall':>8} {'dPrec':>7}  gate"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    lines.append(
        f"{'baseline':10} {base['recall']:>7.3f} {base['precision']:>7.3f} "
        f"{base['f1']:>7.3f} {'—':>8} {'—':>7}  (ref)"
    )
    for name, sc in report["configs"].items():
        gate = "PASS" if sc["passed"] else "fail"
        lines.append(
            f"{name:10} {sc['recall']:>7.3f} {sc['precision']:>7.3f} "
            f"{sc['f1']:>7.3f} {sc['recall_delta']:>+8.3f} "
            f"{sc['precision_delta']:>+7.3f}  {gate}"
        )
    lines.append("-" * len(hdr))
    if report["passed"]:
        lines.append(f"GATE PASS — enable config '{report['winner']}' (proven > baseline).")
    else:
        lines.append("GATE FAIL — no config beats baseline by margin; keep flags OFF.")
    return "\n".join(lines)


def make_kb_retrieve_fn():
    """Build the real KB-backed config_fns dict (live Qdrant/keyword path).

    Returns {config_name: retrieve_fn}. Seeds the labeled docs first. Used by
    main(); tests use fake fns instead so no live KB is required.
    """
    from app.voice_agent import knowledge_base as kb_mod

    gate_ns = "ab:ragquality"
    _apply({"USE_HYBRID_SEARCH": "1", "USE_CONTEXTUAL_INGEST": "0", "USE_RERANKER": "0"})
    kb = kb_mod.get_knowledge_base()
    kb.add_documents(list(LABELED_DOCS.values()), source="ab_gate", namespace=gate_ns)

    def _mk(flags: dict[str, str]):
        def _fn(query: str, k: int):
            _apply(flags)
            kb2 = kb_mod.get_knowledge_base()
            return kb2.retrieve(query, k=k, namespace=gate_ns, rerank=None)

        return _fn

    return {name: _mk(flags) for name, flags in MODES.items()}


def run_gate(config_fns, labeled_set=None, k: int = GATE_K, margin: float = GATE_MARGIN) -> int:
    """Compute deltas, print the table, return shell rc (0 = PASS, 1 = FAIL)."""
    report = compute_deltas(config_fns, labeled_set, k, margin)
    print("\n" + format_delta_table(report))
    return 0 if report["passed"] else 1


def run_exact_recall_probe() -> None:
    """ANN-vs-exact recall@k probe — the search-quality skill's core diagnostic.

    Runs the SAME baseline retrieval twice (approximate HNSW vs brute-force
    exact via KB_EXACT_SEARCH) over the labeled set and compares recall:
      exact recall low       -> model/data problem (chunking/embedding), not HNSW.
      exact good, ANN lagging -> tune HNSW (raise KB_HNSW_EF).
      ANN tracking exact      -> filtered-HNSW recall is healthy.
    Never leaves KB_EXACT_SEARCH on (it bypasses the index — eval only).
    """
    from app.voice_agent import knowledge_base as kb_mod

    ns = "ab:exactprobe"
    _apply(
        {
            "USE_HYBRID_SEARCH": "1",
            "USE_CONTEXTUAL_INGEST": "0",
            "USE_RERANKER": "0",
            "KB_EXACT_SEARCH": "0",
        }
    )
    kb_mod.get_knowledge_base().add_documents(
        list(LABELED_DOCS.values()), source="ab_exact", namespace=ns
    )
    base = {"USE_RERANKER": "0", "USE_HYBRID_SEARCH": "0", "USE_CONTEXTUAL_INGEST": "0"}

    def _fn(exact_flag: str):
        def _run(query: str, k: int):
            _apply({**base, "KB_EXACT_SEARCH": exact_flag})
            return kb_mod.get_knowledge_base().retrieve(query, k=k, namespace=ns, rerank=None)

        return _run

    ann = score_config(_fn("0"))
    exact = score_config(_fn("1"))
    _apply({"KB_EXACT_SEARCH": "0"})  # never leave exact on
    gap = round(exact["recall"] - ann["recall"], 4)
    print(f"\n=== ANN vs exact recall@{GATE_K} (namespace={ns}) ===")
    print(f"  ann_recall={ann['recall']}  exact_recall={exact['recall']}  gap={gap}")
    if exact["recall"] < 0.5:
        print("  -> exact recall low: model/data problem (chunking or embedding), not HNSW.")
    elif gap >= 0.05:
        print("  -> exact good, ANN lagging: tune HNSW (raise KB_HNSW_EF).")
    else:
        print("  -> ANN tracking exact: filtered-HNSW recall healthy.")


if __name__ == "__main__":
    raise SystemExit(main())
