"""RRF fusion for dense (vector) + sparse (BM25/keyword) retrieval hits.

Gated via ``USE_HYBRID_SEARCH=1`` in ``knowledge_base.retrieve``. Never raises.
"""

from __future__ import annotations

import os
from typing import Any


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def hybrid_enabled() -> bool:
    return _flag("USE_HYBRID_SEARCH")


def _key(hit: dict[str, Any]) -> str:
    t = str(hit.get("text") or "").strip()
    src = str(hit.get("source") or "")
    return f"{src}::{t[:240]}"


def rrf_merge(
    dense: list[dict[str, Any]],
    sparse: list[dict[str, Any]],
    top_k: int = 3,
    k_const: int = 60,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion — combine two ranked lists. Never raises."""
    if not dense and not sparse:
        return []
    if not sparse:
        return dense[: max(1, top_k)]
    if not dense:
        return sparse[: max(1, top_k)]
    try:
        scores: dict[str, float] = {}
        store: dict[str, dict[str, Any]] = {}
        for rank, hit in enumerate(dense):
            key = _key(hit)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k_const + rank + 1)
            store[key] = hit
        for rank, hit in enumerate(sparse):
            key = _key(hit)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k_const + rank + 1)
            if key not in store:
                store[key] = hit
        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        out: list[dict[str, Any]] = []
        for key, sc in ordered[: max(1, top_k)]:
            h = dict(store[key])
            h["score"] = float(sc)
            h["hybrid_rrf"] = True
            out.append(h)
        return out
    except Exception:
        return dense[: max(1, top_k)]


__all__ = ["hybrid_enabled", "rrf_merge"]
