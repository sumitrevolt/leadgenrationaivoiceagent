"""Agent self-recall — Hermes "search own past runs/decisions" parity.

Hermes-class infra agents ka ek capability = apne PURANE runs/decisions ko search
karke context-carry karna (har baar zero-context se shuru nahi). Is project me agents
events `agent_events` table + obsidian me likhte the par koi lightweight "apna pichla
faisla dhoondo" recall-helper nahi tha.

Yeh module woh deta (append-only jsonl + semantic-if-available, keyword-fallback):
  - `record(kind, text, meta)` → data/agent_recall.jsonl me ek line append.
  - `recall(query, k)` → pehle project VectorStore try (semantic); kisi bhi failure pe
    case-insensitive token-overlap scoring jsonl pe (deterministic fallback).
  - Admin POST/GET /api/agents-ext/recall.

Design (project patterns):
  - never-raise: record/recall dono ANY exception pe safe-default ([] / {ok:False}).
  - `enabled()` sirf AUTOMATIC background recall-write ko gate karta — default OFF =
    zero behaviour change. record()/recall() khud hamesha safe-callable (admin + direct).
  - VectorStore LAZY import (heavy ChromaDB) — function ke andar.
  - jsonl = source-of-truth; vector store best-effort overlay. Live business-KB se alag.

Flag: AGENT_RECALL=1
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE_PATH = Path("data/agent_recall.jsonl")
_VS_DIR = "data/agent_recall_vs"
_VS_COLLECTION = "agent_recall"
_MAX_SCAN = 5000  # jsonl tail-scan cap (keyword fallback ko bounded rakho)
_TEXT_CAP = 4000


def enabled() -> bool:
    """Gates AUTOMATIC background recall-writes. record()/recall() flag-independent."""
    return (os.getenv("AGENT_RECALL") or "").strip().lower() in ("1", "true", "yes")


def record(kind: str, text: str, meta: dict | None = None) -> dict[str, Any]:
    """Ek agent run/decision recall-store me append karo. Never raises.

    Returns {ok, at} on success, {ok:False, error} on failure.
    """
    body = (text or "").strip()
    if not body:
        return {"ok": False, "error": "empty text"}
    # Governance gate (fail-CLOSED, active only while MEMORY_STACK_ENABLED is on):
    # an unreadable do-not-remember authority must not let durable memory grow.
    try:
        from app.platform.memory_governance import durable_writes_allowed

        _g = durable_writes_allowed()
        if not _g["ok"]:
            return {"ok": False, "deferred": True, "code": _g["code"], "error": _g["reason"]}
    except Exception:
        return {
            "ok": False,
            "deferred": True,
            "code": "MEMORY_WRITE_DEFERRED_GOVERNANCE_UNAVAILABLE",
            "error": "governance module unavailable",
        }
    row = {
        "kind": str(kind or "note").strip()[:80],
        "text": body[:_TEXT_CAP],
        "meta": meta if isinstance(meta, dict) else {},
        "at": time.time(),
    }
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _STORE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover - disk/perm issue
        logger.debug(f"agent_recall.record failed: {e}")
        return {"ok": False, "error": str(e)[:200]}
    # Best-effort semantic index (gated AUTOMATIC write); failure = ignore.
    if enabled():
        try:
            _index_vector(row)
        except Exception as e:  # pragma: no cover
            logger.debug(f"agent_recall vector index skipped: {e}")
    return {"ok": True, "at": row["at"]}


def _index_vector(row: dict[str, Any]) -> None:
    """Best-effort: row ko project VectorStore me daalo (ChromaDB lazy)."""
    from app.ml.vector_store import VectorStore

    vs = VectorStore(persist_directory=_VS_DIR, collection_name=_VS_COLLECTION)
    coll = vs.collection  # property; raises if chroma truly dead → caller swallows
    emb = vs._generate_embedding(row["text"])
    rid = f"r-{int(row['at'] * 1000)}"
    coll.add(
        ids=[rid],
        embeddings=[emb],
        documents=[row["text"]],
        metadatas=[{"kind": row["kind"], "at": row["at"]}],
    )


def _load_rows() -> list[dict[str, Any]]:
    """jsonl ki latest _MAX_SCAN rows load karo (newest-last). Never raises."""
    if not _STORE_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with _STORE_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        for ln in lines[-_MAX_SCAN:]:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict) and obj.get("text"):
                    rows.append(obj)
            except Exception:
                continue
    except Exception as e:  # pragma: no cover
        logger.debug(f"agent_recall load failed: {e}")
        return []
    return rows


def _tokenize(s: str) -> set[str]:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in s).split() if len(t) > 1}


def _keyword_recall(query: str, k: int) -> list[dict[str, Any]]:
    """Deterministic token-overlap + substring fallback over jsonl."""
    rows = _load_rows()
    if not rows:
        return []
    q = query.strip().lower()
    q_tokens = _tokenize(q)
    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        text = str(r.get("text") or "")
        tl = text.lower()
        score = 0.0
        if q and q in tl:
            score += 2.0  # full substring hit = strong signal
        if q_tokens:
            overlap = len(q_tokens & _tokenize(text))
            score += overlap / max(1, len(q_tokens))
        if score <= 0:
            continue
        scored.append((score, r))
    scored.sort(key=lambda x: (x[0], x[1].get("at") or 0), reverse=True)
    out: list[dict[str, Any]] = []
    for score, r in scored[: max(1, k)]:
        out.append(
            {
                "kind": r.get("kind"),
                "text": r.get("text"),
                "score": round(float(score), 3),
                "at": r.get("at"),
                "meta": r.get("meta") or {},
            }
        )
    return out


def _semantic_recall(query: str, k: int) -> list[dict[str, Any]] | None:
    """Project VectorStore se semantic search. None = unavailable → keyword fallback."""
    try:
        from app.ml.vector_store import VectorStore

        vs = VectorStore(persist_directory=_VS_DIR, collection_name=_VS_COLLECTION)
        coll = vs.collection
        emb = vs._generate_embedding(query)
        res = coll.query(query_embeddings=[emb], n_results=max(1, k))
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        if not docs:
            return None
        out: list[dict[str, Any]] = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else 1.0
            out.append(
                {
                    "kind": (meta or {}).get("kind"),
                    "text": doc,
                    "score": round(max(0.0, 1.0 - float(dist)), 3),
                    "at": (meta or {}).get("at"),
                    "meta": meta or {},
                }
            )
        return out
    except Exception as e:  # pragma: no cover - chroma missing / empty / version skew
        logger.debug(f"agent_recall semantic unavailable: {e}")
        return None


async def recall(query: str, k: int = 6) -> list[dict[str, Any]]:
    """Agent ke apne past runs/decisions search karo. Never raises.

    Pehle project vector store (semantic); kisi bhi failure/empty pe deterministic
    keyword (token-overlap + substring) fallback over data/agent_recall.jsonl.
    Returns [{kind, text, score, at, meta}].
    """
    q = (query or "").strip()
    if not q:
        return []
    kk = max(1, min(int(k or 6), 50))
    # Semantic best-effort: agar raise/empty ho to keyword pe fall karo (spec: ANY failure).
    try:
        sem = _semantic_recall(q, kk)
        if sem:
            return sem
    except Exception as e:  # pragma: no cover - semantic raised → keyword fallback
        logger.debug(f"agent_recall semantic raised, keyword fallback: {e}")
    try:
        return _keyword_recall(q, kk)
    except Exception as e:  # pragma: no cover - blanket safety
        logger.debug(f"agent_recall.recall failed: {e}")
        return []


__all__ = ["enabled", "record", "recall"]
