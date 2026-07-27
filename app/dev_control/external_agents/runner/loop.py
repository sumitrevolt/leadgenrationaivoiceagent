"""Bounded unattended run of one GREEN mission (Cursor then Claude review)."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.dev_control.external_agents import adapters, orchestrator, policy, store
from app.dev_control.external_agents.runner import authorize, claude_exec, cursor_exec, eligibility
from app.dev_control.external_agents.runner.flags import runner_enabled
from app.dev_control.external_agents.runner.lease_contract import derive_lease_and_interval
from app.dev_control.external_agents.runner.process_safe import (
    HeartbeatController,
    ProcessSafetyError,
)
from app.dev_control.external_agents.runner.worktrees import (
    allowed_worktree_root,
    ensure_mission_worktree,
)
from app.dev_control.external_agents.schema import Mission, MissionState


def wall_timeout_s(mission: Mission, requested: int) -> int:
    """Hard wall-clock bound from mission budgets (token/cost CLI caps are unavailable)."""
    caps = [max(30, int(requested))]
    if mission.max_runtime_s:
        caps.append(max(30, int(mission.max_runtime_s)))
    # Cheap heuristic when cost budget is tiny: keep the window short.
    if mission.cost_budget_usd and float(mission.cost_budget_usd) > 0:
        caps.append(max(30, min(600, int(float(mission.cost_budget_usd) * 120))))
    # Token budget: ~assume 50 tok/s worst-case free-stack burn → seconds floor.
    if mission.token_budget:
        caps.append(max(30, min(int(requested), int(mission.token_budget) // 50)))
    return max(30, min(caps))


def observed_changed_files(mission_worktree: str, base_sha: str) -> list[str]:
    """Trust git observation over the agent's self-reported changed_files list."""
    files: set[str] = set()
    try:
        for args in (
            ["git", "-C", mission_worktree, "diff", "--name-only", f"{base_sha}...HEAD"],
            ["git", "-C", mission_worktree, "diff", "--name-only", "--"],
            ["git", "-C", mission_worktree, "diff", "--cached", "--name-only", "--"],
            [
                "git",
                "-C",
                mission_worktree,
                "ls-files",
                "--others",
                "--exclude-standard",
            ],
        ):
            out = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=60,
                check=False,
            )
            for line in (out.stdout or "").splitlines():
                p = line.strip().replace("\\", "/")
                if p:
                    files.add(p)
    except Exception:
        return []
    return sorted(files)


def _mission_cancelled(mission_id: str) -> bool:
    m = store.get(mission_id)
    return m is not None and m.status is MissionState.CANCELLED


def _diff_for_mission(mission_worktree: str, base_sha: str) -> str:
    """Collect committed + working-tree diff (dogfood often leaves uncommitted files)."""
    chunks: list[str] = []
    try:
        committed = subprocess.run(
            ["git", "-C", mission_worktree, "diff", f"{base_sha}...HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=60,
            check=False,
        )
        if committed.stdout:
            chunks.append(committed.stdout)
        # Unstaged + staged working tree (STATUS.txt dogfood path).
        for args in (
            ["git", "-C", mission_worktree, "diff", "--", "."],
            ["git", "-C", mission_worktree, "diff", "--cached", "--", "."],
            ["git", "-C", mission_worktree, "status", "--short"],
        ):
            part = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=60,
                check=False,
            )
            if part.stdout:
                chunks.append(part.stdout)
        # Untracked files under allowed fixture path (new STATUS.txt).
        untracked = subprocess.run(
            [
                "git",
                "-C",
                mission_worktree,
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                "tests/fixtures/external_agent_runner",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=30,
            check=False,
        )
        for rel in (untracked.stdout or "").splitlines():
            rel = rel.strip()
            if not rel:
                continue
            fp = Path(mission_worktree) / rel
            try:
                body = fp.read_text(encoding="utf-8", errors="replace")[:2000]
            except Exception:
                body = "<unreadable>"
            chunks.append(f"--- /dev/null\n+++ b/{rel}\n+{body}\n")
        return "\n".join(chunks)[:12000]
    except Exception:
        return ""


def run_mission_once(
    mission_id: str,
    *,
    repo_root: str,
    owner: str | None = None,
    timeout_s: int = 900,
) -> dict[str, Any]:
    """Full vertical slice for one mission. Fail-closed; never raises into callers."""
    if not runner_enabled():
        return {"ok": False, "reason": "runner_or_orchestrator_off"}

    mission = store.get(mission_id)
    elig = eligibility.evaluate(mission)
    if not elig.get("eligible"):
        return {"ok": False, **elig}

    assert mission is not None
    auth = authorize.authorize_mission(mission)
    if not auth.get("authorized"):
        if auth.get("reason") == "owner_decision_required":
            try:
                orchestrator.advance(mission_id, MissionState.OWNER_DECISION_REQUIRED)
            except Exception:
                pass
        return {"ok": False, **auth}

    owner = owner or f"runner:{uuid.uuid4().hex[:8]}"
    evidence: dict[str, Any] = {"authorization": auth, "owner": owner}
    root = str(allowed_worktree_root())

    try:
        wt = ensure_mission_worktree(
            repo_root=repo_root,
            base_sha=mission.base_sha or "HEAD",
            branch=mission.branch,
            worktree=mission.worktree,
        )
        evidence["worktree"] = wt
    except ProcessSafetyError as exc:
        return {"ok": False, "reason": str(exc), "evidence": evidence}

    # Lifecycle: preflight → claim → start
    if mission.status.value == "CREATED":
        pf = orchestrator.preflight(mission_id, evidence={"runner": True})
        if not pf.get("ok"):
            return {"ok": False, "reason": "preflight_failed", "detail": pf}
    cl = orchestrator.claim(mission_id, owner, ttl_s=max(120, timeout_s + 120))
    if not cl.get("ok"):
        return {"ok": False, "reason": "claim_failed", "detail": cl}
    st = orchestrator.start(mission_id, owner)
    if not st.get("ok"):
        return {"ok": False, "reason": "start_failed", "detail": st}

    mission = store.get(mission_id)
    assert mission is not None
    packet = adapters.packet_for(mission)
    exec_timeout = wall_timeout_s(mission, timeout_s)
    lease_plan = derive_lease_and_interval(exec_timeout)
    if not lease_plan.get("ok"):
        return {
            "ok": False,
            "reason": lease_plan.get("reason") or "lease_heartbeat_contract_invalid",
            "evidence": {**evidence, "lease_plan": lease_plan},
        }
    lease_ttl = int(lease_plan["lease_ttl_s"])
    hb_interval = float(lease_plan["heartbeat_interval_s"])
    evidence["lease_contract"] = lease_plan
    # Re-claim / renew with contract-safe TTL (initial claim used timeout_s floor).
    orchestrator.heartbeat(mission_id, owner, ttl_s=lease_ttl)

    def _hb_factory() -> HeartbeatController:
        return HeartbeatController(
            interval_s=hb_interval,
            beat=lambda: bool(orchestrator.heartbeat(mission_id, owner, ttl_s=lease_ttl).get("ok")),
            cancel_check=lambda: _mission_cancelled(mission_id),
        )

    hb = _hb_factory()

    # ---- executor ----
    try:
        if mission.executor == "cursor":
            proc, manifest, parse_error = cursor_exec.invoke_cursor(
                mission, packet, allowed_root=root, timeout_s=exec_timeout, heartbeat=hb
            )
        else:
            return {
                "ok": False,
                "reason": "executor_not_supported_for_impl",
                "executor": mission.executor,
            }
    except ProcessSafetyError as exc:
        orchestrator.cancel(mission_id, reason=str(exc))
        return {"ok": False, "reason": str(exc), "evidence": evidence}

    evidence["executor_process"] = {
        "exit_code": proc.exit_code,
        "duration_s": proc.duration_s,
        "timed_out": proc.timed_out,
        "cancelled": proc.cancelled,
        "termination_reason": proc.termination_reason,
        "pid": proc.pid,
        "heartbeats": hb.beats,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
        "truncated": bool(getattr(proc, "truncated", False)),
        "manifest_parse_error": parse_error,
    }

    if proc.cancelled or proc.timed_out or proc.exit_code != 0 or not manifest:
        blocker = proc.termination_reason or f"executor_exit_{proc.exit_code}"
        store.record_event(mission_id, "runner_executor_failed", evidence["executor_process"])
        # Mark blocked via a rejected synthetic result if still leased
        bad = {
            "mission_id": mission_id,
            "executor": mission.executor,
            "changed_files": ["__runner_failure__"],
            "commands": [],
            "tests": [{"command": "runner", "exit_code": 1, "summary": blocker}],
            "summary": blocker,
            "evidence": evidence["executor_process"],
            "scope_breach": True,
        }
        orchestrator.submit_result(mission_id, owner, bad)
        return {"ok": False, "reason": "executor_failed", "evidence": evidence}

    # Prefer git-observed paths over agent self-report for scope enforcement.
    observed = observed_changed_files(mission.worktree, mission.base_sha or "HEAD")
    if observed:
        manifest = dict(manifest)
        reported = [str(x) for x in (manifest.get("changed_files") or [])]
        manifest["changed_files"] = sorted(set(reported) | set(observed))
        manifest["evidence"] = dict(manifest.get("evidence") or {})
        manifest["evidence"]["observed_changed_files"] = observed
    breach = policy.path_violations(mission, list(manifest.get("changed_files") or []))
    if breach:
        manifest = dict(manifest)
        manifest["scope_breach"] = True
        evidence["scope_breach_observed"] = breach

    # Wall-clock + measured CLI usage budget (when envelope provides it).
    usage = claude_exec.extract_usage_from_cli_json(proc.stdout or "")
    manifest = dict(manifest)
    manifest["tokens_used"] = int(usage.get("tokens_used") or 0)
    manifest["cost_usd"] = float(usage.get("cost_usd") or 0.0)
    budget = policy.budget_check(
        mission,
        tokens_used=int(manifest["tokens_used"]),
        cost_usd=float(manifest["cost_usd"]),
    )
    if float(proc.duration_s or 0) > float(mission.max_runtime_s or exec_timeout):
        return {
            "ok": False,
            "reason": "wall_clock_budget_exceeded",
            "evidence": evidence,
        }
    if not budget.get("allowed"):
        evidence["budget"] = budget
        return {"ok": False, "reason": budget.get("reason"), "evidence": evidence}
    evidence["budget"] = budget

    sr = orchestrator.submit_result(mission_id, owner, manifest)
    evidence["submit_result"] = {
        "ok": sr.get("ok"),
        "reason": sr.get("reason"),
        "status": (sr.get("mission") or {}).get("status"),
    }
    if not sr.get("ok"):
        return {"ok": False, "reason": "submit_result_failed", "detail": sr, "evidence": evidence}

    # ---- independent review (other agent) ----
    reviewer = (mission.reviewer or "").strip().lower()
    if reviewer != "claude":
        return {"ok": False, "reason": "reviewer_not_claude", "evidence": evidence}

    diff = _diff_for_mission(mission.worktree, mission.base_sha or "HEAD")
    review_timeout = wall_timeout_s(mission, min(600, timeout_s))
    hb2 = _hb_factory()
    try:
        rproc, review, parse_ev = claude_exec.invoke_claude_review(
            mission,
            result_manifest=manifest,
            diff_text=diff,
            allowed_root=root,
            timeout_s=review_timeout,
            heartbeat=hb2,
            expected_head=mission.base_sha or "",
        )
    except ProcessSafetyError as exc:
        return {"ok": False, "reason": str(exc), "evidence": evidence}

    evidence["review_process"] = {
        "exit_code": rproc.exit_code,
        "duration_s": rproc.duration_s,
        "heartbeats": hb2.beats,
        "timed_out": rproc.timed_out,
        "pid": rproc.pid,
        "stderr_tail": (rproc.stderr or "")[-500:],
        "stdout_tail": (rproc.stdout or "")[-500:],
        "termination_reason": rproc.termination_reason,
        "truncated": bool(getattr(rproc, "truncated", False)),
        "parse": parse_ev,
    }
    if not review:
        return {
            "ok": False,
            "reason": parse_ev.get("reason") or "review_manifest_missing",
            "evidence": evidence,
        }

    review_usage = claude_exec.extract_usage_from_cli_json(rproc.stdout or "")
    review_budget = policy.budget_check(
        mission,
        tokens_used=int(review_usage.get("tokens_used") or 0),
        cost_usd=float(review_usage.get("cost_usd") or 0.0),
    )
    evidence["review_budget"] = review_budget
    if not review_budget.get("allowed"):
        return {
            "ok": False,
            "reason": review_budget.get("reason"),
            "evidence": evidence,
        }

    # Missing citations stay missing — never fabricate provenance.
    if not (review.get("citations") or []):
        review = dict(review)
        review["evidence_status"] = "MISSING"
        review.setdefault(
            "evidence_absence_reason",
            "Reviewer did not provide supporting evidence",
        )

    rv = orchestrator.submit_review(mission_id, review)
    evidence["submit_review"] = {
        "ok": rv.get("ok"),
        "verdict": rv.get("verdict"),
        "status": (rv.get("mission") or {}).get("status"),
    }
    store.record_event(mission_id, "runner_complete", {"verdict": rv.get("verdict")})
    return {
        "ok": bool(rv.get("ok")),
        "mission_id": mission_id,
        "verdict": rv.get("verdict"),
        "status": (rv.get("mission") or {}).get("status"),
        "evidence": evidence,
        "result_manifest": manifest,
        "review_manifest": review,
    }


def _result_manifest_from_mission(mission) -> dict[str, Any] | None:
    for ev in reversed(mission.evidence_refs or []):
        if getattr(ev, "kind", "") == "result_manifest" or (
            isinstance(ev, dict) and ev.get("kind") == "result_manifest"
        ):
            ref = ev.ref if hasattr(ev, "ref") else ev.get("ref")
            if isinstance(ref, dict) and ref.get("mission_id"):
                return ref
            if isinstance(ref, dict):
                # Stored form may be redacted result without nesting.
                return ref
    return None


def run_review_once(
    mission_id: str,
    *,
    timeout_s: int = 600,
) -> dict[str, Any]:
    """Resume independent Claude review for a mission already in REVIEW_REQUIRED."""
    if not runner_enabled():
        return {"ok": False, "reason": "runner_or_orchestrator_off"}
    mission = store.get(mission_id)
    if mission is None:
        return {"ok": False, "reason": "mission_not_found"}
    if mission.status is not MissionState.REVIEW_REQUIRED:
        return {
            "ok": False,
            "reason": "not_in_review",
            "status": mission.status.value,
        }
    if (mission.reviewer or "").strip().lower() != "claude":
        return {"ok": False, "reason": "reviewer_not_claude"}
    manifest = _result_manifest_from_mission(mission)
    if not manifest:
        return {"ok": False, "reason": "result_manifest_missing"}
    root = str(allowed_worktree_root())
    owner = mission.lease_owner or f"runner-review:{uuid.uuid4().hex[:8]}"
    review_timeout = wall_timeout_s(mission, timeout_s)
    lease_plan = derive_lease_and_interval(review_timeout)
    if not lease_plan.get("ok"):
        return {"ok": False, "reason": lease_plan.get("reason"), "lease_plan": lease_plan}
    lease_ttl = int(lease_plan["lease_ttl_s"])
    hb_interval = float(lease_plan["heartbeat_interval_s"])
    # Refresh lease so heartbeats remain valid during review.
    if mission.lease_owner:
        orchestrator.heartbeat(mission_id, owner, ttl_s=lease_ttl)
    evidence: dict[str, Any] = {
        "owner": owner,
        "resumed_review": True,
        "lease_contract": lease_plan,
    }
    diff = _diff_for_mission(mission.worktree, mission.base_sha or "HEAD")
    hb = HeartbeatController(
        interval_s=hb_interval,
        beat=lambda: bool(orchestrator.heartbeat(mission_id, owner, ttl_s=lease_ttl).get("ok")),
        cancel_check=lambda: _mission_cancelled(mission_id),
    )
    try:
        rproc, review, parse_ev = claude_exec.invoke_claude_review(
            mission,
            result_manifest=manifest,
            diff_text=diff,
            allowed_root=root,
            timeout_s=review_timeout,
            heartbeat=hb,
            expected_head=mission.base_sha or "",
        )
    except ProcessSafetyError as exc:
        return {"ok": False, "reason": str(exc), "evidence": evidence}
    evidence["review_process"] = {
        "exit_code": rproc.exit_code,
        "duration_s": rproc.duration_s,
        "heartbeats": hb.beats,
        "timed_out": rproc.timed_out,
        "pid": rproc.pid,
        "stderr_tail": (rproc.stderr or "")[-500:],
        "stdout_tail": (rproc.stdout or "")[-500:],
        "truncated": bool(getattr(rproc, "truncated", False)),
        "parse": parse_ev,
    }
    if not review:
        return {
            "ok": False,
            "reason": parse_ev.get("reason") or "review_manifest_missing",
            "evidence": evidence,
        }
    if not (review.get("citations") or []):
        review = dict(review)
        review["evidence_status"] = "MISSING"
        review.setdefault(
            "evidence_absence_reason",
            "Reviewer did not provide supporting evidence",
        )
    rv = orchestrator.submit_review(mission_id, review)
    evidence["submit_review"] = {
        "ok": rv.get("ok"),
        "verdict": rv.get("verdict"),
        "status": (rv.get("mission") or {}).get("status"),
    }
    store.record_event(mission_id, "runner_review_complete", {"verdict": rv.get("verdict")})
    return {
        "ok": bool(rv.get("ok")),
        "mission_id": mission_id,
        "verdict": rv.get("verdict"),
        "status": (rv.get("mission") or {}).get("status"),
        "evidence": evidence,
        "result_manifest": manifest,
        "review_manifest": review,
    }
