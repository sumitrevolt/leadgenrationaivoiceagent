"""Mission eligibility for unattended runner invocation."""

from __future__ import annotations

from typing import Any

from app.dev_control.external_agents import policy, store
from app.dev_control.external_agents.runner.flags import runner_enabled
from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass

ELIGIBLE_STATUSES = frozenset(
    {
        MissionState.CREATED,
        MissionState.PREFLIGHT,
        MissionState.CLAIMED,
        MissionState.CHANGES_REQUESTED,
        MissionState.FAILED_RETRYABLE,
    }
)

KNOWN_EXECUTORS = frozenset({"cursor", "claude"})


def evaluate(mission: Mission | None) -> dict[str, Any]:
    """Return ``{eligible, reason, ...}``. Never raises."""
    if not runner_enabled():
        return {"eligible": False, "reason": "runner_or_orchestrator_off"}
    if mission is None:
        return {"eligible": False, "reason": "mission_not_found"}
    if mission.risk_class is RiskClass.RED:
        return {"eligible": False, "reason": "red_refused"}
    if mission.risk_class is RiskClass.AMBER:
        return {
            "eligible": False,
            "reason": "owner_decision_required",
            "park": MissionState.OWNER_DECISION_REQUIRED.value,
        }
    if mission.risk_class is not RiskClass.GREEN:
        return {"eligible": False, "reason": "unknown_risk"}
    if mission.status not in ELIGIBLE_STATUSES:
        return {
            "eligible": False,
            "reason": "status_not_eligible",
            "status": mission.status.value,
        }
    ex = (mission.executor or "").strip().lower()
    if ex not in KNOWN_EXECUTORS:
        return {"eligible": False, "reason": "unknown_executor", "executor": ex}
    if not (mission.allowed_paths or []):
        return {"eligible": False, "reason": "allowed_paths_required"}
    if not policy.normalise_prohibited(mission.prohibited_paths):
        return {"eligible": False, "reason": "prohibited_paths_missing"}
    if ex == "cursor" and not (mission.branch and mission.worktree):
        return {"eligible": False, "reason": "cursor_requires_branch_worktree"}
    conflict = policy.ownership_conflict(mission, store.list_missions(limit=500))
    if conflict.get("conflict"):
        return {"eligible": False, "reason": "ownership_conflict", "conflict": conflict}
    if not policy.retry_allowed(mission) and mission.status is MissionState.FAILED_RETRYABLE:
        return {"eligible": False, "reason": "retry_budget_exhausted"}
    return {
        "eligible": True,
        "reason": "ok",
        "executor": ex,
        "reviewer": (mission.reviewer or "").strip().lower(),
    }
