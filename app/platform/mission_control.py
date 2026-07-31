"""Chat-first mission control plane — Owner OS authority, not a 32nd agent.

Converts short owner commands into durable mission packets + append-only ledger.
Does NOT dispatch RED outbound. Executors must prove a real session/job ID or be
marked ``unavailable`` — never fabricate parallelism.

Architecture credit (concepts only, no vendored runtime):
- Awesome Agent Orchestrators catalog patterns (control-plane / loop runners)
- Omnigent-style budget + policy + sandbox ideas
- OpenClaw chat/channel execution as Owner OS edge Copilot
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.file_lock import file_lock

_LEDGER = Path("data/mission_control/ledger.jsonl")
_MISSIONS = Path("data/mission_control/missions")
_IDEM_INDEX = Path("data/mission_control/idempotency_index.json")

# Chat aliases → mission templates (GREEN prep; RED gates listed, not armed).
_CHAT_ALIASES = {
    "launch-ready": "launch_ready",
    "launch ready": "launch_ready",
    "revenue-ready": "revenue_ready",
    "revenue ready": "revenue_ready",
    "income-today": "income_today",
    "income today": "income_today",
    "status": "status",
}

_PROTECTED_OFF = (
    "WHATSAPP_AUTO_SEND",
    "PLATFORM_DIAL_DAILY",
    "REPLY_AUTO_SEND",
    "UPI_AUTO_ACTIVATE",
    "AUTO_EMAIL_OUTREACH",
    "SELF_IMPROVE_LOOP",
)

_TEMPLATES: dict[str, dict[str, Any]] = {
    "launch_ready": {
        "business_outcome": "Core Marketing launch-ready with burn-in + continuous monitoring",
        "priority": 10,
        "lanes": [
            {
                "lane": "cursor_impl",
                "agent": "cursor",
                "role": "implementation",
                "allowed_paths": ["app/", "tests/", "scripts/", "frontend/", "docs/context/"],
                "forbidden_paths": ["app/voice_agent/", "app/telephony/"],
                "acceptance": ["prod_check", "targeted_pytest", "burn_in_20m"],
            },
            {
                "lane": "openclaw_ops",
                "agent": "openclaw",
                "role": "ops_revenue",
                "allowed_paths": ["docs/", "data/mission_control/"],
                "forbidden_paths": ["app/voice_agent/"],
                "acceptance": ["money_path_200", "activation_summary"],
            },
            {
                "lane": "verifier",
                "agent": "opencode_verifier",
                "role": "independent_verify",
                "allowed_paths": ["docs/", "tests/"],
                "forbidden_paths": ["app/"],
                "acceptance": ["sha_parity", "browser_smoke", "no_false_green"],
            },
        ],
        "red_gates_held": list(_PROTECTED_OFF),
        "rollback": "APP_VERSION pin recreate + flag revert",
    },
    "revenue_ready": {
        "business_outcome": "Verified funnel can accept, track, bill, and serve a real customer",
        "priority": 20,
        "lanes": [
            {
                "lane": "cursor_impl",
                "agent": "cursor",
                "role": "funnel_wiring",
                "allowed_paths": ["app/billing/", "app/api/", "frontend/", "tests/"],
                "forbidden_paths": ["app/voice_agent/"],
                "acceptance": ["pricing_start_200", "pay_info_armed", "plans_truth"],
            },
            {
                "lane": "openclaw_ops",
                "agent": "openclaw",
                "role": "crm_hot_queue",
                "allowed_paths": ["docs/", "data/"],
                "forbidden_paths": ["app/telephony/"],
                "acceptance": ["hot_queue_visible", "draft_not_auto_sent"],
            },
            {
                "lane": "verifier",
                "agent": "opencode_verifier",
                "role": "payment_evidence",
                "allowed_paths": ["docs/", "tests/"],
                "forbidden_paths": ["app/"],
                "acceptance": ["no_fake_revenue", "upi_manual_primary"],
            },
        ],
        "red_gates_held": list(_PROTECTED_OFF),
        "rollback": "UPI_AUTO_ACTIVATE stays 0; no live-send",
    },
    "income_today": {
        "business_outcome": "Lawful GREEN prep toward first/next paid conversion today",
        "priority": 30,
        "lanes": [
            {
                "lane": "openclaw_ops",
                "agent": "openclaw",
                "role": "prospect_drafts",
                "allowed_paths": ["docs/", "data/"],
                "forbidden_paths": ["app/telephony/"],
                "acceptance": ["drafts_queued", "owner_approval_required"],
            },
            {
                "lane": "cursor_impl",
                "agent": "cursor",
                "role": "inbox_canary_prep",
                "allowed_paths": ["app/", "tests/", "scripts/"],
                "forbidden_paths": ["app/voice_agent/"],
                "acceptance": ["canary_packet_ready", "no_auto_send"],
            },
            {
                "lane": "verifier",
                "agent": "opencode_verifier",
                "role": "compliance_check",
                "allowed_paths": ["docs/", "tests/"],
                "forbidden_paths": ["app/"],
                "acceptance": ["dnd_intact", "no_cold_wa", "no_dial"],
            },
        ],
        "red_gates_held": list(_PROTECTED_OFF),
        "rollback": "Owner canary only; no bulk outreach",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_dirs() -> None:
    _MISSIONS.mkdir(parents=True, exist_ok=True)
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)


def _load_idem_index() -> dict[str, str]:
    if not _IDEM_INDEX.is_file():
        return {}
    try:
        data = json.loads(_IDEM_INDEX.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_idem_index(index: dict[str, str]) -> None:
    _IDEM_INDEX.parent.mkdir(parents=True, exist_ok=True)
    tmp = _IDEM_INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(_IDEM_INDEX)


def _append_ledger(event: dict[str, Any]) -> None:
    _ensure_dirs()
    row = dict(event)
    row.setdefault("at", _utc())
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with file_lock(_LEDGER):
        with open(_LEDGER, "a", encoding="utf-8") as f:
            f.write(line)


def _write_mission(mission: dict[str, Any]) -> Path:
    _ensure_dirs()
    mid = str(mission["mission_id"])
    path = _MISSIONS / f"{mid}.json"
    with file_lock(path):
        path.write_text(json.dumps(mission, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _read_mission(mission_id: str) -> dict[str, Any] | None:
    path = _MISSIONS / f"{mission_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def probe_executors() -> dict[str, Any]:
    """Prove which executors are callable — never invent remote session IDs."""
    out: dict[str, Any] = {}
    # This process may implement work, but it is NOT a proven Cursor Cloud session.
    out["cursor"] = {
        "status": "manual_local",
        "session_id": None,
        "note": (
            "Super Admin may implement in an isolated worktree; "
            "no automatic Cursor job/session adapter — do not claim READY auto-dispatch"
        ),
        "pid_hint": os.getpid(),
    }
    # OpenClaw = flag + import gate (still no remote session receipt here)
    try:
        from app.integrations.openclaw.policies import openclaw_enabled

        on = bool(openclaw_enabled())
        out["openclaw"] = {
            "status": "flag_on_no_session" if on else "flag_off",
            "session_id": None,
            "note": "Edge Copilot importable when OPENCLAW_ENABLED; no Gateway job ID in this probe",
            "OPENCLAW_ENABLED": on,
        }
    except Exception as e:
        out["openclaw"] = {"status": "unavailable", "session_id": None, "error": type(e).__name__}
    out["opencode_verifier"] = {
        "status": "unavailable",
        "session_id": None,
        "note": "No auto-dispatch adapter; verifier must be invoked explicitly",
    }
    out["claude_codex"] = {
        "status": "unavailable",
        "session_id": None,
        "note": "No auto-dispatch adapter in this wave",
    }
    return out


def parse_chat_command(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    low = raw.lower()
    # pause|resume|approve|rollback <arg>
    m = re.match(r"^(pause|resume|approve|rollback)\s+(.+)$", low)
    if m:
        return {
            "ok": True,
            "verb": m.group(1),
            "arg": m.group(2).strip(),
            "template": None,
            "safety_lane": "AMBER",
        }
    for alias, template in _CHAT_ALIASES.items():
        if low == alias or low.startswith(alias + " "):
            return {
                "ok": True,
                "verb": template if template != "status" else "status",
                "arg": None,
                "template": None if template == "status" else template,
                "safety_lane": "GREEN",
            }
    return {
        "ok": False,
        "error": "unknown_command",
        "hint": "launch-ready | revenue-ready | income-today | status | pause <lane> | resume <lane> | approve <gate> | rollback <mission-id>",
    }


def create_mission(
    template_key: str,
    *,
    actor: str,
    base_sha: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    tmpl = _TEMPLATES.get(template_key)
    if not tmpl:
        return {"ok": False, "error": "unknown_template", "template": template_key}

    key = (idempotency_key or "").strip()
    if not key:
        return {
            "ok": False,
            "error": "idempotency_key_required",
            "hint": "Pass stable idempotency_key to avoid duplicate missions",
        }

    _ensure_dirs()
    # Atomic dedupe: idempotency index under ledger lock (full key space, not scan-cap).
    with file_lock(_LEDGER):
        index = _load_idem_index()
        existing_id = index.get(key)
        if existing_id:
            old = _read_mission(existing_id)
            if old and old.get("state") not in (
                "COMPLETE",
                "CANCELLED",
                "ROLLED_BACK",
            ):
                return {"ok": True, "deduped": True, "mission": old}
            # Terminal / missing — allow re-issue under same key by clearing stale map.
            index.pop(key, None)

        mid = f"msn_{uuid.uuid4().hex[:16]}"
        executors = probe_executors()
        packets = []
        for lane in tmpl["lanes"]:
            ex = executors.get(lane["agent"], {"status": "unavailable", "session_id": None})
            ready = bool(ex.get("session_id")) and ex.get("status") == "available"
            packets.append(
                {
                    "packet_id": f"pkt_{uuid.uuid4().hex[:12]}",
                    "lane": lane["lane"],
                    "agent": lane["agent"],
                    "role": lane["role"],
                    "executor_status": ex.get("status"),
                    "executor_session_id": ex.get("session_id"),
                    "allowed_paths": lane["allowed_paths"],
                    "forbidden_paths": lane["forbidden_paths"],
                    "acceptance_tests": lane["acceptance"],
                    "budget": {
                        "token_max": 200000,
                        "time_minutes": 90,
                        "tool_calls_max": 200,
                    },
                    "retry": {"max": 2, "dlq": "data/mission_control/dlq.jsonl"},
                    "state": "READY" if ready else "MANUAL_OR_UNAVAILABLE",
                }
            )

        mission = {
            "mission_id": mid,
            "schema": "mission-control-v1",
            "template": template_key,
            "business_outcome": tmpl["business_outcome"],
            "priority": tmpl["priority"],
            "state": "CREATED",
            "actor": actor,
            "base_sha": (base_sha or "").strip() or "UNKNOWN",
            "created_at": _utc(),
            "idempotency_key": key,
            "packets": packets,
            "dependencies": [p["packet_id"] for p in packets],
            "red_gates_held": tmpl["red_gates_held"],
            "rollback": tmpl["rollback"],
            "kill_switch": "MISSION_CONTROL_KILL=1 or Owner OS pause",
            "evidence_required": [
                "acceptance_tests_green",
                "sha_parity",
                "provider_or_payment_id_if_claimed",
            ],
            "final_ids": {"commit": None, "pr": None, "deploy": None, "runtime": None},
            "attribution": {
                "concepts": [
                    "https://github.com/andyrewlee/awesome-agent-orchestrators",
                    "https://github.com/omnigent-ai/omnigent",
                    "https://github.com/openclaw/openclaw",
                ],
                "vendored_code": False,
                "note": "Concepts only — repo-native Owner OS / agent_runtime remain authority",
            },
        }
        _write_mission(mission)
        index[key] = mid
        _save_idem_index(index)
        row = {
            "event": "mission_created",
            "mission_id": mid,
            "template": template_key,
            "actor": actor,
            "packets": len(packets),
            "at": _utc(),
            "idempotency_key": key,
        }
        with open(_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"ok": True, "deduped": False, "mission": mission, "executors": executors}


def list_missions(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_dirs()
    rows = []
    for p in sorted(_MISSIONS.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[
        :limit
    ]:
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return rows


def mission_status(mission_id: str | None = None) -> dict[str, Any]:
    executors = probe_executors()
    if mission_id:
        m = _read_mission(mission_id)
        if not m:
            return {"ok": False, "error": "mission_not_found", "mission_id": mission_id}
        return {"ok": True, "mission": m, "executors": executors}
    return {
        "ok": True,
        "missions": list_missions(10),
        "executors": executors,
        "protected_off": {k: os.environ.get(k, "0") for k in _PROTECTED_OFF},
        "soak_policy": "cancelled_as_prelaunch_blocker",
        "launch_gate": "contract_tests + burn_in_20m + synthetic_canary + continuous_monitor",
    }


def apply_amber_action(
    verb: str,
    arg: str,
    *,
    actor: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """AMBER control — parks unless confirm=True (Owner OS explicit)."""
    if not confirm:
        return {
            "ok": True,
            "status": "APPROVAL_REQUIRED",
            "safety_lane": "AMBER",
            "verb": verb,
            "arg": arg,
            "note": "Owner OS confirm=true required; OpenClaw will not mutate",
            "actor": actor,
        }
    if verb == "rollback":
        m = _read_mission(arg)
        if not m:
            return {"ok": False, "error": "mission_not_found", "mission_id": arg}
        m["state"] = "ROLLED_BACK"
        m["rolled_back_at"] = _utc()
        m["rolled_back_by"] = actor
        _write_mission(m)
        _append_ledger({"event": "mission_rolled_back", "mission_id": arg, "actor": actor})
        return {"ok": True, "status": "ROLLED_BACK", "mission": m}
    if verb in ("pause", "resume"):
        _append_ledger({"event": f"lane_{verb}", "lane": arg, "actor": actor, "confirmed": True})
        return {"ok": True, "status": verb.upper() + "D", "lane": arg, "actor": actor}
    if verb == "approve":
        _append_ledger({"event": "gate_approved", "gate": arg, "actor": actor})
        # Never silently arm RED env from chat — record scoped approval only.
        return {
            "ok": True,
            "status": "APPROVAL_RECORDED",
            "gate": arg,
            "note": "RED env flips still require explicit ops script + allowlist; chat cannot arm dial/WA/UPI",
        }
    return {"ok": False, "error": "unknown_verb", "verb": verb}


def handle_chat(
    text: str,
    *,
    actor: str,
    base_sha: str | None = None,
    idempotency_key: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    parsed = parse_chat_command(text)
    if not parsed.get("ok"):
        return parsed
    verb = parsed["verb"]
    if verb == "status":
        return {"ok": True, "verb": "status", **mission_status()}
    if parsed.get("safety_lane") == "AMBER":
        # GREEN chat ingress must NEVER execute AMBER mutations even with confirm=true.
        # Park for dedicated mission.pause/resume/approve/rollback Owner OS path.
        _append_ledger(
            {
                "event": "amber_parked_from_chat",
                "verb": verb,
                "arg": parsed.get("arg"),
                "actor": actor,
                "confirm_ignored": bool(confirm),
            }
        )
        return {
            "ok": True,
            "status": "APPROVAL_REQUIRED",
            "safety_lane": "AMBER",
            "verb": verb,
            "arg": parsed.get("arg"),
            "note": (
                "Parked — use typed Owner OS mission.pause|resume|approve|rollback "
                "with explicit confirm; chat cannot mutate"
            ),
            "actor": actor,
        }
    if parsed.get("template"):
        created = create_mission(
            str(parsed["template"]),
            actor=actor,
            base_sha=base_sha,
            idempotency_key=idempotency_key,
        )
        return {"ok": True, "verb": verb, **created}
    return {"ok": False, "error": "unhandled", "parsed": parsed}


__all__ = [
    "apply_amber_action",
    "create_mission",
    "handle_chat",
    "list_missions",
    "mission_status",
    "parse_chat_command",
    "probe_executors",
]
