"""
agent_memory.py — per-lead / per-client AGENT MEMORY (cross-session recall).

KYUN (gap): KB (kb_main) tumhare BUSINESS facts ka RAG hai — par "is LEAD ne pichhli
baar kya kaha / iska budget / kab interested tha" kahin yaad nahi rehta. RAG ≠ memory.
Yeh module wahi bharta: har lead/client ke durable facts extract -> store -> recall,
taaki agent continuity de (follow-up, qualification lift). Mem0-PATTERN, par native —
tumhare maujooda Qdrant + free LLM reuse, koi naya heavy dep nahi (image protobuf-pin
safe). Optional asli `mem0` backend bhi (MEM0_BACKEND=mem0) — install ho to use, warna
native par graceful fallback.

DESIGN (semantic_cache.py jaisi proven rules):
  - FLAG-GATED: env `AGENT_MEMORY` (OFF default) — unset = ZERO behaviour/IO.
  - FAIL-OPEN: koi error/timeout = recall [] / remember skip; request kabhi block/raise nahi.
  - OFF-LOOP + DEADLINE: embed + Qdrant `asyncio.to_thread` + `wait_for` (voice hot-path
    pe ML kabhi event-loop block na kare — 3 prod-downs ka sabak).
  - SHARED METRICS: recall_hit/recall_miss/stored/error Redis me (multi-worker-correct);
    /metrics (health.py) expose karta.
  - DUCK-TYPED BACKEND: core ek backend pe; default native (Qdrant+free_ai). Tests fake de.

USAGE:
    from app.voice_agent import agent_memory
    block = await agent_memory.recall_block(lead_id, user_text, scope="lead")   # prompt-inject
    await agent_memory.remember(lead_id, history, scope="lead")                  # fire-and-forget

Top-level imports SIRF stdlib — app.* sab lazy (module bina poore app ke import/test ho).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REDIS_PREFIX = "agentmem"
_STATS: dict[str, int] = {"recall_hit": 0, "recall_miss": 0, "stored": 0, "error": 0, "disabled": 0}


# --- config (env, runtime-toggle-able) ----------------------------------------
def is_enabled() -> bool:
    return (os.getenv("AGENT_MEMORY", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _collection() -> str:
    return (os.getenv("AGENT_MEMORY_COLLECTION", "") or "agent_memory").strip()


def _min_sim() -> float:
    try:
        return float(os.getenv("AGENT_MEMORY_MIN_SIM", "0.35") or 0.35)
    except Exception:
        return 0.35


def _recall_limit() -> int:
    try:
        return int(os.getenv("AGENT_MEMORY_RECALL_LIMIT", "4") or 4)
    except Exception:
        return 4


def _embed_timeout() -> float:
    try:
        return float(os.getenv("AGENT_MEMORY_EMBED_TIMEOUT_S", "2.0") or 2.0)
    except Exception:
        return 2.0


def _op_timeout() -> float:
    try:
        return float(os.getenv("AGENT_MEMORY_OP_TIMEOUT_S", "1.5") or 1.5)
    except Exception:
        return 1.5


def _max_facts() -> int:
    try:
        return int(os.getenv("AGENT_MEMORY_MAX_FACTS", "4") or 4)
    except Exception:
        return 4


# --- stats (shared Redis, /metrics-correct) -----------------------------------
async def _bump(kind: str) -> None:
    try:
        from app.cache import get_cache_redis_client

        r = await get_cache_redis_client()
        await asyncio.wait_for(r.incr(f"{_REDIS_PREFIX}:{kind}"), 0.3)  # bound: hot-path no-hang
    except Exception:
        pass


async def _record(kind: str) -> None:
    _STATS[kind] = _STATS.get(kind, 0) + 1
    await _bump(kind)


async def redis_stats() -> dict[str, int]:
    out = {"recall_hit": 0, "recall_miss": 0, "stored": 0, "error": 0, "disabled": 0}
    try:
        from app.cache import get_cache_redis_client

        r = await get_cache_redis_client()
        for k in list(out):
            v = await asyncio.wait_for(r.get(f"{_REDIS_PREFIX}:{k}"), 0.3)  # bound (no-hang)
            out[k] = int(v or 0)
    except Exception:
        pass
    return out


def stats() -> dict[str, int]:
    return dict(_STATS)


# --- helpers ------------------------------------------------------------------
async def _safe_thread(fn, *args, timeout: float):
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout)
    except Exception as e:
        logger.debug("agent_memory backend op skipped: %s", e)
        return None


def _subject(subject_id: Any, scope: str) -> str:
    return f"{scope}:{str(subject_id).strip()}" if subject_id else ""


# Stored (2nd-order) prompt-injection guard: lead utterances become DURABLE facts that
# get re-injected into later prompts. Drop any "fact" that looks like an instruction /
# meta-directive so an attacker can't plant a persistent injection via spoken memory.
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all",
    "disregard previous",
    "forget previous",
    "system prompt",
    "your instructions",
    "reveal your",
    "disclose all",
    "pretend to be",
    "act as",
    "you are now",
    "developer mode",
    "jailbreak",
    "override your",
    "bypass your",
    "new instructions",
    "tum ab",
    "purane instructions bhul",
)


def _is_injection_like(fact: str) -> bool:
    low = (fact or "").lower()
    return any(m in low for m in _INJECTION_MARKERS)


# --- native production backend (lazy app.* imports) ---------------------------
class _NativeBackend:
    """fastembed (reuse KB embedder = same vector space) + Qdrant (dedicated
    `agent_memory` collection, kb_main pollute nahi). Sab lazy + best-effort."""

    def __init__(self) -> None:
        self.collection = _collection()

    def embed(self, text: str) -> list[float]:
        from app.voice_agent.knowledge_base import _get_qdrant_embedder

        emb = _get_qdrant_embedder()
        vec = next(iter(emb.embed([f"query: {text}"])))
        return [float(x) for x in vec]

    def _client(self):
        from app.voice_agent.knowledge_base import _get_qdrant_client

        return _get_qdrant_client()

    def _ensure(self, client, dim: int) -> None:
        from qdrant_client import models as qm

        if not client.collection_exists(self.collection):
            client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            )
            for field in ("subject",):
                try:
                    client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field,
                        field_schema=qm.PayloadSchemaType.KEYWORD,
                    )
                except Exception:
                    pass

    def search(self, vec: list[float], subject: str, limit: int) -> list[dict[str, Any]]:
        from qdrant_client import models as qm

        client = self._client()
        if not client.collection_exists(self.collection):
            return []
        res = client.query_points(
            collection_name=self.collection,
            query=vec,
            query_filter=qm.Filter(
                must=[qm.FieldCondition(key="subject", match=qm.MatchValue(value=subject))]
            ),
            limit=max(1, int(limit)),
            with_payload=True,
        )
        out: list[dict[str, Any]] = []
        for p in getattr(res, "points", None) or []:
            pl = getattr(p, "payload", None) or {}
            out.append(
                {
                    "fact": pl.get("fact"),
                    "score": float(getattr(p, "score", 0.0) or 0.0),
                    "ts": float(pl.get("ts", 0.0) or 0.0),
                }
            )
        return out

    def upsert(self, vec: list[float], subject: str, fact: str, ts: float) -> None:
        from qdrant_client import models as qm

        client = self._client()
        self._ensure(client, len(vec))
        client.upsert(
            collection_name=self.collection,
            points=[
                qm.PointStruct(
                    # Deterministic ID (subject+fact) -> exact re-statements OVERWRITE same
                    # point instead of accumulating (bounds growth; no extra query).
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{subject}|{fact[:400]}")),
                    vector=vec,
                    payload={"subject": subject, "fact": fact[:400], "ts": ts},
                )
            ],
        )
        return True

    def scroll_subject(self, subject: str, limit: int) -> list[dict[str, Any]]:
        """Operator view: list every stored fact for a subject (no vector search)."""
        from qdrant_client import models as qm

        client = self._client()
        if not client.collection_exists(self.collection):
            return []
        points, _ = client.scroll(
            collection_name=self.collection,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="subject", match=qm.MatchValue(value=subject))]
            ),
            limit=max(1, int(limit)),
            with_payload=True,
            with_vectors=False,
        )
        out: list[dict[str, Any]] = []
        for p in points or []:
            pl = getattr(p, "payload", None) or {}
            out.append({"fact": pl.get("fact"), "ts": float(pl.get("ts", 0.0) or 0.0)})
        return out

    def purge_subject(self, subject: str) -> int:
        """DPDP "right to be forgotten": delete every fact for a subject.
        Returns the count that was present (best-effort; -1 if count failed)."""
        from qdrant_client import models as qm

        client = self._client()
        if not client.collection_exists(self.collection):
            return 0
        try:
            c = client.count(
                collection_name=self.collection,
                count_filter=qm.Filter(
                    must=[qm.FieldCondition(key="subject", match=qm.MatchValue(value=subject))]
                ),
                exact=True,
            )
            n = int(getattr(c, "count", 0) or 0)
        except Exception:
            n = -1
        client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="subject", match=qm.MatchValue(value=subject))]
                )
            ),
        )
        return n


_BACKEND: Any | None = None


def _backend() -> Any:
    """Pick backend by env. Default native; MEM0_BACKEND=mem0 -> real mem0 if importable,
    warna native (graceful). Result cached."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    choice = (os.getenv("MEM0_BACKEND", "") or "native").strip().lower()
    if choice == "mem0":
        try:
            _BACKEND = _Mem0Backend()
            logger.info("[agent_memory] using mem0 library backend")
            return _BACKEND
        except Exception as e:
            logger.warning("[agent_memory] mem0 backend init failed (%s) — native fallback", e)
    _BACKEND = _NativeBackend()
    return _BACKEND


class _Mem0Backend:
    """OPTIONAL real-mem0 backend (qdrant-only mode). mem0ai install na ho to __init__
    raises -> _backend() native par fall back. Interface native jaisa (embed unused)."""

    def __init__(self) -> None:
        from mem0 import Memory  # raises if mem0ai absent

        host = (os.getenv("QDRANT_HOST", "") or "127.0.0.1").strip()
        try:
            port = int(os.getenv("QDRANT_PORT", "6333") or 6333)
        except Exception:
            port = 6333
        cfg = {
            "vector_store": {
                "provider": "qdrant",
                "config": {"collection_name": _collection(), "host": host, "port": port},
            }
        }
        self._m = Memory.from_config(cfg)

    # mem0 apna extraction/embedding khud karta — yahan high-level add/search.
    def mem0_add(self, messages: list[dict[str, str]], subject: str) -> None:
        self._m.add(messages, user_id=subject)

    def mem0_search(self, query: str, subject: str, limit: int) -> list[dict[str, Any]]:
        res = self._m.search(query=query, user_id=subject, limit=limit)
        items = res.get("results", res) if isinstance(res, dict) else res
        out = []
        for it in items or []:
            out.append(
                {
                    "fact": (it or {}).get("memory") or (it or {}).get("text"),
                    "score": float((it or {}).get("score", 0.0) or 0.0),
                    "ts": 0.0,
                }
            )
        return out

    def mem0_list(self, subject: str, limit: int) -> list[dict[str, Any]]:
        res = self._m.get_all(user_id=subject) or {}
        items = res.get("results", res) if isinstance(res, dict) else res
        out: list[dict[str, Any]] = []
        for it in (items or [])[: max(1, int(limit))]:
            out.append({"fact": (it or {}).get("memory") or (it or {}).get("text"), "ts": 0.0})
        return out

    def mem0_purge(self, subject: str) -> int:
        # Mem0 doesn't report a count; signal "unknown but done" via -1.
        self._m.delete_all(user_id=subject)
        return -1


# --- fact extraction (free LLM, off-loop) -------------------------------------
_EXTRACT_SYS = (
    "You extract DURABLE memory facts about the LEAD/customer from a conversation. "
    "Keep only stable, reusable facts (budget, timeline, specific need, identity, "
    "location, decision-maker, objection). IGNORE greetings/smalltalk. Each fact "
    '<= 12 words. Return ONLY a JSON array of strings (e.g. ["budget ~50k", '
    '"wants bridal package in December"]). Nothing worth keeping -> [].'
)


async def _extract_facts(messages: list[dict[str, str]]) -> list[str]:
    """free_ai.chat se 0-N durable facts. Never-raise; [] on any issue."""
    try:
        from app.voice_agent import free_ai

        convo = "\n".join(
            f"{(m.get('role') or 'user')}: {str(m.get('content') or '').strip()}"
            for m in (messages or [])
            if str(m.get("content") or "").strip()
        )[-2000:]
        if not convo:
            return []
        text, _prov = await free_ai.chat(
            system=_EXTRACT_SYS,
            messages=[{"role": "user", "content": convo}],
            max_tokens=160,
            temperature=0.0,
            scope="memory_extract",
        )
        if not text:
            return []
        m = re.search(r"\[.*\]", text, re.S)
        arr = json.loads(m.group(0)) if m else []
        facts = []
        for f in arr if isinstance(arr, list) else []:
            s = str(f).strip()
            if s and not _is_injection_like(s):  # drop instruction-like (2nd-order injection)
                facts.append(s[:400])
        return facts[: _max_facts()]
    except Exception as e:
        logger.debug("agent_memory extract skipped: %s", e)
        return []


# --- public API ---------------------------------------------------------------
async def recall(
    subject_id: Any,
    query: str,
    *,
    scope: str = "lead",
    limit: int | None = None,
    backend: Any = None,
) -> list[str]:
    """Subject ke durable facts jo `query` se relevant — fact-strings list. Fail = []."""
    if not is_enabled():
        return []
    subject = _subject(subject_id, scope)
    q = (query or "").strip()
    if not subject or not q:
        return []
    be = backend or _backend()
    lim = int(limit if limit is not None else _recall_limit())
    try:
        # mem0 backend: apna embed+search
        if isinstance(be, _Mem0Backend):
            found = await _safe_thread(be.mem0_search, q, subject, lim, timeout=_op_timeout()) or []
        else:
            vec = await _safe_thread(be.embed, q, timeout=_embed_timeout())
            if vec is None:
                await _record("error")
                return []
            found = await _safe_thread(be.search, vec, subject, lim, timeout=_op_timeout()) or []
        facts = []
        for f in found:
            if not (f and f.get("fact")):
                continue
            if float(f.get("score") or 0.0) < _min_sim():
                continue
            s = str(f.get("fact")).strip()
            if s and not _is_injection_like(s):  # defense-in-depth on already-stored facts
                facts.append(s)
        await _record("recall_hit" if facts else "recall_miss")
        return facts
    except Exception as e:
        logger.debug("agent_memory recall skipped: %s", e)
        await _record("error")
        return []


async def recall_block(subject_id: Any, query: str, *, scope: str = "lead", **kw) -> str:
    """Prompt-inject ke liye ek SHORT line (phone hot-path — no paragraphs). "" agar khaali."""
    facts = await recall(subject_id, query, scope=scope, **kw)
    if not facts:
        return ""
    joined = " | ".join(facts)
    return f"YAAD (is {scope} ke baare me, relevant ho to use karo): {joined[:240]}"


async def remember(
    subject_id: Any,
    messages: list[dict[str, str]],
    *,
    scope: str = "lead",
    backend: Any = None,
) -> dict[str, Any]:
    """Conversation se durable facts extract karke store karo. Fire-and-forget friendly
    (kabhi raise/block nahi). Returns {"stored": n}.

    GOVERNANCE (fail-CLOSED, only while MEMORY_STACK_ENABLED is on): if the
    do-not-remember authority is unreadable/unknown we refuse to persist and
    return a typed deferral instead — the caller can still answer, it just does
    not remember. Flag OFF = byte-identical legacy behaviour.
    """
    if not is_enabled():
        return {"stored": 0, "disabled": True}
    try:
        from app.platform.memory_governance import durable_writes_allowed

        _g = durable_writes_allowed()
        if not _g["ok"]:
            return {"stored": 0, "deferred": True, "code": _g["code"], "reason": _g["reason"]}
    except Exception as _e:  # governance itself unavailable => cannot prove allowed
        logger.debug("agent_memory governance gate unavailable: %s", _e)
        return {
            "stored": 0,
            "deferred": True,
            "code": "MEMORY_WRITE_DEFERRED_GOVERNANCE_UNAVAILABLE",
            "reason": "governance module unavailable",
        }
    subject = _subject(subject_id, scope)
    if not subject:
        return {"stored": 0}
    be = backend or _backend()
    try:
        # mem0 backend khud extract karta — seedha add.
        if isinstance(be, _Mem0Backend):
            await _safe_thread(
                be.mem0_add, list(messages or []), subject, timeout=_op_timeout() * 2
            )
            await _record("stored")
            return {"stored": 1, "backend": "mem0"}

        facts = await _extract_facts(messages)
        if not facts:
            return {"stored": 0}
        now = time.time()
        n = 0
        for fact in facts:
            vec = await _safe_thread(be.embed, fact, timeout=_embed_timeout())
            if vec is None:
                continue
            ok = await _safe_thread(be.upsert, vec, subject, fact, now, timeout=_op_timeout())
            if ok:  # upsert -> True on success; _safe_thread -> None on failure/timeout
                n += 1
        if n:
            await _record("stored")
        return {"stored": n}
    except Exception as e:
        logger.debug("agent_memory remember skipped: %s", e)
        await _record("error")
        return {"stored": 0, "error": str(e)[:120]}


async def list_facts(
    subject_id: Any,
    *,
    scope: str = "lead",
    limit: int = 100,
    backend: Any = None,
) -> list[dict[str, Any]]:
    """Operator-facing scroll: every stored fact for a subject (no vector search).

    Used by /api/agent-memory/inspect for /app/automation debugging — "what
    does the agent actually remember about this lead?". Disabled-or-error -> [].
    """
    if not is_enabled():
        return []
    subject = _subject(subject_id, scope)
    if not subject:
        return []
    be = backend or _backend()
    try:
        if isinstance(be, _Mem0Backend):
            return (
                await _safe_thread(be.mem0_list, subject, int(limit), timeout=_op_timeout()) or []
            )
        return (
            await _safe_thread(be.scroll_subject, subject, int(limit), timeout=_op_timeout()) or []
        )
    except Exception as e:
        logger.debug("agent_memory list_facts skipped: %s", e)
        return []


async def purge_subject(
    subject_id: Any,
    *,
    scope: str = "lead",
    backend: Any = None,
) -> dict[str, Any]:
    """DPDP/TRAI "right to be forgotten": erase every fact for this subject.

    Wired by /api/agent-memory/purge (admin) and SHOULD also be called from
    consent_ledger.record_opt_out() so memories vanish with the opt-out. Native
    backend returns the prior count; Mem0 returns -1 (count not reported).
    Always best-effort: a backend error returns {"purged": 0, "error": "..."}.
    """
    if not is_enabled():
        return {"purged": 0, "disabled": True}
    subject = _subject(subject_id, scope)
    if not subject:
        return {"purged": 0, "error": "no_subject"}
    be = backend or _backend()
    try:
        if isinstance(be, _Mem0Backend):
            cnt = await _safe_thread(be.mem0_purge, subject, timeout=_op_timeout())
        else:
            cnt = await _safe_thread(be.purge_subject, subject, timeout=_op_timeout())
        await _record("purged")
        return {"purged": int(cnt if cnt is not None else 0), "subject": subject}
    except Exception as e:
        logger.debug("agent_memory purge_subject skipped: %s", e)
        await _record("error")
        return {"purged": 0, "error": str(e)[:120]}


# --- session-scoped ephemeral memory (Redis TTL, no Qdrant) -----------------
# Working memory for one call/session — auto-expires, never writes to Qdrant.
# Gated by SESSION_MEMORY=1 (separate from AGENT_MEMORY cross-session durable store).


def is_session_memory_enabled() -> bool:
    return (os.getenv("SESSION_MEMORY", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _session_ttl() -> int:
    try:
        return int(os.getenv("SESSION_MEMORY_TTL", "7200") or 7200)
    except Exception:
        return 7200


def _redis_session_key(session_id: str) -> str:
    return f"session_mem:{str(session_id).strip()}"


async def session_remember(session_id: str, fact: str) -> bool:
    """Store ephemeral fact for this session. Auto-expires in SESSION_MEMORY_TTL seconds (default 2h).
    Best-effort — never raises."""
    if not is_session_memory_enabled() or not fact or not session_id:
        return False
    fact = (fact or "").strip()[:400]
    if _is_injection_like(fact):
        return False
    try:
        from app.cache import get_cache_redis_client

        r = await get_cache_redis_client()
        key = _redis_session_key(session_id)
        await asyncio.wait_for(r.hset(key, str(uuid.uuid4())[:8], fact), 0.5)
        await asyncio.wait_for(r.expire(key, _session_ttl()), 0.3)
        return True
    except Exception as e:
        logger.debug("session_remember skipped: %s", e)
        return False


async def session_recall(session_id: str) -> list[str]:
    """Recall all ephemeral facts for this session. [] on error or if disabled."""
    if not is_session_memory_enabled() or not session_id:
        return []
    try:
        from app.cache import get_cache_redis_client

        r = await get_cache_redis_client()
        data = await asyncio.wait_for(r.hgetall(_redis_session_key(session_id)), 0.5)
        facts = []
        for v in (data or {}).values():
            s = str(v).strip()
            if s and not _is_injection_like(s):
                facts.append(s)
        return facts
    except Exception as e:
        logger.debug("session_recall skipped: %s", e)
        return []


async def session_cleanup(session_id: str) -> bool:
    """Purge all ephemeral session memory on session end. Best-effort."""
    if not session_id:
        return False
    try:
        from app.cache import get_cache_redis_client

        r = await get_cache_redis_client()
        await asyncio.wait_for(r.delete(_redis_session_key(session_id)), 0.5)
        return True
    except Exception:
        return False


__all__ = [
    "is_enabled",
    "recall",
    "recall_block",
    "remember",
    "redis_stats",
    "stats",
    "list_facts",
    "purge_subject",
    "is_session_memory_enabled",
    "session_remember",
    "session_recall",
    "session_cleanup",
]
