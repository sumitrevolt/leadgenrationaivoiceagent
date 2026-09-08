"""Coordination Hub — thin Owner OS projection (NOT a second control plane).

Assembles read-only views from Owner OS registry, external-agent missions,
office Active Coordination, tool presence, desktop-app registry, events,
and bounded git. Mutations stay on existing Owner OS / missions endpoints.
"""

from __future__ import annotations

from typing import Any

from app.platform.coordination_desktop_registry import registry_slice
from app.platform.coordination_hub_auth import hub_enabled, tool_auth_status
from app.platform.coordination_hub_events import list_events, list_presence
from app.platform.coordination_hub_git import probe_git
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_MUTATION_POINTERS = {
    "pause_agent": {
        "error": "use_owner_os",
        "href": "/api/admin/owner-os/agents/{id}/pause",
        "ui": "/app/owner#agents",
    },
    "kill_switch": {
        "error": "use_owner_os",
        "href": "/api/admin/owner-os/kill-switches",
        "ui": "/app/owner#kill",
    },
    "create_mission": {
        "error": "use_missions",
        "href": "/api/dev-tasks/missions",
        "ui": "/app/dev-control",
    },
    "deploy": {
        "error": "refused",
        "note": "Hub never deploys — use deploy_vps.sh after owner authorize",
    },
}


def mutation_refused(action: str) -> dict[str, Any]:
    tip = _MUTATION_POINTERS.get(action) or {
        "error": "use_owner_os",
        "ui": "/app/owner",
    }
    return {"ok": False, **tip, "hub": "projection_only"}


def _owner_agents_slice() -> dict[str, Any]:
    try:
        from app.platform import owner_os

        reg = owner_os.agent_registry()
        return {
            "ok": True,
            "canonical_agents": reg.get("canonical_agents") or reg.get("total"),
            "workforce": {
                k: reg.get(k)
                for k in (
                    "canonical_agents",
                    "system_supervisors",
                    "service_identities",
                    "runnable_workers",
                    "paused_manual_run",
                    "total",
                )
                if k in reg
            }
            or reg,
            "note": "Projected from owner_os.agent_registry — Hub does not own STAFF",
        }
    except Exception as e:
        logger.debug("[coord_hub] owner agents: %s", e)
        return {"ok": False, "error": str(e)[:120]}


def _missions_slice() -> dict[str, Any]:
    try:
        from app.dev_control.external_agents import orchestrator, policy

        if not policy.orchestrator_enabled():
            return {
                "ok": True,
                "enabled": False,
                "note": "EXTERNAL_AGENT_ORCHESTRATOR off — ledger inert",
                "summary": {},
                "rows": [],
            }
        summary = orchestrator.summary()
        rows = orchestrator.dashboard_rows(limit=20)
        return {
            "ok": True,
            "enabled": True,
            "summary": summary,
            "rows": rows,
            "note": "Projected from external_agents ledger — Hub does not claim leases",
        }
    except Exception as e:
        logger.debug("[coord_hub] missions: %s", e)
        return {"ok": False, "error": str(e)[:120], "enabled": False}


def _office_coordination_slice() -> dict[str, Any]:
    try:
        from app.platform import office_hq

        rows = office_hq.build_coordination(limit=8)
        return {
            "ok": True,
            "topology": office_hq.coordination_topology(),
            "rows": rows,
            "note": "Projected from office_hq / coordination_runs.jsonl",
        }
    except Exception as e:
        logger.debug("[coord_hub] office coord: %s", e)
        return {"ok": False, "error": str(e)[:120], "rows": []}


def _automation_orchestrator_slice() -> dict[str, Any]:
    try:
        from app.platform.automation_orchestrator import AutomationOrchestrator

        orch = AutomationOrchestrator()
        kanban = orch.get_kanban_board()
        metrics = orch.get_metrics()
        return {
            "ok": True,
            "kanban": kanban,
            "metrics": metrics,
            "note": "Projected from automation_orchestrator task ledger",
        }
    except Exception as e:
        logger.debug("[coord_hub] automation orchestrator: %s", e)
        return {"ok": False, "error": str(e)[:120], "kanban": {}, "metrics": {}}


def snapshot(*, include_git: bool = True, events_limit: int = 40) -> dict[str, Any]:
    """Assemble Hub dashboard payload. Safe when flag OFF (inert empty)."""
    enabled = hub_enabled()
    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "role": "owner_os_thin_projection",
            "note": "COORDINATION_HUB_ENABLED=0 — inert",
            "owner_agents": {},
            "missions": {"enabled": False, "rows": []},
            "office_coordination": {"rows": []},
            "automation_orchestrator": _automation_orchestrator_slice(),
            "tools_presence": {"tools": {}},
            "tool_auth": tool_auth_status(),
            "desktop_registry": {
                "ok": True,
                "enabled": False,
                "apps": [],
                "note": "COORDINATION_HUB_ENABLED=0 — inert",
            },
            "git": None,
            "events_tail": [],
            "mutations": "refused_use_owner_os_or_missions",
        }

    git_block = None
    if include_git:
        try:
            git_block = probe_git()
        except Exception as e:  # pragma: no cover
            git_block = {"ok": False, "error": str(e)[:120]}

    return {
        "ok": True,
        "enabled": True,
        "role": "owner_os_thin_projection",
        "note": (
            "Read-only projection. Mutations via Owner OS / external missions only. "
            "Not a second STAFF or mission registry."
        ),
        "owner_agents": _owner_agents_slice(),
        "missions": _missions_slice(),
        "office_coordination": _office_coordination_slice(),
        "automation_orchestrator": _automation_orchestrator_slice(),
        "tools_presence": list_presence(),
        "tool_auth": tool_auth_status(),
        "desktop_registry": registry_slice(),
        "git": git_block,
        "events_tail": list_events(limit=events_limit),
        "mutations": "refused_use_owner_os_or_missions",
        "pointers": {
            "owner_os_ui": "/app/owner",
            "missions_ui": "/app/dev-control",
            "office_ui": "/app/office",
        },
    }


__all__ = ["snapshot", "mutation_refused", "hub_enabled"]

