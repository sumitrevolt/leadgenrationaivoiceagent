"""Mission-control OpenClaw surface — GREEN chat ingress + AMBER controls.

Owner OS remains sole mutation authority. RED outbound never unlocked here.
"""

from __future__ import annotations

from typing import Any

MISSION_GREEN = frozenset(
    {
        "mission.status",
        "mission.launch_ready",
        "mission.revenue_ready",
        "mission.income_today",
        "mission.chat",
        "mission.executors",
        "mission.dispatch_ops",
    }
)

MISSION_AMBER = frozenset(
    {
        "mission.pause",
        "mission.resume",
        "mission.approve",
        "mission.rollback",
    }
)


def _mission_status(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform import mission_control as mc

    mid = str(params.get("mission_id") or "").strip() or None
    body = mc.mission_status(mid)
    return {
        "status": "SUCCEEDED" if body.get("ok") else "FAILED",
        "verified": True,
        "result": body,
        "evidence": {"correlation_id": correlation_id, "actor": actor},
        "next_action": "mission.chat se launch-ready / revenue-ready bhejo",
    }


def _mission_executors(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    from app.platform import mission_control as mc

    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": mc.probe_executors(),
        "evidence": {"correlation_id": correlation_id, "actor": actor},
        "next_action": "Unavailable adapters implement karo ya lane manual mark karo",
    }


def _mission_dispatch_ops(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    from app.platform import mission_control as mc

    mid = str(params.get("mission_id") or "").strip()
    if not mid:
        return {
            "status": "FAILED",
            "verified": True,
            "result": {"ok": False, "error": "mission_id_required"},
            "evidence": {"correlation_id": correlation_id, "actor": actor},
            "next_action": "mission_id pass karo (income-today create ke baad)",
        }
    out = mc.dispatch_openclaw_lane(
        mid,
        actor=actor,
        wa_limit=int(params.get("wa_limit") or 5),
        prep_limit=int(params.get("prep_limit") or 10),
    )
    return {
        "status": "SUCCEEDED" if out.get("ok") else "FAILED",
        "verified": True,
        "result": out,
        "evidence": {
            "correlation_id": correlation_id,
            "actor": actor,
            "session_id": out.get("session_id"),
        },
        "command_id": out.get("session_id") or f"ocmd_{correlation_id[-12:]}",
        "next_action": "Owner approval inbox me drafts review/send; RED flags OFF",
    }


def _spawn(
    template: str, params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    from app.platform import mission_control as mc

    # Never auto-mint keys from correlation_id — that would create a new mission per call.
    idem = str(params.get("idempotency_key") or "").strip()
    if not idem:
        return {
            "status": "FAILED",
            "verified": True,
            "result": {
                "ok": False,
                "error": "idempotency_key_required",
                "hint": "Pass stable idempotency_key (e.g. launch_ready:2026-07-31)",
            },
            "evidence": {"correlation_id": correlation_id, "actor": actor, "template": template},
            "next_action": "Stable idempotency_key bhejo; chat path bhi same rule follow karta hai",
        }
    created = mc.create_mission(
        template,
        actor=actor,
        base_sha=str(params.get("base_sha") or "") or None,
        idempotency_key=idem,
    )
    return {
        "status": "SUCCEEDED" if created.get("ok") else "FAILED",
        "verified": True,
        "result": created,
        "evidence": {"correlation_id": correlation_id, "actor": actor, "template": template},
        "next_action": "Manual lanes implement; verifier false-green reject kare",
    }


def _mission_launch_ready(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    return _spawn("launch_ready", params, actor=actor, correlation_id=correlation_id)


def _mission_revenue_ready(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    return _spawn("revenue_ready", params, actor=actor, correlation_id=correlation_id)


def _mission_income_today(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    return _spawn("income_today", params, actor=actor, correlation_id=correlation_id)


def _mission_chat(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    from app.platform import mission_control as mc

    text = str(params.get("text") or params.get("command") or "").strip()
    # GREEN handler: never pass confirm through — AMBER always parks from chat.
    out = mc.handle_chat(
        text,
        actor=actor,
        base_sha=str(params.get("base_sha") or "") or None,
        idempotency_key=str(params.get("idempotency_key") or "") or None,
        confirm=False,
    )
    return {
        "status": "SUCCEEDED" if out.get("ok") else "FAILED",
        "verified": True,
        "result": out,
        "evidence": {"correlation_id": correlation_id, "actor": actor},
        "next_action": out.get("hint") or out.get("note") or "status / launch-ready",
    }


def _amber_mission(
    params: dict[str, Any], *, actor: str, correlation_id: str, verb: str
) -> dict[str, Any]:
    from app.platform import mission_control as mc

    arg = str(
        params.get("arg")
        or params.get("lane")
        or params.get("gate")
        or params.get("mission_id")
        or ""
    ).strip()
    out = mc.apply_amber_action(verb, arg, actor=actor, confirm=bool(params.get("confirm")))
    return {
        "status": "SUCCEEDED" if out.get("ok") else "FAILED",
        "verified": True,
        "result": out,
        "evidence": {"correlation_id": correlation_id, "actor": actor, "verb": verb},
        "next_action": "confirm=true Owner OS pe; RED flags chat se nahi khulte",
    }


def _mission_pause(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    return _amber_mission(params, actor=actor, correlation_id=correlation_id, verb="pause")


def _mission_resume(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    return _amber_mission(params, actor=actor, correlation_id=correlation_id, verb="resume")


def _mission_approve(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    return _amber_mission(params, actor=actor, correlation_id=correlation_id, verb="approve")


def _mission_rollback(params: dict[str, Any], *, actor: str, correlation_id: str) -> dict[str, Any]:
    return _amber_mission(params, actor=actor, correlation_id=correlation_id, verb="rollback")


MISSION_HANDLERS = {
    "mission.status": _mission_status,
    "mission.executors": _mission_executors,
    "mission.dispatch_ops": _mission_dispatch_ops,
    "mission.launch_ready": _mission_launch_ready,
    "mission.revenue_ready": _mission_revenue_ready,
    "mission.income_today": _mission_income_today,
    "mission.chat": _mission_chat,
    "mission.pause": _mission_pause,
    "mission.resume": _mission_resume,
    "mission.approve": _mission_approve,
    "mission.rollback": _mission_rollback,
}

__all__ = ["MISSION_AMBER", "MISSION_GREEN", "MISSION_HANDLERS"]
