"""Read-only provider-health snapshot for the dev control plane.

Merges the routing catalog (``registry.MODEL_CATALOG``) with the live
circuit-breaker state that ``app.voice_agent.free_ai`` already maintains
(`_LLM_COOLDOWN_UNTIL` escalating cooldowns). No new breaker is implemented --
free_ai remains the single owner of provider cooldown truth; this module only
observes it so routing/admin surfaces can show quota health without another
parallel health system.

``breaker_lookup`` is injectable so tests never import the heavy free_ai module.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable


def _free_ai_breaker_state(provider: str) -> dict[str, Any]:
    """Best-effort view of free_ai's cooldown map; 'unknown' when unavailable."""
    try:
        from app.voice_agent import free_ai

        until = float(getattr(free_ai, "_LLM_COOLDOWN_UNTIL", {}).get(provider, 0.0) or 0.0)
        streak = int(getattr(free_ai, "_LLM_TRIP_STREAK", {}).get(provider, 0) or 0)
        now = time.time()
        if until > now:
            return {
                "state": "cooling",
                "cooldown_remaining_s": int(until - now),
                "trip_streak": streak,
            }
        return {"state": "closed", "cooldown_remaining_s": 0, "trip_streak": streak}
    except Exception:
        return {"state": "unknown", "cooldown_remaining_s": None, "trip_streak": None}


def provider_health_snapshot(
    breaker_lookup: Callable[[str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """One row per catalog provider: config, cost class, capabilities, breaker."""
    from app.dev_control.registry import MODEL_CATALOG

    lookup = breaker_lookup or _free_ai_breaker_state
    checked_at = datetime.utcnow().isoformat()
    rows: list[dict[str, Any]] = []
    for alias, meta in MODEL_CATALOG.items():
        breaker = lookup(alias) or {}
        cost_free = (
            float(meta.get("cost_input_usd_per_million", 0) or 0) == 0.0
            and float(meta.get("cost_output_usd_per_million", 0) or 0) == 0.0
        )
        rows.append(
            {
                "provider_name": alias,
                "model_name": meta.get("model"),
                "task_capabilities": list(meta.get("capabilities", [])),
                "privacy_class": meta.get("privacy"),
                "cost_class": "free" if cost_free else "paid",
                "enabled": bool(meta.get("configured")),
                "circuit_breaker_state": breaker.get("state", "unknown"),
                "cooldown_remaining_s": breaker.get("cooldown_remaining_s"),
                "trip_streak": breaker.get("trip_streak"),
                "last_health_check": checked_at,
            }
        )
    return rows


def healthy_providers(snapshot: list[dict[str, Any]] | None = None) -> list[str]:
    """Providers that are configured and not currently cooling down."""
    rows = snapshot if snapshot is not None else provider_health_snapshot()
    return [
        r["provider_name"]
        for r in rows
        if r.get("enabled") and r.get("circuit_breaker_state") != "cooling"
    ]
