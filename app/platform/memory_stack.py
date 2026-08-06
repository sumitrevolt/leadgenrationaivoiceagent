"""Memory Stack — 7-layer AGENT MEMORY facade over the lanes we already have.

KYUN (gap): is repo me memory ke saat lane already the, par koi ek jagah nahi
jahan se agent "is kaam ke liye jo yaad hai wo do" maang sake — har caller apna
prompt khud jodta hai (coordinator me hardcoded `hint[:600]`). Natija: koi TOKEN
budget nahi, koi DEADLINE nahi, aur do layers (working window + prospective
"baad me yeh karna hai") kahin the hi nahi.

  L1 working      — is module ka bounded FIFO turn buffer (TTL + eviction)
  L2 episodic     — voice_agent.agent_memory (Qdrant lead/client facts)
  L3 semantic     — platform.workforce_memory L2/L3 (scenario/persona)
  L4 procedural   — platform.skill_library (lessons + success-rate tactics)
  L5 hierarchical — YEH module: hot -> warm -> cold, token budget + deadline
  L6 prospective  — platform.prospective_store (DURABLE: claim/lease/idempotency)
  L7 shared       — platform.workforce_memory shared/equip mirror (ACL-respecting)

REVIEW-DRIVEN CORRECTIONS (v2, 2026-08-05):
  - L6 ab JSONL pe NAHI — durable table + atomic claim (`prospective_store`).
    JSONL read-modify-write exactly-once nahi tha; wo path hata diya gaya hai.
  - `tenant_id` har read/write/assemble/dispatch pe MANDATORY. Koi global
    fallback tenant nahi — blank tenant = refuse.
  - Budget ab TOKEN-based (repo ka `estimate_tokens`), completion headroom
    reserve ke saath; char-slicing gaya.
  - Master flag `MEMORY_STACK_ENABLED` + subordinate per-layer flags +
    `validate_config()`; invalid/partial config = FAIL-CLOSED, koi dispatch nahi.
  - L1 explicitly NON-AUTHORITATIVE hot cache (per-process, TTL, evicted).

INVARIANTS: never-raise · off-loop (`to_thread` + `wait_for`) · no paid AI · no
new dependency · additive (kisi lane ka behaviour nahi badla) · INERT until the
master flag is armed. Top-level imports SIRF stdlib; app.* lazy.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- vocabulary

TIER_HOT = "hot"
TIER_WARM = "warm"
TIER_COLD = "cold"
TIERS = (TIER_HOT, TIER_WARM, TIER_COLD)

# layer key -> (tier, token quota share). Unspent quota cascades to later layers.
LAYER_SPECS: tuple[tuple[str, str, float], ...] = (
    ("working", TIER_HOT, 0.22),
    ("prospective", TIER_HOT, 0.13),
    ("episodic", TIER_HOT, 0.20),
    ("semantic", TIER_WARM, 0.20),
    ("procedural", TIER_WARM, 0.15),
    ("shared", TIER_COLD, 0.10),
)
LAYERS = tuple(k for k, _t, _s in LAYER_SPECS)

_STATS: dict[str, int] = {
    "assembled": 0,
    "disabled": 0,
    "layer_timeout": 0,
    "layer_error": 0,
    "truncated": 0,
    "deduped": 0,
    "scheduled": 0,
    "dispatched": 0,
    "dispatch_failed": 0,
    "dispatch_duplicate_suppressed": 0,
    "suppressed_writes": 0,
    "deferred_writes": 0,
    "ephemeral_writes": 0,
    "stale_facts_dropped": 0,
    "conflicted_facts": 0,
    "drain_blocked": 0,
    "error": 0,
}


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(str(os.getenv(name) or default).strip())))
    except Exception:
        return default


# ------------------------------------------------------------- flag contract


def is_enabled() -> bool:
    """MASTER gate. Everything below is subordinate to this."""
    return _truthy(os.getenv("MEMORY_STACK_ENABLED"))


def layer_enabled(layer: str) -> bool:
    """Per-layer flag, subordinate to the master. Default ON when master is ON."""
    if not is_enabled():
        return False
    raw = os.getenv(f"MEMORY_STACK_LAYER_{layer.upper()}")
    return True if raw is None or raw.strip() == "" else _truthy(raw)


def dispatch_ready() -> tuple[bool, str]:
    """Can prospective work actually be dispatched? Fail-CLOSED when not."""
    if not is_enabled():
        return False, "master flag MEMORY_STACK_ENABLED off"
    if not layer_enabled("prospective"):
        return False, "prospective layer disabled"
    try:
        from app.platform import prospective_store

        if not prospective_store.available():
            return False, "durable prospective store unavailable (no dispatch)"
    except Exception:
        return False, "prospective store import failed"
    return True, "ok"


def validate_config() -> dict[str, Any]:
    """Startup/ops diagnostics. Reports problems instead of guessing defaults."""
    problems: list[str] = []
    master = is_enabled()
    lanes = {k: layer_enabled(k) for k in LAYERS}
    # CONFIGURED = what the env asks for. EFFECTIVE = what actually runs once the
    # master flag and dependencies are applied. The UI must show both, so an
    # operator never reads "enabled" off a lane whose dependency is down.
    configured = {
        k: (os.getenv(f"MEMORY_STACK_LAYER_{k.upper()}") is None)
        or _truthy(os.getenv(f"MEMORY_STACK_LAYER_{k.upper()}"))
        for k in LAYERS
    }

    if master:
        if lanes["episodic"] and not _truthy(os.getenv("AGENT_MEMORY")):
            problems.append("episodic layer on but AGENT_MEMORY off — lane will stay empty")
        if (lanes["semantic"] or lanes["shared"]) and not _truthy(os.getenv("WORKFORCE_MEMORY")):
            problems.append(
                "semantic/shared layer on but WORKFORCE_MEMORY off — lanes will stay empty"
            )
        ok, why = dispatch_ready()
        if lanes["prospective"] and not ok:
            problems.append(f"prospective dispatch blocked: {why}")
        if _token_budget() + _reserve_tokens() > _context_tokens():
            problems.append(
                "token budget + completion reserve exceeds context window — budget will be clamped"
            )
        if not any(lanes.values()):
            problems.append("master flag on but every layer disabled — assemble returns nothing")

    ok_dispatch, why_dispatch = dispatch_ready()
    health: dict[str, Any] = {}
    try:
        from app.platform.memory_governance import rules_health

        health = rules_health()
        if not health.get("readable", True) or health.get("unparsable"):
            problems.append(
                "do-not-remember authority damaged — ALL durable memory writes are "
                "refused (fail-closed); agents answer without remembering"
            )
    except Exception:
        problems.append("governance module unavailable — durable memory writes refused")
    return {
        "ok": not problems,
        "master": master,
        "layers": lanes,  # EFFECTIVE
        "layers_configured": configured,  # what env asked for
        "dependency_failures": {k: (configured[k] and not lanes[k]) for k in LAYERS},
        "warm": _WARM,
        "tiers": list(active_tiers()),
        "dispatch_ready": ok_dispatch,
        "dispatch_reason": why_dispatch,
        "suppression_rules": health,
        # explicit privacy posture for operators: durable remembering on/off
        "durable_writes_allowed": remembering_allowed("__healthcheck__"),
        "problems": problems,
    }


def active_tiers() -> tuple[str, ...]:
    raw = (os.getenv("MEMORY_STACK_TIERS") or "").strip()
    if not raw:
        return TIERS
    want = tuple(t.strip().lower() for t in raw.split(",") if t.strip().lower() in TIERS)
    return want or TIERS


# ----------------------------------------------------------- token budgeting


def _context_tokens() -> int:
    """Model context window we are budgeting inside."""
    return _env_int("MEMORY_STACK_CONTEXT_TOKENS", 8000, lo=512, hi=200_000)


def _reserve_tokens() -> int:
    """Headroom kept for system prompt + tools + the completion itself."""
    return _env_int("MEMORY_STACK_RESERVE_TOKENS", 1200, lo=0, hi=100_000)


def _token_budget() -> int:
    """Tokens the memory block may occupy (before clamping against the window)."""
    return _env_int("MEMORY_STACK_TOKEN_BUDGET", 600, lo=32, hi=50_000)


def effective_token_budget(requested: int | None = None, *, prompt_overhead: int = 0) -> int:
    """Clamp the ask against context window minus reserved headroom+overhead."""
    want = int(requested or _token_budget())
    room = _context_tokens() - _reserve_tokens() - max(0, int(prompt_overhead))
    return max(0, min(want, room))


_WARM = False
_TOKENIZER: Callable[[str], int] | None = None


def _warm_sync() -> None:
    """Resolve the lazy helpers ONCE, off the assembly deadline.

    Bug caught in harness (2026-08-05): the first `assemble()` after boot spent
    ~580ms importing `context_packets` (redaction + tokenizer), which blew the
    250ms deadline and timed out EVERY lane — the first agent turn silently got
    an empty memory block. Import cost now happens before the clock starts.
    """
    global _WARM, _TOKENIZER
    try:
        from app.dev_control.context_packets import estimate_tokens

        _TOKENIZER = estimate_tokens
    except Exception as e:
        logger.debug("[memory_stack] warm fell back to builtin helpers: %s", e)
    finally:
        _WARM = True


async def prewarm() -> bool:
    """Idempotent, never-raises warm-up. Safe to call from startup or scheduler."""
    if _WARM:
        return True
    try:
        await asyncio.wait_for(asyncio.to_thread(_warm_sync), timeout=5.0)
    except Exception:
        globals()["_WARM"] = True  # do not retry-storm on a broken import
    return True


def count_tokens(text: str) -> int:
    """Repo-native estimator (context_packets). Falls back to chars/4."""
    try:
        if _TOKENIZER is not None:
            return int(_TOKENIZER(text or ""))
        from app.dev_control.context_packets import estimate_tokens

        return int(estimate_tokens(text or ""))
    except Exception:
        return max(0, len(text or "") // 4)


def _truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Deterministic truncation at a line boundary. Returns (text, truncated?)."""
    if max_tokens <= 0:
        return "", True
    if count_tokens(text) <= max_tokens:
        return text, False
    lines = (text or "").split("\n")
    kept: list[str] = []
    used = 0
    for ln in lines:
        t = count_tokens(ln) + 1
        if used + t > max_tokens:
            break
        kept.append(ln)
        used += t
    if not kept:  # single oversized line — hard char cut, still deterministic
        return (text or "")[: max_tokens * 4].rstrip() + " …", True
    return "\n".join(kept) + "\n…", True


DEFER_CODE = "MEMORY_WRITE_DEFERRED_GOVERNANCE_UNAVAILABLE"


def _write_decision(
    tenant_id: str,
    *,
    session_id: str = "",
    subject_id: str = "",
    text: str = "",
    durable: bool = True,
) -> dict[str, Any]:
    """Do-not-remember gate. **FAIL-CLOSED** for durable writes.

    If the DNR authority cannot be trusted (unreadable/malformed/unavailable, or
    this module cannot even be imported) the decision is `deferred`: the caller
    must NOT persist the content — not in the row, not in retry state, not in
    `last_error`, not in an audit payload. The foreground agent may still answer;
    it just answers WITHOUT remembering.
    """
    try:
        from app.platform.memory_governance import check_write

        return check_write(
            tenant_id,
            session_id=session_id,
            subject_id=subject_id,
            text=text,
            durable=durable,
        )
    except Exception as e:
        logger.debug("[memory_stack] governance unavailable: %s", e)
        return {
            "decision": "deferred",
            "code": DEFER_CODE,
            "reason": "governance module unavailable",
        }


def remembering_allowed(tenant_id: str) -> bool:
    """False => callers must run in answer-without-remembering mode."""
    return _write_decision(tenant_id, durable=True)["decision"] != "deferred"


_WS = re.compile(r"\s+")


def _norm_line(line: str) -> str:
    return _WS.sub(" ", (line or "").strip().lstrip("-• ").lower())


def _dedupe_lines(text: str, seen: set[str]) -> str:
    """Cross-layer duplicate suppression (same fact from vault + workforce etc.)."""
    out: list[str] = []
    for ln in (text or "").split("\n"):
        key = _norm_line(ln)
        if not key:
            continue
        # Non-crypto dedupe key only (collision-resistant id, not a password hash).
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if h in seen:
            _STATS["deduped"] += 1
            continue
        seen.add(h)
        out.append(ln)
    return "\n".join(out)


# TWO redaction policies live in `memory_governance` (stdlib-only, cheap import):
#   POLICY A `scrub_secrets`        -> prompt-bound text (this hot path)
#   POLICY B `mask_for_observability` -> logs/audit/admin/UI/errors
# Measured 2026-08-05: the canonical PII+secret redactor costs ~80ms per call,
# so it cannot run six times inside a 250ms assembly. It is NOT weakened — it
# still runs on every observability destination; the prompt path (already
# tenant-scoped and authorized) only needs secrets removed, because the lead's
# phone/name IS the memory payload.
def _redact(text: str) -> str:
    """POLICY A — prompt-bound secret scrub. Never raises."""
    try:
        from app.platform.memory_governance import scrub_secrets

        return scrub_secrets(text)
    except Exception:
        return text or ""


def _mask(text: str) -> str:
    """POLICY B — anything an operator/log/API can see. Never raises."""
    try:
        from app.platform.memory_governance import mask_for_observability

        return mask_for_observability(text)
    except Exception:
        return text or ""


# --------------------------------------- L1 working memory (NON-AUTHORITATIVE)
# Per-process hot cache ONLY. Multi-worker => har worker apna buffer dekhega;
# restart => gone. Durable cheez L6 (table) ya L2 (Qdrant) me jaani chahiye.
# Key = tenant + session, taaki do tenants ka window kabhi mix na ho.

_WORKING: OrderedDict[str, deque] = OrderedDict()
_WORKING_SEEN: dict[str, float] = {}
# Sessions written while governance was unavailable: allowed in the NON-durable
# hot cache only ("answer without remembering"), never promotable to a lane.
_DEGRADED_SESSIONS: set[str] = set()


def _working_turns() -> int:
    """Per-session entry cap (deque maxlen)."""
    return _env_int("MEMORY_STACK_WORKING_TURNS", 12, lo=2, hi=200)


def _working_ttl() -> int:
    return _env_int("MEMORY_STACK_WORKING_TTL_S", 1800, lo=30, hi=86_400)


def _working_max_sessions() -> int:
    """TOTAL hard capacity across all tenants (LRU beyond this)."""
    return _env_int("MEMORY_STACK_WORKING_MAX_SESSIONS", 500, lo=10, hi=100_000)


def _working_max_per_tenant() -> int:
    """Per-tenant session cap — one noisy tenant cannot evict everyone else."""
    return _env_int("MEMORY_STACK_WORKING_MAX_PER_TENANT", 50, lo=1, hi=10_000)


def _wkey(tenant_id: str, session_id: str) -> str | None:
    t = str(tenant_id or "").strip()[:64]
    s = str(session_id or "").strip()[:120]
    return f"{t}::{s}" if t and s else None


def _sweep_working(now: float | None = None, *, tenant_id: str = "") -> int:
    """TTL eviction + per-tenant cap + total hard capacity (LRU). Deterministic."""
    ref = now if now is not None else time.time()
    ttl = _working_ttl()
    evicted = 0
    try:
        for k in [k for k, seen in list(_WORKING_SEEN.items()) if ref - seen > ttl]:
            _WORKING.pop(k, None)
            _WORKING_SEEN.pop(k, None)
            _DEGRADED_SESSIONS.discard(k)  # marker dies with the session (TTL)
            evicted += 1
        evicted += _enforce_caps(tenant_id)
    except Exception:
        _STATS["error"] += 1
    return evicted


def _enforce_caps(tenant_id: str = "") -> int:
    """Per-tenant cap + total hard capacity. Called AFTER a write, so the new
    entry itself counts against the cap (pre-write sweeping let the cap be
    exceeded by one — caught by harness 2026-08-05)."""
    evicted = 0
    if tenant_id:
        prefix = f"{str(tenant_id).strip()[:64]}::"
        cap = _working_max_per_tenant()
        mine = [k for k in _WORKING if k.startswith(prefix)]  # insertion = LRU order
        for k in mine[: max(0, len(mine) - cap)]:
            _WORKING.pop(k, None)
            _WORKING_SEEN.pop(k, None)
            evicted += 1
    while len(_WORKING) > _working_max_sessions():
        k, _v = _WORKING.popitem(last=False)  # oldest-used first
        _WORKING_SEEN.pop(k, None)
        _DEGRADED_SESSIONS.discard(k)
        evicted += 1
    # hard bound: markers can never outnumber the sessions they describe
    while len(_DEGRADED_SESSIONS) > _working_max_sessions():
        _DEGRADED_SESSIONS.pop()
    return evicted


def push_turn(tenant_id: str, session_id: str, role: str, content: str) -> bool:
    """Ek turn hot cache me. Tenant mandatory — koi shared/global window nahi.

    Do-not-remember rules are enforced HERE, at the write boundary, so
    suppressed content never reaches memory in the first place.

    L1 is process-local, TTL-bounded and NON-durable, so it is the one place
    allowed to keep a turn while governance is unavailable — that is exactly
    "answer without remembering". The session is marked degraded and can never
    be promoted (nothing promotes L1 into a durable lane; locked by a test).
    """
    try:
        key = _wkey(tenant_id, session_id)
        text = (content or "").strip()
        if not key or not text:
            return False
        decision = _write_decision(tenant_id, session_id=session_id, text=text, durable=False)
        if decision["decision"] == "suppressed":
            _STATS["suppressed_writes"] += 1
            return False
        if not remembering_allowed(tenant_id):
            _DEGRADED_SESSIONS.add(key)  # ephemeral-only for this session
            _STATS["ephemeral_writes"] += 1
        else:
            _DEGRADED_SESSIONS.discard(key)  # governance recovered => normal mode
        _sweep_working(tenant_id=tenant_id)
        buf = _WORKING.get(key)
        if buf is None or buf.maxlen != _working_turns():
            buf = deque(list(buf or [])[-_working_turns() :], maxlen=_working_turns())
            _WORKING[key] = buf
        _WORKING.move_to_end(key)
        _WORKING_SEEN[key] = time.time()
        buf.append({"role": (role or "user")[:16], "content": _redact(text)[:2000]})
        _enforce_caps(tenant_id)  # after the write — the new entry counts too
        return True
    except Exception:
        _STATS["error"] += 1
        return False


def working_window(tenant_id: str, session_id: str, *, max_tokens: int = 150) -> str:
    """Newest-last transcript slice inside a TOKEN budget. Oldest turns drop first."""
    try:
        key = _wkey(tenant_id, session_id)
        if not key:
            return ""
        _sweep_working()
        buf = list(_WORKING.get(key) or [])
        if not buf:
            return ""
        _WORKING.move_to_end(key, last=True)
        _WORKING_SEEN[key] = time.time()
        lines: list[str] = []
        used = 0
        for row in reversed(buf):
            line = f"{row.get('role', 'user')}: {row.get('content', '')}"
            t = count_tokens(line) + 1
            if used + t > max(0, int(max_tokens)):
                break
            lines.append(line)
            used += t
        return "\n".join(reversed(lines))
    except Exception:
        _STATS["error"] += 1
        return ""


def clear_working(tenant_id: str, session_id: str) -> bool:
    key = _wkey(tenant_id, session_id)
    if not key:
        return False
    _WORKING_SEEN.pop(key, None)
    _DEGRADED_SESSIONS.discard(key)
    return _WORKING.pop(key, None) is not None


def clear_tenant_working(tenant_id: str) -> int:
    """Namespace cleanup (tenant offboarding / DPDP)."""
    t = str(tenant_id or "").strip()[:64]
    if not t:
        return 0
    n = 0
    for key in [k for k in list(_WORKING) if k.startswith(f"{t}::")]:
        _WORKING.pop(key, None)
        _WORKING_SEEN.pop(key, None)
        _DEGRADED_SESSIONS.discard(key)
        n += 1
    for key in [k for k in list(_DEGRADED_SESSIONS) if k.startswith(f"{t}::")]:
        _DEGRADED_SESSIONS.discard(key)
    return n


def working_snapshot() -> dict[str, Any]:
    _sweep_working()
    return {
        "authoritative": False,  # explicit: process-local hot cache only
        "lost_on_restart": True,  # documented: only hot-cache turns are lost
        "sessions": len(_WORKING),
        "turns": sum(len(v) for v in _WORKING.values()),
        "ttl_seconds": _working_ttl(),
        "capacity_total": _working_max_sessions(),
        "capacity_per_tenant": _working_max_per_tenant(),
        "turns_per_session": _working_turns(),
        "warm": _WARM,
        "degraded_sessions": len(_DEGRADED_SESSIONS),
    }


# ------------------------------------------------ L6 prospective (delegated)


def schedule(
    tenant_id: str,
    agent_id: str,
    action: str,
    *,
    due_at: Any = None,
    in_minutes: int | None = None,
    payload: dict[str, Any] | None = None,
    note: str = "",
    source: str = "memory_stack",
) -> dict[str, Any]:
    """Durable future action. Idempotent producer; never raises."""
    try:
        from app.platform import prospective_store as ps

        # DURABLE write => fail-CLOSED. No raw content in the response either.
        decision = _write_decision(
            tenant_id, subject_id=str(agent_id), text=str(action or ""), durable=True
        )
        if decision["decision"] == "suppressed":
            _STATS["suppressed_writes"] += 1
            return {
                "ok": False,
                "code": decision["code"],
                "error": "suppressed by do-not-remember rule",
            }
        if decision["decision"] == "deferred":
            _STATS["deferred_writes"] += 1
            return {
                "ok": False,
                "deferred": True,
                "code": decision["code"],
                "error": decision["reason"],  # reason only — never the content
            }

        when = due_at
        if isinstance(when, str) and when.strip():
            try:
                when = datetime.fromisoformat(when.strip().replace("Z", "+00:00"))
            except Exception:
                when = None
        if isinstance(when, datetime) and when.tzinfo is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        out = ps.enqueue(
            tenant_id,
            agent_id,
            action,
            due_at=when if isinstance(when, datetime) else None,
            in_minutes=in_minutes,
            payload=payload,
            note=note,
            source=source,
        )
        if out.get("ok"):
            _STATS["scheduled"] += 1
        return out
    except Exception:
        _STATS["error"] += 1
        return {"ok": False, "error": "schedule_failed"}


async def _default_dispatch(row: dict[str, Any]) -> str:
    """Due row -> normal agent_task_queue task, IDEMPOTENTLY.

    Review P0 (duplicate side effect): the task id is derived from
    tenant+row, so a worker that crashed after `assign()` but before the ack
    re-derives the SAME id — the retry finds the existing task instead of
    creating a second one. Guarantee: exactly one LOGICAL internal task per
    prospective row, no matter how many dispatch attempts happen.
    """
    from app.platform import agent_task_queue as atq
    from app.platform import prospective_store as ps

    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    extra: dict[str, Any] = {}
    if payload.get("client_id"):
        extra["client_id"] = str(payload["client_id"])
    if payload.get("campaign_id"):
        extra["campaign_id"] = str(payload["campaign_id"])
    task = await atq.assign_idempotent(
        str(row.get("agent_id") or ""),
        str(row.get("action") or ""),
        dispatch_key=ps.dispatch_key(row),
        delegated_by="memory_stack",  # provenance
        **extra,
    )
    if task.get("duplicate"):
        _STATS["dispatch_duplicate_suppressed"] += 1
    return str((task or {}).get("id") or "")


async def drain_due(
    *,
    handler: Callable[[dict[str, Any]], Any] | None = None,
    limit: int = 20,
    worker_id: str = "",
) -> dict[str, Any]:
    """Recover expired leases, atomically claim, dispatch OUTSIDE any DB lock.

    Fail-CLOSED: no durable store => zero dispatch (never a JSONL best-effort).
    Handler failure => retry/dead via the store, never a silent completion.
    """
    ok, why = dispatch_ready()
    if not ok:
        _STATS["drain_blocked"] += 1
        return {"skipped": why, "fired": 0}

    from app.platform import prospective_store as ps

    recovered = ps.recover_expired()
    rows = ps.claim_batch(worker_id or ps.worker_identity(), limit=limit)

    fired = 0
    failed = 0
    for row in rows:  # no session held here — dispatch is a network/DB call of its own
        try:
            fn = handler or _default_dispatch
            res = fn(row)
            if asyncio.iscoroutine(res):
                res = await res
            task_id = str(res or "")
            if not task_id:
                raise RuntimeError("dispatch returned no task id")
            if ps.mark_dispatched(row["id"], task_id):
                fired += 1
                _STATS["dispatched"] += 1
            else:
                failed += 1
                _STATS["dispatch_failed"] += 1
        except Exception as e:
            failed += 1
            _STATS["dispatch_failed"] += 1
            ps.mark_failed(row["id"], str(e)[:200])
    return {"recovered": recovered, "claimed": len(rows), "fired": fired, "failed": failed}


async def drain_if_enabled(*, limit: int = 20) -> dict[str, Any]:
    """Scheduler hook (memory_vault.sync_if_enabled ka pattern)."""
    try:
        return await drain_due(limit=limit)
    except Exception:
        _STATS["error"] += 1
        return {"skipped": "error", "error": "drain_failed", "fired": 0}


# --------------------------------------------- lane delegates (sync, bounded)
# signature: (tenant_id, agent_id, query, ctx, max_tokens) -> str


def _lane_working(tenant_id: str, agent_id: str, query: str, ctx: dict, mt: int) -> str:
    return working_window(tenant_id, str(ctx.get("session_id") or ""), max_tokens=mt)


def _lane_prospective(tenant_id: str, agent_id: str, query: str, ctx: dict, mt: int) -> str:
    from app.platform import prospective_store as ps

    rows = ps.list_rows(tenant_id, agent_id=agent_id, status=ps.STATUS_PENDING, limit=5)
    lines: list[str] = []
    used = 0
    for r in rows:
        line = f"- {str(r.get('due_at') or '')[:16]} — {r.get('action', '')}"
        t = count_tokens(line) + 1
        if used + t > mt:
            break
        lines.append(line)
        used += t
    return "\n".join(lines)


def _lane_semantic(tenant_id: str, agent_id: str, query: str, ctx: dict, mt: int) -> str:
    from app.platform import workforce_memory as wm

    return wm.recall_brief(agent_id, query, max_chars=mt * 4, tenant_id=tenant_id) or ""


def _lane_procedural(tenant_id: str, agent_id: str, query: str, ctx: dict, mt: int) -> str:
    from app.platform import skill_library

    return (skill_library.lessons_snippet(query or agent_id, k=3) or "")[: mt * 4]


def _lane_shared(tenant_id: str, agent_id: str, query: str, ctx: dict, mt: int) -> str:
    """Cross-agent shared entries — workforce_memory ka ACL respect karta."""
    from app.platform import workforce_memory as wm

    rows = (
        wm.recall(
            agent_id,
            query,
            assets=[wm.ASSET_WIKI, wm.ASSET_SKILL],
            limit=3,
            tenant_id=tenant_id,
        )
        or []
    )
    lines: list[str] = []
    used = 0
    for r in rows:
        if str(r.get("visibility") or "") != "team":
            continue
        line = f"- [{r.get('layer', '?')}] {str(r.get('content') or '')[:200]}"
        t = count_tokens(line) + 1
        if used + t > mt:
            break
        lines.append(line)
        used += t
    return "\n".join(lines)


_SYNC_LANES: dict[str, Callable[[str, str, str, dict, int], str]] = {
    "working": _lane_working,
    "prospective": _lane_prospective,
    "semantic": _lane_semantic,
    "procedural": _lane_procedural,
    "shared": _lane_shared,
}

_LANE_TITLES = {
    "working": "## Abhi ki baat-cheet (working)",
    "prospective": "## Aane wale kaam (prospective)",
    "episodic": "## Pichhli baar kya hua (episodic)",
    "semantic": "## Pakki baatein (semantic)",
    "procedural": "## Kaise karna hai (procedural)",
    "shared": "## Team se saanjha (shared)",
}


async def _lane_episodic(tenant_id: str, agent_id: str, query: str, ctx: dict, mt: int) -> str:
    subject_id = ctx.get("subject_id")
    if not subject_id:
        return ""
    from app.voice_agent import agent_memory

    block = await agent_memory.recall_block(
        subject_id, query, scope=str(ctx.get("scope") or "lead")
    )
    return (block or "")[: mt * 4]


def _deadline_ms() -> int:
    return _env_int("MEMORY_STACK_DEADLINE_MS", 250, lo=20, hi=5_000)


def _empty(reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "reason": reason,
        "block": "",
        "layers": {},
        "tokens": 0,
        "budget_tokens": 0,
        "tiers": [],
        "elapsed_ms": 0,
        "timeouts": 0,
        "errors": 0,
        "truncated": False,
    }


async def assemble(
    tenant_id: str,
    agent_id: str,
    query: str = "",
    *,
    session_id: str = "",
    subject_id: Any = None,
    scope: str = "lead",
    token_budget: int | None = None,
    prompt_overhead: int = 0,
    tiers: Iterable[str] | None = None,
    layers: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Saat layers se ek TOKEN-budgeted, deadline-bounded context block.

    Hierarchical (L5): hot layers pehle apna quota lete hain, bacha hua warm ko,
    phir cold ko. Deadline khatam = baaki lanes chhodi jaati hain (partial
    context > slow turn). Kabhi raise nahi karta.
    """
    if not is_enabled():
        _STATS["disabled"] += 1
        return _empty("master flag off")
    tid = str(tenant_id or "").strip()[:64]
    if not tid:
        _STATS["disabled"] += 1
        return _empty("tenant_id required")  # no global fallback tenant, ever

    # Import/warm cost is paid BEFORE the deadline clock starts — otherwise the
    # first call after boot times out every lane (see _warm_sync docstring).
    await prewarm()

    t0 = time.monotonic()
    budget = effective_token_budget(token_budget, prompt_overhead=prompt_overhead)
    if budget <= 0:
        return _empty("no token room after reserve")
    want_tiers = tuple(t for t in (tiers or active_tiers()) if t in TIERS) or TIERS
    want_layers = set(layers or LAYERS)
    deadline = t0 + (_deadline_ms() / 1000.0)
    ctx = {"session_id": session_id, "subject_id": subject_id, "scope": scope}

    parts: list[str] = []
    lane_parts: list[tuple[str, str]] = []
    used = 0
    per_layer: dict[str, int] = {}
    seen_lines: set[str] = set()
    timeouts = errors = 0
    truncated = False

    for tier in TIERS:
        if tier not in want_tiers:
            continue
        for key, ltier, share in LAYER_SPECS:
            if ltier != tier or key not in want_layers or not layer_enabled(key):
                continue
            remaining = budget - used
            if remaining <= 8:
                truncated = True
                break
            left_ms = (deadline - time.monotonic()) * 1000.0
            if left_ms <= 0:
                timeouts += 1
                _STATS["layer_timeout"] += 1
                truncated = True
                break
            quota = max(16, min(remaining, int(budget * share)))
            try:
                if key == "episodic":
                    text = await asyncio.wait_for(
                        _lane_episodic(tid, agent_id, query, ctx, quota),
                        timeout=max(0.02, left_ms / 1000.0),
                    )
                else:
                    fn = _SYNC_LANES[key]
                    text = await asyncio.wait_for(
                        asyncio.to_thread(fn, tid, agent_id, query, ctx, quota),
                        timeout=max(0.02, left_ms / 1000.0),
                    )
            except asyncio.TimeoutError:
                timeouts += 1
                _STATS["layer_timeout"] += 1
                logger.debug("[memory_stack] lane %s timed out", key)
                continue
            except Exception as e:
                errors += 1
                _STATS["layer_error"] += 1
                logger.debug("[memory_stack] lane %s skipped: %s", key, e)
                continue

            text = _dedupe_lines(_redact((text or "").strip()), seen_lines).strip()
            if not text:
                continue
            title = _LANE_TITLES.get(key, key)
            body, cut = _truncate_to_tokens(
                text, max(1, min(quota, budget - used) - count_tokens(title) - 1)
            )
            if not body.strip():
                truncated = truncated or cut
                continue
            block = f"{title}\n{body}"
            cost = count_tokens(block) + 1
            if used + cost > budget:
                truncated = True
                continue
            parts.append(block)
            lane_parts.append((key, block))  # lane identity kept for authority ranking
            used += cost
            per_layer[key] = cost
            truncated = truncated or cut

    # Staleness/conflict resolution runs LAST so it can see facts from EVERY
    # lane, and it knows which lane each fact came from so source authority can
    # break an equal-timestamp tie. An unresolved conflict injects NEITHER value.
    # Dropping only shrinks the block, so the token budget above stays valid.
    block = "\n\n".join(parts)
    conflicts: list[dict[str, Any]] = []
    unresolved = 0
    try:
        from app.platform.memory_governance import REASON_CONFLICTED, resolve_facts

        resolved, conflicts = resolve_facts(lane_parts)
        block = "\n\n".join(t for _lane, t in resolved if t.strip())
        if conflicts:
            unresolved = sum(1 for c in conflicts if c.get("reason") == REASON_CONFLICTED)
            _STATS["stale_facts_dropped"] += len(conflicts) - unresolved
            _STATS["conflicted_facts"] += unresolved
            used = count_tokens(block)
    except Exception as e:
        logger.debug("[memory_stack] conflict resolution skipped: %s", e)

    if truncated:
        _STATS["truncated"] += 1
    _STATS["assembled"] += 1
    return {
        "enabled": True,
        "reason": "",
        "tenant_id": tid,
        "block": block,
        "conflicts_resolved": len(conflicts),
        "conflicts_unresolved": unresolved,
        "conflict_report": conflicts,  # masked values only (POLICY B)
        "layers": per_layer,
        "tokens": used,
        "budget_tokens": budget,
        "tiers": list(want_tiers),
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
        "timeouts": timeouts,
        "errors": errors,
        "truncated": truncated,
    }


async def assemble_block(tenant_id: str, agent_id: str, query: str = "", **kw) -> str:
    """Prompt-injection convenience — sirf string, kabhi raise nahi."""
    try:
        return str((await assemble(tenant_id, agent_id, query, **kw)).get("block") or "")
    except Exception:
        _STATS["error"] += 1
        return ""


def stats() -> dict[str, int]:
    return dict(_STATS)


_BACKING = {
    "working": "memory_stack in-process FIFO (NON-authoritative, TTL+LRU)",
    "prospective": "prospective_store (Postgres: claim/lease/idempotency)",
    "episodic": "voice_agent.agent_memory (Qdrant) — needs AGENT_MEMORY",
    "semantic": "platform.workforce_memory L2/L3 — needs WORKFORCE_MEMORY",
    "procedural": "platform.skill_library",
    "shared": "platform.workforce_memory shared/equip — needs WORKFORCE_MEMORY",
}


def snapshot(tenant_id: str = "") -> dict[str, Any]:
    """Ops view. Counts + config only — never memory CONTENT (no leak surface)."""
    lanes: dict[str, Any] = {}
    for key, tier, share in LAYER_SPECS:
        lanes[key] = {
            "tier": tier,
            "quota_share": share,
            "enabled": layer_enabled(key),
            "backed_by": _BACKING.get(key, ""),
        }
    prospective: dict[str, Any] = {"available": False}
    try:
        from app.platform import prospective_store as ps

        prospective = ps.stats(tenant_id)
    except Exception:
        pass
    return {
        "enabled": is_enabled(),
        "config": validate_config(),
        "budget": {
            "context_tokens": _context_tokens(),
            "reserve_tokens": _reserve_tokens(),
            "token_budget": _token_budget(),
            "effective": effective_token_budget(),
            "deadline_ms": _deadline_ms(),
        },
        "lanes": lanes,
        "working": working_snapshot(),
        "prospective": prospective,
        "counters": stats(),
        "upstream_flags": {
            "AGENT_MEMORY": _truthy(os.getenv("AGENT_MEMORY")),
            "WORKFORCE_MEMORY": _truthy(os.getenv("WORKFORCE_MEMORY")),
        },
    }


__all__ = [
    "LAYERS",
    "LAYER_SPECS",
    "TIERS",
    "is_enabled",
    "layer_enabled",
    "dispatch_ready",
    "validate_config",
    "active_tiers",
    "count_tokens",
    "effective_token_budget",
    "prewarm",
    "push_turn",
    "working_window",
    "clear_working",
    "clear_tenant_working",
    "working_snapshot",
    "schedule",
    "drain_due",
    "drain_if_enabled",
    "assemble",
    "assemble_block",
    "stats",
    "snapshot",
]
