"""
budget_guard.py — per-scope LLM cost/usage governance + emergency kill-switch.

KYUN: free_ai.py ka circuit-breaker provider-level 429/quota handle karta, par
"ek scope (client/loop/niche) ne aaj kitne LLM calls/tokens jala diye" ka koi
per-tenant/per-loop CAP nahi tha. Runaway self-improve loop ya ek client ka abuse
poora free-tier (Groq TPD) kha sakta = baaki sabki availability + margin gir jaati.
Yeh module daily per-scope budget + ek HARD global kill-switch deta.

DESIGN (prod-rules ke according — semantic_cache.py jaisa):
  - FLAG-GATED: `LLM_BUDGET_GUARD` (OFF default) — unset = is_enabled() False =
    free_ai turant skip karta (ZERO extra I/O, ZERO behaviour change).
  - FAIL-OPEN: koi bhi redis/error = allow=True (LLM kabhi block na ho galti se).
    EXCEPTION: `LLM_BUDGET_HARD_KILL=1` = jaan-boojh ke emergency stop (fail-CLOSED
    by design — admin ne manually daala hai).
  - DURABLE COUNTERS: main redis (noeviction) — LRU cache redis nahi (evict = undercount).
  - SHARED: multi-worker-correct (redis), /metrics expose karta hai.
  - DECOUPLED: core duck-typed; default backend lazily app.cache redis use karta.

USAGE (free_ai.chat opt-in karta):
    from app.llm import budget_guard
    if budget_guard.is_enabled():
        ok, info = await budget_guard.allow(scope)
        if not ok:
            return "", ""        # graceful — jaise saare providers exhaust
    ... call ...
    await budget_guard.record(scope, prompt_tokens=pt, completion_tokens=ct)

Top-level imports SIRF stdlib — app.* sab lazy (bina poore app ke import/test ho sake).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PREFIX = "llmbudget"
_GLOBAL = "__global__"
_COUNTER_TTL_S = 172800  # 2 days — daily counter, thoda buffer

# per-process quick snapshot (debug). Source-of-truth = redis.
_LOCAL: dict[str, int] = {"allowed": 0, "blocked": 0, "killed": 0, "error": 0, "disabled": 0}


# --- config (env, runtime-toggle-able) ----------------------------------------
def is_enabled() -> bool:
    return (os.getenv("LLM_BUDGET_GUARD", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _hard_kill() -> bool:
    """Emergency global stop — fail-CLOSED by design (admin ne manually set kiya)."""
    return (os.getenv("LLM_BUDGET_HARD_KILL", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def active() -> bool:
    """Guard ko consult karna chahiye? = normal budget guard ON, YA emergency hard-kill ON.
    free_ai is helper se gate karta taaki sirf LLM_BUDGET_HARD_KILL=1 set karne pe bhi
    kill reachable rahe (warna emergency switch inert)."""
    return is_enabled() or _hard_kill()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return default


def _scope_call_cap() -> int:
    # per-scope/day calls. 0 = is dimension pe koi cap nahi.
    return _int_env("LLM_BUDGET_DAILY_CALLS", 5000)


def _scope_token_cap() -> int:
    # per-scope/day tokens. 0 = no cap.
    return _int_env("LLM_BUDGET_DAILY_TOKENS", 3_000_000)


def _global_call_cap() -> int:
    # global/day calls (sab scopes ka jod). 0 = no cap.
    return _int_env("LLM_BUDGET_GLOBAL_DAILY_CALLS", 50_000)


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _safe_scope(scope: str) -> str:
    s = (scope or "global").strip().lower()
    # redis-key-safe + bounded
    return "".join(ch if (ch.isalnum() or ch in "-_:.") else "_" for ch in s)[:80] or "global"


def _ckey(day: str, scope: str, kind: str) -> str:
    return f"{_PREFIX}:{day}:{scope}:{kind}"


# --- redis backend (lazy, best-effort) ----------------------------------------
async def _redis():
    """Main (noeviction) redis — durable counters. semantic_cache cache-redis nahi."""
    from app.cache import get_redis_client

    return await get_redis_client()


async def _get_int(r: Any, key: str) -> int:
    try:
        v = await r.get(key)
        return int(v or 0)
    except Exception:
        return 0


# --- public API ---------------------------------------------------------------
async def allow(scope: str = "global") -> tuple[bool, dict[str, Any]]:
    """Is scope ko abhi LLM call karne dena chahiye?

    Returns (allowed, info). FAIL-OPEN: redis/koi error = (True, ...). Hard-kill ON
    = (False, ...) hamesha (fail-closed, intentional emergency stop).
    """
    info: dict[str, Any] = {"scope": scope, "reason": "ok"}

    # Emergency manual kill-switch — guard flag se INDEPENDENT (fail-closed, jaan-boojh ke).
    # is_enabled() check se PEHLE: incident me sirf LLM_BUDGET_HARD_KILL=1 set karne se bhi
    # turant sab LLM band ho (warna emergency switch inert reh jaata — review finding #1).
    if _hard_kill():
        _LOCAL["killed"] += 1
        info["reason"] = "hard_kill"
        return False, info

    if not is_enabled():
        _LOCAL["disabled"] += 1
        info["reason"] = "disabled"
        return True, info

    sc = _safe_scope(scope)
    day = _day()
    try:
        r = await _redis()
        # global cap
        gcap = _global_call_cap()
        if gcap > 0:
            gcalls = await _get_int(r, _ckey(day, _GLOBAL, "calls"))
            if gcalls >= gcap:
                _LOCAL["blocked"] += 1
                info.update(reason="global_calls", used=gcalls, cap=gcap)
                return False, info
        # per-scope caps
        ccap = _scope_call_cap()
        if ccap > 0:
            scalls = await _get_int(r, _ckey(day, sc, "calls"))
            if scalls >= ccap:
                _LOCAL["blocked"] += 1
                info.update(reason="scope_calls", used=scalls, cap=ccap)
                return False, info
        tcap = _scope_token_cap()
        if tcap > 0:
            stoks = await _get_int(r, _ckey(day, sc, "tokens"))
            if stoks >= tcap:
                _LOCAL["blocked"] += 1
                info.update(reason="scope_tokens", used=stoks, cap=tcap)
                return False, info
    except Exception as e:  # redis down / any error → FAIL-OPEN
        _LOCAL["error"] += 1
        logger.debug("budget_guard allow fail-open: %s", e)
        info["reason"] = "error_failopen"
        return True, info

    _LOCAL["allowed"] += 1
    return True, info


async def record(
    scope: str = "global",
    *,
    calls: int = 1,
    prompt_tokens: int | None = 0,
    completion_tokens: int | None = 0,
) -> None:
    """Ek LLM call ka usage count karo (best-effort, never-raise)."""
    if not is_enabled():
        return
    toks = int(prompt_tokens or 0) + int(completion_tokens or 0)
    sc = _safe_scope(scope)
    day = _day()
    try:
        r = await _redis()
        for key, amt in (
            (_ckey(day, sc, "calls"), int(calls or 0)),
            (_ckey(day, sc, "tokens"), toks),
            (_ckey(day, _GLOBAL, "calls"), int(calls or 0)),
            (_ckey(day, _GLOBAL, "tokens"), toks),
        ):
            if amt <= 0:
                continue
            try:
                pipe = r.pipeline()
                pipe.incrby(key, amt)
                pipe.expire(key, _COUNTER_TTL_S)
                await pipe.execute()
            except Exception:
                # pipeline na ho (e.g. Redis-down -> InMemoryCache fallback, jisme
                # pipeline/incrby nahi) -> incrby try, warna get+set (review finding #2:
                # warna outage me counters dormant ho jaate = guard non-enforcing).
                try:
                    await r.incrby(key, amt)
                except Exception:
                    try:
                        cur = int(await r.get(key) or 0)
                        await r.set(key, cur + amt)
                        try:
                            await r.expire(key, _COUNTER_TTL_S)
                        except Exception:
                            pass
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("budget_guard record skipped: %s", e)


def snapshot() -> dict[str, int]:
    """Per-process counters (quick debug). /metrics ke liye redis_stats()."""
    return dict(_LOCAL)


async def redis_stats() -> dict[str, Any]:
    """Aaj ke GLOBAL counters + config — /metrics ke liye. Fail = zeros + enabled flag."""
    out: dict[str, Any] = {
        "enabled": is_enabled(),
        "hard_kill": _hard_kill(),
        "global_calls": 0,
        "global_tokens": 0,
        "global_call_cap": _global_call_cap(),
        "scope_call_cap": _scope_call_cap(),
        "scope_token_cap": _scope_token_cap(),
        **{f"events_{k}": v for k, v in _LOCAL.items()},
    }
    if not is_enabled():
        return out
    try:
        r = await _redis()
        day = _day()
        out["global_calls"] = await _get_int(r, _ckey(day, _GLOBAL, "calls"))
        out["global_tokens"] = await _get_int(r, _ckey(day, _GLOBAL, "tokens"))
    except Exception:
        pass
    return out


def reset_local() -> None:
    for k in _LOCAL:
        _LOCAL[k] = 0
