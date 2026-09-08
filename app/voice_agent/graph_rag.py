"""Knowledge-graph RAG via **LightRAG** (HKUDS) — optional, opt-in, never-crash.

Why LightRAG (not Microsoft GraphRAG): it builds a *lightweight* entity/relation
graph during ingest and supports **incremental append** (no full rebuild), with far
fewer LLM calls than GraphRAG — which matters because we run on free LLM quotas. It
plugs into our existing free stack: LLM via ``free_ai`` (Cerebras→Groq→…), embeddings
via the same fastembed model the Qdrant KB uses. Per-namespace graph store under
``data/lightrag/<namespace>`` so niche/client graphs stay separate.

This sits ALONGSIDE the vector KB (``knowledge_base.py``) — it does not replace it.
Use it when answers depend on relationships/causality across documents (e.g. a client's
full business profile, multi-fact niche knowledge). OFF by default; any missing dep /
init error / query error disables it and returns a safe empty result — never raises.

Enable:
  pip install "lightrag-hku"          # + fastembed (already used by the KB)
  export USE_LIGHTRAG=1
  # plus a free provider key already used by free_ai (CEREBRAS_API_KEY / GROQ_API_KEY)

Use (after enabling):
  from app.voice_agent.graph_rag import get_graph_rag
  await get_graph_rag().ainsert(business_profile_text, namespace="client:42")
  res = await get_graph_rag().aquery("Is client ka USP aur target area kya hai?", namespace="client:42")
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_EMBED_DIM = int(os.getenv("LIGHTRAG_EMBED_DIM", "384"))  # multilingual-e5-small = 384
_BASE_DIR = os.getenv("LIGHTRAG_DIR", "data/lightrag")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_ns(namespace: str) -> str:
    keep = "".join(c if c.isalnum() else "_" for c in (namespace or "default"))
    return keep[:80] or "default"


class GraphRAG:
    """Lazy, defensive wrapper over per-namespace LightRAG instances."""

    def __init__(self) -> None:
        self._enabled = _flag("USE_LIGHTRAG")
        self._broken = False
        self._instances: dict[str, Any] = {}
        self._embedder = None
        self._embed_func = None

    # ---- shared free-stack adapters (LLM + embeddings) ----
    async def _llm_func(self, prompt, system_prompt=None, history_messages=None, **kwargs):
        from app.voice_agent import free_ai

        msgs = list(history_messages or [])
        msgs.append({"role": "user", "content": str(prompt)})
        reply, _ = await free_ai.chat(
            system=system_prompt or "",
            messages=msgs,
            max_tokens=int(kwargs.get("max_tokens", 1024)),
            temperature=0.2,
        )
        return reply or ""

    def _get_embedder(self):
        if self._embedder is None:
            # reuse the KB's fastembed model so graph + vector share one embedding space
            from app.voice_agent.knowledge_base import _get_qdrant_embedder

            self._embedder = _get_qdrant_embedder()
        return self._embedder

    def _make_embedding_func(self):
        import numpy as np
        from lightrag.utils import EmbeddingFunc

        async def _embed(texts: list[str]):
            emb = self._get_embedder()
            vecs = list(emb.embed(list(texts)))
            return np.array([list(v) for v in vecs], dtype="float32")

        return EmbeddingFunc(embedding_dim=_EMBED_DIM, max_token_size=512, func=_embed)

    async def _instance(self, namespace: str):
        if not self._enabled or self._broken:
            return None
        ns = _safe_ns(namespace)
        if ns in self._instances:
            return self._instances[ns]
        try:
            from lightrag import LightRAG

            wd = os.path.join(_BASE_DIR, ns)
            os.makedirs(wd, exist_ok=True)
            rag = LightRAG(
                working_dir=wd,
                llm_model_func=self._llm_func,
                embedding_func=self._make_embedding_func(),
            )
            # newer LightRAG requires explicit async storage init
            if hasattr(rag, "initialize_storages"):
                await rag.initialize_storages()
                try:
                    from lightrag.kg.shared_storage import initialize_pipeline_status

                    await initialize_pipeline_status()
                except Exception:
                    pass
            self._instances[ns] = rag
            logger.info("GraphRAG: LightRAG ready for ns=%s", ns)
            return rag
        except Exception as exc:  # dep/init drift -> disable forever, never crash
            self._broken = True
            logger.info("GraphRAG disabled (init failed: %s)", exc)
            return None

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._broken

    async def ainsert(self, text: str, namespace: str = "default") -> bool:
        """Add text into the knowledge graph for `namespace`. True on success."""
        if not (text or "").strip():
            return False
        rag = await self._instance(namespace)
        if rag is None:
            return False
        try:
            await rag.ainsert(text)
            return True
        except Exception as exc:
            logger.info("GraphRAG.ainsert error: %s", exc)
            return False

    async def aquery(self, question: str, namespace: str = "default", mode: str = "hybrid") -> dict:
        """Graph-grounded answer. Always returns a dict, never raises.

        {"ok": bool, "answer": str, "namespace": str, "mode": str}
        ok=False with empty answer means disabled/unavailable -> caller should fall
        back to the vector KB (knowledge_base.retrieve / grounded_answer).
        """
        rag = await self._instance(namespace)
        if rag is None:
            return {"ok": False, "answer": "", "namespace": namespace, "mode": mode}
        try:
            from lightrag import QueryParam

            ans = await rag.aquery(question, param=QueryParam(mode=mode))
            return {"ok": True, "answer": str(ans or ""), "namespace": namespace, "mode": mode}
        except Exception as exc:
            logger.info("GraphRAG.aquery error: %s", exc)
            return {"ok": False, "answer": "", "namespace": namespace, "mode": mode}


_singleton: GraphRAG | None = None


def get_graph_rag() -> GraphRAG:
    """Process-wide GraphRAG (lazy singleton)."""
    global _singleton
    if _singleton is None:
        _singleton = GraphRAG()
    return _singleton


__all__ = ["GraphRAG", "get_graph_rag"]
