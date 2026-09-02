"""
Board Governance — Paperclip-inspired human override layer.
============================================================

Provides:
1. Approval gates on high-impact actions (spend, publish, send)
2. Pause any agent tree (agent + all reports)
3. Emergency kill switch (pause ALL agents)
4. Audit trail of all governance decisions

High-impact actions must be approved before execution:
- Spending > threshold (voice minutes, LLM budget)
- Publishing content externally
- Sending customer-facing messages
- Changing billing/pricing config

Gated by BOARD_GOVERNANCE env flag (default OFF = inert/passthrough).

Usage:
    from app.platform import board_governance

    # Check if action needs approval
    result = board_governance.requires_approval("publish_content", agent_id="isha", meta={"channel": "instagram"})

    # Request approval (creates pending record)
    req = board_governance.request_approval("isha", "publish_content", "Instagram post for Jiya Makeover")

    # Approve/reject (admin UI)
    board_governance.approve(request_id, by="sumit")
    board_governance.reject(request_id, by="sumit", reason="Not brand safe")

    # Emergency controls
    board_governance.pause_tree("rohan")       # Pause rohan + all reports
    board_governance.emergency_stop()          # Pause ALL agents
    board_governance.resume_all()              # Resume all
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ENABLED = os.environ.get("BOARD_GOVERNANCE", "0").strip().lower() in ("1", "true", "yes")
_GOVERNANCE_FILE = os.path.join("data", "governance_requests.json")

# Actions that require approval when governance is enabled
HIGH_IMPACT_ACTIONS = {
    "publish_content": {"description": "Publishing content externally", "auto_approve": False},
    "send_customer_message": {
        "description": "Sending customer-facing message",
        "auto_approve": False,
    },
    "voice_outbound": {"description": "Making outbound voice call", "auto_approve": False},
    "budget_override": {"description": "Overriding agent budget limit", "auto_approve": False},
    "pricing_change": {"description": "Changing billing/pricing config", "auto_approve": False},
    "data_export": {"description": "Exporting customer data", "auto_approve": False},
    "agent_deploy": {"description": "Deploying new agent capability", "auto_approve": False},
}


def is_enabled() -> bool:
    return _ENABLED


def _load_requests() -> list[dict[str, Any]]:
    try:
        if os.path.exists(_GOVERNANCE_FILE):
            with open(_GOVERNANCE_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_requests(reqs: list[dict[str, Any]]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_GOVERNANCE_FILE, "w", encoding="utf-8") as f:
            json.dump(reqs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"[governance] save failed: {e}")


def requires_approval(
    action: str, *, agent_id: str = "", meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Check if an action requires board approval.
    Returns {"required": True/False, "reason": "..."}."""
    if not _ENABLED:
        return {"required": False, "reason": "governance disabled"}

    if action in HIGH_IMPACT_ACTIONS:
        info = HIGH_IMPACT_ACTIONS[action]
        if info.get("auto_approve"):
            return {"required": False, "reason": "auto-approved by policy"}
        return {"required": True, "reason": info["description"], "action": action}

    return {"required": False, "reason": "action not governed"}


def request_approval(
    agent_id: str,
    action: str,
    description: str,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a pending approval request. Returns request_id."""
    if not _ENABLED:
        return {"ok": True, "auto_approved": True, "reason": "governance disabled"}

    req_id = str(uuid.uuid4())
    req = {
        "id": req_id,
        "agent_id": agent_id.strip().lower(),
        "action": action,
        "description": description[:500],
        "status": "pending",
        "meta": meta or {},
        "requested_at": time.time(),
        "decided_at": None,
        "decided_by": None,
        "decision_reason": None,
    }
    reqs = _load_requests()
    reqs.append(req)
    _save_requests(reqs)

    # Log + notify
    _log_event(agent_id, "approval_requested", f"🔐 {action}: {description[:100]}")
    _notify(f"🔐 Approval needed: {agent_id} wants to {action} — {description[:100]}")

    return {"ok": True, "id": req_id, "status": "pending"}


def approve(request_id: str, *, by: str = "admin") -> dict[str, Any]:
    """Approve a pending request."""
    reqs = _load_requests()
    for r in reqs:
        if r["id"] == request_id and r["status"] == "pending":
            r["status"] = "approved"
            r["decided_at"] = time.time()
            r["decided_by"] = by
            _save_requests(reqs)
            _log_event(r["agent_id"], "approval_granted", f"✅ {r['action']} approved by {by}")
            return {"ok": True}
    return {"ok": False, "error": "request not found or already decided"}


def reject(request_id: str, *, by: str = "admin", reason: str = "") -> dict[str, Any]:
    """Reject a pending request."""
    reqs = _load_requests()
    for r in reqs:
        if r["id"] == request_id and r["status"] == "pending":
            r["status"] = "rejected"
            r["decided_at"] = time.time()
            r["decided_by"] = by
            r["decision_reason"] = reason
            _save_requests(reqs)
            _log_event(
                r["agent_id"],
                "approval_rejected",
                f"❌ {r['action']} rejected by {by}: {reason[:100]}",
            )
            return {"ok": True}
    return {"ok": False, "error": "request not found or already decided"}


def pending_requests() -> list[dict[str, Any]]:
    """All pending approval requests."""
    return [r for r in _load_requests() if r.get("status") == "pending"]


def is_approved(request_id: str) -> bool:
    """Check if a specific request has been approved."""
    return any(r["id"] == request_id and r["status"] == "approved" for r in _load_requests())


def pause_tree(agent_id: str, *, by: str = "admin") -> dict[str, Any]:
    """Pause an agent AND all its reports (org chart cascade)."""
    try:
        from app.platform import agent_controls, org_chart

        paused = []
        key = agent_id.strip().lower()

        # Pause the agent itself
        agent_controls.pause(key, by=by, note=f"Board governance: tree pause by {by}")
        paused.append(key)

        # Pause all reports (recursive)
        def _pause_reports(mgr_id: str, depth: int = 0) -> None:
            if depth > 5:
                return
            for report in org_chart.reports(mgr_id):
                agent_controls.pause(
                    report, by=by, note=f"Board governance: tree pause (parent={mgr_id})"
                )
                paused.append(report)
                _pause_reports(report, depth + 1)

        _pause_reports(key)
        _log_event(key, "tree_paused", f"🌳 Tree paused ({len(paused)} agents) by {by}")
        _notify(f"🌳 Agent tree paused: {key} + {len(paused) - 1} reports by {by}")
        return {"ok": True, "paused": paused}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def emergency_stop(*, by: str = "admin") -> dict[str, Any]:
    """EMERGENCY: Pause ALL agents immediately."""
    try:
        from app.platform import agent_controls
        from app.platform.team import STAFF

        paused = []
        for key in STAFF:
            try:
                agent_controls.pause(key, by=by, note="EMERGENCY STOP by board governance")
                paused.append(key)
            except Exception:
                pass

        _log_event("manager", "emergency_stop", f"🚨 ALL {len(paused)} agents paused by {by}")
        _notify(f"🚨 EMERGENCY STOP: ALL {len(paused)} agents paused by {by}")
        return {"ok": True, "paused": paused, "count": len(paused)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def resume_all(*, by: str = "admin") -> dict[str, Any]:
    """Resume ALL agents after emergency stop."""
    try:
        from app.platform import agent_controls
        from app.platform.team import STAFF

        resumed = []
        for key in STAFF:
            try:
                agent_controls.resume(key, by=by, note="Board governance: resume all")
                resumed.append(key)
            except Exception:
                pass

        _log_event("manager", "resume_all", f"✅ ALL {len(resumed)} agents resumed by {by}")
        return {"ok": True, "resumed": resumed, "count": len(resumed)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def governance_dashboard() -> dict[str, Any]:
    """Full governance state for admin UI."""
    reqs = _load_requests()
    pending = [r for r in reqs if r["status"] == "pending"]
    recent = sorted(reqs, key=lambda r: r.get("requested_at", 0), reverse=True)[:20]

    return {
        "enabled": _ENABLED,
        "pending_count": len(pending),
        "pending": pending,
        "recent_decisions": recent,
        "high_impact_actions": list(HIGH_IMPACT_ACTIONS.keys()),
    }


def _log_event(agent_id: str, action: str, detail: str) -> None:
    try:
        from app.platform import team

        team.log_event(agent_id, action, detail)
    except Exception:
        pass


def _notify(message: str) -> None:
    try:
        import httpx

        ntfy_url = os.environ.get("NTFY_URL")
        if ntfy_url:
            httpx.post(
                ntfy_url,
                content=message,
                headers={"Title": "Board Governance", "Priority": "4"},
                timeout=5,
            )
    except Exception:
        pass
