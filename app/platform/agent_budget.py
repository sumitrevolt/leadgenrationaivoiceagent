"""
Agent Budget Governor — Paperclip-inspired 3-tier spend governance.
===================================================================

Tier 1: Dashboard visibility (agent_cost_tracker.today_snapshot() — already done)
Tier 2: Soft alert at threshold% — ntfy push notification
Tier 3: Hard ceiling — auto-pause agent via agent_controls.pause()

Budget config stored in Redis (hot) + data/agent_budgets.json (durable).
Per-agent daily token limits. Cascade: global default → per-agent override.

Usage:
    from app.platform import agent_budget

    # Set budget for an agent (tokens_per_day)
    agent_budget.set_budget("isha", tokens_per_day=50000)

    # Check before LLM call (called from run_member or free_ai)
    allowed = agent_budget.check("isha")  # True/False

    # Get all budgets
    budgets = agent_budget.get_all_budgets()
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_BUDGET_FILE = os.path.join("data", "agent_budgets.json")
_DEFAULT_DAILY_TOKENS = int(os.environ.get("AGENT_BUDGET_DEFAULT_DAILY", "100000"))
_SOFT_ALERT_PCT = float(os.environ.get("AGENT_BUDGET_SOFT_PCT", "0.80"))  # 80%
_HARD_STOP_PCT = float(os.environ.get("AGENT_BUDGET_HARD_PCT", "1.0"))  # 100%
_BUDGET_ENABLED = os.environ.get("AGENT_BUDGET_ENABLED", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _load_budgets() -> dict[str, dict[str, Any]]:
    """Load per-agent budget config from JSON file."""
    try:
        if os.path.exists(_BUDGET_FILE):
            with open(_BUDGET_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"[agent_budget] load skip: {e}")
    return {}


def _save_budgets(budgets: dict[str, dict[str, Any]]) -> None:
    """Save per-agent budget config to JSON file."""
    try:
        os.makedirs("data", exist_ok=True)
        with open(_BUDGET_FILE, "w", encoding="utf-8") as f:
            json.dump(budgets, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"[agent_budget] save skip: {e}")


def set_budget(
    agent_id: str, *, tokens_per_day: int = 0, unlimited: bool = False
) -> dict[str, Any]:
    """Set daily token budget for an agent. unlimited=True = no ceiling."""
    key = agent_id.strip().lower()
    budgets = _load_budgets()
    budgets[key] = {
        "tokens_per_day": int(tokens_per_day) if not unlimited else 0,
        "unlimited": bool(unlimited),
    }
    _save_budgets(budgets)
    return {"ok": True, "agent_id": key, **budgets[key]}


def get_budget(agent_id: str) -> dict[str, Any]:
    """Get budget config for an agent. Falls back to global default."""
    key = agent_id.strip().lower()
    budgets = _load_budgets()
    if key in budgets:
        return {"agent_id": key, **budgets[key]}
    return {"agent_id": key, "tokens_per_day": _DEFAULT_DAILY_TOKENS, "unlimited": False}


def get_all_budgets() -> dict[str, dict[str, Any]]:
    """All configured budgets + defaults."""
    return _load_budgets()


def _get_today_usage(agent_id: str) -> int:
    """Get today's total token usage for an agent from Redis."""
    try:
        from app.platform import agent_cost_tracker as act

        data = act.agent_today(agent_id)
        total = data.get("total", {})
        return (total.get("tokens_in", 0) or 0) + (total.get("tokens_out", 0) or 0)
    except Exception:
        return 0


def check(agent_id: str) -> dict[str, Any]:
    """Check if agent is within budget. Returns status + action taken.

    Returns:
        {"allowed": True/False, "tier": 1|2|3, "usage": N, "limit": N, "pct": 0.XX}

    Tier 1 = within budget (dashboard only)
    Tier 2 = soft alert sent (80%+ used)
    Tier 3 = hard stop (100%+ used) — agent auto-paused
    """
    if not _BUDGET_ENABLED:
        return {
            "allowed": True,
            "tier": 0,
            "note": "budget governance disabled (AGENT_BUDGET_ENABLED=0)",
        }

    key = agent_id.strip().lower()
    budget = get_budget(key)

    if budget.get("unlimited"):
        return {"allowed": True, "tier": 1, "usage": 0, "limit": 0, "pct": 0, "note": "unlimited"}

    limit = budget.get("tokens_per_day", _DEFAULT_DAILY_TOKENS)
    if limit <= 0:
        return {"allowed": True, "tier": 1, "usage": 0, "limit": 0, "pct": 0}

    usage = _get_today_usage(key)
    pct = usage / limit if limit > 0 else 0

    result: dict[str, Any] = {
        "agent_id": key,
        "usage": usage,
        "limit": limit,
        "pct": round(pct, 3),
    }

    # Tier 3: Hard stop
    if pct >= _HARD_STOP_PCT:
        result["allowed"] = False
        result["tier"] = 3
        result["action"] = "auto_paused"
        _hard_stop(key, usage, limit)
        return result

    # Tier 2: Soft alert
    if pct >= _SOFT_ALERT_PCT:
        result["allowed"] = True
        result["tier"] = 2
        result["action"] = "soft_alert_sent"
        _soft_alert(key, usage, limit, pct)
        return result

    # Tier 1: Within budget
    result["allowed"] = True
    result["tier"] = 1
    return result


def _soft_alert(agent_id: str, usage: int, limit: int, pct: float) -> None:
    """Tier 2: Send ntfy push notification at 80%+ usage. Deduplicated per day."""
    try:
        import redis as _redis

        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = _redis.from_url(url, decode_responses=True, socket_timeout=2)

        from app.platform.agent_cost_tracker import _day

        dedup_key = f"agent_budget:alert:{_day()}:{agent_id}"
        if r.get(dedup_key):
            return  # already alerted today
        r.set(dedup_key, "1", ex=86400)
    except Exception:
        pass

    try:
        from app.platform import team

        team.log_event(
            agent_id,
            "budget_soft_alert",
            f"⚠️ {int(pct * 100)}% budget used ({usage:,}/{limit:,} tokens)",
            status="warn",
        )
    except Exception:
        pass

    # ntfy push
    try:
        import httpx

        ntfy_url = os.environ.get("NTFY_URL")
        if ntfy_url:
            httpx.post(
                ntfy_url,
                content=f"⚠️ Agent {agent_id}: {int(pct * 100)}% daily budget ({usage:,}/{limit:,} tokens)",
                headers={"Title": f"Budget Alert: {agent_id}", "Priority": "3"},
                timeout=5,
            )
    except Exception:
        pass


def _hard_stop(agent_id: str, usage: int, limit: int) -> None:
    """Tier 3: Auto-pause agent + ntfy alert. Agent can be resumed manually."""
    try:
        from app.platform import agent_controls

        agent_controls.pause(
            agent_id, by="budget_governor", note=f"Daily token limit exceeded ({usage:,}/{limit:,})"
        )
    except Exception as e:
        logger.warning(f"[agent_budget] hard_stop pause failed: {e}")

    try:
        from app.platform import team

        team.log_event(
            agent_id,
            "budget_hard_stop",
            f"🛑 HARD STOP — daily limit exceeded ({usage:,}/{limit:,} tokens). Agent paused.",
            status="error",
        )
    except Exception:
        pass

    # ntfy push — high priority
    try:
        import httpx

        ntfy_url = os.environ.get("NTFY_URL")
        if ntfy_url:
            httpx.post(
                ntfy_url,
                content=f"🛑 Agent {agent_id} AUTO-PAUSED: daily budget exceeded ({usage:,}/{limit:,} tokens)",
                headers={
                    "Title": f"HARD STOP: {agent_id}",
                    "Priority": "5",
                    "Tags": "rotating_light",
                },
                timeout=5,
            )
    except Exception:
        pass


def budget_dashboard() -> dict[str, Any]:
    """Full budget dashboard — all agents' usage vs limits. For admin UI."""
    try:
        from app.platform import agent_cost_tracker as act
        from app.platform.team import STAFF

        snapshot = act.today_snapshot()
        agents_usage = snapshot.get("agents", {})
        budgets = _load_budgets()

        rows = []
        for key in sorted(STAFF.keys()):
            usage_data = agents_usage.get(key, {})
            total_tokens = (usage_data.get("tokens_in", 0) or 0) + (
                usage_data.get("tokens_out", 0) or 0
            )
            budget_cfg = budgets.get(key, {})
            limit = budget_cfg.get("tokens_per_day", _DEFAULT_DAILY_TOKENS)
            unlimited = budget_cfg.get("unlimited", False)
            pct = (total_tokens / limit) if limit > 0 and not unlimited else 0

            tier = 1
            if not unlimited and limit > 0:
                if pct >= _HARD_STOP_PCT:
                    tier = 3
                elif pct >= _SOFT_ALERT_PCT:
                    tier = 2

            rows.append(
                {
                    "agent_id": key,
                    "tokens_used": total_tokens,
                    "tokens_limit": 0 if unlimited else limit,
                    "unlimited": unlimited,
                    "pct": round(pct, 3),
                    "tier": tier,
                    "calls": usage_data.get("calls", 0) or 0,
                }
            )

        return {
            "date": snapshot.get("date", ""),
            "enabled": _BUDGET_ENABLED,
            "default_daily": _DEFAULT_DAILY_TOKENS,
            "soft_pct": _SOFT_ALERT_PCT,
            "hard_pct": _HARD_STOP_PCT,
            "agents": rows,
        }
    except Exception as e:
        logger.warning(f"[agent_budget] dashboard failed: {e}")
        return {"error": str(e)}
