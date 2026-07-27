"""Bounded execution adapters for the two external agents.

An adapter never runs a shell, never writes files and never calls a provider.
It does exactly two things:

  1. ``build_packet(mission)`` — the structured, redacted brief an external
     agent session (Cursor Composer / Claude Code) must obey.
  2. ``validate_result(mission, result)`` — deterministic acceptance of the
     result manifest that session returns, including scope-breach detection.

That keeps prompt text firmly out of the execution path: nothing an agent
writes can widen its own scope, and every acceptance decision is code, not an
LLM assertion.
"""

from __future__ import annotations

from typing import Any

from app.dev_control.external_agents import policy
from app.dev_control.external_agents.schema import Mission, RiskClass

CURSOR = "cursor"
CLAUDE = "claude"

_STOP_CONDITIONS = (
    "scope breach: any changed path outside allowed_paths",
    "protected path touched (voice/telephony/billing/.env/alembic/deploy workflow)",
    "risk escalation discovered (mission risk_class no longer accurate)",
    "required test cannot run",
    "budget or max_runtime exceeded",
    "destructive git/deploy/calling/billing action would be needed",
)

RESULT_SCHEMA: dict[str, str] = {
    "mission_id": "str — must equal the assigned mission",
    "executor": "str — cursor|claude",
    "changed_files": "list[str] — repo-relative; empty for review-only missions",
    "commands": "list[str] — exact commands run",
    "tests": "list[{command,exit_code,summary}]",
    "summary": "str",
    "evidence": "dict — freeform, redacted",
    "scope_breach": "bool — self-declared; verified independently",
}

REVIEW_SCHEMA: dict[str, str] = {
    "mission_id": "str",
    "reviewer": "str",
    "verdict": "PASS|CHANGES_REQUIRED|BLOCKED",
    "findings": "list[str] — each must cite file/line, test or command output",
    "citations": "list[str] — file:line, test name or command",
}


class ScopeBreach(RuntimeError):
    """Executor touched something the mission does not own."""


class _BaseAdapter:
    name = "base"
    role = "executor"
    requires_worktree = True

    def build_packet(self, mission: Mission) -> dict[str, Any]:
        return policy.redact(
            {
                "schema_version": mission.schema_version,
                "mission_id": mission.mission_id,
                "adapter": self.name,
                "role": self.role,
                "title": mission.title,
                "description": mission.description,
                "risk_class": mission.risk_class.value,
                "scope": {
                    "allowed_paths": mission.allowed_paths,
                    "prohibited_paths": policy.normalise_prohibited(mission.prohibited_paths),
                    "branch": mission.branch,
                    "worktree": mission.worktree,
                    "base_sha": mission.base_sha,
                },
                "acceptance_criteria": mission.acceptance_criteria,
                "expected_outputs": mission.expected_outputs,
                "required_tests": mission.required_tests,
                "required_checks": mission.required_checks,
                "budget": {
                    "max_runtime_s": mission.max_runtime_s,
                    "token_budget": mission.token_budget,
                    "cost_budget_usd": mission.cost_budget_usd,
                },
                "stop_conditions": list(_STOP_CONDITIONS),
                "result_schema": RESULT_SCHEMA if self.role == "executor" else REVIEW_SCHEMA,
                "authority": "Owner OS is the sole action authority; this packet grants no deploy/calling/billing/send rights",
                "rollback_plan": mission.rollback_plan,
            }
        )

    def _base_violations(self, mission: Mission, result: dict[str, Any]) -> list[str]:
        violations: list[str] = []
        if str(result.get("mission_id") or "") != mission.mission_id:
            violations.append("mission_id mismatch")
        if str(result.get("executor") or "").lower() != self.name:
            violations.append(f"executor must be {self.name}")
        breach = policy.path_violations(mission, list(result.get("changed_files") or []))
        if breach:
            violations.append("scope_breach:" + ",".join(breach))
        return violations

    def validate_result(self, mission: Mission, result: dict[str, Any]) -> dict[str, Any]:
        violations = self._base_violations(mission, result)
        return {
            "accepted": not violations,
            "violations": violations,
            "result": policy.redact(result),
        }


class CursorAdapter(_BaseAdapter):
    """Primary engineering executor: code changes on an isolated branch/worktree."""

    name = CURSOR
    role = "executor"

    def build_packet(self, mission: Mission) -> dict[str, Any]:
        packet = super().build_packet(mission)
        packet["preflight"] = [
            "verify repo root and that HEAD == base_sha",
            "verify dedicated worktree + branch exist and are clean",
            "run graphify impact map for the affected flow",
        ]
        packet["required_evidence"] = ["impact_map", "tests", "diff"]
        return packet

    def validate_result(self, mission: Mission, result: dict[str, Any]) -> dict[str, Any]:
        violations = self._base_violations(mission, result)
        if self.requires_worktree and not (mission.branch and mission.worktree):
            violations.append("cursor mission needs a dedicated branch and worktree")
        if not result.get("changed_files"):
            violations.append("cursor mission must report changed_files")
        tests = result.get("tests") or []
        if mission.required_tests and not tests:
            violations.append("required tests were not run")
        for test in tests:
            if int(test.get("exit_code", 1)) != 0:
                violations.append(f"test failed: {test.get('command')}")
        return {
            "accepted": not violations,
            "violations": violations,
            "result": policy.redact(result),
        }


class ClaudeAdapter(_BaseAdapter):
    """Admin / review / operations executor. Read-first, bounded, non-overlapping."""

    name = CLAUDE
    role = "reviewer"
    requires_worktree = False

    def build_packet(self, mission: Mission) -> dict[str, Any]:
        packet = super().build_packet(mission)
        packet["interface"] = "claude code CLI (non-interactive) + MCP tools"
        packet["prohibited_actions"] = [
            "editing paths owned by another live mission",
            "running deploy, calling, billing, outreach or destructive git commands",
            "approving its own implementation work",
        ]
        packet["required_evidence"] = ["citations", "verdict"]
        return packet

    def validate_review(self, mission: Mission, review: dict[str, Any]) -> dict[str, Any]:
        # Review separation is a declared-name convention under a shared admin
        # identity (all routes are require_admin). It prevents the executor
        # *name* from self-approving; it is not per-agent cryptographic attestation.
        violations: list[str] = []
        if str(review.get("mission_id") or "") != mission.mission_id:
            violations.append("mission_id mismatch")
        reviewer = str(review.get("reviewer") or "").strip().lower()
        if not reviewer:
            violations.append("reviewer is required")
        elif reviewer == mission.executor.strip().lower():
            violations.append("reviewer must differ from executor (review separation)")
        verdict = str(review.get("verdict") or "").upper()
        if verdict not in {"PASS", "CHANGES_REQUIRED", "BLOCKED"}:
            violations.append("verdict must be PASS|CHANGES_REQUIRED|BLOCKED")
        citations = list(review.get("citations") or [])
        evidence_status = str(review.get("evidence_status") or "").upper()
        if not citations:
            if evidence_status == "MISSING":
                # Explicit absence — PASS is never allowed; other verdicts stay invalid
                # for the adapter accept gate (submit_review still records the attempt).
                violations.append("review evidence_status=MISSING without citations")
            else:
                violations.append("review must cite code, tests or command evidence")
        if any(str(c).strip().lower() == "runner_auto_review" for c in citations):
            violations.append("synthetic citation runner_auto_review is forbidden")
        if verdict == "PASS" and not citations:
            violations.append("PASS requires concrete citations")
        return {
            "accepted": not violations,
            "verdict": verdict,
            "violations": violations,
            "review": policy.redact(review),
        }


_ADAPTERS: dict[str, _BaseAdapter] = {CURSOR: CursorAdapter(), CLAUDE: ClaudeAdapter()}


def get_adapter(name: str) -> _BaseAdapter:
    key = (name or "").strip().lower()
    if key not in _ADAPTERS:
        raise KeyError(f"unknown executor adapter: {name}")
    return _ADAPTERS[key]


def known_executors() -> list[str]:
    return sorted(_ADAPTERS)


def packet_for(mission: Mission) -> dict[str, Any]:
    """Build the brief for a mission, refusing RED work defensively."""
    if mission.risk_class is RiskClass.RED:
        return {"refused": True, "reason": "RED missions are never dispatched"}
    return get_adapter(mission.executor).build_packet(mission)
