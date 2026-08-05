"""Concurrency caps for PR Factory waves (Wave 1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FactoryBudgets:
    claude_executors: int = 4
    cursor_executors: int = 4
    reviewers: int = 2
    ci_repair: int = 1
    merge_coord: int = 1
    # Deploy is never factory-owned.
    deploy_lane: int = 0


DEFAULT_BUDGETS = FactoryBudgets()


def wave_slots() -> dict[str, int]:
    """Documented wave model: 8 impl + 2 reviewers (+ repair/merge coords)."""
    b = DEFAULT_BUDGETS
    return {
        "implementation_missions": b.claude_executors + b.cursor_executors,
        "reviewers": b.reviewers,
        "ci_repair": b.ci_repair,
        "merge_coord": b.merge_coord,
        "deploy_lane_owner_os_only": b.deploy_lane,
    }


def can_claim_slot(role: str, active_counts: dict[str, int] | None = None) -> dict[str, Any]:
    """Return ok/reason for claiming a concurrency slot."""
    counts = active_counts or {}
    role_n = (role or "").strip().lower()
    b = DEFAULT_BUDGETS
    limits = {
        "claude": b.claude_executors,
        "cursor": b.cursor_executors,
        "reviewer": b.reviewers,
        "ci_repair": b.ci_repair,
        "merge": b.merge_coord,
        "deploy": b.deploy_lane,
    }
    if role_n not in limits:
        return {"ok": False, "reason": "unknown_role", "role": role_n}
    limit = limits[role_n]
    current = int(counts.get(role_n) or 0)
    if role_n == "deploy":
        return {"ok": False, "reason": "deploy_lane_owner_os_only", "limit": 0}
    if current >= limit:
        return {"ok": False, "reason": "budget_exhausted", "role": role_n, "limit": limit}
    return {"ok": True, "role": role_n, "limit": limit, "current": current}
