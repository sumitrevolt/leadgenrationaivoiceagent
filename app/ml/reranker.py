"""Optional reranking for KB retrieval (content/marketing RAG — NOT live voice turns).

Gated ``USE_RERANKER=1``. Fuses the vector retriever score with a lightweight
lexical BM25-style rescore (zero new deps). If ``sentence-transformers`` is
installed and ``RERANKER_BACKEND=crossencoder``, uses
``BAAI/bge-reranker-v2-m3`` instead (heavy — image-bake recommended).

Never raises; on any failure returns the input list truncated to top_k.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

_CROSS_ENCODER = None
_CROSS_BROKEN = False
_CROSS_LOCK = threading.Lock()


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def rerank_enabled() -> bool:
    return _flag("USE_RERANKER")


def _tokenize(text: str) -> list[str]:
    from app.voice_agent.knowledge_base import tokenize

    return tokenize(text or "")


def _lexical_score(query: str, passage: str) -> float:
    """BM25-ish overlap score in [0, 1] — cheap, no ML deps."""
    q = _tokenize(query)
    p = _tokenize(passage)
    if not q or not p:
        return 0.0
    q_counts = Counter(q)
    p_counts = Counter(p)
    p_len = float(len(p))
    k1, b, avgdl = 1.2, 0.75, 120.0
    score = 0.0
    for term, qf in q_counts.items():
        if term not in p_counts:
            continue
        tf = p_counts[term]
        idf = math.log(1.0 + (1.0 / (0.5 + tf / max(p_len, 1.0))))
        denom = tf + k1 * (1.0 - b + b * p_len / avgdl)
        score += idf * (tf * (k1 + 1.0)) / max(denom, 1e-9)
    # squash to 0..1
    return min(1.0, score / (len(q_counts) * 3.0 + 1.0))


def _get_cross_encoder():
    """Lazy CrossEncoder singleton (optional dep)."""
    global _CROSS_ENCODER, _CROSS_BROKEN
    if _CROSS_BROKEN:
        return None
    if _CROSS_ENCODER is not None:
        return _CROSS_ENCODER
    with _CROSS_LOCK:
        if _CROSS_ENCODER is not None:
            return _CROSS_ENCODER
        try:
            from sentence_transformers import CrossEncoder

            model = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
            _CROSS_ENCODER = CrossEncoder(model, max_length=512)
            logger.info("Reranker: CrossEncoder loaded (%s)", model)
            return _CROSS_ENCODER
        except Exception as exc:
            _CROSS_BROKEN = True
            logger.info("Reranker: CrossEncoder unavailable (%s) — lexical fallback", exc)
            return None


def rerank_hits(
    query: str,
    hits: list[dict[str, Any]],
    top_k: int = 3,
    vector_weight: float | None = None,
) -> list[dict[str, Any]]:
    """Rerank retrieval hits. Never raises."""
    if not hits or not (query or "").strip():
        return hits[: max(1, top_k)]
    try:
        vw = vector_weight
        if vw is None:
            vw = float(os.getenv("RERANK_VECTOR_WEIGHT", "0.65") or 0.65)
        lw = max(0.0, 1.0 - vw)
        backend = (os.getenv("RERANKER_BACKEND") or "lexical").strip().lower()
        ce = _get_cross_encoder() if backend == "crossencoder" else None

        scored: list[tuple[float, dict[str, Any]]] = []
        if ce is not None:
            pairs = [(query, str(h.get("text") or "")) for h in hits]
            try:
                raw = ce.predict(pairs)
                for h, r in zip(hits, raw):
                    scored.append((float(r), h))
            except Exception as exc:
                logger.debug("CrossEncoder predict failed: %s", exc)
                ce = None

        if ce is None:
            for h in hits:
                vec = float(h.get("score", 0.0) or 0.0)
                lex = _lexical_score(query, str(h.get("text") or ""))
                fused = vw * vec + lw * lex
                scored.append((fused, {**h, "score": fused, "rerank_lex": lex}))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[: max(1, top_k)]]
    except Exception as exc:
        logger.debug("rerank_hits error: %s", exc)
        return hits[: max(1, top_k)]


__all__ = ["rerank_enabled", "rerank_hits"]
