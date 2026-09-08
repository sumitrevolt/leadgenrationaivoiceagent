"""Memory API — Rowboat-inspired compounding memory (vault + call-prep + live notes).

Routes (admin, mount `app.include_router(memory_router, prefix="/api")` → /api/memory/*):
  GET    /memory/entities?kind=          — memory files list (prospects|clients|topics)
  GET    /memory/entity?kind=&key=       — ek entity ka raw markdown
  PUT    /memory/entity                  — human edit (full overwrite, 64KB cap)
  POST   /memory/sync                    — jsonl stores → memory sync (manual run)
  GET    /memory/prep?phone=&client_id=  — call-prep Hinglish brief (dialer/sales)
  GET    /memory/topics · POST /memory/topics · DELETE /memory/topics/{id}
  POST   /memory/topics/{id}/refresh     — ek topic ka aaj ka live-note update

Sab lazy-import + never-raise (modules error dict dete). Flags: MEMORY_VAULT /
LIVE_NOTES sirf SCHEDULER runs gate karte — manual admin endpoints hamesha chalte.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/memory", tags=["Memory"])


class EntityEdit(BaseModel):
    kind: str
    key: str
    content: str


class TopicIn(BaseModel):
    topic: str
    niche: str | None = ""
    city: str | None = ""


# ------------------------------ Vault ------------------------------ #
@router.get("/entities")
async def entities(kind: str = "prospects", _user=Depends(require_admin)):
    from app.platform import memory_vault

    if kind not in memory_vault.KINDS:
        return {"ok": False, "error": f"kind inme se ho: {', '.join(memory_vault.KINDS)}"}
    return {"ok": True, "kind": kind, "entities": memory_vault.list_entities(kind)}


@router.get("/entity")
async def entity(kind: str, key: str, _user=Depends(require_admin)):
    from app.platform import memory_vault

    md = memory_vault.get_memory(kind, key)
    if md is None:
        return {"ok": False, "error": "memory file nahi mila"}
    return {"ok": True, "kind": kind, "key": key, "markdown": md}


@router.put("/entity")
async def entity_edit(body: EntityEdit, _user=Depends(require_admin)):
    from app.platform import memory_vault

    return memory_vault.edit_memory(body.kind, body.key, body.content)


@router.post("/sync", dependencies=[Depends(rate_limit("memsync", 6, 60))])
async def sync_now(_user=Depends(require_admin)):
    """Manual sync (flag-independent) — jsonl stores tail → memory files.
    Thread me (event loop block nahi — prod-down lesson)."""
    import asyncio

    from app.platform import memory_vault

    try:
        return await asyncio.to_thread(memory_vault.sync_all)
    except Exception as e:
        logger.warning(f"[memory_api] sync failed: {e}")
        return {"ok": False, "error": str(e)}


# ------------------------------ Call prep ------------------------------ #
@router.get("/prep", dependencies=[Depends(rate_limit("memprep", 20, 60))])
async def prep(phone: str = "", client_id: str = "", _user=Depends(require_admin)):
    """Dialer/sales ke liye 'prep me for this call' Hinglish brief."""
    from app.platform import call_prep

    return await call_prep.prep_brief(phone=phone or None, client_id=client_id or None)


# ------------------------------ Live notes ------------------------------ #
@router.get("/topics")
async def topics(_user=Depends(require_admin)):
    from app.platform import live_notes

    return {"ok": True, "enabled": live_notes.enabled(), "topics": live_notes.list_topics()}


@router.post("/topics")
async def topic_add(body: TopicIn, _user=Depends(require_admin)):
    from app.platform import live_notes

    return live_notes.add_topic(body.topic, niche=body.niche or "", city=body.city or "")


@router.delete("/topics/{topic_id}")
async def topic_remove(topic_id: str, _user=Depends(require_admin)):
    from app.platform import live_notes

    return live_notes.remove_topic(topic_id)


@router.post("/topics/{topic_id}/refresh", dependencies=[Depends(rate_limit("memtopic", 10, 60))])
async def topic_refresh(topic_id: str, _user=Depends(require_admin)):
    """Ek topic ka aaj ka update abhi likho (manual, flag-independent)."""
    from app.platform import live_notes

    for t in live_notes._read_topics():
        if t.get("id") == topic_id:
            return await live_notes.refresh_topic(t)
    return {"ok": False, "error": "topic id nahi mila"}


__all__ = ["router"]
