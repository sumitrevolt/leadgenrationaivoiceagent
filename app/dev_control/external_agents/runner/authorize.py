"""Owner OS authorization gate for runner invocation.

GREEN missions in a local canary may receive a recorded auto-authorization when
both flags are ON. AMBER always parks. RED is refused. This is NOT a production
approval path and never grants deploy/calling/billing rights.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.dev_control.external_agents.runner.flags import runner_enabled
from app.dev_control.external_agents.schema import Mission, RiskClass


def authorize_mission(mission: Mission) -> dict[str, Any]:
    if not runner_enabled():
        return {"authorized": False, "reason": "runner_or_orchestrator_off"}
    if mission.risk_class is RiskClass.RED:
        return {"authorized": False, "reason": "red_refused"}
    if mission.risk_class is RiskClass.AMBER:
        return {
            "authorized": False,
            "reason": "owner_decision_required",
            "authority": "Owner OS — AMBER cannot auto-run",
        }
    if mission.risk_class is not RiskClass.GREEN:
        return {"authorized": False, "reason": "unknown_risk"}
    # GREEN local canary: record a deterministic authorization evidence blob.
    # Production enablement of the runner flag remains a separate owner gate.
    return {
        "authorized": True,
        "reason": "green_local_canary_authorized",
        "authority": "Owner OS sole authority preserved — runner grants no deploy/calling/billing rights",
        "authorized_at": datetime.utcnow().isoformat() + "Z",
        "mission_id": mission.mission_id,
        "risk_class": mission.risk_class.value,
    }
