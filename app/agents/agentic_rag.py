"""Agentic RAG — a self-correcting (CRAG-style) retrieval loop over the existing
Qdrant knowledge base. Optional, opt-in, never-crash.

Plain vector RAG retrieves once and hopes the chunks are relevant. This adds the
*agentic* steps used in production RAG (retrieval grading + corrective RAG):

    retrieve → grade relevance → (if weak) rewrite the query and retry → generate a
    grounded answer (or an honest "not in KB" fallback).

It reuses what we already have — ``knowledge_base.retrieve`` (Qdrant/Chroma/keyword)
for retrieval and ``free_ai.chat`` (Cerebras→Groq→…) for grading/rewriting/answering —
so there are **no new dependencies**. Everything is async and defensive: any LLM/KB
hiccup degrades to the plain KB path; it never raises.

OFF by default. Enable with ``USE_AGENTIC_RAG=1`` (a provider key for free_ai is what
makes grading/rewriting actually run; without it, it still returns the best KB hit).

Use:
  from app.agents.agentic_rag import get_agentic_rag
  res = await get_agentic_rag().answer("solar subsidy kitni milti hai?", namespace="niche:solar_residential")
  # -> {"ok", "answer", "grounded", "used_query", "rewrites", "sources"}
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MIN_SCORE = float(os.getenv("AGENTIC_RAG_MIN_SCORE", "0.30"))
_SAFE = "Yeh info abhi knowledge base me nahi hai — team se confirm karwa deti hoon."


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


class AgenticRAG:
    """Self-correcting retrieval over the vector KB. Always returns a dict."""

    def __init__(self) -> None:
        self._enabled = _flag("USE_AGENTIC_RAG")

    def _kb(self):
        from app.voice_agent.knowledge_base import get_knowledge_base

        return get_knowledge_base()

    @staticmethod
    def _ctx(hits: list[dict]) -> str:
        return "\n".join(f"- {(h.get('text') or '').strip()}" for h in hits if h.get("text"))

    async def _grade(self, query: str, hits: list[dict]) -> bool:
        """LLM relevance gate. Falls back to the KB score if the LLM is unavailable."""
        if not hits:
            return False
        top = hits[0].get("score", 0.0) or 0.0
        try:
            from app.voice_agent import free_ai

            reply, _ = await free_ai.chat(
                system="You grade whether the CONTEXT can answer the QUESTION. Reply with only YES or NO.",
                messages=[
                    {"role": "user", "content": f"QUESTION: {query}\n\nCONTEXT:\n{self._ctx(hits)}"}
                ],
                max_tokens=3,
                temperature=0.0,
            )
            if reply:
                return reply.strip().upper().startswith("Y")
        except Exception as exc:
            logger.debug("AgenticRAG._grade error: %s", exc)
        return top >= _MIN_SCORE  # fallback: trust the retriever score

    async def _rewrite(self, query: str) -> str:
        """Ask the LLM for a better search query; fall back to the original."""
        try:
            from app.voice_agent import free_ai

            reply, _ = await free_ai.chat(
                system="Rewrite the user's question into a better keyword search query for a "
                "knowledge base. Output ONLY the rewritten query, no quotes.",
                messages=[{"role": "user", "content": query}],
                max_tokens=40,
                temperature=0.3,
            )
            r = (reply or "").strip().strip('"')
            return r or query
        except Exception:
            return query

    async def _generate(self, query: str, hits: list[dict]) -> str:
        """Grounded answer strictly from context; safe fallback if the LLM is down."""
        try:
            from app.voice_agent import free_ai

            reply, _ = await free_ai.chat(
                system="Answer the question ONLY from the context, concise (max 2 sentences), in "
                "Hinglish (Roman script). If the context does not contain the answer, say you'll "
                "confirm with the team. Do not invent facts.",
                messages=[
                    {"role": "user", "content": f"QUESTION: {query}\n\nCONTEXT:\n{self._ctx(hits)}"}
                ],
                max_tokens=120,
                temperature=0.3,
            )
            if reply and reply.strip():
                return reply.strip()
        except Exception as exc:
            logger.debug("AgenticRAG._generate error: %s", exc)
        # deterministic fallback: best chunk trimmed
        if hits and hits[0].get("text"):
            return hits[0]["text"].strip()[:220]
        return _SAFE

    async def answer(
        self, query: str, namespace: str = "default", k: int = 4, max_rewrites: int = 1
    ) -> dict:
        """Run retrieve→grade→(rewrite→retry)→generate. Never raises."""
        out = {
            "ok": False,
            "answer": _SAFE,
            "grounded": False,
            "used_query": query,
            "rewrites": 0,
            "sources": [],
            "namespace": namespace,
        }
        if not (query or "").strip():
            return out
        try:
            kb = self._kb()
            cur = query
            hits: list[dict] = []
            rewrites = 0
            # corrective loop: grade, and rewrite+retry while weak
            while True:
                # off-loop: kb.retrieve is sync (embed+Qdrant); on the loop it blocks
                # all concurrent requests and makes the callers' asyncio.wait_for deadline
                # illusory (wait_for can't interrupt a sync section).
                hits = await asyncio.to_thread(kb.retrieve, cur, k=k, namespace=namespace) or []
                good = (
                    await self._grade(query, hits)
                    if self._enabled
                    else bool(hits and (hits[0].get("score", 0.0) or 0.0) >= _MIN_SCORE)
                )
                if good or rewrites >= max_rewrites or not self._enabled:
                    break
                cur = await self._rewrite(query)
                rewrites += 1

            out["used_query"] = cur
            out["rewrites"] = rewrites
            out["sources"] = [
                {
                    "source": h.get("source", ""),
                    "score": round(float(h.get("score", 0.0) or 0.0), 3),
                }
                for h in hits[:k]
            ]
            grounded = bool(hits and (hits[0].get("score", 0.0) or 0.0) >= _MIN_SCORE)
            out["grounded"] = grounded
            out["answer"] = await self._generate(query, hits) if hits else _SAFE
            out["ok"] = True
            return out
        except Exception as exc:
            logger.info("AgenticRAG.answer error: %s", exc)
            return out


_singleton: AgenticRAG | None = None


def get_agentic_rag() -> AgenticRAG:
    """Process-wide AgenticRAG (lazy singleton)."""
    global _singleton
    if _singleton is None:
        _singleton = AgenticRAG()
    return _singleton


__all__ = ["AgenticRAG", "get_agentic_rag"]
