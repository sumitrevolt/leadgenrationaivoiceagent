"""Objection extractor — transcripts + replies → Qdrant objections:{niche} namespace.

GATED OBJECTION_KB=1 (default ON). Never raises.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_EXTRACTED = os.path.join("data", "objection_patterns.jsonl")


def _enabled() -> bool:
    v = os.environ.get("OBJECTION_KB", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


_OBJECTION_CUES = re.compile(
    r"(mahnga|mehnga|expensive|budget|soch|baad me|not interested|nahi chahiye|"
    r"already have|competitor|trust nahi|scam|time nahi|busy|call mat)",
    re.I,
)


async def extract_from_transcript(
    messages: list[dict[str, Any]],
    *,
    niche: str = "general",
    call_id: str = "",
) -> list[dict[str, Any]]:
    """Rule-based objection phrases from call transcript turns."""
    if not _enabled():
        return []
    found: list[dict[str, Any]] = []
    for m in messages or []:
        role = str(m.get("role") or "").lower()
        if role not in ("user", "customer", "caller"):
            continue
        text = str(m.get("content") or m.get("text") or "").strip()
        if not text or not _OBJECTION_CUES.search(text):
            continue
        rec = {
            "niche": niche,
            "text": text[:500],
            "source": "voice",
            "call_id": call_id,
        }
        found.append(rec)
        _append(rec)
    if found:
        await _ingest_qdrant(found, niche)
    return found


async def extract_from_reply(text: str, *, niche: str = "general", intent: str = "") -> list[dict[str, Any]]:
    if not _enabled() or not text:
        return []
    if intent in ("objection", "not_interested", "unsubscribe") or _OBJECTION_CUES.search(text):
        rec = {"niche": niche, "text": text[:500], "source": "email", "intent": intent}
        _append(rec)
        await _ingest_qdrant([rec], niche)
        return [rec]
    return []


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_EXTRACTED, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


async def _ingest_qdrant(records: list[dict[str, Any]], niche: str) -> None:
    try:
        from app.voice_agent.knowledge_base import KnowledgeBase

        kb = KnowledgeBase()
        ns = f"objections:{niche or 'general'}"
        docs = [
            f"Objection ({r.get('source')}): {r.get('text', '')}"
            for r in records
            if r.get("text")
        ]
        if docs:
            kb.add_documents(docs, source="objection_extractor", namespace=ns)
    except Exception as e:
        logger.debug("[objection_extractor] qdrant skip: %s", e)


async def scan_recent_transcripts(limit: int = 20) -> dict[str, Any]:
    """Batch scan data/call_transcripts/*.jsonl for objections."""
    total = 0
    tdir = Path("data") / "call_transcripts"
    if not tdir.is_dir():
        return {"ok": True, "extracted": 0}
    files = sorted(tdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    msgs = rec.get("messages") or rec.get("transcript") or []
                    niche = str(rec.get("niche") or "general")
                    cid = str(rec.get("call_id") or fp.stem)
                    found = await extract_from_transcript(msgs, niche=niche, call_id=cid)
                    total += len(found)
        except Exception:
            pass
    return {"ok": True, "extracted": total, "files_scanned": len(files)}


__all__ = ["extract_from_transcript", "extract_from_reply", "scan_recent_transcripts"]
