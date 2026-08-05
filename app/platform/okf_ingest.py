"""OKF → Qdrant ingest bridge (ADR-119 Phase-1).

Additive, flag-gated (``OKF_INGEST_ENABLED`` OFF default). Uses existing
``KnowledgeBase.add_documents`` into namespace ``okf`` with per-file sources
``okf:{relpath}`` + replace_source so re-ingest is idempotent.

Never writes customer namespaces. Never embeds secrets (bundle loader blocks).
"""

from __future__ import annotations

from typing import Any

from app.platform import okf_bundle as bundle

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


def _chunk_payload(doc: bundle.OkfDoc) -> str:
    """Prefix title/type so dense retrieval has structured cues."""
    head = f"# {doc.title}\nType: {doc.doc_type}\nPath: {doc.relpath}\n"
    if doc.description:
        head += f"Description: {doc.description}\n"
    if doc.tags:
        head += f"Tags: {', '.join(doc.tags)}\n"
    return f"{head}\n{doc.body}".strip()


def dry_run(*, root=None) -> dict[str, Any]:
    docs = bundle.list_docs(root=root)
    ready = [d for d in docs if d.ok and d.body.strip()]
    skipped = [
        {"relpath": d.relpath, "reason": d.blocked_reason or "empty_body"}
        for d in docs
        if (not d.ok) or (not d.body.strip())
    ]
    return {
        "dry_run": True,
        "ingest_enabled": bundle.ingest_enabled(),
        "namespace": bundle.OKF_NAMESPACE,
        "ready_count": len(ready),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "sources": [d.kb_source for d in ready],
        "approx_chars": sum(len(_chunk_payload(d)) for d in ready),
    }


def ingest(*, root=None, force: bool = False) -> dict[str, Any]:
    """Ingest OKF docs into kb_main namespace ``okf``. Fail-closed unless armed."""
    if not force and not bundle.ingest_enabled():
        return {
            "ok": False,
            "reason": "okf_ingest_disabled",
            "hint": "Set OKF_INGEST_ENABLED=1 to arm; dry_run stays available.",
            "dry_run": dry_run(root=root),
        }

    docs = [d for d in bundle.list_docs(root=root) if d.ok and d.body.strip()]
    from app.voice_agent.knowledge_base import get_knowledge_base

    kb = get_knowledge_base()
    per_file: list[dict[str, Any]] = []
    total = 0
    errors: list[str] = []

    for doc in docs:
        try:
            n = kb.add_documents(
                [_chunk_payload(doc)],
                source=doc.kb_source,
                namespace=bundle.OKF_NAMESPACE,
                replace_source=True,
            )
            total += int(n or 0)
            per_file.append({"source": doc.kb_source, "chunks": int(n or 0)})
        except Exception as e:
            msg = f"{doc.relpath}: {e}"
            errors.append(msg)
            logger.warning("OKF ingest failed for %s: %s", doc.relpath, e)

    return {
        "ok": not errors,
        "namespace": bundle.OKF_NAMESPACE,
        "files": len(docs),
        "chunks": total,
        "per_file": per_file,
        "errors": errors,
        "backend": kb.backend(bundle.OKF_NAMESPACE),
    }


def recall(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Retrieve curated OKF chunks only (namespace filter). Fail-open → []."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        return get_knowledge_base().retrieve(
            q, k=max(1, min(int(k or 5), 20)), namespace=bundle.OKF_NAMESPACE
        )
    except Exception as e:
        logger.debug("OKF recall skip: %s", e)
        return []
