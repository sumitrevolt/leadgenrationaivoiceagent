"""Compact Owner Copilot context — PII-minimized, tenant-aware, capped."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.integrations.openclaw.policies import redact_secrets


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_owner_context(*, tenant_id: str | None = None) -> dict[str, Any]:
    """Read-only snapshot for Copilot prompts / status. Never raises."""
    platform: dict[str, Any] = {
        "health": "unknown",
        "environment": os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "unknown",
        "version": os.getenv("APP_VERSION") or "dev",
        "source": "env",
        "as_of": _now(),
    }
    agents: dict[str, Any] = {
        "total": 31,
        "running": 0,
        "paused": [],
        "unhealthy": [],
        "source": "owner_os.agent_registry",
    }
    queues: dict[str, Any] = {"pending": 0, "failed": 0, "dead": 0, "source": "automation_health"}
    approvals: dict[str, Any] = {"pending": 0, "source": "approvals_bridge"}
    customers: dict[str, Any] = {
        "active_count": 0,
        "delivery_risks": [],
        "source": "owner_os",
        "filter_tenant": tenant_id,
    }
    safety: dict[str, Any] = {
        "calling_enabled": False,
        "calling_hard_off": True,
        "kill_switches": [],
        "source": "owner_os.kill_switch_board",
    }
    next_actions: list[dict[str, Any]] = []

    try:
        from app.platform import owner_os

        home = owner_os.owner_home()
        platform["health"] = "healthy" if home.get("ok") else "degraded"
        platform["source"] = "owner_os.owner_home"
        wf = home.get("workforce") or {}
        agents.update(
            {
                "total": int(wf.get("canonical_agents") or wf.get("total") or 31),
                "running": int(wf.get("working") or 0),
                "paused": [],
                "paused_manual_run_count": int(wf.get("paused_manual_run") or 0),
            }
        )
        if wf.get("paused_manual_run"):
            # Names only when cheap — avoid dumping full registry into every prompt.
            try:
                reg = owner_os.agent_registry()
                agents["paused"] = [
                    a.get("id") for a in (reg.get("agents") or []) if a.get("paused")
                ][:20]
            except Exception:
                pass
        approvals["pending"] = int(home.get("approvals_pending") or 0)
        kills = home.get("kill_switches") or {}
        safety["kill_switches"] = [
            k for k, v in kills.items() if isinstance(v, dict) and v.get("engaged")
        ][:20]
        safety["calling_hard_off"] = True
        safety["calling_enabled"] = False
        for rec in home.get("recommended") or []:
            next_actions.append(
                {
                    "label": rec.get("label"),
                    "command_hint": rec.get("command"),
                    "source": "owner_os.recommended",
                }
            )
        customers["active_count"] = 1  # honest: Jiya is the only paying customer today
        if tenant_id:
            customers["filter_tenant"] = tenant_id
            customers["note"] = "tenant filter applied — no cross-tenant expansion"
    except Exception as exc:
        platform["health"] = "degraded"
        platform["error"] = type(exc).__name__

    try:
        from app.platform.automation_health import queue_depth

        qd = queue_depth() or {}
        queues.update(
            {
                "pending": int(qd.get("celery") or 0),
                "failed": int(qd.get("dlq") or 0),
                "dead": int(qd.get("dead") or 0),
            }
        )
    except Exception:
        pass

    # Delivery risk for requested tenant only (read-only, no PII dump).
    if tenant_id:
        try:
            from app.platform import owner_os as _oos

            # Prefer existing safe status report builder if present.
            if hasattr(_oos, "_build_status_report"):
                rep = _oos._build_status_report(tenant_id)  # noqa: SLF001 — intentional reuse
                risks = []
                if isinstance(rep, dict):
                    if rep.get("pending_approvals") or rep.get("approval_pending"):
                        risks.append("approval_pending")
                    if rep.get("undelivered") or (rep.get("counts") or {}).get("undelivered"):
                        risks.append("undelivered")
                customers["delivery_risks"] = risks[:10]
                customers["report_keys"] = sorted(rep.keys())[:20] if isinstance(rep, dict) else []
        except Exception:
            customers["delivery_risks"] = ["status_unavailable"]

    # ADR-154: compact workforce memory hub snapshot (no entry bodies / no PII dump).
    workforce_memory: dict[str, Any] = {"enabled": False, "source": "workforce_memory"}
    try:
        from app.platform import workforce_memory as _wfm

        snap = _wfm.hub_snapshot(max_agents=5)
        workforce_memory = {
            "enabled": bool(snap.get("enabled")),
            "agents_with_memory": int(snap.get("agents_with_memory") or 0),
            "sample_agent_ids": [s.get("agent_id") for s in (snap.get("sample") or [])][:5],
            "counters": snap.get("counters") or {},
            "source": "workforce_memory.hub_snapshot",
        }
    except Exception as exc:
        workforce_memory["error"] = type(exc).__name__

    ctx = {
        "platform": platform,
        "agents": agents,
        "queues": queues,
        "approvals": approvals,
        "customers": customers,
        "safety": safety,
        "workforce_memory": workforce_memory,
        "next_actions": next_actions[:5],
        "generated_at": _now(),
        "max_payload_note": "compact context — no DB dump, no secrets, no cross-tenant",
    }
    return redact_secrets(ctx)
