"""OpenClaw GREEN surface for the External Agent Orchestrator (read-only).

Owner Copilot can SEE Cursor/Claude missions. It cannot create, claim, advance,
approve, merge or deploy them — those stay on the admin API behind Owner OS.
No new STAFF persona is invented; these are observation commands only.
"""

from __future__ import annotations

from typing import Any

EXTERNAL_AGENT_GREEN = frozenset(
    {
        "external.missions",
        "external.mission_status",
    }
)


def _summary_payload() -> dict[str, Any]:
    from app.dev_control.external_agents import orchestrator, policy

    if not policy.orchestrator_enabled():
        return {
            "enabled": False,
            "note": f"{policy.FLAG}=0 — external agent orchestrator inert",
            "missions": [],
            "summary": {},
        }
    return {
        "enabled": True,
        "summary": orchestrator.summary(),
        "missions": orchestrator.dashboard_rows(limit=25),
    }


def _external_missions(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    payload = _summary_payload()
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": payload,
        "evidence": {
            "source": "dev_control.external_agents.orchestrator",
            "correlation_id": correlation_id,
            "actor": actor,
            "read_only": True,
        },
        "next_action": "Admin → Dev Control Plane → Missions se act karo (Owner OS authority)",
    }


def _external_mission_status(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    from app.dev_control.external_agents import orchestrator, policy, store

    mission_id = str((params or {}).get("mission_id") or "").strip()
    if not policy.orchestrator_enabled():
        return _external_missions(params, actor=actor, correlation_id=correlation_id)
    mission = store.get(mission_id) if mission_id else None
    if mission is None:
        return {
            "status": "SUCCEEDED",
            "verified": True,
            "result": {"found": False, "mission_id": mission_id, "summary": orchestrator.summary()},
            "evidence": {"correlation_id": correlation_id, "actor": actor, "read_only": True},
            "next_action": "mission_id check karo — `external.missions` se list milegi",
        }
    row = next(
        (
            r
            for r in orchestrator.dashboard_rows(limit=500)
            if r["mission_id"] == mission.mission_id
        ),
        None,
    )
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {"found": True, "mission": row},
        "evidence": {
            "correlation_id": correlation_id,
            "actor": actor,
            "read_only": True,
            "evidence_count": len(mission.evidence_refs),
        },
        "next_action": "Owner decision chahiye to Admin Dev Control Plane use karo",
    }


EXTERNAL_AGENT_HANDLERS = {
    "external.missions": _external_missions,
    "external.mission_status": _external_mission_status,
}
