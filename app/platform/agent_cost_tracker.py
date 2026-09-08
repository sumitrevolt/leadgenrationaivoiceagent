"""
Agent Cost Tracker — per-agent, per-provider LLM token+cost logging.
====================================================================

Lightweight Redis counters (daily rollover) + optional DB write for dashboard.
Piggybacks on existing budget_guard + team.log_event infrastructure.

Usage:
    from app.platform import agent_cost_tracker as act

    # After any LLM call:
    act.record("isha", provider="groq", tokens_in=500, tokens_out=200)

    # Dashboard queries:
    today = act.today_snapshot()        # {agent: {provider: {calls, tokens_in, tokens_out}}}
    agent = act.agent_today("isha")     # {provider: {calls, tokens_in, tokens_out}}
    total = act.total_today()           # {calls, tokens_in, tokens_out, by_provider: {...}}
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PREFIX = "agent_cost"


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _redis_sync():
    """Get sync Redis client — never raises (returns None)."""
    try:
        import redis

        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        return redis.from_url(url, decode_responses=True, socket_timeout=2)
    except Exception:
        return None


def record(
    agent_id: str,
    *,
    provider: str = "unknown",
    tokens_in: int = 0,
    tokens_out: int = 0,
    model: str = "",
) -> None:
    """Record one LLM call's tokens for an agent. Best-effort, never raises."""
    try:
        r = _redis_sync()
        if not r:
            return
        day = _day()
        key = agent_id.strip().lower()
        prov = provider.strip().lower() or "unknown"

        # Keys: agent_cost:<day>:<agent>:<provider>:{calls,in,out}
        base = f"{_PREFIX}:{day}:{key}:{prov}"
        pipe = r.pipeline()
        pipe.incrby(f"{base}:calls", 1)
        pipe.incrby(f"{base}:in", int(tokens_in or 0))
        pipe.incrby(f"{base}:out", int(tokens_out or 0))
        # Also track global per-agent total
        abase = f"{_PREFIX}:{day}:{key}:_total"
        pipe.incrby(f"{abase}:calls", 1)
        pipe.incrby(f"{abase}:in", int(tokens_in or 0))
        pipe.incrby(f"{abase}:out", int(tokens_out or 0))
        # Set TTL 48h on all keys
        for suffix in (":calls", ":in", ":out"):
            pipe.expire(f"{base}{suffix}", 172800)
            pipe.expire(f"{abase}{suffix}", 172800)
        pipe.execute()
    except Exception as e:
        logger.debug(f"[agent_cost] record skip: {e}")


def agent_today(agent_id: str) -> dict[str, Any]:
    """Get today's cost breakdown for one agent."""
    try:
        r = _redis_sync()
        if not r:
            return {}
        day = _day()
        key = agent_id.strip().lower()
        # Scan for all provider keys
        pattern = f"{_PREFIX}:{day}:{key}:*:calls"
        result: dict[str, dict[str, int]] = {}
        for k in r.scan_iter(pattern, count=100):
            prov = k.split(":")[-2]
            if prov == "_total":
                continue
            base = k.rsplit(":calls", 1)[0]
            result[prov] = {
                "calls": int(r.get(f"{base}:calls") or 0),
                "tokens_in": int(r.get(f"{base}:in") or 0),
                "tokens_out": int(r.get(f"{base}:out") or 0),
            }
        # Total
        tbase = f"{_PREFIX}:{day}:{key}:_total"
        total = {
            "calls": int(r.get(f"{tbase}:calls") or 0),
            "tokens_in": int(r.get(f"{tbase}:in") or 0),
            "tokens_out": int(r.get(f"{tbase}:out") or 0),
        }
        return {"agent_id": key, "date": day, "total": total, "by_provider": result}
    except Exception as e:
        logger.debug(f"[agent_cost] agent_today skip: {e}")
        return {}


def today_snapshot() -> dict[str, Any]:
    """Per-agent cost snapshot for today — for dashboard."""
    try:
        r = _redis_sync()
        if not r:
            return {}
        day = _day()
        pattern = f"{_PREFIX}:{day}:*:_total:calls"
        agents: dict[str, dict[str, int]] = {}
        for k in r.scan_iter(pattern, count=200):
            parts = k.split(":")
            agent_id = parts[2]
            base = f"{_PREFIX}:{day}:{agent_id}:_total"
            agents[agent_id] = {
                "calls": int(r.get(f"{base}:calls") or 0),
                "tokens_in": int(r.get(f"{base}:in") or 0),
                "tokens_out": int(r.get(f"{base}:out") or 0),
            }
        return {"date": day, "agents": agents}
    except Exception as e:
        logger.debug(f"[agent_cost] snapshot skip: {e}")
        return {}


def total_today() -> dict[str, int]:
    """Grand total across all agents for today."""
    snap = today_snapshot()
    total_calls = sum(a.get("calls", 0) for a in snap.get("agents", {}).values())
    total_in = sum(a.get("tokens_in", 0) for a in snap.get("agents", {}).values())
    total_out = sum(a.get("tokens_out", 0) for a in snap.get("agents", {}).values())
    return {"calls": total_calls, "tokens_in": total_in, "tokens_out": total_out}
