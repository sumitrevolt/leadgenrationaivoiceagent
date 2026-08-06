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
    token_budget: int | None = None,
    lock: Any = None,
    initial_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a mission shell.

    ``initial_evidence`` (optional) is attached on the in-memory mission
    *before* the final canonical ``store.save`` in this function — callers
    must not ``store.get`` + mutate + ``store.save`` after return (lost-update
    risk vs later ``apply_cas`` writers). Each item is
    ``{"kind": str, "ref": Any, "note": str?}``.
    """
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

    # Cursor executors must declare a non-empty allowed scope — empty allowed_paths
    # would otherwise silently skip the allowed-scope breach check (Claude review).
    if (executor or "").strip().lower() == adapters.CURSOR and not (allowed_paths or []):
        return _fail(
            "cursor_requires_allowed_paths",
            note="executor-role missions must declare a non-empty allowed_paths scope",
        )

    create_kwargs: dict[str, Any] = {
        "title": title,
        "description": description,
        "executor": executor.strip().lower(),
        "reviewer": reviewer.strip().lower(),
        "risk_class": classification["risk_class"],
        "idempotency_key": idempotency_key,
        "allowed_paths": allowed_paths or [],
        "prohibited_paths": policy.normalise_prohibited(prohibited_paths),
        "branch": branch,
        "worktree": worktree,
        "base_sha": base_sha,
        "acceptance_criteria": acceptance_criteria or [],
        "required_tests": required_tests or [],
        "required_checks": required_checks or [],
        "rollback_plan": rollback_plan,
        "parent_goal_id": parent_goal_id,
        "priority": priority,
    }
    if token_budget is not None:
        create_kwargs["token_budget"] = int(token_budget)
    mission = Mission.create(**create_kwargs)

    # Atomic first-writer-wins BEFORE any side effects. Concurrent creator with
    # the same key loses and returns the winner's mission — no duplicate docs.
    reg = store.register_idempotency(idempotency_key, mission.mission_id)
    if not reg.get("created"):
        winner = _wait_for_mission(str(reg.get("mission_id") or ""), idempotency_key)
        if winner:
            return _ok(winner, reused=True)
        return _fail("idempotency_race", detail=reg)

    # Persist the winning shell immediately so concurrent losers can resolve it
    # before we run ownership / path-lock checks.
    store.save(mission)

    conflict = policy.ownership_conflict(mission, store.list_missions(limit=500))
    if conflict.get("conflict"):
        store.record_event(mission.mission_id, "ownership_conflict", conflict)
        try:
            mission.transition(MissionState.CANCELLED)
            mission.blocker = "ownership_conflict_after_create"
            store.save(mission)
        except Exception:
            pass
        return _fail("ownership_conflict", conflict=conflict)

    if mission.allowed_paths:
        acquired = (lock or locks.get_lock()).acquire(mission.mission_id, mission.allowed_paths)
        if not acquired.get("acquired"):
            return _fail("path_lock_conflict", conflict=acquired.get("conflict"))

    mission.add_evidence(
        "classification", classification | {"risk_class": classification["risk_class"].value}
    )
    for item in initial_evidence or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        mission.add_evidence(kind, item.get("ref"), note=str(item.get("note") or ""))
    store.save(mission)
    store.record_event(
        mission.mission_id,
        "created",
        {
            "risk": mission.risk_class.value,
            "executor": mission.executor,
            "cas": store.persistence_report().get("backend"),
        },
    )
    return _ok(mission, reused=False, classification=classification["reason"])


def _wait_for_mission(mission_id: str, idempotency_key: str, *, attempts: int = 50):
    """Loser of an idempotency race waits briefly for the winner's document."""
    import time

    for _ in range(max(1, attempts)):
        winner = store.get(mission_id) if mission_id else None
        if winner is None:
            winner = store.find_by_idempotency_key(idempotency_key)
        if winner:
            return winner
        time.sleep(0.02)
    return None


# ---------------------------------------------------------------- lifecycle


def preflight(mission_id: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    _require_enabled()

    def _mutate(mission: Mission) -> None:
        mission.transition(MissionState.PREFLIGHT)
        mission.blocker = ""
        mission.add_evidence("preflight", policy.redact(evidence or {}))

    out = store.apply_cas(mission_id, expected_status=MissionState.CREATED, mutate=_mutate)
    if not out.get("ok"):
        return _fail(
            str(out.get("reason") or "preflight_failed"),
            **{k: v for k, v in out.items() if k not in {"ok", "reason", "mission"}},
        )
    store.record_event(mission_id, "preflight", evidence)
    return _ok(out["mission"], packet=adapters.packet_for(out["mission"]))


def claim(
    mission_id: str, owner: str, *, ttl_s: int = DEFAULT_LEASE_S, now: datetime | None = None
) -> dict[str, Any]:
    _require_enabled()
    claimed = store.claim(mission_id, owner, ttl_s=ttl_s, now=now)
    if not claimed.get("claimed"):
        detail = {k: v for k, v in claimed.items() if k not in {"claimed", "reason"}}
        return _fail(str(claimed.get("reason") or "claim_failed"), **detail)

    # Fold PREFLIGHT -> CLAIMED into a CAS-safe mutation so a concurrent cancel
    # cannot be overwritten by a stale writer after the lease was taken.
    def _mutate(mission: Mission) -> None:
        if mission.status is MissionState.PREFLIGHT:
            mission.transition(MissionState.CLAIMED)

    out = store.apply_cas(mission_id, mutate=_mutate)
    if not out.get("ok"):
        return _fail(str(out.get("reason") or "claim_transition_failed"))
    return _ok(out["mission"], packet=adapters.packet_for(out["mission"]))


def heartbeat(mission_id: str, owner: str, *, ttl_s: int = DEFAULT_LEASE_S) -> dict[str, Any]:
    _require_enabled()
    ok = store.heartbeat(mission_id, owner, ttl_s=ttl_s)
    return {"ok": ok, "reason": "" if ok else "lease_not_owned"}


def submit_result(mission_id: str, owner: str, result: dict[str, Any]) -> dict[str, Any]:
    """Executor hands back its manifest. Scope breach = mission blocked."""
    _require_enabled()
    # Capture adapter verdict under the CAS lock so status + evidence land together.
    verdict_box: dict[str, Any] = {}

    def _mutate(mission: Mission) -> None:
        if mission.lease_owner != owner:
            raise InvalidMissionTransition("lease_not_owned")
        if mission.status is not MissionState.RUNNING:
            raise InvalidMissionTransition(
                f"stale_transition:{mission.status.value}:expected:RUNNING"
            )
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
        verdict_box["verdict"] = verdict
        mission.add_evidence("result_manifest", verdict["result"])
        if not verdict["accepted"]:
            mission.transition(MissionState.BLOCKED, actor_role="executor")
            mission.blocker = "; ".join(verdict["violations"])[:500]
            return
        mission.transition(MissionState.IMPLEMENTED, actor_role="executor")
        mission.transition(MissionState.TESTING, actor_role="executor")
        mission.add_evidence("tests", result.get("tests") or [])
        mission.transition(MissionState.REVIEW_REQUIRED, actor_role="executor")

    out = store.apply_cas(mission_id, mutate=_mutate)
    if not out.get("ok"):
        reason = str(out.get("reason") or "submit_result_failed")
        if reason == "lease_not_owned":
            return _fail("lease_not_owned")
        if reason.startswith("stale_transition:"):
            return _fail("stale_transition", detail=reason)
        return _fail(reason)
    mission = out["mission"]
    verdict = verdict_box.get("verdict") or {}
    if not verdict.get("accepted", True):
        store.record_event(mission_id, "result_rejected", {"violations": verdict.get("violations")})
        return _fail(
            "result_rejected",
            violations=verdict.get("violations") or [],
            mission=mission.to_dict(),
        )
    store.record_event(
        mission_id, "review_required", {"changed_files": result.get("changed_files")}
    )
    return _ok(mission, review_packet=adapters.get_adapter(mission.reviewer).build_packet(mission))


def start(mission_id: str, owner: str) -> dict[str, Any]:
    _require_enabled()

    def _mutate(mission: Mission) -> None:
        if mission.lease_owner != owner:
            raise InvalidMissionTransition("lease_not_owned")
        mission.transition(MissionState.RUNNING, actor_role="executor")

    out = store.apply_cas(mission_id, expected_status=MissionState.CLAIMED, mutate=_mutate)
    if not out.get("ok"):
        reason = str(out.get("reason") or "start_failed")
        if reason == "lease_not_owned":
            return _fail("lease_not_owned")
        return _fail(reason)
    store.record_event(mission_id, "running", {"owner": owner})
    return _ok(out["mission"])


def submit_review(mission_id: str, review: dict[str, Any]) -> dict[str, Any]:
    """Independent reviewer verdict. Implementer can never self-approve."""
    _require_enabled()
    checked_box: dict[str, Any] = {}

    def _mutate(mission: Mission) -> None:
        if mission.status is not MissionState.REVIEW_REQUIRED:
            raise InvalidMissionTransition(f"not_in_review:{mission.status.value}")
        checked = adapters.ClaudeAdapter().validate_review(mission, review)
        checked_box["checked"] = checked
        if not checked["accepted"]:
            raise InvalidMissionTransition("review_rejected:" + ",".join(checked["violations"]))
        mission.add_evidence("review", checked["review"], note=checked["verdict"])
        if checked["verdict"] == "PASS":
            mission.transition(MissionState.REVIEW_PASSED)
        elif checked["verdict"] == "CHANGES_REQUIRED":
            mission.transition(MissionState.CHANGES_REQUESTED)
        else:
            mission.transition(MissionState.BLOCKED)
            mission.blocker = "reviewer BLOCKED"

    out = store.apply_cas(mission_id, expected_status=MissionState.REVIEW_REQUIRED, mutate=_mutate)
    if not out.get("ok"):
        reason = str(out.get("reason") or "submit_review_failed")
        if reason.startswith("review_rejected:"):
            return _fail(
                "review_rejected",
                violations=reason.split(":", 1)[1].split(",") if ":" in reason else [reason],
            )
        if reason.startswith("not_in_review:"):
            return _fail("not_in_review", status=reason.split(":", 1)[1])
        return _fail(reason)
    checked = checked_box.get("checked") or {}
    store.record_event(
        mission_id,
        "review_" + str(checked.get("verdict") or "").lower(),
        {"reviewer": review.get("reviewer")},
    )
    return _ok(out["mission"], verdict=checked.get("verdict"))


def advance(
    mission_id: str,
    target: str | MissionState,
    *,
    evidence: dict[str, Any] | None = None,
    owner_approved: bool = False,
    approval_decision_id: str | None = None,
) -> dict[str, Any]:
    """Drive PR/CI/merge/deploy states. AMBER stops for the owner."""
    _require_enabled()
    target_state = MissionState(target) if not isinstance(target, MissionState) else target

    # Review verdicts MUST go through submit_review() so the citation +
    # review-separation gates cannot be skipped by an admin advance call.
    if target_state in {MissionState.REVIEW_PASSED, MissionState.CHANGES_REQUESTED}:
        return _fail(
            "use_submit_review_endpoint",
            target=target_state.value,
            note="REVIEW_PASSED / CHANGES_REQUESTED require submit_review()",
        )

    gate_box: dict[str, Any] = {}

    def _mutate(mission: Mission) -> None:
        if policy.approval_required(mission, target_state):
            # Request-body boolean alone is never sufficient (Owner OS ledger).
            if owner_approved and not (approval_decision_id or "").strip():
                gate_box["owner_gate"] = True
                gate_box["reason"] = "approval_decision_id_required"
                if mission.status is not MissionState.OWNER_DECISION_REQUIRED:
                    mission.transition(MissionState.OWNER_DECISION_REQUIRED)
                mission.approval_state = "required"
                mission.blocker = (
                    f"AMBER requires Owner OS approval_decision_id before {target_state.value}"
                )
                mission.add_evidence(
                    "approval_gate",
                    {"blocked_target": target_state.value, "boolean_alone_refused": True},
                )
                return
            from app.dev_control.external_agents import approval as amber_approval

            verified = amber_approval.assert_amber_approved(
                str(approval_decision_id or ""),
                mission,
                target_state=target_state,
                head_sha=mission.base_sha,
            )
            if not verified.get("ok"):
                if mission.status is not MissionState.OWNER_DECISION_REQUIRED:
                    mission.transition(MissionState.OWNER_DECISION_REQUIRED)
                mission.approval_state = "required"
                mission.blocker = (
                    f"AMBER approval required before {target_state.value}: {verified.get('reason')}"
                )
                mission.add_evidence(
                    "approval_gate",
                    {
                        "blocked_target": target_state.value,
                        "reason": verified.get("reason"),
                        "approval_decision_id": approval_decision_id,
                    },
                )
                gate_box["owner_gate"] = True
                gate_box["reason"] = verified.get("reason")
                return
            gate_box["amber_verified"] = verified
        if target_state in {MissionState.MERGED, MissionState.VERIFIED, MissionState.COMPLETE}:
            missing = _missing_evidence(mission, target_state)
            if missing:
                gate_box["missing"] = missing
                raise InvalidMissionTransition("evidence_incomplete")
        mission.transition(target_state)
        if gate_box.get("amber_verified"):
            mission.approval_state = "approved"
            mission.add_evidence(
                "amber_approval",
                policy.redact(
                    {
                        "approval_decision_id": gate_box["amber_verified"].get(
                            "approval_decision_id"
                        ),
                        "binding_hash": (gate_box["amber_verified"].get("binding") or {}).get(
                            "binding_hash"
                        ),
                    }
                ),
            )
        if evidence:
            mission.add_evidence(target_state.value.lower(), policy.redact(evidence))

    out = store.apply_cas(mission_id, mutate=_mutate)
    if not out.get("ok"):
        reason = str(out.get("reason") or "advance_failed")
        if reason == "evidence_incomplete":
            return _fail("evidence_incomplete", missing=gate_box.get("missing") or [])
        return _fail(reason)
    mission = out["mission"]
    if gate_box.get("owner_gate"):
        store.record_event(
            mission_id,
            "owner_decision_required",
            {"target": target_state.value, "reason": gate_box.get("reason")},
        )
        return _fail(
            "owner_approval_required",
            mission=mission.to_dict(),
            target=target_state.value,
            approval_reason=gate_box.get("reason") or "owner_approval_required",
        )
    if gate_box.get("amber_verified"):
        from app.dev_control.external_agents import approval as amber_approval

        amber_approval.consume_amber_approval(
            str(gate_box["amber_verified"].get("approval_decision_id") or ""),
            actor="orchestrator",
        )
    store.record_event(
        mission_id,
        "advanced",
        {
            "to": target_state.value,
            "approval_decision_id": (gate_box.get("amber_verified") or {}).get(
                "approval_decision_id"
            ),
        },
    )
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

    def _mutate(mission: Mission) -> None:
        mission.transition(MissionState.CANCELLED)
        mission.clear_lease()
        mission.blocker = (reason or "cancelled")[:500]

    out = store.apply_cas(mission_id, mutate=_mutate)
    if not out.get("ok"):
        return _fail(str(out.get("reason") or "cancel_failed"))
    store.record_event(mission_id, "cancelled", {"reason": reason})
    return _ok(out["mission"])


def retry(mission_id: str) -> dict[str, Any]:
    _require_enabled()
    exhausted_box: dict[str, Any] = {}

    def _mutate(mission: Mission) -> None:
        if not policy.retry_allowed(mission):
            mission.transition(MissionState.FAILED_TERMINAL)
            mission.blocker = "retry_budget_exhausted"
            exhausted_box["exhausted"] = True
            return
        mission.transition(MissionState.PREFLIGHT)
        mission.retry_count += 1
        mission.clear_lease()
        mission.blocker = ""

    out = store.apply_cas(mission_id, mutate=_mutate)
    if not out.get("ok"):
        return _fail(str(out.get("reason") or "retry_failed"))
    mission = out["mission"]
    if exhausted_box.get("exhausted"):
        store.record_event(mission_id, "retry_exhausted", {"count": mission.retry_count})
        return _fail("retry_budget_exhausted", mission=mission.to_dict())
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
