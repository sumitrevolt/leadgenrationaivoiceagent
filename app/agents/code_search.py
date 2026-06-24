"""Codebase semantic search for engineering agents — Kilo-Code "codebase_search" parity.

Kilo Code (open-source AI coding agent) ka standout engineering feature: pura repo
embeddings me index karke agents `codebase_search` se ACTUAL relevant code uthate hain
(ek file guess karke blind-prompt nahi). Yahi gap is project me tha — `CodebaseIndexer`
already built tha par uska search-path orphan + toota hua (non-existent method call) aur
Vikram code_upgrader sirf ek guessed `area` + blind-LLM pe proposal banata tha.

Yeh module woh capability AI staff ko deta hai (read-only, never-raise, gated):
  - Vikram code_upgrader → proposals ab retrieved real code se grounded (flag ON pe).
  - coordinator engineering crew / future agents → same helper reuse kar sakte hain.
  - Admin GET /api/growth/upgrader/code-search → verify + ad-hoc lookup.

Design (project patterns):
  - Index build daily training_scheduler run pe piggyback karta (alag job nahi).
  - `enabled()` sirf AUTOMATIC agent-grounding ko gate karta — default OFF = zero
    behaviour change. `search()` khud hamesha safe-callable (admin endpoint ke liye).
  - Live business-KB Qdrant se DECOUPLED: indexer ka apna ChromaDB collection
    ("code_patterns") use hota — niche/client knowledge ko kabhi nahi chhuta.
  - Index khaali / deps missing / koi error → [] (kabhi raise nahi).

Flag: CODE_SEARCH=1
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SNIPPET_CAP = 800


def enabled() -> bool:
    """Gates AUTOMATIC agent grounding (Vikram). Admin search endpoint flag-independent."""
    return (os.getenv("CODE_SEARCH") or "").strip().lower() in ("1", "true", "yes")


async def search(
    query: str,
    k: int = 6,
    language: str | None = None,
    agent_domain: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic code search → normalized hits.

    Returns list of {file, start_line, end_line, score, snippet, language, domain}.
    Never raises; returns [] if query empty / index empty / deps missing.
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        from app.ml.codebase_indexer import get_codebase_indexer

        indexer = get_codebase_indexer()
        rows = await indexer.search_code(
            query=q,
            agent_domain=agent_domain,
            language=language,
            limit=max(1, min(int(k or 6), 20)),
        )
        return [r for r in (rows or []) if r.get("file")][: max(1, int(k or 6))]
    except Exception as e:  # pragma: no cover - defensive (never break the caller)
        logger.debug(f"code_search failed: {e}")
        return []


def grounding_block(hits: list[dict[str, Any]], max_chars: int = 2400) -> str:
    """Format hits as a compact LLM grounding context (file refs + code snippets)."""
    if not hits:
        return ""
    out: list[str] = []
    used = 0
    for h in hits:
        head = (
            f"# {h.get('file')}:{h.get('start_line')}-{h.get('end_line')} "
            f"(score {round(float(h.get('score') or 0.0), 2)})"
        )
        body = (h.get("snippet") or "")[:_SNIPPET_CAP]
        block = head + "\n" + body
        if used + len(block) > max_chars:
            break
        out.append(block)
        used += len(block)
    if not out:
        return ""
    return (
        "Relevant existing code (cite these exact file paths / line ranges in your fix):\n\n"
        + "\n\n".join(out)
    )


__all__ = ["enabled", "search", "grounding_block"]
