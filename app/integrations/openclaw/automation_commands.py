"""OpenClaw GREEN surface for Automation-Max agents (read-only).

Does NOT invent STAFF personas. Wraps existing cadence / journey / flags /
scheduler heartbeats so Owner Copilot can see which automation agents are
actually live under OpenClaw Stage A.

Control mutations stay AMBER via existing agent.pause/resume → Owner OS.
"""

from __future__ import annotations

import os
from typing import Any

# GREEN — Automation-Max introspection for Copilot.
AUTOMATION_GREEN = frozenset(
    {
        "automation.status",
        "automation.agents",
    }
)

# Agents that own Automation-Max loops (scheduler / engines). OpenClaw observes;
# runtime pilot allowlist is separate (ADR Wave-B).
_AUTOMATION_AGENT_MAP: dict[str, dict[str, Any]] = {
    "anika": {
        "role": "Cadence Manager",
        "engines": ["CADENCE_ENGINE"],
        "jobs": [],  # advanced inside growth pulse
        "openclaw_lane": "observe",
        "note": "Omnichannel cadence drafts; auto-send OFF (ban-safe).",
    },
    "kavya": {
        "role": "Ops / Watchdog",
        "engines": ["OPS_WATCHDOG", "AUTOMATION_HEALTH_ALERTS", "INTEGRATION_ALERTS"],
        "jobs": ["ops", "watchdog", "saturday_hygiene"],
        "openclaw_lane": "observe",
        "note": "Hourly health + dead-man recovery; never dials.",
    },
    "isha": {
        "role": "Content",
        "engines": [],
        "jobs": ["content", "blog", "afternoon_content", "weekly_marketing", "social_drain"],
        "openclaw_lane": "observe",
        "note": "Draft generation; publish still human/Owner OS approval.",
    },
    "rohan": {
        "role": "Prospect / reply triage",
        "engines": ["AUTO_EMAIL_OUTREACH", "REPLY_AGENT", "NICHE_ROTATION"],
        "jobs": [
            "prospect",
            "midday_prospect",
            "evening_prospect",
            "email_outreach",
            "email_followup",
            "reply_triage",
        ],
        "openclaw_lane": "observe",
        "note": "Cold email gated OFF by default (Automation-Max Phase-1).",
    },
    "neha": {
        "role": "Pipeline / journey hooks",
        "engines": ["JOURNEY_ENGINE"],
        "jobs": ["pipeline"],
        "openclaw_lane": "observe",
        "note": "Inquiry journey drafts; WhatsApp auto-send stays OFF.",
    },
}


def _flag_on(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _job_beats(job_ids: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not job_ids:
        return out
    beats: dict[str, Any] = {}
    try:
        import json
        from pathlib import Path

        p = Path("data/job_heartbeats.json")
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                beats = raw
    except Exception:
        beats = {}
    for j in job_ids:
        b = beats.get(j)
        if isinstance(b, dict):
            out[j] = {
                "at": b.get("at"),
                "ok": b.get("ok"),
                "note": b.get("note") or "",
                "s": b.get("s"),
            }
        else:
            out[j] = None
    return out


def automation_agent_package(agent_id: str) -> dict[str, Any] | None:
    """Per-agent OpenClaw package (like Swara transfer, but automation observe)."""
    aid = (agent_id or "").strip().lower()
    meta = _AUTOMATION_AGENT_MAP.get(aid)
    if not meta:
        return None
    engines = {f: _flag_on(f) for f in (meta.get("engines") or [])}
    jobs = list(meta.get("jobs") or [])
    pkg: dict[str, Any] = {
        "status": "AUTOMATION_OBSERVE",
        "role": meta.get("role"),
        "openclaw_lane": meta.get("openclaw_lane") or "observe",
        "engines": engines,
        "engines_on": sum(1 for v in engines.values() if v),
        "jobs": jobs,
        "heartbeats": _job_beats(jobs),
        "note": meta.get("note"),
        "mutation_via_openclaw": False,
        "calling_hard_off": True,
    }
    if aid == "anika":
        try:
            from app.marketing import cadence

            s = cadence.stats() or {}
            pkg["cadence"] = {
                "engine_on": bool(s.get("engine_on")),
                "active": s.get("active"),
                "done": s.get("done"),
                "enrolled": s.get("enrolled"),
            }
        except Exception as e:
            pkg["cadence"] = {"error": type(e).__name__}
    if aid == "neha":
        try:
            from app.marketing import journeys

            rules = journeys.list_journeys()
            en = [r for r in rules if r.get("enabled")]
            pkg["journey"] = {
                "engine_on": _flag_on("JOURNEY_ENGINE"),
                "rules_total": len(rules),
                "rules_enabled": len(en),
                "inquiry_enabled": any(
                    r.get("enabled") and r.get("trigger") == "inquiry_received" for r in rules
                ),
            }
        except Exception as e:
            pkg["journey"] = {"error": type(e).__name__}
    return pkg


def _automation_status(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    """GREEN: Automation-Max live board for Owner Copilot."""
    flags = {
        "OPS_WATCHDOG": _flag_on("OPS_WATCHDOG"),
        "CADENCE_ENGINE": _flag_on("CADENCE_ENGINE"),
        "JOURNEY_ENGINE": _flag_on("JOURNEY_ENGINE"),
        "APPROVAL_EMAIL_NOTIFY": _flag_on("APPROVAL_EMAIL_NOTIFY"),
        "AUTOMATION_HEALTH_ALERTS": _flag_on("AUTOMATION_HEALTH_ALERTS"),
        "HOT_QUEUE_BRIEF_DAILY": _flag_on("HOT_QUEUE_BRIEF_DAILY"),
        "AUTO_EMAIL_OUTREACH": _flag_on("AUTO_EMAIL_OUTREACH"),
        "PLATFORM_DIAL_DAILY": _flag_on("PLATFORM_DIAL_DAILY"),
        "WHATSAPP_AUTO_SEND": _flag_on("WHATSAPP_AUTO_SEND"),
        "SALES_AUTOPILOT_ENABLED": _flag_on("SALES_AUTOPILOT_ENABLED"),
        "OPENCLAW_ENABLED": _flag_on("OPENCLAW_ENABLED"),
    }
    agents = []
    for aid in sorted(_AUTOMATION_AGENT_MAP):
        pkg = automation_agent_package(aid) or {}
        agents.append(
            {
                "id": aid,
                "role": pkg.get("role"),
                "engines_on": pkg.get("engines_on"),
                "engines": pkg.get("engines"),
                "jobs": pkg.get("jobs"),
            }
        )

    cadence_stats: dict[str, Any] = {}
    try:
        from app.marketing import cadence

        s = cadence.stats() or {}
        cadence_stats = {
            "engine_on": s.get("engine_on"),
            "active": s.get("active"),
            "done": s.get("done"),
            "enrolled": s.get("enrolled"),
        }
    except Exception as e:
        cadence_stats = {"error": type(e).__name__}

    approval_allowlist: list[str] = []
    try:
        from app.platform import approval_notifier as an

        approval_allowlist = sorted(an.approval_client_allowlist())
    except Exception:
        pass

    flags_off = [
        k
        for k, v in flags.items()
        if not v
        and k
        not in (
            "PLATFORM_DIAL_DAILY",
            "WHATSAPP_AUTO_SEND",
            "SALES_AUTOPILOT_ENABLED",
            "AUTO_EMAIL_OUTREACH",
        )
    ]
    never_off_ok = [
        k
        for k in (
            "PLATFORM_DIAL_DAILY",
            "WHATSAPP_AUTO_SEND",
            "SALES_AUTOPILOT_ENABLED",
        )
        if not flags.get(k)
    ]

    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "phase": "automation_max",
            "flags": flags,
            "safe_flags_off": flags_off,
            "never_correctly_off": never_off_ok,
            "cadence": cadence_stats,
            "approval_email_allowlist": approval_allowlist,
            "automation_agents": agents,
            "calling_hard_off": True,
            "whatsapp_auto_off": not flags.get("WHATSAPP_AUTO_SEND"),
        },
        "evidence": {
            "sources": [
                "env_flags",
                "cadence.stats",
                "approval_notifier.allowlist",
                "job_heartbeats",
            ],
            "actor": actor,
            "correlation_id": correlation_id,
        },
        "next_action": (
            "Owner merge/deploy OpenClaw automation board; human approve pending drafts"
            if flags.get("CADENCE_ENGINE")
            else "CADENCE_ENGINE OFF — Automation-Max Phase-1 incomplete"
        ),
    }


def _automation_agents(
    params: dict[str, Any], *, actor: str, correlation_id: str
) -> dict[str, Any]:
    """GREEN: detailed packages for Automation-Max agents under OpenClaw."""
    want = str(params.get("agent_id") or params.get("agent") or "").strip().lower()
    ids = [want] if want else sorted(_AUTOMATION_AGENT_MAP)
    packages = []
    for aid in ids:
        pkg = automation_agent_package(aid)
        if pkg:
            packages.append({"id": aid, **pkg})
    if want and not packages:
        return {
            "status": "FAILED",
            "verified": True,
            "error": "not an automation-max OpenClaw agent",
            "result": {"known": sorted(_AUTOMATION_AGENT_MAP)},
            "evidence": {"correlation_id": correlation_id, "actor": actor},
            "next_action": "Use anika|kavya|isha|rohan|neha or omit agent_id",
        }
    return {
        "status": "SUCCEEDED",
        "verified": True,
        "result": {
            "count": len(packages),
            "agents": packages,
            "mutation_via_openclaw": False,
        },
        "evidence": {"correlation_id": correlation_id, "actor": actor},
        "next_action": "Pause/resume still AMBER → Owner OS approval",
    }


AUTOMATION_HANDLERS = {
    "automation.status": _automation_status,
    "automation.agents": _automation_agents,
}

__all__ = [
    "AUTOMATION_GREEN",
    "AUTOMATION_HANDLERS",
    "automation_agent_package",
]
