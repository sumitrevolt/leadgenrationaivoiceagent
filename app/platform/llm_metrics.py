"""LLM observability (Langfuse/Helicone-pattern, free file-based).

Har free-LLM provider call ka record: provider, ok/fail, latency-ms, error.
Isse pata chalta kaunsa provider kitna reliable/fast hai, fallback kitni baar
chala, aur AI automation ka asli health kya hai. Voice critical-path me hook
ULTRA-LIGHT hai (file append, never-raise, koi network nahi).

Store: data/llm_calls.jsonl (auto-trim ~10k lines). stats() = per-provider
calls/ok-rate/avg-ms/last-error + chain fallback-rate. Import-safe.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

_LOG = os.path.join("data", "llm_calls.jsonl")
_MAX_LINES = 10_000


def record(provider: str, ok: bool, ms: float, error: str = "", kind: str = "chat") -> None:
    """Ek provider attempt record karo. KABHI raise nahi, fast."""
    try:
        os.makedirs(os.path.dirname(_LOG) or ".", exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "p": (provider or "?")[:20],
                        "ok": bool(ok),
                        "ms": round(float(ms), 1),
                        "e": (error or "")[:120],
                        "k": kind[:10],
                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        # occasional trim (1% chance per call — file kabhi unbounded na ho)
        if hash(datetime.now().microsecond) % 100 == 0:
            _trim()
    except Exception:
        pass


def record_cache(hit: bool) -> None:
    """LLM response-cache lookup record (hit/miss) — W1.12 revisit-trigger prereq:
    cache hit-rate ke data ke bina L2/Redis-cache decision hunch hota. kind="cache"
    rows stats() me provider aggregation se ALAG rehti hain (fallback-rate/capacity
    -alert skew nahi). record() reuse = same never-raise + trim. Ultra-light."""
    record("cache", bool(hit), 0.0, "" if hit else "miss", kind="cache")


# Rate-limit-class error keywords — free_ai._trip_cooldown ke is_rate_limit jaisa
# (429/quota/TPD family). stats() me per-provider explicit count ke liye.
_RL_KEYS = ("429", "rate", "quota", "queue", "too_many", "exhaust")


def _trim() -> None:
    # READ-MODIFY-WRITE — multi-worker me lock zaroori (do process ek saath
    # trim karein to file truncate ho sakti thi). Lock + atomic os.replace.
    try:
        from app.utils.file_lock import file_lock

        with file_lock(_LOG):
            with open(_LOG, encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > _MAX_LINES:
                tmp = f"{_LOG}.tmp.{os.getpid()}"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(lines[-_MAX_LINES // 2 :])
                os.replace(tmp, _LOG)
    except Exception:
        pass


def _read_tail(n: int = 2000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_LOG):
            with open(_LOG, encoding="utf-8") as f:
                lines = f.readlines()[-n:]
            for line in lines:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return rows


def stats(window: int = 2000) -> dict[str, Any]:
    """Per-provider health + overall fallback rate + cache hit-rate. Kabhi raise nahi."""
    all_rows = _read_tail(window)
    # kind="cache" rows alag — provider health/fallback-rate (capacity-alert input)
    # ko cache lookups pollute na karein.
    rows = [r for r in all_rows if r.get("k") != "cache"]
    cache_rows = [r for r in all_rows if r.get("k") == "cache"]
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        p = r.get("p", "?")
        d = by.setdefault(p, {"calls": 0, "ok": 0, "ms_sum": 0.0, "last_error": "", "rl": 0})
        d["calls"] += 1
        if r.get("ok"):
            d["ok"] += 1
            d["ms_sum"] += float(r.get("ms", 0) or 0)
        elif r.get("e"):
            d["last_error"] = r["e"]
        if not r.get("ok") and any(k in str(r.get("e") or "").lower() for k in _RL_KEYS):
            d["rl"] += 1
    out: dict[str, Any] = {"providers": {}, "total_calls": len(rows)}
    for p, d in by.items():
        ok = d["ok"]
        out["providers"][p] = {
            "calls": d["calls"],
            "ok_rate": round(ok / max(d["calls"], 1), 3),
            "avg_ms": round(d["ms_sum"] / max(ok, 1), 1),
            "last_error": d["last_error"],
            "rate_limited": d["rl"],
        }
    fails = sum(1 for r in rows if not r.get("ok"))
    out["fallback_or_fail_rate"] = round(fails / max(len(rows), 1), 3)
    if cache_rows:
        hits = sum(1 for r in cache_rows if r.get("ok"))
        out["cache"] = {
            "lookups": len(cache_rows),
            "hits": hits,
            "hit_rate": round(hits / max(len(cache_rows), 1), 3),
        }
    return out


async def run_capacity_watch() -> dict[str, Any]:
    """LLM gateway CAPACITY/RELIABILITY alert (competitor best-practice — LiteLLM/Vapi:
    alert jab fallback-rate high ya provider-headroom low). Free providers exhaust hote
    (groq TPD, gemini quota-0, openrouter 404) -> voice latency + content quality girti =
    project ka #1 live bottleneck. Ye bottleneck system KHUD flag kare (observability->
    action) taaki capacity/upgrade decision data-driven ho. GATED LLM_CAPACITY_ALERTS=1
    (off = sirf return, no send). Dedupe via ops_watchdog cooldown. Never-raise."""
    try:
        import os as _os

        st = stats(window=300)
        total = int(st.get("total_calls", 0) or 0)
        rate = float(st.get("fallback_or_fail_rate", 0) or 0)
        provs = st.get("providers", {}) or {}
        healthy = [
            p
            for p, v in provs.items()
            if isinstance(v, dict)
            and float(v.get("ok_rate", 0) or 0) >= 0.5
            and int(v.get("calls", 0) or 0) >= 3
        ]
        exhausted = [
            p
            for p, v in provs.items()
            if isinstance(v, dict)
            and any(
                k in str(v.get("last_error", "")).lower()
                for k in (
                    "quota",
                    "tpd",
                    "per day",
                    "rate limit",
                    "exhaust",
                    "429",
                    "resource_exhausted",
                )
            )
        ]
        degraded = total >= 30 and (rate >= 0.4 or len(healthy) <= 1)
        res = {
            "ok": not degraded,
            "total_calls": total,
            "fallback_rate": rate,
            "healthy_providers": healthy,
            "exhausted": exhausted,
        }
        if degraded and _os.environ.get("LLM_CAPACITY_ALERTS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            try:
                from app.platform import ops_watchdog

                if ops_watchdog._should_alert("llm_capacity"):
                    body = (
                        f"LLM capacity DEGRADED — fallback/fail-rate {rate}, healthy providers "
                        f"{len(healthy)} ({', '.join(healthy) or 'NONE'}), exhausted: {', '.join(exhausted) or '-'}.\n"
                        f"Asar: voice latency badhti (script-fallback), content quality template pe girti.\n"
                        f"Fix (highest ROI): ek headroom/paid LLM key add karo — Groq Dev tier ya 1 paid provider."
                    )
                    await ops_watchdog._alert(
                        "⚠️ LeadGenAI: LLM capacity low (voice/content affected)", body
                    )
                    res["alerted"] = True
            except Exception:
                pass
        return res
    except Exception as e:  # pragma: no cover
        return {"ok": True, "error": str(e)[:120]}
