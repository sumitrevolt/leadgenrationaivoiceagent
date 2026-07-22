"""Kavach — the OpenClaw Agent Harness Controller.

Identity (NON-dispatchable, NOT a STAFF member, does not change the canonical
31-agent count). Kavach is advisory/validation/orchestration only and reaches
mutations exclusively through Owner OS. It is registered as an OpenClaw *system*
agent, never selected by worker/dispatcher selectors.

Authority chain enforced by this module:
    Admin -> OpenClaw Copilot -> Kavach -> Owner OS -> Boss/dispatcher -> 31 agents
Kavach never dispatches, never calls Celery/billing/WAHA/Postiz/calling directly.
"""

from __future__ import annotations

import os
import re
from typing import Any

# --- Agent identity ---------------------------------------------------
KAVACH_AGENT: dict[str, Any] = {
    "id": "openclaw_harness",
    "display_name": "Kavach",
    "type": "openclaw_system",  # not "staff", not "worker"
    "authority": "advisory_validation_orchestration_enforcement_via_owner_os",
    "dispatchable": False,  # never selectable by worker selectors
    "staff_member": False,  # NOT in team.STAFF
    "customer_facing": False,
    "counts_toward_staff": False,  # canonical STAFF count impact: None
    "second_dispatcher": False,  # strictly forbidden
    "calling_capable": False,
    "flag": "OPENCLAW_HARNESS_AGENT",  # INERT default (0)
}


def is_enabled() -> bool:
    return (os.getenv("OPENCLAW_HARNESS_AGENT") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_dispatchable() -> bool:
    """Kavach is never dispatchable. Kept as an explicit invariant for tests."""
    return False


# --- Deterministic NL -> harness command -----------------------------
def classify_harness_nl(text: str) -> dict[str, Any]:
    """Map free-form owner intent to ONE typed harness command.

    Ambiguous input resolves to the safest read (harness.status). Mirrors the
    fail-safe posture of openclaw.commands.classify_nl.
    """
    raw = (text or "").strip()
    low = raw.lower()
    params: dict[str, Any] = {}

    run_m = re.search(r"\brun[_ ]?id[:= ]+([a-z0-9\-]{6,})", low)
    if run_m:
        params["run_id"] = run_m.group(1)
    agent_m = re.search(r"\bagent[:= ]+([a-z0-9_\-]+)", low)
    if agent_m:
        params["agent_id"] = agent_m.group(1)

    def prop(cmd: str, lane: str, note: str | None = None, conf: str = "high") -> dict[str, Any]:
        return {
            "ok": True,
            "command": cmd,
            "params": params,
            "safety_lane": lane,
            "confidence": conf,
            "original": raw[:2000],
            "note": note,
            "approval_required": lane == "AMBER",
            "agent": KAVACH_AGENT["id"],
        }

    # Read intents (GREEN)
    if "conformance" in low or "control matrix" in low:
        return prop("harness.conformance", "GREEN")
    if ("explain" in low or "kyun" in low or "why" in low) and params.get("run_id"):
        return prop("harness.explain", "GREEN")
    if "replay" in low and params.get("run_id"):
        return prop("harness.replay", "GREEN")
    if "eval" in low or "evaluation" in low:
        return prop("harness.evaluate", "GREEN")
    if any(x in low for x in ("harness status", "harness state", "status", "kaisa")):
        return prop("harness.status", "GREEN")

    # Control intents (AMBER — parked for Owner OS approval)
    if "shadow" in low:
        return prop(
            "harness.shadow.enable" if "enable" in low or "on" in low else "harness.shadow.disable",
            "AMBER",
        )
    if "canary" in low:
        return prop(
            "harness.canary.enable" if "enable" in low or "on" in low else "harness.canary.disable",
            "AMBER",
        )
    if "enforce" in low:
        return prop(
            (
                "harness.enforce.enable"
                if "enable" in low or "on" in low
                else "harness.enforce.disable"
            ),
            "AMBER",
        )
    if "pause" in low or "rok" in low:
        return prop("harness.pause", "AMBER")
    if "resume" in low or "chalu" in low:
        return prop("harness.resume", "AMBER")
    if "cancel" in low:
        return prop("harness.cancel", "AMBER")
    if "checkpoint" in low:
        return prop("harness.checkpoint", "AMBER")
    if "kill" in low:
        return prop("harness.kill", "AMBER")
    if "restore" in low:
        return prop("harness.restore", "AMBER")

    return prop("harness.status", "GREEN", note="Ambiguous -> read-only harness.status", conf="low")


def handle(
    text: str,
    *,
    actor: str = "admin",
    correlation_id: str | None = None,
    confirm: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Parse intent, then route through the SAME Owner OS gate as every other
    OpenClaw command. Kavach adds nothing that bypasses policy or Owner OS."""
    if not is_enabled():
        return {
            "ok": False,
            "error": "OPENCLAW_HARNESS_AGENT=0 — Kavach inert",
            "agent": KAVACH_AGENT["id"],
        }

    plan = classify_harness_nl(text)
    from app.integrations.openclaw.commands import execute_typed_command

    result = execute_typed_command(
        plan["command"],
        plan.get("params") or {},
        actor=actor,
        idempotency_key=idempotency_key,
        confirm=confirm,
        correlation_id=correlation_id,
        text=text,
    )
    return {"agent": KAVACH_AGENT["id"], "plan": plan, "result": result}
