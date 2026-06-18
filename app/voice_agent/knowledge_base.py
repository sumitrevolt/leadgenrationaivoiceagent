"""
Knowledge Base / RAG Grounding System
=====================================

Banata hai AI voice agent ko *factually accurate* — customer ke sawaal ka jawab
SIRF stored knowledge (chunks) se deta hai, banata (hallucinate) nahi. Yeh
Retell/Vapi ke "Knowledge Base" feature jaisa hai: aap docs/website/FAQ daalo,
agent unhi se grounded answer de.

Design (Dograh / production voice-agent best practices):
  1. STORE: documents ko chhote chunks me todo + store karo (per-namespace, taaki
     har client/niche ka apna KB ho).
  2. RETRIEVE: query ke liye top-k sabse relevant chunks laao (score ke saath).
  3. GROUND: jawab SIRF retrieved chunks se banao. Kuch relevant na mile to safe
     fallback do ("main team se confirm karwa deta hoon") — kabhi mat banao.

Backends (auto-detect, zero-config):
  - SABSE PEHLE Qdrant (sirf jab QDRANT_URL set ho + qdrant-client/fastembed
    installed + server reachable) — single "kb_main" collection, payload-
    partitioned per-namespace multi-tenancy, multilingual-e5-small embeddings.
  - PHIR app.ml.vector_store ki Chroma-based store reuse karne ki koshish
    (semantic embeddings). Agar woh / sentence-transformers / chromadb available
    nahi, ya mock par gir jaaye, to...
  - PURE-PYTHON TF-IDF / keyword-overlap retriever fallback — koi external
    service ya key nahi chahiye. Hamesha kaam karta hai.

Usage (text mode, no external services needed):
    from app.voice_agent.knowledge_base import get_knowledge_base

    kb = get_knowledge_base()
    kb.add_documents(
        ["Pricing per qualified lead hoti hai, ₹200-500/lead.",
         "Demo bilkul free hai — 15 minute me dikha dete hain."],
        source="faq",
        namespace="solar_commercial",
    )

    hits = kb.retrieve("kitne paise lagte hain?", k=3, namespace="solar_commercial")
    # -> [{"text": "...", "score": 0.42, "source": "faq"}, ...]

    ans = kb.grounded_answer("pricing kya hai?", namespace="solar_commercial")
    # -> "Pricing per qualified lead hoti hai, ₹200-500/lead."

Notes:
  - `retrieve()` ALWAYS returns a list[dict] with keys: text, score, source.
    Higher score = more relevant. Empty list = kuch relevant nahi mila.
  - Thread-safety: simple in-process locking ke saath singleton.
"""

from __future__ import annotations

import math
import os
import re
import threading
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Text helpers — chunking + tokenization (pure-python, no deps)
# --------------------------------------------------------------------------- #
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Common Hindi(Roman)/English stopwords — TF-IDF ko noise se bachane ke liye.
_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "at",
    "by",
    "from",
    "as",
    "it",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "do",
    "does",
    "did",
    "ka",
    "ke",
    "ki",
    "ko",
    "se",
    "me",
    "mein",
    "hai",
    "hain",
    "ho",
    "hi",
    "bhi",
    "aur",
    "ya",
    "par",
    "kya",
    "kaise",
    "kaun",
    "yeh",
    "ye",
    "woh",
    "wo",
    "ek",
    "kar",
    "karna",
    "karo",
    "raha",
    "rahe",
}


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords hata ke. Hindi-roman + English dono."""
    toks = _WORD_RE.findall((text or "").lower())
    return [t for t in toks if t not in _STOPWORDS and len(t) > 1]


def chunk_text(
    text: str,
    max_chars: int = 500,
    overlap: int = 50,
) -> list[str]:
    """
    Text ko semantic-ish chunks me todo. Pehle paragraph/sentence boundaries
    par, phir agar koi piece bada ho to char-window se. Overlap se context
    continuity rehti hai (RAG best practice).
    """
    text = (text or "").strip()
    if not text:
        return []

    # paragraph-first split
    raw_parts = re.split(r"\n\s*\n+", text)
    pieces: list[str] = []
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chars:
            pieces.append(part)
            continue
        # sentence-aware accumulation
        sentences = re.split(r"(?<=[.?!।])\s+", part)
        buf = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(buf) + len(s) + 1 <= max_chars:
                buf = f"{buf} {s}".strip()
            else:
                if buf:
                    pieces.append(buf)
                if len(s) <= max_chars:
                    buf = s
                else:
                    # hard char-window for a single very long sentence
                    start = 0
                    while start < len(s):
                        pieces.append(s[start : start + max_chars])
                        start += max_chars - overlap
                    buf = ""
        if buf:
            pieces.append(buf)
    return [p for p in pieces if p.strip()]


# --------------------------------------------------------------------------- #
# In-memory TF-IDF / keyword-overlap retriever (zero-dependency fallback)
# --------------------------------------------------------------------------- #
@dataclass
class _Doc:
    text: str
    source: str
    tokens: list[str] = field(default_factory=list)
    tf: dict[str, float] = field(default_factory=dict)


class _KeywordIndex:
    """
    Pure-python TF-IDF cosine retriever. Koi external service/key nahi.

    - Har chunk ka term-frequency vector banata hai.
    - Query ke liye IDF-weighted cosine similarity se top-k laata hai.
    - Hamesha available — yeh hi guarantee deta hai ki KB kabhi crash na ho.
    """

    def __init__(self) -> None:
        self._docs: list[_Doc] = []
        self._df: Counter = Counter()  # document frequency per term

    @property
    def size(self) -> int:
        return len(self._docs)

    def add(self, text: str, source: str = "", embed_prefix: str = "") -> None:
        index_text = f"{embed_prefix}\n{text}".strip() if embed_prefix else text
        toks = tokenize(index_text)
        if not toks:
            # still store so retrieve()/answers can fall back, but no tokens
            self._docs.append(_Doc(text=text, source=source, tokens=[], tf={}))
            return
        counts = Counter(toks)
        total = float(len(toks))
        tf = {t: c / total for t, c in counts.items()}
        for t in counts:
            self._df[t] += 1
        self._docs.append(_Doc(text=text, source=source, tokens=toks, tf=tf))

    def _idf(self, term: str) -> float:
        n = max(1, len(self._docs))
        df = self._df.get(term, 0)
        # smoothed idf
        return math.log((n + 1) / (df + 1)) + 1.0

    def search(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        if not self._docs:
            return []
        q_toks = tokenize(query)
        if not q_toks:
            return []
        q_counts = Counter(q_toks)
        q_total = float(len(q_toks))
        q_vec = {t: (c / q_total) * self._idf(t) for t, c in q_counts.items()}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        scored: list[dict[str, Any]] = []
        for doc in self._docs:
            if not doc.tf:
                continue
            # only iterate over shared terms for the dot product
            dot = 0.0
            d_norm_sq = 0.0
            for term, tf_val in doc.tf.items():
                w = tf_val * self._idf(term)
                d_norm_sq += w * w
                if term in q_vec:
                    dot += w * q_vec[term]
            if dot <= 0:
                continue
            d_norm = math.sqrt(d_norm_sq) or 1.0
            score = dot / (q_norm * d_norm)
            scored.append({"text": doc.text, "score": float(score), "source": doc.source})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]


# --------------------------------------------------------------------------- #
# Chroma-backed retriever (reuses app.ml.vector_store embeddings)
# --------------------------------------------------------------------------- #
class _ChromaIndex:
    """
    app.ml.vector_store.VectorStore ke embedder + Chroma collection ko reuse
    karta hai. Per-namespace ke liye alag collection use karta hai.

    Agar embedder mock (hash-based) ho to similarity bekaar hoti hai — isliye
    KnowledgeBase isko sirf tab "real" maanta hai jab sentence-transformers
    embedder load ho. Warna keyword fallback prefer hota hai.
    """

    def __init__(self, namespace: str = "default") -> None:
        from app.ml.vector_store import VectorStore  # may raise ImportError

        self._store = VectorStore(collection_name=f"kb_{_safe_name(namespace)}")
        self._namespace = namespace
        self._count = 0
        # touch collection to surface init errors early
        _ = self._store.collection

    @property
    def real_embeddings(self) -> bool:
        """True only if a real (non-mock) embedder is active."""
        try:
            from app.ml.vector_store import MockEmbedder

            return not isinstance(self._store.embedder, MockEmbedder)
        except Exception:
            return False

    @property
    def size(self) -> int:
        try:
            return int(self._store.collection.count())
        except Exception:
            return self._count

    def add(self, text: str, source: str = "", embed_prefix: str = "") -> None:
        emb_text = f"{embed_prefix}\n{text}".strip() if embed_prefix else text
        emb = self._store._generate_embedding(emb_text)
        doc_id = f"{self._namespace}-{self._count}"
        self._count += 1
        self._store.collection.add(
            ids=[doc_id],
            embeddings=[emb],
            metadatas=[{"source": source, "namespace": self._namespace}],
            documents=[text],
        )

    def search(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        q_emb = self._store._generate_embedding(query)
        try:
            res = self._store.collection.query(query_embeddings=[q_emb], n_results=k)
        except Exception as e:  # pragma: no cover
            logger.debug(f"chroma query failed: {e}")
            return []
        out: list[dict[str, Any]] = []
        ids = (res or {}).get("ids") or [[]]
        if not ids or not ids[0]:
            return []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i in range(len(ids[0])):
            text = docs[i] if i < len(docs) else ""
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else 1.0
            score = 1.0 / (1.0 + float(dist))
            out.append(
                {
                    "text": text,
                    "score": float(score),
                    "source": (meta or {}).get("source", ""),
                }
            )
        return out


def _safe_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", (name or "default")).strip("_") or "default"


# --------------------------------------------------------------------------- #
# Qdrant-backed retriever (single payload-partitioned collection + fastembed)
# --------------------------------------------------------------------------- #
# Research-decided design (docs/Architecture_Research_RAG_Agents_MCP.md):
#   - EK hi collection "kb_main" me SAB namespaces — payload-partitioned
#     multi-tenancy (Qdrant official best practice; collection-per-tenant NAHI).
#   - Point payload: {"namespace": ..., "text": ..., "source": ...} + keyword
#     payload index on "namespace" for fast filtered search.
#   - Embeddings: fastembed TextEmbedding("intfloat/multilingual-e5-small")
#     (Hinglish-friendly, 384-dim, cosine). e5 models ko "query: " / "passage: "
#     prefix CHAHIYE hota hai — yahan handle hota hai.
#   - settings.qdrant_url empty => backend disabled (default; zero behavior change).
_QDRANT_COLLECTION = "kb_main"
_QDRANT_VECTOR_SIZE = 384  # default; auto-updated to the chosen model's REAL dim
# fastembed versions drop/rename models — try several, first that initializes wins.
# Prefer 384-dim multilingual (matches existing collection); e5-large is last resort.
_EMBED_CANDIDATES = [
    "intfloat/multilingual-e5-small",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "BAAI/bge-small-en-v1.5",
    "intfloat/multilingual-e5-large",
    "BAAI/bge-base-en-v1.5",
]
_E5_MODEL_NAME = _EMBED_CANDIDATES[0]

_QDRANT_LOCK = threading.Lock()
_QDRANT_CLIENT: Any | None = None
_QDRANT_EMBEDDER: Any | None = None
# Pehli hard-failure ke baad is process me dobara try mat karo (slow timeouts
# har naye namespace par repeat na hon). Restart par phir se probe hoga.
_QDRANT_DISABLED = False


def _get_qdrant_url() -> str:
    """settings.qdrant_url (empty string => Qdrant backend disabled)."""
    try:
        from app.config import settings

        return (getattr(settings, "qdrant_url", "") or "").strip()
    except Exception:
        return ""


def _get_qdrant_embedder():
    """Lazy global fastembed TextEmbedding singleton (model load is heavy).

    PROD-SAFETY (2026-06-12): model cache missing hone par fastembed runtime me
    HuggingFace se download karta hai — slow/blocked network par yeh call
    MINUTES tak hang ho sakti hai. Aaj yahi hua: web-call websocket se yeh
    SYNC call dono uvicorn workers ke event loop pe atki -> poora prod down.
    Isliye ab load ek helper THREAD me hota hai with hard deadline
    (KB_EMBED_LOAD_TIMEOUT_S, default 20s). Deadline cross hote hi is process
    me Qdrant DISABLE (callers Chroma/keyword par fall back); orphan thread
    baad me complete ho jaye to singleton set ho jata hai (agla use semantic).
    """
    global _QDRANT_EMBEDDER, _QDRANT_DISABLED
    if _QDRANT_EMBEDDER is not None:
        return _QDRANT_EMBEDDER
    if _QDRANT_DISABLED:
        raise RuntimeError("qdrant embedder disabled (earlier load timeout/failure)")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "15")
    timeout_s = float(os.getenv("KB_EMBED_LOAD_TIMEOUT_S", "20") or 20)
    done = threading.Event()

    def _load() -> None:
        global _QDRANT_EMBEDDER, _QDRANT_VECTOR_SIZE, _E5_MODEL_NAME
        try:
            with _QDRANT_LOCK:
                if _QDRANT_EMBEDDER is None:
                    from fastembed import TextEmbedding  # may raise ImportError

                    last_err = None
                    for _name in _EMBED_CANDIDATES:
                        try:
                            emb = TextEmbedding(model_name=_name)
                            dim = len(list(emb.embed(["test"]))[0])  # verify + real dim
                            _QDRANT_EMBEDDER = emb
                            _QDRANT_VECTOR_SIZE = dim
                            _E5_MODEL_NAME = _name
                            logger.info("fastembed model loaded: %s (dim=%d)", _name, dim)
                            break
                        except Exception as _e:
                            last_err = _e
                            continue
                    if _QDRANT_EMBEDDER is None:
                        logger.warning("no supported fastembed model: %s", last_err)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("fastembed load thread error: %s", e)
        finally:
            done.set()

    threading.Thread(target=_load, name="kb-embed-load", daemon=True).start()
    done.wait(timeout_s)
    if _QDRANT_EMBEDDER is None:
        _QDRANT_DISABLED = True
        raise RuntimeError(
            f"fastembed model not ready within {timeout_s:.0f}s "
            "(likely runtime HF download) — qdrant disabled for this process"
        )
    return _QDRANT_EMBEDDER


def _get_qdrant_client():
    """
    Lazy global QdrantClient singleton. Connection ping + collection ensure +
    namespace payload index — sab yahin, ek hi baar. Failure par raise karta
    hai (caller/factory catch karke Chroma/keyword par fall back karta hai).
    """
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        with _QDRANT_LOCK:
            if _QDRANT_CLIENT is None:
                from qdrant_client import QdrantClient  # may raise ImportError
                from qdrant_client import models as qmodels

                _get_qdrant_embedder()  # sets _QDRANT_VECTOR_SIZE to the real model dim
                url = _get_qdrant_url()
                if not url:
                    raise RuntimeError("QDRANT_URL not configured")
                client = QdrantClient(url=url, timeout=5)
                # ping — server unreachable ho to yahin raise ho jata hai
                client.get_collections()
                _exists = client.collection_exists(_QDRANT_COLLECTION)
                if _exists:
                    # dim mismatch (embedding model changed) -> recreate fresh
                    try:
                        _cur = client.get_collection(_QDRANT_COLLECTION).config.params.vectors.size
                        if _cur != _QDRANT_VECTOR_SIZE:
                            client.delete_collection(_QDRANT_COLLECTION)
                            _exists = False
                    except Exception:
                        pass
                if not _exists:
                    try:
                        client.create_collection(
                            collection_name=_QDRANT_COLLECTION,
                            vectors_config=qmodels.VectorParams(
                                size=_QDRANT_VECTOR_SIZE,
                                distance=qmodels.Distance.COSINE,
                            ),
                        )
                    except Exception:
                        pass  # parallel-create race — collection ab exist karti hai
                try:
                    client.create_payload_index(
                        collection_name=_QDRANT_COLLECTION,
                        field_name="namespace",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                except Exception:
                    pass  # index already exists — ignore (idempotent)
                _QDRANT_CLIENT = client
    return _QDRANT_CLIENT


class _QdrantIndex:
    """
    Qdrant retriever — same internal interface as _ChromaIndex/_KeywordIndex
    (add / search / size). Sab namespaces EK shared "kb_main" collection me
    jaate hain; isolation payload filter (namespace ==) se hota hai.

    Namespace examples: "solar_residential", "client:abc123", "_global".
    """

    def __init__(self, namespace: str = "default") -> None:
        # In dono me se koi bhi raise kare (deps missing / server down) to
        # KnowledgeBase._build_index catch karke agle backend par chala jata hai.
        self._client = _get_qdrant_client()
        self._embedder = _get_qdrant_embedder()
        self._namespace = namespace or "default"

    # -- internals -- #
    def _embed(self, text: str) -> list[float]:
        vec = next(iter(self._embedder.embed([text])))
        return [float(x) for x in vec]

    def _ns_filter(self):
        from qdrant_client import models as qmodels

        return qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="namespace",
                    match=qmodels.MatchValue(value=self._namespace),
                )
            ]
        )

    # -- index interface -- #
    @property
    def size(self) -> int:
        try:
            res = self._client.count(
                collection_name=_QDRANT_COLLECTION,
                count_filter=self._ns_filter(),
                exact=True,
            )
            return int(getattr(res, "count", 0) or 0)
        except Exception:
            return 0

    def add(self, text: str, source: str = "", embed_prefix: str = "") -> None:
        # raise hone par KnowledgeBase.add_documents chunk skip kar deta hai
        from qdrant_client import models as qmodels

        passage = f"{embed_prefix}\n{text}".strip() if embed_prefix else text
        self._client.upsert(
            collection_name=_QDRANT_COLLECTION,
            points=[
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    # e5 requirement: documents ko "passage: " prefix
                    vector=self._embed(f"passage: {passage}"),
                    payload={
                        "namespace": self._namespace,
                        "text": text,
                        "source": source or "",
                    },
                )
            ],
        )

    def search(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        try:
            res = self._client.query_points(
                collection_name=_QDRANT_COLLECTION,
                # e5 requirement: queries ko "query: " prefix
                query=self._embed(f"query: {query}"),
                query_filter=self._ns_filter(),
                limit=max(1, k),
                with_payload=True,
            )
            points = getattr(res, "points", None) or []
        except Exception as e:  # pragma: no cover
            logger.debug(f"qdrant query failed: {e}")
            return []
        out: list[dict[str, Any]] = []
        for p in points:
            payload = getattr(p, "payload", None) or {}
            out.append(
                {
                    "text": str(payload.get("text", "") or ""),
                    "score": float(getattr(p, "score", 0.0) or 0.0),
                    "source": str(payload.get("source", "") or ""),
                }
            )
        return out


# --------------------------------------------------------------------------- #
# KnowledgeBase — public API
# --------------------------------------------------------------------------- #
# safe fallback line jab kuch relevant na mile — kabhi hallucinate mat karo.
_SAFE_FALLBACK = "Achha sawaal — main aapke liye exact detail team se confirm karwa deti hoon."
# agar query short na ho aur retrieved score is se neeche ho to "no answer" maano.
_MIN_GROUND_SCORE = 0.04


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _contextual_prefix(chunk: str, namespace: str, source: str) -> str:
    """Anthropic-style contextual prefix for embedding (display text unchanged)."""
    ns = namespace or "default"
    src = source or "kb"
    meta = f"[{ns}|{src}]"
    if _env_flag("USE_CONTEXTUAL_INGEST_LLM"):
        try:
            import asyncio

            async def _go() -> str:
                from app.voice_agent import free_ai

                reply, _ = await asyncio.wait_for(
                    free_ai.chat(
                        system=(
                            "Write ONE short sentence describing this knowledge chunk "
                            "for semantic search. Hinglish or English. No quotes."
                        ),
                        messages=[{"role": "user", "content": chunk[:900]}],
                        max_tokens=45,
                        temperature=0.0,
                    ),
                    timeout=10.0,
                )
                return (reply or "").strip()

            try:
                asyncio.get_running_loop()
                return meta  # async caller — metadata-only (no nested loop)
            except RuntimeError:
                line = asyncio.run(_go())
                return line or meta
        except Exception:
            return meta
    if _env_flag("USE_CONTEXTUAL_INGEST"):
        return meta
    return ""


class KnowledgeBase:
    """
    Per-namespace RAG knowledge base for the voice agent.

    Har namespace (client/niche) ka apna independent index hota hai. Internally
    Qdrant (agar QDRANT_URL configured + reachable), warna Chroma (agar real
    embeddings available), warna pure-python keyword index use hota hai —
    caller ko farq nahi padta, API same rehti hai.

    Public API:
        add_documents(docs, source=None, namespace="default")
        retrieve(query, k=3, namespace="default") -> list[{text, score, source}]
        grounded_answer(query, namespace="default") -> str
        stats() -> dict
    """

    def __init__(self, prefer_chroma: bool = True) -> None:
        self._prefer_chroma = prefer_chroma
        self._lock = threading.RLock()
        # namespace -> retriever (_QdrantIndex | _ChromaIndex | _KeywordIndex)
        self._indexes: dict[str, Any] = {}
        # namespace -> backend label ("qdrant" | "chroma" | "keyword")
        self._backends: dict[str, str] = {}

    # ----------------------- index management ----------------------- #
    def _get_index(self, namespace: str):
        ns = namespace or "default"
        with self._lock:
            if ns in self._indexes:
                return self._indexes[ns]
            index, backend = self._build_index(ns)
            self._indexes[ns] = index
            self._backends[ns] = backend
            logger.info(f"📚 KB namespace '{ns}' ready (backend={backend})")
            return index

    def _build_index(self, namespace: str):
        """
        Backend selection order:
          1. Qdrant — sirf jab settings.qdrant_url set ho AND qdrant-client +
             fastembed import ho jayein AND server ping ok ho.
          2. Chroma — agar real (non-mock) embeddings available hon.
          3. Pure-python keyword index — hamesha kaam karta hai (final fallback).
        Kabhi raise nahi karta — app crash nahi hota.
        """
        qi = self._try_qdrant(namespace)
        if qi is not None:
            return qi, "qdrant"
        if self._prefer_chroma:
            try:
                ci = _ChromaIndex(namespace)
                if ci.real_embeddings:
                    return ci, "chroma"
                logger.info(
                    "KB: Chroma available but embedder is mock — using keyword fallback "
                    "for reliable grounding."
                )
            except Exception as e:
                logger.info(f"KB: Chroma unavailable ({e}); using keyword fallback.")
        return _KeywordIndex(), "keyword"

    @staticmethod
    def _try_qdrant(namespace: str):
        """_QdrantIndex agar configured + reachable ho, warna None (no crash)."""
        global _QDRANT_DISABLED
        if _QDRANT_DISABLED or not _get_qdrant_url():
            return None
        try:
            return _QdrantIndex(namespace)
        except Exception as e:
            # deps missing / server down — is process me dobara probe mat karo
            _QDRANT_DISABLED = True
            logger.info(f"KB: Qdrant unavailable ({e}); falling back to Chroma/keyword.")
            return None

    def backend(self, namespace: str = "default") -> str:
        """Which backend a namespace uses: 'qdrant', 'chroma' or 'keyword'."""
        self._get_index(namespace)
        return self._backends.get(namespace or "default", "keyword")

    # ----------------------- public API ----------------------- #
    def add_documents(
        self,
        docs: list[str | dict[str, Any]],
        source: str | None = None,
        namespace: str = "default",
    ) -> int:
        """
        Documents ko chunk + store karo.

        Args:
            docs: list of strings, ya dicts. Dict me 'text' required;
                  optional 'source' (per-doc source override).
            source: default source label (dict ka 'source' isko override karta hai).
            namespace: client/niche scope.

        Returns:
            Number of chunks added.
        """
        if not docs:
            return 0
        index = self._get_index(namespace)
        added = 0
        ctx_on = _env_flag("USE_CONTEXTUAL_INGEST") or _env_flag("USE_CONTEXTUAL_INGEST_LLM")
        with self._lock:
            for d in docs:
                if isinstance(d, dict):
                    text = str(d.get("text", "") or "")
                    src = str(d.get("source", source or "") or "")
                else:
                    text = str(d or "")
                    src = source or ""
                if not text.strip():
                    continue
                for chunk in chunk_text(text):
                    try:
                        prefix = _contextual_prefix(chunk, namespace, src) if ctx_on else ""
                        index.add(chunk, source=src, embed_prefix=prefix)
                        added += 1
                    except Exception as e:  # pragma: no cover
                        logger.warning(f"KB add failed, skipping chunk: {e}")
        if added:
            logger.info(f"KB '{namespace}': added {added} chunk(s) from source='{source}'")
        return added

    def retrieve(
        self,
        query: str,
        k: int = 3,
        namespace: str = "default",
        rerank: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query ke top-k most relevant chunks laao.

        ``rerank=None`` (default) → rerank sirf jab ``USE_RERANKER=1`` ho.
        Voice/live paths ko ``rerank=False`` pass karo (latency).

        Returns:
            list[dict] — each: {"text": str, "score": float, "source": str}.
        """
        if not (query or "").strip():
            return []
        index = self._get_index(namespace)
        use_rerank = rerank if rerank is not None else _env_flag("USE_RERANKER")
        pool = k
        if use_rerank:
            try:
                pool = max(k, int(os.getenv("RERANK_POOL_SIZE", "50") or 50))
            except Exception:
                pool = max(k, 50)
        try:
            with self._lock:
                results = index.search(query, k=max(1, pool))
            if use_rerank and results:
                from app.ml.reranker import rerank_hits

                results = rerank_hits(query, results, top_k=max(1, k))
            else:
                results = (results or [])[: max(1, k)]
            return results or []
        except Exception as e:  # pragma: no cover
            logger.warning(f"KB retrieve failed: {e}")
            return []

    def grounded_answer(
        self,
        query: str,
        namespace: str = "default",
        k: int = 3,
    ) -> str:
        """
        Retrieved chunks se hi ek concise grounded answer banao. Kuch relevant
        na mile to safe fallback — kabhi hallucinate nahi.

        Returns:
            A short answer string built ONLY from stored knowledge, or the safe
            "team se confirm karwa deti hoon" fallback.
        """
        hits = self.retrieve(query, k=k, namespace=namespace)
        if not hits:
            return _SAFE_FALLBACK

        top = hits[0]
        # relevance gate — kamzor match par mat bharose karo.
        if top.get("score", 0.0) < _MIN_GROUND_SCORE:
            return _SAFE_FALLBACK

        # Build a concise answer: best chunk, + ek aur agar woh kaafi strong ho.
        answer = _trim_sentence(top["text"])
        if len(hits) > 1:
            second = hits[1]
            if (
                second.get("score", 0.0) >= top.get("score", 0.0) * 0.6
                and second["text"].strip() != top["text"].strip()
            ):
                extra = _trim_sentence(second["text"])
                # avoid near-duplicate concatenation
                if extra.lower() not in answer.lower():
                    answer = f"{answer} {extra}".strip()
        return answer or _SAFE_FALLBACK

    def stats(self, namespace: str | None = None) -> dict[str, Any]:
        """KB stats — namespaces, backend, chunk counts."""
        with self._lock:
            if namespace is not None:
                idx = self._indexes.get(namespace)
                return {
                    "namespace": namespace,
                    "backend": self._backends.get(namespace, "n/a"),
                    "chunks": getattr(idx, "size", 0) if idx else 0,
                }
            return {
                "namespaces": list(self._indexes.keys()),
                "backends": dict(self._backends),
                "chunks": {ns: getattr(idx, "size", 0) for ns, idx in self._indexes.items()},
            }


def _trim_sentence(text: str, max_chars: int = 220) -> str:
    """Voice ke liye chhota rakho — pehla 1-2 sentence, length-capped."""
    text = (text or "").strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.?!।])\s+", text)
    out = sentences[0].strip()
    if len(out) < max_chars and len(sentences) > 1:
        cand = f"{out} {sentences[1].strip()}".strip()
        if len(cand) <= max_chars:
            out = cand
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0].strip() + "…"
    return out


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #
_KB_SINGLETON: KnowledgeBase | None = None
_KB_LOCK = threading.Lock()


def get_knowledge_base() -> KnowledgeBase:
    """
    Process-wide singleton KnowledgeBase. Pehli baar call par banta hai.

    Usage:
        kb = get_knowledge_base()
        kb.add_documents([...], namespace="solar_commercial")
        ans = kb.grounded_answer("pricing?", namespace="solar_commercial")
    """
    global _KB_SINGLETON
    if _KB_SINGLETON is None:
        with _KB_LOCK:
            if _KB_SINGLETON is None:
                _KB_SINGLETON = KnowledgeBase()
    return _KB_SINGLETON


__all__ = [
    "KnowledgeBase",
    "get_knowledge_base",
    "chunk_text",
    "tokenize",
]
