"""Any file / URL → clean LLM-ready Markdown via **Microsoft MarkItDown** (MIT).

MarkItDown converts PDF / DOCX / PPTX / XLSX / HTML / CSV / images into clean
Markdown in one call — perfect for feeding client brochures, menus, price lists and
web pages into the LLM / RAG (LightRAG) pipeline, and it cuts token usage ~30-50%
vs raw text. Lightweight, CPU, no GPU.

Defensive: if markitdown isn't installed, returns "" — never raises.

Use:
  from app.lead_scraper.to_markdown import to_markdown
  md = to_markdown("/path/menu.pdf")          # or a URL, .docx, .pptx, .xlsx ...
  if md:
      await get_graph_rag().ainsert(md, namespace="client:42")   # feed the KB / graph
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def available() -> bool:
    try:
        import markitdown  # noqa: F401

        return True
    except Exception:
        return False


def to_markdown(source: str) -> str:
    """Convert a local file path or URL to clean Markdown. "" if unavailable/failed."""
    if not (source or "").strip():
        return ""
    try:
        from markitdown import MarkItDown

        result = MarkItDown().convert(source)
        text = getattr(result, "text_content", None) or getattr(result, "markdown", None) or ""
        return str(text).strip()
    except Exception as exc:
        logger.info("to_markdown failed for %s (%s)", source, exc)
        return ""


__all__ = ["available", "to_markdown"]
