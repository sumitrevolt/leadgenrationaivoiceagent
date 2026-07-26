"""Risk classification, path ownership and refusal rules for external missions.

Authority model (unchanged by this module):
  * Owner OS = sole action authority. AMBER missions park for owner decision.
  * RED intents are refused at creation and can never be resurrected.
  * Protected runtime areas (voice/Swara, telephony, secrets, billing writes)
    are never assignable to an external executor mission.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass

FLAG = "EXTERNAL_AGENT_ORCHESTRATOR"

#: Intents that are refused outright — no flag, env var or param may enable them.
RED_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\b(enable|turn\s*on|arm)\b.{0,40}\b(calling|dialer|platform[_\s-]?dial|outbound\s*call)",
        "calling enablement",
    ),
    (r"\bplatform_dial_daily\s*=\s*[1-9]", "calling enablement"),
    (r"\b(force[-\s]?merge|merge\s*--admin|admin\s*merge\s*bypass)", "force merge"),
    (
        r"\b(bypass|disable|relax|remove)\b.{0,40}\b(branch\s*protection|required\s*check|status\s*check)",
        "branch-protection bypass",
    ),
    (
        r"\b(drop|truncate|delete)\b.{0,30}\b(table|database|prod(uction)?\s*db)",
        "production database destruction",
    ),
    (
        r"\b(print|echo|expose|leak|paste)\b.{0,30}\b(secret|api[_\s-]?key|token|password|\.env)",
        "secret exposure",
    ),
    (
        r"\b(bulk|mass|blast)\b.{0,30}\b(whatsapp|sms|outreach|campaign|send)",
        "uncontrolled bulk outreach",
    ),
    (
        r"\b(git\s+reset\s+--hard|git\s+clean\s+-[a-z]*f|push\s+--force|force\s+push)",
        "destructive git operation",
    ),
    (
        r"\b(disable|remove|skip)\b.{0,40}\b(dnd|consent|compliance|safety\s*gate|audit)",
        "safety/compliance gate removal",
    ),
    (r"\b(rm\s+-rf|shutdown|format\s+c:)", "destructive shell"),
)

#: Intents that may be *prepared* automatically but need Owner OS / owner sign-off.
AMBER_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(deploy|release|rollout|prod(uction)?\s*ship)", "deployment"),
    (r"\b(migration|alembic|schema\s*change)", "database migration"),
    (r"\b(billing|invoice|price|pricing|subscription|refund)", "billing change"),
    (
        r"\b(customer\s*(message|email|whatsapp|sms)|outreach\s*send|notify\s*customer)",
        "customer messaging",
    ),
    (
        r"\b(secret|api[_\s-]?key|credential|\.env|environment\s*variable|flag\s*flip)",
        "secrets/configuration change",
    ),
    (r"\b(webhook|third[-\s]?party|external\s*api\s*(write|mutate))", "external system mutation"),
    (
        r"\b(scheduler|celery\s*beat|cron|agent\s*loop)\b.{0,30}\b(change|modify|add|enable)",
        "workflow behaviour change",
    ),
    (
        r"\b(upgrade|bump)\b.{0,30}\b(dependency|dependencies|requirements|lock)",
        "dependency upgrade",
    ),
)

#: Repo areas an external mission may never own (frozen / compliance-critical).
PROTECTED_PATH_PREFIXES: tuple[str, ...] = (
    ".env",
    ".github/workflows/deploy",
    "alembic/versions",
    "app/billing/",
    "app/telephony/",
    "app/voice_agent/",
    "data/voice_gemini_keys.json",
    "docker-compose.vps.yml",
)

_ALWAYS_PROHIBITED = tuple(PROTECTED_PATH_PREFIXES)


def orchestrator_enabled() -> bool:
    """Master kill-switch. Default OFF — fail closed."""
    return (os.getenv(FLAG) or "0").strip().lower() in ("1", "true", "yes", "on")


def _match(patterns: tuple[tuple[str, str], ...], text: str) -> str:
    low = (text or "").lower()
    for pattern, label in patterns:
        if re.search(pattern, low):
            return label
    return ""


def classify_intent(text: str) -> tuple[RiskClass, str]:
    """Classify free text into a risk lane. Unknown-but-clean text = GREEN."""
    red = _match(RED_PATTERNS, text)
    if red:
        return RiskClass.RED, red
    amber = _match(AMBER_PATTERNS, text)
    if amber:
        return RiskClass.AMBER, amber
    return RiskClass.GREEN, "no elevated-risk signal"


def classify_mission_request(
    *, title: str, description: str = "", declared: RiskClass | str | None = None
) -> dict[str, Any]:
    """Registry-wins classification: a caller may escalate, never de-escalate."""
    detected, reason = classify_intent(f"{title}\n{description}")
    claimed = RiskClass(declared) if declared else None
    order = {RiskClass.GREEN: 0, RiskClass.AMBER: 1, RiskClass.RED: 2}
    effective = detected
    mismatch = False
    if claimed is not None and claimed != detected:
        mismatch = True
        effective = claimed if order[claimed] > order[detected] else detected
    return {
        "risk_class": effective,
        "detected": detected,
        "claimed": claimed,
        "risk_class_mismatch": mismatch,
        "reason": reason,
    }


def refuse_red(title: str, description: str = "") -> dict[str, Any] | None:
    """Return a refusal payload when the request is RED; else None."""
    risk, reason = classify_intent(f"{title}\n{description}")
    if risk is not RiskClass.RED:
        return None
    return {
        "accepted": False,
        "refused": True,
        "risk_class": RiskClass.RED.value,
        "reason": reason,
        "next_action": "Owner OS / documented admin runbook use karo — no bypass exists",
    }


def normalise_prohibited(paths: list[str] | None) -> list[str]:
    out = list(paths or [])
    for p in _ALWAYS_PROHIBITED:
        if p not in out:
            out.append(p)
    return out


def path_violations(mission: Mission, changed_paths: list[str]) -> list[str]:
    """Paths outside the mission's declared ownership (scope breach evidence)."""
    bad: list[str] = []
    allowed = mission.allowed_paths
    prohibited = normalise_prohibited(mission.prohibited_paths)
    for raw in changed_paths or []:
        p = str(raw).strip().replace("\\", "/").lstrip("./")
        if not p:
            continue
        if any(p == q or p.startswith(q.rstrip("/") + "/") or p.startswith(q) for q in prohibited):
            bad.append(p)
            continue
        if allowed and not any(p == a or p.startswith(a.rstrip("/") + "/") for a in allowed):
            bad.append(p)
    return sorted(set(bad))


def ownership_conflict(mission: Mission, others: list[Mission]) -> dict[str, Any]:
    """Cursor/Claude overlap prevention across live missions."""
    live = [
        m
        for m in others
        if m.mission_id != mission.mission_id
        and m.status
        not in {
            MissionState.COMPLETE,
            MissionState.CANCELLED,
            MissionState.FAILED_TERMINAL,
            MissionState.ROLLED_BACK,
        }
    ]
    mine = set(mission.allowed_paths)
    for other in live:
        clash = sorted(mine & set(other.allowed_paths))
        if clash:
            return {"conflict": True, "kind": "paths", "with": other.mission_id, "paths": clash}
        if mission.branch and mission.branch == other.branch:
            return {
                "conflict": True,
                "kind": "branch",
                "with": other.mission_id,
                "branch": mission.branch,
            }
        if mission.worktree and mission.worktree == other.worktree:
            return {
                "conflict": True,
                "kind": "worktree",
                "with": other.mission_id,
                "worktree": mission.worktree,
            }
    return {"conflict": False}


def approval_required(mission: Mission, target: MissionState) -> bool:
    """AMBER missions cannot cross the merge/deploy boundary without an owner."""
    if mission.risk_class is not RiskClass.AMBER:
        return False
    return target in {
        MissionState.MERGE_QUEUED,
        MissionState.MERGED,
        MissionState.DEPLOYMENT_PENDING,
        MissionState.CANARY_RUNNING,
    }


def budget_check(
    mission: Mission, *, tokens_used: int = 0, cost_usd: float = 0.0
) -> dict[str, Any]:
    if tokens_used > int(mission.token_budget):
        return {"allowed": False, "reason": "token_budget_exceeded"}
    if mission.cost_budget_usd and cost_usd > float(mission.cost_budget_usd):
        return {"allowed": False, "reason": "cost_budget_exceeded"}
    return {"allowed": True, "reason": "within_budget"}


def retry_allowed(mission: Mission) -> bool:
    return int(mission.retry_count) < int(mission.retry_policy.get("max_retries", 0))


def redact(payload: Any) -> Any:
    """Reuse the canonical OpenClaw redactor; never re-implement secret rules."""
    try:
        from app.integrations.openclaw.policies import redact_secrets

        return redact_secrets(payload)
    except Exception:  # pragma: no cover - defensive; redaction must never crash
        return payload
