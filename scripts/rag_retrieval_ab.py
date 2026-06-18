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

MODES = {
    "baseline": {"USE_RERANKER": "0", "USE_HYBRID_SEARCH": "0", "USE_CONTEXTUAL_INGEST": "0"},
    "rerank": {"USE_RERANKER": "1", "USE_HYBRID_SEARCH": "0", "USE_CONTEXTUAL_INGEST": "0"},
    "hybrid": {"USE_RERANKER": "0", "USE_HYBRID_SEARCH": "1", "USE_CONTEXTUAL_INGEST": "0"},
    "full": {"USE_RERANKER": "1", "USE_HYBRID_SEARCH": "1", "USE_CONTEXTUAL_INGEST": "0"},
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
        base_top = (results["baseline"][q][0].get("text", "")[:50] if results["baseline"][q] else "—")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
