"""Mission orchestration glue — the only place missions change state.

Flow (all of it fail-closed):

    create -> preflight -> claim -> running -> implemented -> testing
           -> review_required -> (review_passed | changes_requested)
           -> pr_open -> ci_running -> merge_queued -> merged
           -> [deployment_pending -> canary_running] -> verified -> complete

GREEN missions progress automatically through the code/PR/CI portion.
AMBER missions stop at ``OWNER_DECISION_REQUIRED`` before merge/deploy.
RED requests are refused at creation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.dev_control import locks
from app.dev_control.external_agents import adapters, policy, store
from app.dev_control.external_agents.schema import (
    InvalidMissionTransition,
    Mission,
    MissionState,
    RiskClass,
)

DEFAULT_LEASE_S = 900


class OrchestratorDisabled(RuntimeError):
    """EXTERNAL_AGENT_ORCHESTRATOR is off — nothing may run."""


def _require_enabled() -> None:
    if not policy.orchestrator_enabled():
        raise OrchestratorDisabled(f"{policy.FLAG}=0 — external agent orchestrator is inert")


def _ok(mission: Mission, **extra: Any) -> dict[str, Any]:
    out = {"ok": True, "mission": mission.to_dict()}
    out.update(extra)
    return out


def _fail(reason: str, **extra: Any) -> dict[str, Any]:
    # `extra` may legitimately carry a nested "reason" from a lower layer; the
    # explicit argument always wins and never collides (regression 2026-07-26).
    out = dict(extra)
    out["ok"] = False
    out["reason"] = reason
    return out


# ---------------------------------------------------------------- create


def create_mission(
    *,
    title: str,
    executor: str,
    reviewer: str,
    idempotency_key: str,
    description: str = "",
    declared_risk: str | None = None,
    allowed_paths: list[str] | None = None,
    prohibited_paths: list[str] | None = None,
    branch: str = "",
    worktree: str = "",
    base_sha: str = "",
    acceptance_criteria: list[str] | None = None,
    required_tests: list[str] | None = None,
    required_checks: list[str] | None = None,
    rollback_plan: str = "",
    parent_goal_id: str = "",
    priority: int = 50,
    lock: Any = None,
) -> dict[str, Any]:
    _require_enabled()

    refusal = policy.refuse_red(title, description)
    if refusal:
        store.record_event("-", "red_refused", {"title": title, "reason": refusal["reason"]})
        return {"ok": False, **refusal}

    existing = store.find_by_idempotency_key(idempotency_key)
    if existing:
        return _ok(existing, reused=True)

    classification = policy.classify_mission_request(
        title=title, description=description, declared=declared_risk
    )
    if classification["risk_class"] is RiskClass.RED:
        return {
            "ok": False,
            "refused": True,
            "risk_class": "RED",
            "reason": classification["reason"],
        }

    if (executor or "").strip().lower() not in adapters.known_executors():
        return _fail("unknown_executor", executors=adapters.known_executors())

    mission = Mission.create(
        title=title,
        description=description,
        executor=executor.strip().lower(),
        reviewer=reviewer.strip().lower(),
        risk_class=classification["risk_class"],
        idempotency_key=idempotency_key,
        allowed_paths=allowed_paths or [],
        prohibited_paths=policy.normalise_prohibited(prohibited_paths),
        branch=branch,
        worktree=worktree,
        base_sha=base_sha,
        acceptance_criteria=acceptance_criteria or [],
        required_tests=required_tests or [],
        required_checks=required_checks or [],
        rollback_plan=rollback_plan,
        parent_goal_id=parent_goal_id,
        priority=priority,
    )

    conflict = policy.ownership_conflict(mission, store.list_missions(limit=500))
    if conflict.get("conflict"):
        store.record_event(mission.mission_id, "ownership_conflict", conflict)
        return _fail("ownership_conflict", conflict=conflict)

    if mission.allowed_paths:
        acquired = (lock or locks.get_lock()).acquire(mission.mission_id, mission.allowed_paths)
        if not acquired.get("acquired"):
            return _fail("path_lock_conflict", conflict=acquired.get("conflict"))

    mission.add_evidence(
        "classification", classification | {"risk_class": classification["risk_class"].value}
    )
    store.save(mission)
    store.register_idempotency(idempotency_key, mission.mission_id)
    store.record_event(
        mission.mission_id,
        "created",
        {"risk": mission.risk_class.value, "executor": mission.executor},
    )
    return _ok(mission, reused=False, classification=classification["reason"])


# ---------------------------------------------------------------- lifecycle


def preflight(mission_id: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    _require_enabled()
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    try:
        mission.transition(MissionState.PREFLIGHT)
    except InvalidMissionTransition as exc:
        return _fail(str(exc))
    mission.blocker = ""
    mission.add_evidence("preflight", policy.redact(evidence or {}))
    store.save(mission)
    store.record_event(mission_id, "preflight", evidence)
    return _ok(mission, packet=adapters.packet_for(mission))


def claim(
    mission_id: str, owner: str, *, ttl_s: int = DEFAULT_LEASE_S, now: datetime | None = None
) -> dict[str, Any]:
    _require_enabled()
    claimed = store.claim(mission_id, owner, ttl_s=ttl_s, now=now)
    if not claimed.get("claimed"):
        detail = {k: v for k, v in claimed.items() if k not in {"claimed", "reason"}}
        return _fail(str(claimed.get("reason") or "claim_failed"), **detail)
    mission: Mission = claimed["mission"]
    if mission.status is MissionState.PREFLIGHT:
        mission.transition(MissionState.CLAIMED)
        store.save(mission)
    return _ok(mission, packet=adapters.packet_for(mission))


def heartbeat(mission_id: str, owner: str, *, ttl_s: int = DEFAULT_LEASE_S) -> dict[str, Any]:
    _require_enabled()
    ok = store.heartbeat(mission_id, owner, ttl_s=ttl_s)
    return {"ok": ok, "reason": "" if ok else "lease_not_owned"}


def start(mission_id: str, owner: str) -> dict[str, Any]:
    _require_enabled()
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    if mission.lease_owner != owner:
        return _fail("lease_not_owned")
    try:
        mission.transition(MissionState.RUNNING, actor_role="executor")
    except InvalidMissionTransition as exc:
        return _fail(str(exc))
    store.save(mission)
    store.record_event(mission_id, "running", {"owner": owner})
    return _ok(mission)


def submit_result(mission_id: str, owner: str, result: dict[str, Any]) -> dict[str, Any]:
    """Executor hands back its manifest. Scope breach = mission blocked."""
    _require_enabled()
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    if mission.lease_owner != owner:
        return _fail("lease_not_owned")

    adapter = adapters.get_adapter(mission.executor)
    verdict = adapter.validate_result(mission, result)
    budget = policy.budget_check(
        mission,
        tokens_used=int(result.get("tokens_used") or 0),
        cost_usd=float(result.get("cost_usd") or 0.0),
    )
    if not budget["allowed"]:
        verdict["violations"].append(budget["reason"])
        verdict["accepted"] = False

    mission.add_evidence("result_manifest", verdict["result"])
    if not verdict["accepted"]:
        mission.transition(MissionState.BLOCKED, actor_role="executor")
        mission.blocker = "; ".join(verdict["violations"])[:500]
        store.save(mission)
        store.record_event(mission_id, "result_rejected", {"violations": verdict["violations"]})
        return _fail("result_rejected", violations=verdict["violations"], mission=mission.to_dict())

    mission.transition(MissionState.IMPLEMENTED, actor_role="executor")
    mission.transition(MissionState.TESTING, actor_role="executor")
    mission.add_evidence("tests", result.get("tests") or [])
    mission.transition(MissionState.REVIEW_REQUIRED, actor_role="executor")
    store.save(mission)
    store.record_event(
        mission_id, "review_required", {"changed_files": result.get("changed_files")}
    )
    return _ok(mission, review_packet=adapters.get_adapter(mission.reviewer).build_packet(mission))


def submit_review(mission_id: str, review: dict[str, Any]) -> dict[str, Any]:
    """Independent reviewer verdict. Implementer can never self-approve."""
    _require_enabled()
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    if mission.status is not MissionState.REVIEW_REQUIRED:
        return _fail("not_in_review", status=mission.status.value)

    checked = adapters.ClaudeAdapter().validate_review(mission, review)
    if not checked["accepted"]:
        return _fail("review_rejected", violations=checked["violations"])

    mission.add_evidence("review", checked["review"], note=checked["verdict"])
    if checked["verdict"] == "PASS":
        mission.transition(MissionState.REVIEW_PASSED)
    elif checked["verdict"] == "CHANGES_REQUIRED":
        mission.transition(MissionState.CHANGES_REQUESTED)
    else:
        mission.transition(MissionState.BLOCKED)
        mission.blocker = "reviewer BLOCKED"
    store.save(mission)
    store.record_event(
        mission_id, "review_" + checked["verdict"].lower(), {"reviewer": review.get("reviewer")}
    )
    return _ok(mission, verdict=checked["verdict"])


def advance(
    mission_id: str,
    target: str | MissionState,
    *,
    evidence: dict[str, Any] | None = None,
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Drive PR/CI/merge/deploy states. AMBER stops for the owner."""
    _require_enabled()
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    target_state = MissionState(target) if not isinstance(target, MissionState) else target

    if policy.approval_required(mission, target_state) and not owner_approved:
        if mission.status is not MissionState.OWNER_DECISION_REQUIRED:
            mission.transition(MissionState.OWNER_DECISION_REQUIRED)
        mission.approval_state = "required"
        mission.blocker = f"AMBER approval required before {target_state.value}"
        mission.add_evidence("approval_gate", {"blocked_target": target_state.value})
        store.save(mission)
        store.record_event(mission_id, "owner_decision_required", {"target": target_state.value})
        return _fail(
            "owner_approval_required", mission=mission.to_dict(), target=target_state.value
        )

    if target_state in {MissionState.MERGED, MissionState.VERIFIED, MissionState.COMPLETE}:
        missing = _missing_evidence(mission, target_state)
        if missing:
            return _fail("evidence_incomplete", missing=missing)

    try:
        mission.transition(target_state)
    except InvalidMissionTransition as exc:
        return _fail(str(exc))
    if owner_approved:
        mission.approval_state = "approved"
    if evidence:
        mission.add_evidence(target_state.value.lower(), policy.redact(evidence))
    store.save(mission)
    store.record_event(mission_id, "advanced", {"to": target_state.value})
    return _ok(mission)


def _missing_evidence(mission: Mission, target: MissionState) -> list[str]:
    kinds = mission.evidence_kinds()
    needed = {"result_manifest", "review"}
    if target in {MissionState.VERIFIED, MissionState.COMPLETE}:
        needed |= {"tests"}
    if target is MissionState.COMPLETE and not mission.rollback_plan:
        return sorted((needed - kinds) | {"rollback_plan"})
    return sorted(needed - kinds)


def cancel(mission_id: str, *, reason: str = "") -> dict[str, Any]:
    _require_enabled()
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    try:
        mission.transition(MissionState.CANCELLED)
    except InvalidMissionTransition as exc:
        return _fail(str(exc))
    mission.clear_lease()
    mission.blocker = (reason or "cancelled")[:500]
    store.save(mission)
    store.record_event(mission_id, "cancelled", {"reason": reason})
    return _ok(mission)


def retry(mission_id: str) -> dict[str, Any]:
    _require_enabled()
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    if not policy.retry_allowed(mission):
        mission.transition(MissionState.FAILED_TERMINAL)
        mission.blocker = "retry_budget_exhausted"
        store.save(mission)
        store.record_event(mission_id, "retry_exhausted", {"count": mission.retry_count})
        return _fail("retry_budget_exhausted", mission=mission.to_dict())
    try:
        mission.transition(MissionState.PREFLIGHT)
    except InvalidMissionTransition as exc:
        return _fail(str(exc))
    mission.retry_count += 1
    mission.clear_lease()
    mission.blocker = ""
    store.save(mission)
    store.record_event(mission_id, "retry", {"count": mission.retry_count})
    return _ok(mission)


def rollback_package(mission_id: str) -> dict[str, Any]:
    """Everything an operator needs to undo the mission, no commands executed."""
    mission = store.get(mission_id)
    if mission is None:
        return _fail("mission_not_found")
    return {
        "ok": True,
        "mission_id": mission.mission_id,
        "available": bool(mission.rollback_plan),
        "base_sha": mission.base_sha,
        "branch": mission.branch,
        "worktree": mission.worktree,
        "plan": mission.rollback_plan or "no rollback plan recorded — treat as blocker",
        "evidence_refs": policy.redact(mission.evidence_refs),
        "note": "orchestrator never executes rollback; operator runs the documented runbook",
    }


# ---------------------------------------------------------------- views


def dashboard_rows(limit: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mission in store.list_missions(limit=limit):
        rows.append(
            {
                "mission_id": mission.mission_id,
                "title": mission.title,
                "goal": mission.parent_goal_id,
                "executor": mission.executor,
                "reviewer": mission.reviewer,
                "risk_class": mission.risk_class.value,
                "status": mission.status.value,
                "branch": mission.branch,
                "worktree": mission.worktree,
                "changed_files": _changed_files(mission),
                "tests": _test_status(mission),
                "last_heartbeat": mission.last_heartbeat,
                "lease_owner": mission.lease_owner,
                "approval_state": mission.approval_state,
                "owner_action_required": mission.status is MissionState.OWNER_DECISION_REQUIRED,
                "blocker": mission.blocker,
                "retry_count": mission.retry_count,
                "budget": {"tokens": mission.token_budget, "cost_usd": mission.cost_budget_usd},
                "evidence_count": len(mission.evidence_refs),
                "rollback_available": bool(mission.rollback_plan),
                "updated_at": mission.updated_at,
            }
        )
    return rows


def _changed_files(mission: Mission) -> list[str]:
    for entry in reversed(mission.evidence_refs):
        if entry.get("kind") == "result_manifest":
            ref = entry.get("ref") or {}
            if isinstance(ref, dict):
                return [str(x) for x in (ref.get("changed_files") or [])]
    return []


def _test_status(mission: Mission) -> str:
    for entry in reversed(mission.evidence_refs):
        if entry.get("kind") == "tests":
            tests = entry.get("ref") or []
            if not tests:
                return "none"
            failed = [t for t in tests if int((t or {}).get("exit_code", 1)) != 0]
            return "failed" if failed else f"passed({len(tests)})"
    return "pending"


def summary() -> dict[str, Any]:
    rows = dashboard_rows(limit=500)
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {
        "enabled": policy.orchestrator_enabled(),
        "total": len(rows),
        "by_status": by_status,
        "owner_action_required": sum(1 for r in rows if r["owner_action_required"]),
        "cursor": sum(1 for r in rows if r["executor"] == adapters.CURSOR),
        "claude": sum(1 for r in rows if r["executor"] == adapters.CLAUDE),
        "green": sum(1 for r in rows if r["risk_class"] == "GREEN"),
        "amber": sum(1 for r in rows if r["risk_class"] == "AMBER"),
        "red": sum(1 for r in rows if r["risk_class"] == "RED"),
    }
