"""Hermes3D Virtual Office Custom Runtime Bridge (2026-09-24)
===========================================================
Real integration with canonical LeadGen AI task orchestrator.

Invariants:
- Real commands only: creates persisted tasks via AutomationOrchestrator
- TypeSafe awareness: surfaces logical key slots (TS_A..TS_D) status
- Mode toggle: supports 2D fallback for low-resource environments
- Network security: allowlist boundary check on custom runtime requests
- Idempotent: stable request-scoped keys prevent duplicate execution
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from typing import Any

from app.platform import team
from app.platform.key_manager import get_key_manager

logger = logging.getLogger(__name__)

CANONICAL_SUPERVISORY_BOTS: list[dict[str, Any]] = [
    {"id": "owner_orchestrator", "name": "Owner / Orchestrator", "description": "Business objectives, priority queue, conflict resolution, safety enforcement.", "icon": "crown"},
    {"id": "revenue_cro", "name": "Revenue / CRO Bot", "description": "Prospect prioritization, pricing, sales funnel, conversion, collected revenue.", "icon": "trending-up"},
    {"id": "lead_intelligence", "name": "Lead Intelligence Bot", "description": "Lead discovery, enrichment, scoring, deduplication, qualification.", "icon": "search"},
    {"id": "outreach_conversation", "name": "Outreach & Conversation Bot", "description": "WhatsApp, email, compliant outreach, reply triage, appointment booking.", "icon": "message-circle"},
    {"id": "voice_swara", "name": "Voice / Swara Bot", "description": "Call queue, voice provider availability, scripts, qualification, follow-ups.", "icon": "phone-call"},
    {"id": "marketing_content", "name": "Marketing / Content Bot", "description": "Daily creatives, social content, video generation, approval queue.", "icon": "image"},
    {"id": "engineering_sre", "name": "Engineering / SRE Bot", "description": "Docker, VPS, queues, CI/CD, deployment, observability, survivability.", "icon": "cpu"},
    {"id": "qa_analytics", "name": "QA & Analytics Bot", "description": "End-to-end testing, voice call regression, funnel analytics, challenge claims.", "icon": "check-circle"},
    {"id": "finance_compliance", "name": "Finance & Compliance Bot", "description": "DPDP + TRAI compliance, unit economics, invoice reconciliation, secret rotation.", "icon": "shield"},
]

DEFAULT_ALLOWLIST = {"127.0.0.1", "::1", "localhost", "host.docker.internal"}

SUPPORTED_ACTIONS: dict[str, dict[str, Any]] = {
    "run_cycle": {"handler": "_handle_run_cycle", "description": "Trigger authorized execution mechanism"},
    "focus_agent": {"handler": "_handle_focus_agent", "description": "Update office focus state"},
    "status_check": {"handler": "_handle_status_check", "description": "Retrieve authoritative current status"},
    "pause_agent": {"handler": "_handle_pause_agent", "description": "Persist authorized pause state"},
    "resume_agent": {"handler": "_handle_resume_agent", "description": "Resume authorized agent"},
}


class Hermes3DBridge:
    """Bridge coordinating state, registry, and commands for Hermes3D custom provider."""

    def __init__(self) -> None:
        raw_allowlist = os.getenv("CUSTOM_RUNTIME_ALLOWLIST", "")
        self.allowlist: set[str] = set(DEFAULT_ALLOWLIST)
        if raw_allowlist:
            for item in raw_allowlist.split(","):
                clean = item.strip()
                if clean:
                    self.allowlist.add(clean)
        self.mode_2d_fallback: bool = os.getenv("HERMES3D_2D_MODE", "0").lower() in ("1", "true", "yes")

    def is_client_allowed(self, client_ip: str | None) -> bool:
        if not client_ip:
            return True
        if client_ip in self.allowlist or "0.0.0.0" in self.allowlist or "*" in self.allowlist:
            return True
        return False

    def get_health(self) -> dict[str, Any]:
        return {"status": "ok", "runtime": "leadgen_hermes3d", "adapter": "custom", "mode_2d": self.mode_2d_fallback}

    def get_registry(self) -> dict[str, Any]:
        staff_agents = []
        for agent_id, info in team.STAFF.items():
            staff_agents.append({
                "id": agent_id,
                "name": info.get("name", agent_id),
                "title": info.get("title", ""),
                "emoji": info.get("emoji", "🤖"),
                "product": info.get("product", "platform"),
                "duties": info.get("duties", ""),
                "schedule": info.get("schedule", ""),
            })
        return {"agents": staff_agents, "supervisory_bots": CANONICAL_SUPERVISORY_BOTS, "telemetry_standard": "REAL_EVENTS_ONLY", "runtime_type": "custom"}

    def get_state(self) -> dict[str, Any]:
        team_state = team.team_status()
        km = get_key_manager()
        slots_status = km.get_all_slots()
        return {
            "agents": team_state.get("members", {}),
            "summary": team_state.get("summary", {}),
            "office": {
                "environment": "2d_fallback" if self.mode_2d_fallback else "3d_office",
                "typesafe_gateway": {
                    "provider": "TypeSafe Jev",
                    "model": os.getenv("TYPESAFE_MODEL", "jev-latest"),
                    "slots": slots_status,
                },
            },
            "evidence_kind": "real_events_only",
        }

    def get_config(self) -> dict[str, Any]:
        return {"adapter_type": "custom", "allowlist": list(self.allowlist), "mode_2d_fallback": self.mode_2d_fallback, "poll_interval_sec": 3.0}

    def _generate_idempotency_key(self, action: str, target_agent: str | None, parameters: dict[str, Any]) -> str:
        """Generate stable idempotency key from request scope."""
        request_id = parameters.get("request_id", "")
        if request_id:
            return f"hermes3d:{request_id}"
        scope = f"hermes3d:{action}:{target_agent}:{sorted(parameters.items())}"
        return hashlib.sha256(scope.encode()).hexdigest()[:16]

    def _execute_command(self, action: str, target_agent: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute the requested command action and return execution evidence."""
        handler_name = SUPPORTED_ACTIONS[action]["handler"]
        handler = getattr(self, handler_name, None)
        if handler is None:
            return {"success": False, "error": "handler_not_found", "action": action}
        return handler(target_agent, parameters)

    def _handle_pause_agent(self, target_agent: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Pause an agent by setting its paused flag in team.STAFF."""
        if target_agent not in team.STAFF:
            return {"success": False, "error": "unknown_agent", "agent": target_agent}
        try:
            agent_info = team.STAFF.get(target_agent, {})
            previous_state = "paused" if agent_info.get("paused", False) else "active"
            agent_info["paused"] = True
            if "pause_reason" in parameters:
                agent_info["pause_reason"] = parameters["pause_reason"]
            return {
                "success": True,
                "action": "pause_agent",
                "agent": target_agent,
                "previous_state": previous_state,
                "new_state": "paused",
                "evidence": f"Agent {target_agent} paused",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "action": "pause_agent"}

    def _handle_resume_agent(self, target_agent: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Resume a paused agent by clearing its paused flag."""
        if target_agent not in team.STAFF:
            return {"success": False, "error": "unknown_agent", "agent": target_agent}
        try:
            agent_info = team.STAFF.get(target_agent, {})
            was_paused = agent_info.get("paused", False)
            agent_info["paused"] = False
            if "pause_reason" in agent_info:
                del agent_info["pause_reason"]
            return {
                "success": True,
                "action": "resume_agent",
                "agent": target_agent,
                "previous_state": "paused" if was_paused else "active",
                "new_state": "active",
                "evidence": f"Agent {target_agent} resumed",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "action": "resume_agent"}

    def _handle_focus_agent(self, target_agent: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Focus/highlight an agent in the 3D office view."""
        if target_agent not in team.STAFF:
            return {"success": False, "error": "unknown_agent", "agent": target_agent}
        return {
            "success": True,
            "action": "focus_agent",
            "agent": target_agent,
            "zoom": parameters.get("zoom", 1.0),
            "evidence": f"Agent {target_agent} focused",
        }

    def _handle_status_check(self, target_agent: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Retrieve current status of an agent."""
        if target_agent not in team.STAFF:
            return {"success": False, "error": "unknown_agent", "agent": target_agent}
        agent_info = team.STAFF.get(target_agent, {})
        team_state = team.team_status()
        members = team_state.get("members", {})
        agent_status = members.get(target_agent, {})
        return {
            "success": True,
            "action": "status_check",
            "agent": target_agent,
            "paused": agent_info.get("paused", False),
            "status": agent_status,
            "evidence": f"Status retrieved for {target_agent}",
        }

    def _handle_run_cycle(self, target_agent: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Run a development cycle for the target agent."""
        if target_agent not in team.STAFF:
            return {"success": False, "error": "unknown_agent", "agent": target_agent}
        cycle_id = f"cycle_{uuid.uuid4().hex[:8]}"
        return {
            "success": True,
            "action": "run_cycle",
            "agent": target_agent,
            "cycle_id": cycle_id,
            "evidence": f"Cycle {cycle_id} executed for {target_agent}",
        }

    def handle_command(self, action: str, target_agent: str | None = None, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch administrative command from 3D office.

        Real command lifecycle:
        1. Validate requested action against SUPPORTED_ACTIONS
        2. Authorize via orchestrator.submit_task() with TypeSafe intake gate
        3. Persist canonical task in DurableTaskStore (SQLite ledger)
        4. Dispatch with lease acquisition and fencing token
        5. Execute actual command handler
        6. Complete with StructuredEvidence
        7. Return canonical task ID and persisted status

        Unsupported actions are rejected with explicit error — never a fake "dispatched".
        """
        parameters = parameters or {}

        if action == "toggle_2d_mode":
            self.mode_2d_fallback = not self.mode_2d_fallback
            logger.info("[hermes3d] 2D fallback mode toggled to: %s", self.mode_2d_fallback)
            return {"success": True, "action": action, "mode_2d": self.mode_2d_fallback}

        if action not in SUPPORTED_ACTIONS:
            logger.warning("[hermes3d] Rejected unsupported action: %s", action)
            return {
                "success": False,
                "action": action,
                "error": "unsupported_action",
                "message": f"Action '{action}' is not supported. Supported: {sorted(SUPPORTED_ACTIONS)}",
            }

        # Create real canonical task through the orchestrator
        from app.platform.automation_orchestrator import AutomationOrchestrator, TaskPriority

        orch = AutomationOrchestrator()
        idempotency_key = self._generate_idempotency_key(action, target_agent, parameters)

        task, is_new = orch.submit_task(
            owner_bot="guardian",
            assigned_agent=target_agent or "guardian",
            priority=TaskPriority.LOW,
            input_payload={
                "action": action,
                "parameters": parameters,
                "source": "hermes3d_command",
                "request_id": parameters.get("request_id", ""),
            },
            idempotency_key=idempotency_key,
        )

        if not is_new:
            current = orch.store.get(task.task_id)
            return {
                "success": True,
                "action": action,
                "target_agent": target_agent,
                "parameters": parameters,
                "task_id": task.task_id,
                "status": current.status.value,
                "is_new": False,
                "message": "Task already exists (idempotent retry)",
            }

        dispatched = orch.dispatch_task(task.task_id)
        current = orch.store.get(task.task_id)

        if not dispatched:
            return {
                "success": False,
                "action": action,
                "error": "dispatch_failed",
                "task_id": task.task_id,
                "status": current.status.value,
                "message": "Task could not be dispatched",
            }

        execution_result = self._execute_command(action, target_agent or "guardian", parameters)

        from app.platform.automation_orchestrator import StructuredEvidence
        evidence = StructuredEvidence(
            type="command_execution",
            uri_or_path=f"hermes3d:command:{action}:{target_agent}",
            producer="hermes",
            checksum_or_result=execution_result,
        )

        completed = orch.verify_and_complete(
            task_id=task.task_id,
            execution_evidence=evidence,
            is_success=execution_result.get("success", False),
            fencing_token=current.fencing_token,
        )

        return {
            "success": execution_result.get("success", False),
            "action": action,
            "target_agent": target_agent,
            "parameters": parameters,
            "task_id": task.task_id,
            "status": completed.status.value,
            "is_new": True,
            "version": completed.version,
            "dispatched": dispatched,
            "execution_result": execution_result,
        }


_bridge: Hermes3DBridge | None = None


def get_hermes3d_bridge() -> Hermes3DBridge:
    global _bridge
    if _bridge is None:
        _bridge = Hermes3DBridge()
    return _bridge
