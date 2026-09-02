"""Owner OS litmus gate — ADR-155 harvest from agent-swarm HITL litmus (native).

Deterministic preflight for command plans / execute. No Bun swarm, no paid judge.
Default ON via OWNER_OS_LITMUS — when OFF, report still attaches but execute is not blocked.
"""

from __future__ import annotations

import os
from typing import Any


def litmus_enabled() -> bool:
    return os.getenv("OWNER_OS_LITMUS", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def evaluate_plan_litmus(plan: dict[str, Any]) -> dict[str, Any]:
    """Attachable checklist for parse_intent / preview. Never raises."""
    checks: list[dict[str, Any]] = []
    intent = str(plan.get("intent") or "").strip()
    risk = str(plan.get("risk_level") or "").strip().lower()
    approval = bool(plan.get("approval_required"))

    checks.append(
        {
            "id": "intent_classified",
            "ok": bool(intent) and intent != "unknown",
            "must_pass": False,
            "detail": intent or "empty",
        }
    )
    checks.append(
        {
            "id": "risk_tagged",
            "ok": risk in {"low", "medium", "high", "critical"},
            "must_pass": True,
            "detail": risk or "missing",
        }
    )
    high = risk in {"high", "critical"}
    checks.append(
        {
            "id": "high_risk_requires_approval",
            "ok": (not high) or approval,
            "must_pass": True,
            "detail": f"risk={risk} approval_required={approval}",
        }
    )
    if intent == "status_report":
        pub = bool(plan.get("publish_allowed"))
        notify = bool(plan.get("customer_notify_allowed"))
        checks.append(
            {
                "id": "status_report_no_customer_side_effects",
                "ok": (not pub) and (not notify),
                "must_pass": True,
                "detail": f"publish={pub} notify={notify}",
            }
        )

    kill_ok = False
    kill_detail = "unreachable"
    try:
        from app.platform import owner_os

        board = owner_os.kill_switch_board()
        kill_ok = isinstance(board, dict)
        kill_detail = f"keys={len(board)}" if kill_ok else "bad_shape"
    except Exception as exc:  # noqa: BLE001 — litmus never raises
        kill_detail = type(exc).__name__
    checks.append(
        {
            "id": "kill_board_readable",
            "ok": kill_ok,
            "must_pass": True,
            "detail": kill_detail,
        }
    )

    must = [c for c in checks if c.get("must_pass")]
    failed_must = [c["id"] for c in must if not c.get("ok")]
    return {
        "schema": "owner-os-litmus/1",
        "enabled": litmus_enabled(),
        "ok": not failed_must,
        "failed_must": failed_must,
        "checks": checks,
        "source": "adr-155-feature-harvest",
    }


def evaluate_execute_litmus(
    command: dict[str, Any], plan: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Fail-closed execute preflight when OWNER_OS_LITMUS is on."""
    base = evaluate_plan_litmus(plan or {})
    checks = list(base.get("checks") or [])
    idem = str(command.get("idempotency_key") or "").strip()
    checks.append(
        {
            "id": "idempotency_key_present",
            "ok": bool(idem),
            "must_pass": True,
            "detail": "set" if idem else "missing",
        }
    )
    status = str(command.get("status") or "")
    checks.append(
        {
            "id": "executable_status",
            "ok": status in {"READY", "QUEUED"},
            "must_pass": True,
            "detail": status or "empty",
        }
    )
    must = [c for c in checks if c.get("must_pass")]
    failed_must = [c["id"] for c in must if not c.get("ok")]
    return {
        "schema": "owner-os-litmus/1",
        "enabled": litmus_enabled(),
        "ok": not failed_must,
        "failed_must": failed_must,
        "checks": checks,
        "source": "adr-155-feature-harvest",
    }


def gate_execute(command: dict[str, Any], plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {ok, litmus, reason?}. When litmus disabled, always ok with report."""
    litmus = evaluate_execute_litmus(command, plan)
    if not litmus_enabled():
        return {"ok": True, "litmus": litmus, "bypassed": True}
    if litmus.get("ok"):
        return {"ok": True, "litmus": litmus}
    return {
        "ok": False,
        "litmus": litmus,
        "reason": "litmus_failed:" + ",".join(litmus.get("failed_must") or []),
    }
