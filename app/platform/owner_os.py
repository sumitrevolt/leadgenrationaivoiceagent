"""owner_os.py — Admin/Owner Operating System (production-safe vertical slice).

Canonical workforce = app.platform.team.STAFF (31). `manager` key = display name Boss
(system supervisor + runnable worker — NOT a missing 32nd agent).

HONEST SCOPE:
- Agent pause gates ONLY manual Run-now (agent_controls) — labeled Pause Manual Runs.
- Outbound calling cannot be *enabled from this UI* (use PLATFORM_DIAL_DAILY / data file);
  badge reflects live `platform_dial.enabled()` truth (LIVE vs OFF).
- Safe command intents may execute; high-risk intents stay APPROVAL_REQUIRED.
- Storage: Postgres (Alembic 019) with hardened JSONL fallback (OWNER_OS_STORAGE=jsonl).
- No shell/SQL/arbitrary code execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.platform import owner_os_store as store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Test monkeypatches may still set these; store module paths are authoritative.
_CMD_STORE = store.CMD_STORE
_KILL_STORE = store.KILL_STORE
_AUDIT_STORE = store.AUDIT_STORE


def owner_os_flag_on() -> bool:
    v = (os.getenv("OWNER_OS") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


STATUSES = (
    "DRAFT",
    "VALIDATED",
    "APPROVAL_REQUIRED",
    "READY",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"VALIDATED", "APPROVAL_REQUIRED", "READY", "CANCELLED"}),
    "VALIDATED": frozenset({"APPROVAL_REQUIRED", "READY", "QUEUED", "CANCELLED"}),
    "APPROVAL_REQUIRED": frozenset({"READY", "QUEUED", "CANCELLED", "FAILED"}),
    "READY": frozenset({"QUEUED", "RUNNING", "CANCELLED", "APPROVAL_REQUIRED"}),
    "QUEUED": frozenset({"RUNNING", "CANCELLED", "FAILED"}),
    "RUNNING": frozenset({"SUCCEEDED", "FAILED", "CANCELLED"}),
    "SUCCEEDED": frozenset(),
    "FAILED": frozenset({"QUEUED", "CANCELLED"}),
    "CANCELLED": frozenset({"QUEUED"}),  # retry path only
}

# System supervisors = STAFF keys that also act as control-plane supervisors.
SYSTEM_SUPERVISOR_IDS = frozenset({"manager"})  # display: Boss
# Non-STAFF service identities (queues/workers) — not counted as workforce agents.
SERVICE_IDENTITY_IDS = frozenset({"celery", "scheduler", "voice_stream", "social_drain"})

DEPARTMENT_FOR_PRODUCT = {
    "platform": "Infrastructure and Reliability",
    "voice": "Voice and Calling",
    "marketing": "Marketing and Content",
}

SAFE_INTENTS = {
    "status_report",
    "list_agents",
    "list_approvals",
    "list_kill_switches",
    "pause_agent",
    "resume_agent",
    "training_help",
}

HIGH_RISK_INTENTS = {
    "enable_calling",
    "bulk_email",
    "whatsapp_campaign",
    "social_publish",
    "payment_mutate",
    "customer_delete",
}

# Kill switch → real enforcement points (documented for UI + tests).
KILL_ENFORCEMENT_MATRIX: dict[str, dict[str, Any]] = {
    "platform_dial": {
        "enforcement": ["app.platform.platform_dial.enabled", "PLATFORM_DIAL_DAILY=0"],
        "can_enable_here": False,
        "note": "Owner OS cannot ENABLE dial — arm via PLATFORM_DIAL_DAILY / data file",
    },
    "voice_launch_kill": {
        "enforcement": ["app.telephony.voice_launch.admin_kill_engaged"],
        "can_toggle": True,
    },
    "social_pause": {
        "enforcement": ["app.social_engine.pause.should_pause_job", "emergency_stop"],
        "can_toggle": True,
    },
    "owner_all_agents": {
        "enforcement": ["owner_os.owner_kill_blocks", "owner_os.execute_command"],
        "can_toggle": True,
    },
    "owner_schedulers": {
        "enforcement": [
            "app.tasks.staff_jobs.OwnerSchedulerGuardedTask.apply_async",
            "app.platform.team_scheduler._run_job",
            "owner_os.scheduler_dispatch_allowed",
        ],
        "can_toggle": True,
        "note": (
            "Scheduler dispatch paused. New scheduled jobs will not be queued. "
            "Already queued or running tasks may continue."
        ),
    },
    "owner_publishing": {
        "enforcement": ["app.social_engine.pause.should_pause_job", "owner_os.owner_kill_blocks"],
        "can_toggle": True,
    },
    "owner_bulk_email": {
        "enforcement": ["app.api.admin_dashboard.bulk_email_clients", "owner_os.owner_kill_blocks"],
        "can_toggle": True,
    },
    "owner_whatsapp_outbound": {
        "enforcement": ["app.marketing.whatsapp_campaign.auto_send_enabled gate", "owner_os"],
        "can_toggle": True,
    },
    "owner_payment_mutation": {
        "enforcement": ["owner_os.owner_kill_blocks", "high-risk intent refuse"],
        "can_toggle": True,
    },
}

TRAINING_PAGES = {
    "home": {
        "title": "Owner Home",
        "hinglish": "Yahan se business ka aaj ka pulse dekho — approvals, failed jobs, Hot Queue, agents.",
        "safe_commands": [
            "Sab agents ki current duty batao",
            "Pending approvals dikhao",
            "Jiya ke pending deliverables ka status report banao. Publish mat karna.",
        ],
        "next": "Pehle Attention Queue dekho, phir Commands box se safe order do.",
    },
    "commands": {
        "title": "Owner Command Console",
        "hinglish": "Hinglish me order likho → plan preview dekho → Confirm. High-risk pe automatic block.",
        "safe_commands": [
            "Aaj ke pending approvals dikhao",
            "Isha ko pause karo (sirf manual Run now)",
            "Jiya status report banao, customer message mat bhejna",
        ],
        "next": "Confirm se pehle 'Actions that will NOT run' padho.",
    },
    "agents": {
        "title": "Agent Registry (canonical = 31)",
        "hinglish": (
            "manager = Boss. Pause Manual Runs = sirf Run now. "
            "Isha pe Scheduled Pause / Drain / Stop Claims alag buttons hain."
        ),
        "safe_commands": [
            "Isha ka scheduled dispatch pause karo",
            "Isha ko drain karo",
            "Isha resume karo",
        ],
        "next": "Queued vs running: drain running ko force-kill nahi karta — finish hone do.",
    },
    "workflows": {
        "title": "Workflow Control (read-only aggregator)",
        "hinglish": "Naya scheduler nahi — JOB_META + process_library + health merge. Isha = content + client_content.",
        "safe_commands": ["Isha workflows dikhao"],
        "next": "Enable/disable scheduled job pehle Pause Scheduled / Drain se prove karo.",
    },
    "routes": {
        "title": "OmniRoute Agent Route Matrix",
        "hinglish": "Sirf approved task keys. Credentials kabhi UI me nahi. Route change customer work auto-start nahi karta.",
        "safe_commands": ["Isha route health test (sanitized)"],
        "next": "Arbitrary model string reject — registry se hi primary/fallback.",
    },
    "tasks": {
        "title": "Task Control",
        "hinglish": "Owner commands + recent agent events. Assign/reassign command se.",
        "safe_commands": ["Failed tasks list dikhao"],
        "next": "Retry sirf safe intents pe; calling/email publish yahan se nahi.",
    },
    "approvals": {
        "title": "Approval Center",
        "hinglish": "sales/coordinator/fde decide yahan; content = Open in Mission Control.",
        "safe_commands": ["Pending approvals dikhao"],
        "next": "Same canonical approvals_bridge — Mission Control sync.",
    },
    "kill": {
        "title": "Kill Switches",
        "hinglish": "Calling badge = live platform_dial truth. Social pause / voice kill / owner kills yahan se. Dial ENABLE Owner OS se refuse.",
        "safe_commands": ["Kill switch status dikhao"],
        "next": "Calling ENABLE yahan se intentionally refuse hota hai — env/data-file se arm karo.",
    },
    "training": {
        "title": "Admin Training Mode",
        "hinglish": "Har panel pe 'Teach me' — safe practice commands, risky actions pe warning.",
        "safe_commands": ["Training help dikhao"],
        "next": "Pehle dry-run status report chalao.",
    },
}

PAUSE_SCOPE_NOTE = (
    "Scheduled jobs may continue. Use workflow or scheduler controls to stop scheduled execution."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def calling_posture(*, voice_killed: bool | None = None) -> dict[str, Any]:
    """Honest outbound-calling status for Owner OS UI. Never fabricates.

    Owner OS still refuses ENABLE from this surface — arming stays env/data-file.
    Pass ``voice_killed`` when the caller already evaluated ``admin_kill_status``
    so kill_switch_board snapshots stay single-read.
    """
    live = False
    limit: int | None = None
    try:
        from app.platform import platform_dial as _pd

        live = bool(_pd.enabled())
        try:
            limit = int(_pd.dial_limit())
        except Exception:
            limit = None
    except Exception:
        live = False
    if voice_killed is None:
        try:
            from app.telephony.voice_launch import admin_kill_status

            # Read .engaged explicitly — never bool(status) (AdminKillStatus trap).
            voice_killed = admin_kill_status().engaged is True
        except Exception:
            voice_killed = False
    else:
        voice_killed = voice_killed is True
    effective = bool(live) and not voice_killed
    if effective:
        badge = "Calling LIVE (compliance on)"
        if limit is not None and limit > 0:
            badge = f"Calling LIVE · cap {limit}/run"
        return {
            "live": True,
            "hard_off": False,
            "badge": badge,
            "voice_killed": False,
            "dial_limit": limit,
        }
    if voice_killed:
        return {
            "live": False,
            "hard_off": True,
            "badge": "Calling OFF (voice kill)",
            "voice_killed": True,
            "dial_limit": limit,
        }
    return {
        "live": False,
        "hard_off": True,
        "badge": "Calling OFF",
        "voice_killed": False,
        "dial_limit": limit,
    }


def _sync_store_paths() -> None:
    """Honor test monkeypatches on module-level path constants."""
    store.CMD_STORE = _CMD_STORE
    store.KILL_STORE = _KILL_STORE
    store.AUDIT_STORE = _AUDIT_STORE
    # If tests redirected sidecar paths away from defaults, force JSONL backend.
    if (
        _CMD_STORE != os.path.join("data", "owner_commands.jsonl")
        or _KILL_STORE != os.path.join("data", "owner_kill_switches.jsonl")
        or _AUDIT_STORE != os.path.join("data", "owner_os_audit.jsonl")
    ):
        os.environ["OWNER_OS_STORAGE"] = "jsonl"
        store.reset_storage_mode()


def audit(actor: str, action: str, detail: dict[str, Any] | None = None) -> None:
    _sync_store_paths()
    d = detail or {}
    store.append_audit(
        actor,
        action,
        target=str(
            d.get("target") or d.get("command_id") or d.get("agent_id") or d.get("key") or ""
        )[:120]
        or None,
        tenant_id=d.get("tenant_id"),
        correlation_id=d.get("correlation_id"),
        after_summary=str(d.get("status") or d.get("engaged") or "")[:200] or None,
        meta=d,
    )


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def kill_switch_board() -> dict[str, Any]:
    _sync_store_paths()
    board: dict[str, Any] = {
        "platform_dial": {
            "engaged": True,
            "hard_off": True,
            "source": "env+data",
            "can_enable_here": False,
            **KILL_ENFORCEMENT_MATRIX["platform_dial"],
        },
        "voice_launch_kill": {
            "engaged": False,
            "source": "voice_launch",
            **KILL_ENFORCEMENT_MATRIX["voice_launch_kill"],
        },
        "social_pause": {
            "engaged": False,
            "source": "social_engine",
            **KILL_ENFORCEMENT_MATRIX["social_pause"],
        },
        "owner_all_agents": {
            "engaged": False,
            "source": "owner_kill_switches",
            **KILL_ENFORCEMENT_MATRIX["owner_all_agents"],
        },
        "owner_schedulers": {
            "engaged": False,
            "source": "owner_kill_switches",
            **KILL_ENFORCEMENT_MATRIX["owner_schedulers"],
        },
        "owner_publishing": {
            "engaged": False,
            "source": "owner_kill_switches",
            **KILL_ENFORCEMENT_MATRIX["owner_publishing"],
        },
        "owner_bulk_email": {
            "engaged": False,
            "source": "owner_kill_switches",
            **KILL_ENFORCEMENT_MATRIX["owner_bulk_email"],
        },
        "owner_whatsapp_outbound": {
            "engaged": False,
            "source": "owner_kill_switches",
            **KILL_ENFORCEMENT_MATRIX["owner_whatsapp_outbound"],
        },
        "owner_payment_mutation": {
            "engaged": False,
            "source": "owner_kill_switches",
            **KILL_ENFORCEMENT_MATRIX["owner_payment_mutation"],
        },
    }
    _kill = None
    try:
        from app.telephony.voice_launch import admin_kill_status

        # Evaluate ONCE, then read .engaged explicitly. AdminKillStatus has no
        # __bool__ on purpose: bool(status) would be True even when disengaged,
        # so the board would report "engaged" forever.
        _kill = admin_kill_status()
        board["voice_launch_kill"]["engaged"] = _kill.engaged
        # source/reason turn an ambiguous "false" into an actionable one:
        # ENV_DISENGAGED (someone chose this) reads very differently from
        # MISSING or MALFORMED (we cannot tell, so the kill is held ON).
        board["voice_launch_kill"]["source"] = _kill.source
        board["voice_launch_kill"]["reason"] = _kill.reason
        board["voice_launch_kill"]["can_toggle"] = True
    except Exception:
        _kill = None
    posture = calling_posture(voice_killed=(_kill.engaged is True) if _kill is not None else False)
    try:
        from app.platform import platform_dial as _pd

        enabled = bool(_pd.enabled())
        board["platform_dial"].update(
            {
                "engaged": not enabled,
                "hard_off": not enabled,
                "source": "platform_dial",
                "can_enable_here": False,
                "note": (
                    "LIVE — arm/disarm via PLATFORM_DIAL_DAILY / data file; Owner OS ENABLE refuse"
                    if enabled
                    else "OFF — arm via PLATFORM_DIAL_DAILY / data file; Owner OS ENABLE refuse"
                ),
                "live": bool(posture.get("live")),
            }
        )
    except Exception:
        pass
    try:
        from app.social_engine.pause import emergency_stop_active

        board["social_pause"]["engaged"] = bool(emergency_stop_active())
        board["social_pause"]["can_toggle"] = True
    except Exception:
        pass
    for k, rec in store.kill_map().items():
        if k in board:
            board[k] = {
                **board[k],
                "engaged": bool(rec.get("engaged")),
                "by": rec.get("by") or rec.get("changed_by"),
                "at": rec.get("at"),
                "reason": rec.get("reason"),
                "source": "owner_kill_switches",
                "can_toggle": True,
            }
    board["_matrix"] = KILL_ENFORCEMENT_MATRIX
    board["_calling_badge"] = posture.get("badge") or "Calling OFF"
    return board


def set_kill_switch(key: str, engaged: bool, by: str = "admin", reason: str = "") -> dict[str, Any]:
    _sync_store_paths()
    key = (key or "").strip()
    if key in ("platform_dial", "enable_calling", "outbound_calling"):
        audit(by, "kill_switch_refused", {"key": key, "engaged": engaged})
        return {
            "ok": False,
            "error": (
                "platform_dial Owner OS se ENABLE/DISABLE nahi hota — "
                "PLATFORM_DIAL_DAILY / data/platform_dial.json use karo"
            ),
        }
    allowed = {
        "voice_launch_kill",
        "social_pause",
        "owner_all_agents",
        "owner_schedulers",
        "owner_publishing",
        "owner_bulk_email",
        "owner_whatsapp_outbound",
        "owner_payment_mutation",
    }
    if key not in allowed:
        return {"ok": False, "error": f"unknown kill switch: {key}"}

    if key == "voice_launch_kill":
        try:
            from app.telephony import voice_launch as vl

            if hasattr(vl, "set_kill"):
                vl.set_kill(bool(engaged))
        except Exception as e:
            return {"ok": False, "error": f"voice_launch: {type(e).__name__}"}
    if key == "social_pause":
        try:
            path = os.path.join("data", "social_engine.json")
            data: dict[str, Any] = {}
            if os.path.exists(path):
                try:
                    data = json.loads(open(path, encoding="utf-8").read())
                except Exception:
                    data = {}
            data["emergency_stop"] = bool(engaged)
            data["by"] = (by or "admin")[:80]
            data["reason"] = (reason or "")[:200]
            data["at"] = _now_iso()
            os.makedirs("data", exist_ok=True)
            open(path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            return {"ok": False, "error": f"social_pause: {type(e).__name__}"}

    rec = store.set_kill_record(key, engaged, by=by, reason=reason)
    audit(by, "kill_switch_set", {"key": key, "engaged": bool(engaged), "reason": reason})
    return {"ok": True, **rec}


def owner_kill_blocks(intent: str) -> str | None:
    _sync_store_paths()
    km = store.kill_map()
    if km.get("owner_all_agents", {}).get("engaged") and intent not in (
        "list_kill_switches",
        "training_help",
        "list_agents",
    ):
        return "owner_all_agents kill switch ENGAGED"
    if intent in ("social_publish",) and (
        km.get("owner_publishing", {}).get("engaged")
        or kill_switch_board().get("social_pause", {}).get("engaged")
    ):
        return "publishing kill engaged"
    if intent in ("bulk_email",) and km.get("owner_bulk_email", {}).get("engaged"):
        return "bulk email kill engaged"
    if intent in ("whatsapp_campaign",) and km.get("owner_whatsapp_outbound", {}).get("engaged"):
        return "whatsapp outbound kill engaged"
    if intent in ("payment_mutate",) and km.get("owner_payment_mutation", {}).get("engaged"):
        return "payment mutation kill engaged"
    if intent in ("enable_calling",):
        return "outbound calling Owner OS se ENABLE refuse — use PLATFORM_DIAL_DAILY"
    return None


def kill_engaged(key: str) -> bool:
    """Public helper for real execution paths (social/email/whatsapp)."""
    _sync_store_paths()
    if key == "platform_dial":
        try:
            from app.platform import platform_dial as _pd

            return not bool(_pd.enabled())
        except Exception:
            return True
    if key == "social_pause":
        try:
            from app.social_engine.pause import emergency_stop_active

            return bool(emergency_stop_active())
        except Exception:
            return False
    return store.kill_engaged(key)


def scheduler_dispatch_allowed(
    agent_id: str | None = None, job: str | None = None
) -> tuple[bool, str]:
    """Explicit scheduled-dispatch gate. False = do not enqueue/start new scheduled work.

    Semantics when blocked:
    - new Beat/schedule/run_due dispatches: SKIP (not enqueued / early-return)
    - already queued Celery messages: may still be consumed (worker entry also skips work)
    - currently running tasks: not preemptively killed
    - resume: future cadence continues; no automatic catch-up flood of missed intervals
    Manual per-agent Pause Manual Runs does NOT affect this gate.
    V1.1: per-agent scheduled_pause / drain also block (via owner_agent_execution).
    """
    _sync_store_paths()
    if store.kill_engaged("owner_schedulers"):
        return False, "owner_schedulers_kill_switch"
    if store.kill_engaged("owner_all_agents"):
        return False, "owner_all_agents_kill_switch"
    try:
        from app.platform import owner_agent_execution as oae

        blocked, reason = oae.scheduled_dispatch_blocked(agent_id=agent_id, job=job)
        if blocked:
            return False, reason
    except Exception:
        pass
    return True, ""


def record_scheduler_skip(
    job: str | None,
    reason: str = "owner_schedulers_kill_switch",
    *,
    source: str = "dispatch",
) -> dict[str, Any]:
    """Sanitized skip record + audit (never raises)."""
    job_s = str(job or "")[:64]
    reason_s = str(reason or "owner_schedulers_kill_switch")[:80]
    out = {
        "ok": True,
        "skipped": True,
        "reason": reason_s,
        "job": job_s,
        "source": source[:40],
        "note": (
            "Scheduler dispatch paused. New scheduled jobs will not be queued. "
            "Already queued or running tasks may continue."
        ),
    }
    try:
        audit(
            "system",
            "scheduler_dispatch_skipped",
            {
                "target": job_s or "staff_job",
                "job": job_s,
                "reason": reason_s,
                "source": source,
            },
        )
    except Exception:
        pass
    try:
        from app.platform import automation_health as _ah

        if job_s:
            _ah.record_run(job_s, True, 0.0, note=reason_s)
    except Exception:
        pass
    try:
        from app.platform.automation_log_service import log_event as _log_auto

        if job_s:
            _log_auto(
                client_id="",
                job_type=job_s,
                status="skipped",
                output_summary=reason_s,
                triggered_by="scheduler",
                meta_json={"phase": "skipped", "reason": reason_s, "source": source},
            )
    except Exception:
        pass
    try:
        # Optional metric hook (no-op if registry missing)
        from app.platform import job_metrics

        if hasattr(job_metrics, "incr"):
            job_metrics.incr("owner_schedulers_skipped")
    except Exception:
        pass
    return out


def agent_registry() -> dict[str, Any]:
    """Canonical inventory — separate workforce / supervisors / services / runnable."""
    from app.platform.team import STAFF

    agents: list[dict[str, Any]] = []
    paused: dict[str, Any] = {}
    runnable: set[str] = set()
    members_live: dict[str, Any] = {}
    try:
        from app.platform import agent_controls
        from app.platform.office_hq import RUNNABLE_MEMBERS, room_for_member
        from app.platform.team import team_status

        paused = agent_controls.list_paused()
        runnable = set(RUNNABLE_MEMBERS)
        ts = team_status() or {}
        members_live = {m.get("key"): m for m in (ts.get("members") or [])}
    except Exception:
        from app.platform.office_hq import RUNNABLE_MEMBERS, room_for_member

        runnable = set(RUNNABLE_MEMBERS)

    orphan_runnable = sorted(k for k in runnable if k not in STAFF)
    route_by_key: dict[str, Any] = {}
    try:
        from app.platform.agent_os_routing import agent_route_table

        # agent_route_table() returns dict[agent_key → policy fields], not a list.
        table = agent_route_table() or {}
        if isinstance(table, dict):
            for key, row in table.items():
                route_by_key[str(key)] = row if isinstance(row, dict) else {}
    except Exception:
        pass

    maturity_portfolio: dict[str, Any] = {}
    maturity_by_key: dict[str, dict[str, Any]] = {}
    try:
        from app.platform import agent_maturity

        maturity_portfolio = agent_maturity.portfolio()
        maturity_by_key = {
            str(row.get("agent_id")): row for row in (maturity_portfolio.get("agents") or [])
        }
    except Exception as exc:
        logger.debug("[owner_os] maturity projection unavailable: %s", exc)

    supervisors: list[dict[str, Any]] = []
    for key, meta in STAFF.items():
        live = members_live.get(key) or {}
        product = str(meta.get("product") or "platform")
        room = room_for_member(key, product)
        route = route_by_key.get(key) or {}
        maturity = maturity_by_key.get(key) or {}
        is_supervisor = key in SYSTEM_SUPERVISOR_IDS
        row = {
            "id": key,
            "agent_id": key,
            "name": meta.get("name", key),
            "emoji": meta.get("emoji", "🤖"),
            "title": meta.get("title", ""),
            "department": DEPARTMENT_FOR_PRODUCT.get(product, product),
            "product": product,
            "room": room,
            "responsibility": meta.get("duties", ""),
            "schedule": meta.get("schedule", ""),
            "status": live.get("state") or "offline",
            "today_actions": int(live.get("today_actions") or 0),
            "today_errors": int(live.get("today_errors") or 0),
            "last_activity": live.get("last_activity"),
            "runnable": key in runnable,
            "paused": key in paused,
            "pause_scope": "manual_runs_only",
            "pause_label": "Pause Manual Runs" if key not in paused else "Resume Manual Runs",
            "pause_note": PAUSE_SCOPE_NOTE,
            "is_system_supervisor": is_supervisor,
            "omniroute_eligible": bool(route.get("omniroute_eligible")),
            "requires_human_approval_before_publish": bool(
                route.get("requires_human_approval_before_publish")
            ),
            "queue": route.get("queue") or "celery",
            "risk_level": "high" if product == "voice" else ("medium" if key == "zara" else "low"),
            "approval_level": (
                "human_before_publish"
                if route.get("requires_human_approval_before_publish")
                else "owner_for_high_risk"
            ),
            "enterprise_profile": maturity.get("setup_state") or "unknown",
            "rollout_state": maturity.get("rollout_state") or "unknown",
            "memory_namespace": (maturity.get("memory") or {}).get("namespace") or "",
            "knowledge_namespaces": maturity.get("knowledge") or {},
            "role_skills": (maturity.get("skills") or {}).get("role_specific") or [],
            "coordination_ready": bool((maturity.get("coordination") or {}).get("ready")),
            "coordination_team": (maturity.get("coordination") or {}).get("team") or "",
            "decision_authority": (maturity.get("coordination") or {}).get("decision_authority")
            or "",
            "enterprise_skill_count": len(
                (maturity.get("skills") or {}).get("enterprise_baseline") or []
            ),
            "maturity_problems": maturity.get("problems") or [],
        }
        agents.append(row)
        if is_supervisor:
            supervisors.append(
                {
                    "id": key,
                    "name": meta.get("name", key),
                    "role": "system_supervisor",
                    "note": "Canonical STAFF key; display name Boss. Not a separate 32nd agent.",
                }
            )

    agents.sort(key=lambda a: (a["department"], a["name"]))
    service_identities = [
        {"id": sid, "role": "service_identity", "note": "Not a STAFF workforce agent"}
        for sid in sorted(SERVICE_IDENTITY_IDS)
    ]
    counts = {
        "canonical_agents": len(agents),
        "system_supervisors": len(supervisors),
        "service_identities": len(service_identities),
        "runnable_workers": len([a for a in agents if a.get("runnable")]),
        "paused_manual_runs": len(paused),
        "orphan_runnable_ids": orphan_runnable,
    }
    return {
        "ok": True,
        "staff_count": counts["canonical_agents"],
        "inventory": counts,
        "manager_explanation": (
            "manager is the canonical STAFF key for the agent displayed as Boss. "
            "It is a system supervisor AND a runnable manual-run worker. "
            "It is not a missing 32nd agent — workforce stays 31."
        ),
        "marketing_note": "Docs sometimes say ~32; code truth is 31 STAFF keys (manager=Boss)",
        "agents": agents,
        "system_supervisors": supervisors,
        "service_identities": service_identities,
        "runnable_members": sorted(runnable),
        "paused_count": len(paused),
        "maturity": {
            "ok": maturity_portfolio.get("ok", False),
            "profile_version": maturity_portfolio.get("profile_version"),
            "enterprise_profiles_ready": maturity_portfolio.get("enterprise_profiles_ready", 0),
            "rollout_counts": maturity_portfolio.get("rollout_counts") or {},
            "claim_note": maturity_portfolio.get("claim_note") or "",
            "coordination": maturity_portfolio.get("coordination") or {},
            "problems": maturity_portfolio.get("problems") or [],
        },
        "pause_semantics": {
            "label_pause": "Pause Manual Runs",
            "label_resume": "Resume Manual Runs",
            "scope": "manual_runs_only",
            "note": PAUSE_SCOPE_NOTE,
            "scheduled_dispatch": "not_blocked_by_manual_pause",
            "queued_tasks": "already-queued Celery tasks may still run",
            "running_tasks": "in-flight runs are not preemptively killed",
        },
    }


def approvals_inbox() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    counts = {"pending": 0, "by_source": {}}
    try:
        from app.platform import approvals_bridge

        d = approvals_bridge.list_drafts(include_decided=False) or {}
        counts = d.get("counts") or counts
        for row in d.get("items") or d.get("drafts") or []:
            src = str(row.get("source") or "")
            decidable = src in ("sales", "coordinator", "fde", "owner_os_verification")
            items.append(
                {
                    "source": src,
                    "item_id": row.get("item_id") or row.get("id"),
                    "title": (row.get("title") or row.get("summary") or "")[:160],
                    "risk": row.get("risk") or row.get("risk_tier") or "medium",
                    "status": row.get("status") or "pending",
                    "customer": row.get("client_id") or row.get("customer") or "",
                    "tenant_id": row.get("client_id") or row.get("customer") or "",
                    "requesting_agent": row.get("agent") or row.get("member") or src,
                    "action_type": row.get("action") or row.get("kind") or src,
                    "expected_impact": (row.get("impact") or row.get("summary") or "")[:200],
                    "category": (
                        "internal_verification" if src == "owner_os_verification" else "agent_draft"
                    ),
                    "decidable_here": decidable,
                    "disposable": bool(row.get("disposable") or src == "owner_os_verification"),
                    "no_side_effects": bool(
                        row.get("no_side_effects") or src == "owner_os_verification"
                    ),
                    "ui_state": "operational" if decidable else "view_only",
                    "open_in": None if decidable else "/app/automation#approvals",
                    "open_reason": (
                        None
                        if decidable
                        else "Content/unsupported source — decide in Mission Control (canonical UI)"
                    ),
                }
            )
    except Exception as e:
        logger.debug("[owner_os] approvals_bridge: %s", e)
    try:
        path = os.path.join("data", "content_approvals.jsonl")
        for row in store._read_jsonl(path)[-40:]:
            if str(row.get("status") or "pending") != "pending":
                continue
            items.append(
                {
                    "source": "content",
                    "item_id": row.get("id") or row.get("approval_id"),
                    "title": (row.get("caption") or row.get("title") or "content approval")[:160],
                    "risk": "medium",
                    "status": "pending",
                    "customer": row.get("client_id") or "",
                    "tenant_id": row.get("client_id") or "",
                    "requesting_agent": "zara",
                    "action_type": "content_publish",
                    "expected_impact": "Customer-facing social content",
                    "category": "customer_content",
                    "decidable_here": False,
                    "ui_state": "view_only",
                    "open_in": "/app/automation#approvals",
                    "open_reason": "Customer content publish — Open in Mission Control (no auto-exec from Owner OS)",
                }
            )
    except Exception:
        pass
    # Governed Boss+Second-Brain decisions (same Owner OS surface; no parallel SPA)
    governed_pending = 0
    try:
        from app.platform import boss_decision_governance as _bdg

        gov = _bdg.owner_os_visibility(limit=40) or {}
        governed_pending = int(gov.get("pending") or 0)
        for row in gov.get("items") or []:
            items.append(
                {
                    "source": "boss_decision_governance",
                    "item_id": row.get("decision_id"),
                    "title": row.get("title") or "governed decision",
                    "risk": "high" if row.get("lane") in ("AMBER", "RED") else "medium",
                    "status": row.get("state") or "pending",
                    "customer": row.get("tenant_id") or "",
                    "tenant_id": row.get("tenant_id") or "",
                    "requesting_agent": row.get("agent_id") or "",
                    "action_type": row.get("decision_type") or "governed_decision",
                    "expected_impact": f"lane={row.get('lane')} sha={(row.get('content_sha256') or '')[:12]}",
                    "category": "agent_permission",
                    "decidable_here": bool(row.get("decidable_here")),
                    "ui_state": row.get("ui_state") or "view_only",
                    "open_in": "/app/owner",
                    "open_reason": "Boss+Second-Brain governed decision (hash-bound)",
                }
            )
    except Exception as e:
        logger.debug("[owner_os] boss_decision_governance: %s", e)
    by_source = dict((counts or {}).get("by_source") or {})
    if governed_pending:
        by_source["boss_decision_governance"] = governed_pending
    return {
        "ok": True,
        "pending": int((counts or {}).get("pending") or 0) + governed_pending,
        "by_source": by_source,
        "items": items[:80],
        "categories": [
            "customer_content",
            "social_publishing",
            "outbound_email",
            "whatsapp_message",
            "outbound_calling",
            "payment_billing",
            "agent_permission",
            "workflow_change",
        ],
        "note": "Decisions reuse approvals_bridge.decide + boss_decision_governance visibility. Calling HARD OFF.",
        "bridge": "approvals_bridge",
        "governance": "boss_decision_governance",
    }


def decide_approval(
    source: str,
    item_id: str,
    decision: str,
    actor: str = "admin",
    reason: str = "",
) -> dict[str, Any]:
    """Canonical approval bridge — no second approval system."""
    source = (source or "").strip().lower()
    item_id = (item_id or "").strip()
    decision = (decision or "").strip().lower()
    if source == "content":
        return {
            "ok": False,
            "error": "content approvals are view-only in Owner OS",
            "open_in": "/app/automation#approvals",
            "reason": "Customer publish path — decide in Mission Control",
        }
    if source in ("boss_decision_governance", "governed_decision"):
        # Hash-bound Boss+Second-Brain consumer — flag-gated inside adapter.
        try:
            from app.platform import boss_decision_governance as _bdg

            out = _bdg.owner_os_decide_governed(
                item_id,
                decision=decision,
                actor=actor,
                reason=reason[:200],
            )
            audit(
                actor,
                "governed_decision_decide",
                {
                    "source": "boss_decision_governance",
                    "item_id": item_id,
                    "decision": decision,
                    "ok": bool(out.get("ok")),
                    "error": out.get("error"),
                    "state": out.get("state"),
                },
            )
            return out
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200], "fail_closed": True}
    if decision not in ("approve", "reject", "request_changes"):
        return {"ok": False, "error": "decision must be approve|reject|request_changes"}
    if decision == "request_changes":
        # Bridge only supports approve|reject — map to reject with reason stamp via reject.
        decision = "reject"
        reason = (reason or "request_changes").strip() or "request_changes"
    try:
        from app.platform import approvals_bridge

        out = approvals_bridge.decide(source, item_id, decision, by=actor, reason=reason[:200])
        audit(
            actor,
            "approval_decide",
            {
                "source": source,
                "item_id": item_id,
                "decision": decision,
                "reason": reason[:200],
                "noop": out.get("noop"),
                "status": out.get("status"),
            },
        )
        return out
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}


def create_verification_approval(actor: str = "admin") -> dict[str, Any]:
    """Create disposable internal approval for Owner OS ↔ Mission Control sync proof."""
    from app.platform import approvals_bridge

    out = approvals_bridge.create_verification_approval(
        by=actor,
        title="Owner OS production verification (disposable)",
        note="Internal disposable approval — no publish/email/WA/call/billing/customer mutation",
        ttl_hours=24,
    )
    if out.get("ok"):
        audit(
            actor,
            "approval_verification_created",
            {
                "target": out.get("id"),
                "source": "owner_os_verification",
                "item_id": out.get("id"),
            },
        )
    return out


def task_board() -> dict[str, Any]:
    _sync_store_paths()
    cmds = list_commands(limit=40)
    running = [c for c in cmds if c.get("status") in ("QUEUED", "RUNNING", "READY")]
    failed = [c for c in cmds if c.get("status") == "FAILED"]
    waiting = [c for c in cmds if c.get("status") == "APPROVAL_REQUIRED"]
    done = [c for c in cmds if c.get("status") == "SUCCEEDED"]
    events: list[dict[str, Any]] = []
    try:
        from app.platform.team import recent_events

        for ev in (recent_events(30) if callable(recent_events) else []) or []:
            events.append(
                {
                    "agent": ev.get("agent") or ev.get("member"),
                    "action": ev.get("action") or ev.get("event"),
                    "status": ev.get("status"),
                    "detail": (ev.get("detail") or ev.get("message") or "")[:160],
                    "at": ev.get("at") or ev.get("created_at"),
                }
            )
    except Exception:
        try:
            from app.platform import team

            st = team.team_status() or {}
            for m in st.get("members") or []:
                if m.get("last_activity"):
                    events.append(
                        {
                            "agent": m.get("key"),
                            "action": "last_activity",
                            "status": m.get("state"),
                            "detail": "",
                            "at": m.get("last_activity"),
                        }
                    )
        except Exception:
            pass
    return {
        "ok": True,
        "views": {
            "my_attention": waiting[:20],
            "running": running[:20],
            "waiting_approval": waiting[:20],
            "failed": failed[:20],
            "completed": done[:20],
        },
        "recent_events": events[:30],
        "counts": {
            "running": len(running),
            "waiting_approval": len(waiting),
            "failed": len(failed),
            "completed": len(done),
        },
    }


def _extract_tenant(text: str) -> str | None:
    t = (text or "").lower()
    if "jiya" in t:
        return "jiya-makeover"
    m = re.search(r"client[_\s-]?id[:\s]+([a-z0-9\-_]{3,60})", t)
    if m:
        return m.group(1)
    return None


def _extract_agent(text: str) -> str | None:
    from app.platform.team import STAFF

    t = (text or "").lower()
    for key, meta in STAFF.items():
        name = str(meta.get("name") or "").lower()
        if key in t or (name and name in t):
            return key
    return None


def parse_intent(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    low = raw.lower()
    tenant = _extract_tenant(raw)
    agent = _extract_agent(raw)

    forbidden: list[str] = []
    will_not = [
        "shell/SSH/terminal access",
        "raw SQL",
        "arbitrary Python exec",
        "unrestricted infra changes",
    ]

    intent = "unknown"
    risk = "low"
    approval = False
    actions: list[str] = []
    tools: list[str] = []
    publish_allowed = False
    customer_notify_allowed = False

    if any(x in low for x in ("kill switch", "kill-switch", "emergency stop", "band karo calling")):
        intent = "list_kill_switches"
        actions = ["Show production safety board"]
        tools = ["owner_os.kill_switch_board"]
    elif any(x in low for x in ("training", "sikhao", "teach me", "kaise use")):
        intent = "training_help"
        actions = ["Show Admin Training Mode tips"]
        tools = ["owner_os.training"]
    elif any(x in low for x in ("approval", "approve", "pending approval", "manzoori")):
        intent = "list_approvals"
        actions = ["List pending approvals across bridges"]
        tools = ["approvals_bridge", "content_approvals"]
    elif re.search(r"\b(pause|rok|band)\b", low) and agent:
        intent = "pause_agent"
        actions = [f"Pause Manual Runs for agent '{agent}'"]
        tools = ["agent_controls.pause"]
        risk = "low"
        will_not.append(PAUSE_SCOPE_NOTE)
    elif re.search(r"\b(resume|chalu|unpause)\b", low) and agent:
        intent = "resume_agent"
        actions = [f"Resume Manual Runs for agent '{agent}'"]
        tools = ["agent_controls.resume"]
    elif any(x in low for x in ("sab agents", "all agents", "duty", "workforce", "registry")):
        intent = "list_agents"
        actions = ["Return full 31-agent inventory with supervisor separation"]
        tools = ["team.STAFF", "agent_controls"]
    elif any(
        x in low
        for x in (
            "status report",
            "deliverable",
            "pending post",
            "pending social",
            "report banao",
            "status batao",
        )
    ) or (tenant and "jiya" in low):
        intent = "status_report"
        actions = [
            "Build read-only deliverables/status report for tenant",
            "Mark command SUCCEEDED with evidence JSON",
        ]
        tools = ["marketing.clients_store", "delivery ledger (read)"]
        will_not.extend(
            [
                "content publish",
                "customer WhatsApp/email send",
                "payment capture",
                "outbound calling",
            ]
        )
        publish_allowed = False
        customer_notify_allowed = False
        if not tenant:
            tenant = "jiya-makeover" if "jiya" in low else None
    elif any(
        x in low
        for x in (
            "call chalu",
            "calling enable",
            "enable calling",
            "enable calls",
            "start calling",
            "platform_dial",
            "swara calling on",
        )
    ):
        intent = "enable_calling"
        risk = "critical"
        approval = True
        actions = ["REFUSED — dial ENABLE Owner OS se nahi; PLATFORM_DIAL_DAILY use karo"]
        forbidden.append("enable_calling")
    elif any(x in low for x in ("publish", "post karo", "zara publish", "social pe daalo")):
        intent = "social_publish"
        risk = "high"
        approval = True
        actions = ["Would require Approval Center + SOCIAL gate"]
        will_not.append("auto-publish without owner approve")
    elif any(x in low for x in ("bulk email", "mass email", "saare ko email")):
        intent = "bulk_email"
        risk = "critical"
        approval = True
        actions = ["Blocked pending explicit owner approval path"]
    else:
        intent = "unknown"
        risk = "medium"
        approval = True
        actions = ["Needs clarification — unrecognized intent fails closed"]

    block = owner_kill_blocks(intent)
    if block:
        approval = True
        forbidden.append(block)

    safe = intent in SAFE_INTENTS and not approval and intent != "unknown"
    status = "VALIDATED" if intent != "unknown" else "DRAFT"
    if approval or intent in HIGH_RISK_INTENTS or intent == "unknown":
        status = "APPROVAL_REQUIRED"
    if safe:
        status = "READY"
    if intent == "status_report":
        publish_allowed = False
        customer_notify_allowed = False

    plan_out: dict[str, Any] = {
        "ok": True,
        "original": raw[:2000],
        "intent": intent,
        "normalized": intent,
        "tenant_id": tenant,
        "agent_id": agent,
        "department": None,
        "priority": "normal",
        "risk_level": risk,
        "approval_required": bool(approval) or intent in HIGH_RISK_INTENTS or intent == "unknown",
        "safe_to_execute": safe,
        "publish_allowed": publish_allowed,
        "customer_notify_allowed": customer_notify_allowed,
        "actions": actions,
        "tools": tools,
        "will_not_perform": will_not,
        "forbidden": forbidden,
        "expected_output": "Inspectable evidence object + audit row",
        "status": status,
        "preview_summary": _preview_summary(
            intent, tenant, agent, actions, will_not, risk, publish_allowed, customer_notify_allowed
        ),
    }
    try:
        from app.platform.owner_os_litmus import evaluate_plan_litmus

        litmus = evaluate_plan_litmus(plan_out)
        plan_out["litmus"] = litmus
        plan_out["preview_summary"] = (
            plan_out["preview_summary"]
            + "\nLitmus: "
            + ("PASS" if litmus.get("ok") else "FAIL " + ",".join(litmus.get("failed_must") or []))
        )
    except Exception:
        plan_out["litmus"] = {"ok": True, "enabled": False, "error": "litmus_unavailable"}
    return plan_out


def _preview_summary(
    intent: str,
    tenant: str | None,
    agent: str | None,
    actions: list[str],
    will_not: list[str],
    risk: str,
    publish_allowed: bool = False,
    customer_notify_allowed: bool = False,
) -> str:
    lines = [
        f"Intent: {intent}",
        f"Tenant: {tenant or '—'}",
        f"Agent: {agent or '—'}",
        f"Risk: {risk}",
        f"Publish allowed: {publish_allowed}",
        f"Customer notify allowed: {customer_notify_allowed}",
        "Actions: " + "; ".join(actions[:4]),
        "Will NOT: " + "; ".join(will_not[:4]),
    ]
    return "\n".join(lines)


def list_commands(limit: int = 50) -> list[dict[str, Any]]:
    _sync_store_paths()
    return store.list_commands(limit)


def get_command(command_id: str) -> dict[str, Any] | None:
    _sync_store_paths()
    return store.get_command(command_id)


def create_command(
    text: str,
    actor: str = "admin",
    idempotency_key: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    _sync_store_paths()
    plan = parse_intent(text)
    if idempotency_key:
        existing = store.find_by_idempotency(idempotency_key)
        if existing:
            return _normalize_command_result(
                {"ok": True, "deduped": True, "command": existing, "plan": plan}
            )

    cid = "ocmd_" + uuid.uuid4().hex[:12]
    corr = "corr_" + uuid.uuid4().hex[:12]
    if not idempotency_key:
        idempotency_key = hashlib.sha256(
            f"{actor}|{text.strip().lower()}|{_now_iso()[:13]}".encode()
        ).hexdigest()[:24]

    status = plan["status"]
    if plan["safe_to_execute"] and confirm:
        status = "QUEUED"
    elif plan["safe_to_execute"] and not confirm:
        status = "READY"
    elif plan["approval_required"] or plan["intent"] == "unknown":
        status = "APPROVAL_REQUIRED"

    cmd = {
        "command_id": cid,
        "idempotency_key": idempotency_key,
        "actor": (actor or "admin")[:120],
        "actor_id": (actor or "admin")[:120],
        "original": plan["original"],
        "original_instruction": plan["original"],
        "intent": plan["intent"],
        "normalized_intent": plan["intent"],
        "tenant_id": plan.get("tenant_id"),
        "agent_id": plan.get("agent_id"),
        "priority": "normal",
        "risk_level": plan["risk_level"],
        "approval_required": plan["approval_required"],
        "approval_state": "required" if plan["approval_required"] else "none",
        "parameters": {
            "actions": plan["actions"],
            "tools": plan["tools"],
            "will_not_perform": plan["will_not_perform"],
        },
        "status": status,
        "execution_state": status,
        "progress": 0,
        "retry_count": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "evidence": None,
        "error": None,
        "preview_summary": plan["preview_summary"],
        "publish_allowed": bool(plan.get("publish_allowed")),
        "customer_notify_allowed": bool(plan.get("customer_notify_allowed")),
        "correlation_id": corr,
        "version": 1,
    }
    if plan["intent"] == "status_report":
        cmd["publish_allowed"] = False
        cmd["customer_notify_allowed"] = False

    saved = store.insert_command(cmd)
    # If insert deduped via unique constraint race
    if saved.get("command_id") != cid and saved.get("idempotency_key") == idempotency_key:
        return _normalize_command_result(
            {"ok": True, "deduped": True, "command": saved, "plan": plan}
        )
    audit(
        actor,
        "command_create",
        {
            "command_id": saved.get("command_id") or cid,
            "intent": cmd["intent"],
            "status": status,
            "correlation_id": corr,
            "tenant_id": cmd.get("tenant_id"),
        },
    )
    return _normalize_command_result({"ok": True, "command": saved, "plan": plan})


def _normalize_command_result(out: dict[str, Any]) -> dict[str, Any]:
    """Stable top-level command_id (+ status) while keeping nested ``command`` for legacy.

    Production canary saw adapters reading top-level command_id as null when only
    the nested dictionary shape was present. Do not invent runtime_run_id here —
    a command is not yet a runtime run.
    """
    cmd = out.get("command") if isinstance(out.get("command"), dict) else {}
    cid = out.get("command_id") or (cmd.get("command_id") if cmd else None)
    status = out.get("status") or (cmd.get("status") if cmd else None)
    if cid:
        out["command_id"] = cid
    if status:
        out["status"] = status
    # Compatibility aliases used by some Owner OS / OpenClaw projections.
    if cid and not out.get("id"):
        out["id"] = cid
    return out


def _update_command(command_id: str, **fields: Any) -> dict[str, Any]:
    _sync_store_paths()
    cur = get_command(command_id)
    if not cur:
        return {"ok": False, "error": "command not found"}
    new_status = fields.get("status")
    if new_status and new_status != cur.get("status"):
        if not can_transition(str(cur.get("status")), str(new_status)):
            return {
                "ok": False,
                "error": f"illegal transition {cur.get('status')} → {new_status}",
                "command": cur,
            }
    return store.update_command(command_id, **fields)


def approve_command(command_id: str, actor: str = "admin") -> dict[str, Any]:
    cur = get_command(command_id)
    if not cur:
        return {"ok": False, "error": "command not found"}
    if cur.get("status") in ("QUEUED", "RUNNING", "SUCCEEDED"):
        return {"ok": False, "error": "already approved/executed", "command": cur}
    if cur.get("intent") in HIGH_RISK_INTENTS or cur.get("intent") == "enable_calling":
        return {"ok": False, "error": "this intent cannot be approved for auto-exec in Owner OS v1"}
    plan = parse_intent(str(cur.get("original") or ""))
    if not plan.get("safe_to_execute"):
        return {"ok": False, "error": "not a safe executable intent", "plan": plan}
    out = _update_command(command_id, status="QUEUED", progress=10, approval_state="approved")
    audit(
        actor,
        "command_approve",
        {"command_id": command_id, "correlation_id": cur.get("correlation_id")},
    )
    return out


def cancel_command(command_id: str, actor: str = "admin") -> dict[str, Any]:
    cur = get_command(command_id)
    if not cur:
        return {"ok": False, "error": "command not found"}
    if cur.get("status") in ("SUCCEEDED", "CANCELLED"):
        return {"ok": False, "error": f"cannot cancel from {cur.get('status')}"}
    out = _update_command(command_id, status="CANCELLED", progress=100)
    audit(actor, "command_cancel", {"command_id": command_id})
    return out


def retry_command(command_id: str, actor: str = "admin") -> dict[str, Any]:
    cur = get_command(command_id)
    if not cur:
        return {"ok": False, "error": "command not found"}
    if cur.get("status") not in ("FAILED", "CANCELLED"):
        return {"ok": False, "error": "retry only for FAILED/CANCELLED"}
    out = _update_command(
        command_id,
        status="QUEUED",
        progress=5,
        retry_count=int(cur.get("retry_count") or 0) + 1,
        error=None,
        sanitized_error=None,
    )
    audit(
        actor,
        "command_retry",
        {"command_id": command_id, "retry_count": int(cur.get("retry_count") or 0) + 1},
    )
    return out


def reassign_command(command_id: str, agent_id: str, actor: str = "admin") -> dict[str, Any]:
    from app.platform.team import STAFF

    if agent_id not in STAFF:
        return {"ok": False, "error": "unknown agent"}
    cur = get_command(command_id)
    if not cur:
        return {"ok": False, "error": "command not found"}
    if cur.get("status") in ("RUNNING", "SUCCEEDED"):
        return {"ok": False, "error": "cannot reassign after execution started/completed"}
    out = _update_command(command_id, agent_id=agent_id, assigned_agent_id=agent_id)
    audit(actor, "command_reassign", {"command_id": command_id, "agent_id": agent_id})
    return out


def _build_status_report(tenant_id: str) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "tenant_id": tenant_id,
        "publish": False,
        "customer_notify": False,
        "publish_allowed": False,
        "customer_notify_allowed": False,
        "profile": {},
        "pending_approvals": 0,
        "notes": [],
    }
    try:
        from app.marketing.clients_store import get_client

        c = get_client(tenant_id) or {}
        evidence["profile"] = {
            "client_id": c.get("client_id") or tenant_id,
            "business_name": c.get("business_name"),
            "plan": c.get("plan"),
            "status": c.get("status"),
            "product": c.get("product"),
            "onboarding_status": c.get("onboarding_status") or c.get("setup_status"),
        }
    except Exception as e:
        evidence["notes"].append(f"clients_store: {type(e).__name__}")
    try:
        path = os.path.join("data", "content_approvals.jsonl")
        n = 0
        for row in store._read_jsonl(path):
            if (
                str(row.get("client_id") or "") == tenant_id
                and str(row.get("status") or "pending") == "pending"
            ):
                n += 1
        evidence["pending_approvals"] = n
    except Exception:
        pass
    try:
        ledger = os.path.join("data", "delivery_ledger", f"{tenant_id}.jsonl")
        events = store._read_jsonl(ledger)
        evidence["delivery_ledger_events"] = len(events)
        evidence["delivery_ledger_tail"] = [
            {
                "at": e.get("at") or e.get("ts"),
                "event": e.get("event") or e.get("type"),
                "ok": e.get("ok"),
            }
            for e in events[-8:]
        ]
    except Exception:
        evidence["delivery_ledger_events"] = 0
    evidence["notes"].append(
        "Read-only report — no publish, no customer message, no payment mutation"
    )
    return evidence


def execute_command(command_id: str, actor: str = "admin") -> dict[str, Any]:
    _sync_store_paths()
    cur = get_command(command_id)
    if not cur:
        return {"ok": False, "error": "command not found"}
    if cur.get("status") == "SUCCEEDED":
        return {
            "ok": True,
            "deduped": True,
            "command": cur,
            "note": "already succeeded — no re-exec",
        }
    if cur.get("status") not in ("READY", "QUEUED"):
        return {"ok": False, "error": f"cannot execute from status {cur.get('status')}"}

    intent = str(cur.get("intent") or "")
    block = owner_kill_blocks(intent)
    if block:
        _update_command(
            command_id, status="FAILED", error=block, sanitized_error=block, progress=100
        )
        return {"ok": False, "error": block}

    if intent not in SAFE_INTENTS:
        return {"ok": False, "error": "intent not safe for Owner OS v1 execution"}

    # ADR-155 litmus — deterministic HITL preflight (flag OWNER_OS_LITMUS, default ON).
    try:
        from app.platform.owner_os_litmus import gate_execute

        plan = parse_intent(str(cur.get("original") or ""))
        gated = gate_execute(cur, plan)
        if not gated.get("ok"):
            reason = str(gated.get("reason") or "litmus_failed")
            _update_command(
                command_id,
                status="FAILED",
                error=reason,
                sanitized_error=reason,
                progress=100,
                evidence={"litmus": gated.get("litmus")},
            )
            audit(
                actor,
                "command_litmus_blocked",
                {"command_id": command_id, "reason": reason},
            )
            return {"ok": False, "error": reason, "litmus": gated.get("litmus")}
    except Exception:
        pass

    # Safe reports always force publish/notify off
    if intent == "status_report":
        _update_command(command_id, publish_allowed=False, customer_notify_allowed=False)

    started = _update_command(command_id, status="RUNNING", progress=30)
    if not started.get("ok"):
        return started

    try:
        evidence: dict[str, Any] = {"intent": intent}
        if intent == "status_report":
            tenant = str(cur.get("tenant_id") or "jiya-makeover")
            evidence = _build_status_report(tenant)
            if not cur.get("agent_id"):
                _update_command(command_id, agent_id="isha", assigned_agent_id="isha")
        elif intent == "list_agents":
            evidence = {"registry": agent_registry()}
        elif intent == "list_approvals":
            evidence = approvals_inbox()
        elif intent == "list_kill_switches":
            evidence = kill_switch_board()
        elif intent == "training_help":
            evidence = {"pages": TRAINING_PAGES}
        elif intent == "pause_agent":
            from app.platform import agent_controls
            from app.platform.office_hq import RUNNABLE_MEMBERS

            agent = str(cur.get("agent_id") or "")
            if agent not in RUNNABLE_MEMBERS:
                raise ValueError(
                    f"agent '{agent}' is not in RUNNABLE_MEMBERS (Pause Manual Runs N/A)"
                )
            evidence = agent_controls.pause(agent, by=actor, note="owner_os Pause Manual Runs")
            evidence["pause_label"] = "Pause Manual Runs"
            evidence["pause_note"] = PAUSE_SCOPE_NOTE
        elif intent == "resume_agent":
            from app.platform import agent_controls

            agent = str(cur.get("agent_id") or "")
            evidence = agent_controls.resume(agent, by=actor)
            evidence["pause_label"] = "Resume Manual Runs"
        else:
            raise ValueError(f"unhandled safe intent: {intent}")

        out = _update_command(
            command_id,
            status="SUCCEEDED",
            progress=100,
            evidence=evidence,
            error=None,
            sanitized_error=None,
        )
        audit(
            actor,
            "command_execute",
            {
                "command_id": command_id,
                "intent": intent,
                "status": "SUCCEEDED",
                "correlation_id": cur.get("correlation_id"),
                "tenant_id": cur.get("tenant_id"),
            },
        )
        return out
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
        out = _update_command(
            command_id, status="FAILED", progress=100, error=err, sanitized_error=err
        )
        audit(
            actor,
            "command_execute",
            {
                "command_id": command_id,
                "intent": intent,
                "status": "FAILED",
                "correlation_id": cur.get("correlation_id"),
            },
        )
        return out


def run_now(text: str, actor: str = "admin", idempotency_key: str | None = None) -> dict[str, Any]:
    plan = parse_intent(text)
    created = create_command(
        text, actor=actor, idempotency_key=idempotency_key, confirm=plan.get("safe_to_execute")
    )
    cmd = created.get("command") or {}
    if created.get("deduped") and cmd.get("status") == "SUCCEEDED":
        return {
            "ok": True,
            "plan": plan,
            "created": created,
            "executed": {"ok": True, "command": cmd, "deduped": True},
        }
    if plan.get("safe_to_execute") and cmd.get("command_id"):
        if cmd.get("status") not in ("QUEUED", "READY"):
            _update_command(cmd["command_id"], status="QUEUED", progress=5)
        executed = execute_command(cmd["command_id"], actor=actor)
        return {"ok": True, "plan": plan, "created": created, "executed": executed}
    return {
        "ok": True,
        "plan": plan,
        "created": created,
        "executed": None,
        "note": "Confirm/approve required before execution",
    }


def owner_home() -> dict[str, Any]:
    reg = agent_registry()
    appr = approvals_inbox()
    kills = kill_switch_board()
    tasks = task_board()
    agents = reg.get("agents") or []
    inv = reg.get("inventory") or {}
    working = [a for a in agents if a.get("status") == "working"]
    paused = [a for a in agents if a.get("paused")]
    attention: list[dict[str, Any]] = []
    if appr.get("pending"):
        attention.append(
            {
                "kind": "approvals",
                "title": f"{appr['pending']} pending approvals",
                "href": "/app/owner#approvals",
                "priority": "high",
            }
        )
    if kills.get("platform_dial", {}).get("hard_off"):
        attention.append(
            {
                "kind": "safety",
                "title": "Outbound calling OFF",
                "href": "/app/owner#kill",
                "priority": "info",
            }
        )
    elif kills.get("platform_dial", {}).get("live") or not kills.get("platform_dial", {}).get(
        "hard_off"
    ):
        # live when hard_off is false
        if not kills.get("platform_dial", {}).get("hard_off"):
            attention.append(
                {
                    "kind": "safety",
                    "title": "Calling LIVE — DND/TRAI/AI-disclosure gates on call path",
                    "href": "/app/dialer",
                    "priority": "info",
                }
            )
    if tasks["counts"]["failed"]:
        attention.append(
            {
                "kind": "failed",
                "title": f"{tasks['counts']['failed']} failed owner commands",
                "href": "/app/owner#tasks",
                "priority": "high",
            }
        )
    # Speed-to-lead SLA (world-class <5 min median) — red when breached.
    stl_badge = "Speed-to-lead: Unknown"
    try:
        from app.platform import speed_to_lead as _stl

        stl = _stl.summary(30) or {}
        if stl.get("ok") and stl.get("touched"):
            med = float(stl.get("median_seconds") or 0)
            u5 = stl.get("under_5min_pct")
            stl_badge = f"Speed-to-lead median {med / 60:.1f}m · <5min {u5}%"
            if not stl.get("sla_5min_ok"):
                attention.append(
                    {
                        "kind": "speed_to_lead",
                        "title": f"SLA red — median {med / 60:.1f} min (>5 min). Hot Queue check karo.",
                        "href": "/app/inbox",
                        "priority": "high",
                    }
                )
            else:
                attention.append(
                    {
                        "kind": "speed_to_lead",
                        "title": f"SLA green — {u5}% under 5 min",
                        "href": "/app/automation#clientops",
                        "priority": "info",
                    }
                )
        elif stl.get("ok"):
            stl_badge = "Speed-to-lead: no touched inquiries (30d)"
    except Exception:
        pass
    # Unpaid converted chase
    try:
        from app.platform.sales_autopilot import store as _sap

        unpaid_n = sum(
            1
            for r in _sap.list_prospects(limit=500)
            if r.get("status") == _sap.STATUS_AWAITING_PAYMENT
        )
        if unpaid_n:
            attention.append(
                {
                    "kind": "unpaid_converted",
                    "title": f"{unpaid_n} converted awaiting payment (ledger proof missing)",
                    "href": "/app/inbox",
                    "priority": "high",
                }
            )
    except Exception:
        pass
    attention.append(
        {
            "kind": "hot_queue",
            "title": "Hot Queue / Inbox check karo",
            "href": "/app/inbox",
            "priority": "medium",
        }
    )
    posture = calling_posture()
    return {
        "ok": True,
        "owner_os_flag": owner_os_flag_on(),
        "storage_mode": store.storage_mode(),
        "generated_at": _now_iso(),
        "staff_count": reg.get("staff_count"),
        "inventory": inv,
        "manager_explanation": reg.get("manager_explanation"),
        "workforce": {
            "total": inv.get("canonical_agents", len(agents)),
            "canonical_agents": inv.get("canonical_agents", len(agents)),
            "system_supervisors": inv.get("system_supervisors", 0),
            "service_identities": inv.get("service_identities", 0),
            "runnable_workers": inv.get("runnable_workers", 0),
            "working": len(working),
            "paused_manual_run": len(paused),
            "runnable": len(reg.get("runnable_members") or []),
        },
        "pause_semantics": reg.get("pause_semantics"),
        "calling_badge": posture.get("badge") or "Calling OFF",
        "calling_live": bool(posture.get("live")),
        "speed_to_lead_badge": stl_badge,
        "attention": attention,
        "approvals_pending": appr.get("pending"),
        "kill_switches": {
            k: {"engaged": v.get("engaged"), "hard_off": v.get("hard_off")}
            for k, v in kills.items()
            if not str(k).startswith("_")
        },
        "tasks": tasks["counts"],
        "recent_commands": list_commands(8),
        "recommended": [
            {
                "label": "Jiya status report (safe)",
                "command": "Jiya ke pending deliverables ka status report banao. Koi content publish ya customer message mat bhejna.",
            },
            {"label": "Pending approvals", "command": "Pending approvals dikhao"},
            {"label": "Kill switch board", "command": "Kill switch status dikhao"},
        ],
        "links": {
            "inbox": "/app/inbox",
            "office": "/app/office",
            "automation": "/app/automation",
            "control_center": "/app/control-center",
            "admin": "/app/admin",
        },
    }


def workflow_registry() -> dict[str, Any]:
    """Read-only join of scheduler jobs + process library — no second scheduler."""
    items: list[dict[str, Any]] = []
    try:
        from app.platform import scheduler_config

        for j in scheduler_config.list_jobs().get("jobs") or []:
            owner = str(j.get("owner") or "")
            items.append(
                {
                    "workflow_id": j.get("job"),
                    "kind": "scheduled_job",
                    "business_purpose": j.get("label"),
                    "owner_department": DEPARTMENT_FOR_PRODUCT.get(
                        "marketing" if owner == "isha" else "platform", "platform"
                    ),
                    "participating_agents": [owner] if owner else [],
                    "tenant_scope": "global",
                    "enabled": j.get("enabled"),
                    "kill_switch_state": (
                        "owner_schedulers" if kill_engaged("owner_schedulers") else "clear"
                    ),
                    "schedule": j.get("cadence"),
                    "last_run": j.get("last_run"),
                    "next_run": None,
                    "status": j.get("status"),
                    "external_side_effects": (
                        "social_publish_possible"
                        if j.get("job") == "social_drain"
                        else "internal_or_draft"
                    ),
                }
            )
    except Exception as e:
        logger.debug("[owner_os] workflow jobs: %s", e)
    try:
        from app.agents import process_library

        for p in process_library.list_processes() or []:
            items.append(
                {
                    "workflow_id": p.get("key"),
                    "kind": "process",
                    "business_purpose": p.get("name"),
                    "owner_department": (
                        "Marketing and Content" if p.get("key") == "client_content" else "Platform"
                    ),
                    "participating_agents": ["isha"] if p.get("key") == "client_content" else [],
                    "tenant_scope": "per_run_inputs.client_id",
                    "enabled": True,
                    "schedule": "on_demand",
                    "approvals": "breakpoint_human_review",
                    "external_side_effects": "none_until_breakpoint",
                }
            )
    except Exception as e:
        logger.debug("[owner_os] workflow processes: %s", e)
    return {
        "ok": True,
        "count": len(items),
        "workflows": items,
        "note": "Aggregator only — state remains in scheduler_config / process_engine / automation_health.",
    }


def workflow_detail(workflow_id: str) -> dict[str, Any]:
    wid = str(workflow_id or "").strip()
    if not wid:
        return {"ok": False, "error": "workflow_id required"}
    reg = workflow_registry()
    hit = next((w for w in reg.get("workflows") or [] if w.get("workflow_id") == wid), None)
    if not hit:
        return {"ok": False, "error": "not found"}
    # Attach Isha control + route when relevant.
    extra: dict[str, Any] = {}
    agents = hit.get("participating_agents") or []
    if "isha" in agents or wid in (
        "content",
        "blog",
        "afternoon_content",
        "weekly_marketing",
        "social_drain",
        "client_content",
    ):
        try:
            from app.platform import owner_agent_execution as oae

            extra["agent_control"] = oae.control_view("isha")
            extra["task_counts"] = oae.task_counts_for_agent("isha")
        except Exception:
            pass
        try:
            from app.platform.agent_os_routing import get_agent_policy

            p = get_agent_policy("isha", "marketing")
            extra["current_model_routes"] = {
                "primary": p.omniroute_task,
                "privacy_class": p.privacy_class,
                "timeout_seconds": p.timeout_seconds,
            }
        except Exception:
            pass
    return {"ok": True, "workflow": {**hit, **extra}}


def route_matrix() -> dict[str, Any]:
    """Agent × work-type × approved OmniRoute mapping — secret-free."""
    rows: list[dict[str, Any]] = []
    try:
        from app.platform.agent_os_routing import agent_route_table
        from app.platform.omniroute_client import _TASK_ROUTES, agents_enabled, omniroute_available

        table = agent_route_table() or {}
        for agent_key, pol in table.items():
            task = pol.get("omniroute_task")
            route = _TASK_ROUTES.get(task) if task else None
            rows.append(
                {
                    "agent": agent_key,
                    "work_type": pol.get("category"),
                    "primary_route": route.primary_model if route else None,
                    "fallback_route": route.fallback_model if route else None,
                    "task_type": task,
                    "timeout": pol.get("timeout_seconds"),
                    "latency_target": 1500 if agent_key == "swara" else 5000,
                    "privacy_class": pol.get("privacy_class"),
                    "cost_class": "low_cost" if pol.get("may_use_free_models") else "premium",
                    "health": (
                        "eligible" if pol.get("omniroute_eligible") else "forbidden_or_local"
                    ),
                    "last_route_used": None,
                }
            )
        health = {
            "omniroute_available": bool(omniroute_available()),
            "agents_hook_armed": bool(agents_enabled()),
            "api_key_present": bool(os.getenv("OMNIROUTE_API_KEY")),
            # Never return key material.
        }
    except Exception as e:
        logger.debug("[owner_os] route_matrix: %s", e)
        health = {"error": type(e).__name__}
    dumped = json.dumps({"rows": rows, "health": health})
    if "sk-" in dumped.lower() or "Bearer " in dumped:
        return {"ok": False, "error": "secret_leak_prevented"}
    return {
        "ok": True,
        "rows": rows,
        "health": health,
        "policies": [
            "Swara requires low-latency conversational route (leadgen.swara_live).",
            "Routine drafts prefer low-cost approved routes.",
            "Customer data must be masked; credentials never returned.",
            "Arbitrary provider/model strings are rejected.",
            "Route changes do not auto-start customer work.",
        ],
    }


async def route_health_test(
    *,
    task_type: str = "leadgen.agent_ops",
    prompt: str = "Reply with exactly: OWNER_OS_ROUTE_OK",
    actor: str = "admin",
) -> dict[str, Any]:
    """Sanitized non-customer OmniRoute probe via approved registry only."""
    from app.platform.omniroute_client import _TASK_ROUTES, generate, omniroute_available
    from app.platform.safe_ai_payload import SafePayloadError

    tt = str(task_type or "").strip()
    if tt not in _TASK_ROUTES:
        return {"ok": False, "error": "task_not_in_approved_registry", "task_type": tt}
    route = _TASK_ROUTES[tt]
    if route.privacy_class not in ("INTERNAL_SANITIZED",):
        return {
            "ok": False,
            "error": "privacy_class_not_allowed_for_owner_os_probe",
            "privacy_class": route.privacy_class,
        }
    # Block prompts that look like customer PII.
    low = (prompt or "").lower()
    if any(x in low for x in ("@gmail", "+91", "jiya", "customer", "whatsapp", "upi")):
        return {"ok": False, "error": "prompt_looks_like_customer_data"}
    audit(actor, "omniroute_route_health_test", {"task_type": tt, "started": True})
    if not omniroute_available():
        return {
            "ok": True,
            "skipped": True,
            "reason": "omniroute_unavailable",
            "task_type": tt,
            "primary_route": route.primary_model,
            "fallback_route": route.fallback_model,
            "note": "Gateway/key absent — fail-open; no customer impact.",
            "secrets_returned": False,
        }
    try:
        result = await generate(
            tt,
            [{"role": "user", "content": prompt}],
            route.privacy_class,
            agent_key="isha" if tt == "leadgen.agent_ops" else None,
        )
    except SafePayloadError as e:
        return {"ok": False, "error": f"safe_payload:{e}", "secrets_returned": False}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "secrets_returned": False}
    out = {
        "ok": True,
        "task_type": tt,
        "primary_route": route.primary_model,
        "fallback_route": route.fallback_model,
        "provider": getattr(result, "provider", None) if result else None,
        "model": getattr(result, "model", None) if result else None,
        "latency_ms": getattr(result, "latency_ms", None) if result else None,
        "fallback_reason": getattr(result, "fallback_reason", None) if result else None,
        "reply_preview": ((result.text or "")[:80] if result else None),
        "gateway_miss": result is None,
        "secrets_returned": False,
        "customer_work_started": False,
    }
    audit(
        actor, "omniroute_route_health_test", {"task_type": tt, "ok": True, "miss": result is None}
    )
    return out


def training(page: str = "home") -> dict[str, Any]:
    p = TRAINING_PAGES.get((page or "home").lower()) or TRAINING_PAGES["home"]
    return {"ok": True, "page": page, **p, "all_pages": list(TRAINING_PAGES.keys())}


def recent_audit(limit: int = 40) -> list[dict[str, Any]]:
    _sync_store_paths()
    return store.recent_audit(limit)
