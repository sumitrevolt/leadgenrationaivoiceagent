"""AMBER mission approval via Owner OS verification ledger (no second store).

Binds ``approval_decision_id`` (``oosv_*``) to mission identity fields and
verifies through ``approvals_bridge`` + decision stamps — never a request-body
boolean alone.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass

APPROVAL_SOURCE = "owner_os_verification"
_BIND_KIND = "external_agent_amber"


def _paths_key(paths: list[str]) -> str:
    return "|".join(
        sorted(str(p).replace("\\", "/").strip() for p in (paths or []) if str(p).strip())
    )


def approval_binding(
    mission: Mission,
    *,
    target_state: str | MissionState,
    head_sha: str | None = None,
) -> dict[str, Any]:
    target = target_state.value if isinstance(target_state, MissionState) else str(target_state)
    head = (head_sha or mission.base_sha or "").strip()
    paths = _paths_key(list(mission.allowed_paths or []))
    payload = {
        "kind": _BIND_KIND,
        "mission_id": mission.mission_id,
        "target_state": target,
        "head_sha": head,
        "executor": (mission.executor or "").strip().lower(),
        "risk_class": (
            mission.risk_class.value
            if isinstance(mission.risk_class, RiskClass)
            else str(mission.risk_class)
        ),
        "allowed_paths": paths,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    payload["binding_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return payload


def request_amber_approval(
    mission: Mission,
    *,
    target_state: str | MissionState,
    actor: str = "admin",
    head_sha: str | None = None,
    ttl_hours: int = 24,
) -> dict[str, Any]:
    """Create Owner OS verification draft with AMBER binding meta."""
    from app.platform import approvals_bridge, owner_os

    if mission.risk_class is RiskClass.RED:
        return {"ok": False, "reason": "red_never_approvable"}
    bind = approval_binding(mission, target_state=target_state, head_sha=head_sha)
    out = approvals_bridge.create_verification_approval(
        by=actor,
        title=f"AMBER external-agent {mission.mission_id} → {bind['target_state']}",
        note=f"Bound approval for external agent mission {mission.mission_id}",
        ttl_hours=ttl_hours,
        meta=bind,
    )
    if out.get("ok"):
        try:
            owner_os.audit(
                actor,
                "external_agent_amber_approval_requested",
                {
                    "target": out.get("id"),
                    "mission_id": mission.mission_id,
                    "approval_decision_id": out.get("id"),
                    "binding_hash": bind.get("binding_hash"),
                },
            )
        except Exception:
            pass
    return {
        "ok": bool(out.get("ok")),
        "approval_decision_id": out.get("id"),
        "source": APPROVAL_SOURCE,
        "binding": bind,
        "detail": out,
    }


def assert_amber_approved(
    approval_decision_id: str,
    mission: Mission,
    *,
    target_state: str | MissionState,
    head_sha: str | None = None,
) -> dict[str, Any]:
    """Fail-closed verify of an Owner OS approval decision for this mission."""
    from app.platform import approvals_bridge

    if mission.risk_class is RiskClass.RED:
        return {"ok": False, "reason": "red_never_approvable"}
    did = str(approval_decision_id or "").strip()
    if not did:
        return {"ok": False, "reason": "approval_decision_id_required"}

    draft = approvals_bridge.get_verification_draft(did)
    if not draft:
        return {"ok": False, "reason": "approval_decision_unknown"}

    status = str(approvals_bridge._status_for(APPROVAL_SOURCE, did) or "").lower()  # noqa: SLF001
    if status == "consumed":
        return {"ok": False, "reason": "approval_already_consumed"}
    if status in {"rejected", "denied"}:
        return {"ok": False, "reason": "approval_denied"}
    if status != "approved":
        return {"ok": False, "reason": "approval_not_approved", "status": status}

    exp_raw = str(draft.get("expires_at") or "")
    if exp_raw:
        try:
            exp = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return {"ok": False, "reason": "approval_expired"}
        except Exception:
            return {"ok": False, "reason": "approval_expiry_invalid"}

    meta = draft.get("meta") if isinstance(draft.get("meta"), dict) else {}
    if str(meta.get("kind") or "") != _BIND_KIND:
        return {"ok": False, "reason": "approval_binding_kind_mismatch"}
    expected = approval_binding(mission, target_state=target_state, head_sha=head_sha)
    for key in (
        "mission_id",
        "target_state",
        "head_sha",
        "executor",
        "risk_class",
        "allowed_paths",
    ):
        if str(meta.get(key) or "") != str(expected.get(key) or ""):
            return {"ok": False, "reason": f"approval_binding_mismatch:{key}"}
    if str(meta.get("binding_hash") or "") != str(expected.get("binding_hash") or ""):
        return {"ok": False, "reason": "approval_binding_hash_mismatch"}

    return {
        "ok": True,
        "approval_decision_id": did,
        "approver": str(draft.get("created_by") or ""),
        "binding": expected,
        "status": status,
    }


def consume_amber_approval(approval_decision_id: str, *, actor: str = "runner") -> None:
    """One-time consume stamp on the Owner OS decision ledger."""
    from app.platform import approvals_bridge

    did = str(approval_decision_id or "").strip()
    if not did:
        return
    try:
        approvals_bridge._set_status(  # noqa: SLF001
            APPROVAL_SOURCE, did, "consumed", by=actor, reason="external_agent_advance"
        )
    except Exception:
        pass
