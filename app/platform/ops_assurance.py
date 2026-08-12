"""Ops / Governance Assurance — read-only platform-ops issue detection (GREEN lane).

WHY (2026-07-20, Agent-OS assurance slice — platform-ops sibling of
``app.marketing.delivery_assurance``): the platform-ops signals all existed but
were never composed into a single, agent-attributed answer to the governance
question an Owner OS panel needs: *"which platform-ops thing is unhealthy, and
WHICH agent owns fixing it?"*
  - ``automation_health.health()`` = overdue / dead-man jobs + queue/DLQ depth
    (rich dict, but not attributed to an owning agent)
  - ``agent_registry.build_registry()`` = the canonical job -> owning-agent map
    (each ``AgentContract`` carries ``.jobs`` derived from ``JOB_META.owner``)
  - ``infra_handler._check_backups()`` = read-only newest-backup age

This module composes those existing READ primitives into the missing thing: a
structured, agent-attributed list of platform-ops issues — every overdue job,
queue/DLQ backlog and stale-backup mapped to the responsible persona
(Kavya / Hermes / Pranav / Arnav ...) via the registry job-owner truth.

SAFETY CONTRACT (enforced by tests):
  - PURE READ. Calls only read helpers (``automation_health.health``,
    ``infra_handler._check_backups``, ``agent_registry.build_registry``). Never
    restarts a service, never writes/drains a queue, never sends, never mutates
    any state or file.
  - NEVER RAISES. Every signal source is independently guarded — one failing
    source (Redis down, registry unavailable, backups dir missing) can never
    sink the scan or propagate an exception.
  - VOICE-FREE. Imports NO telephony / voice_agent / swara / STT / TTS / call /
    telephony_readiness module. Strictly the platform-ops domain.

OBSERVABILITY: a scan emits ONE ``team.log_event`` under ``kavya`` (Ops
Watchdog owns platform automation health) — no new persona invented — so the run
is visible on the existing team activity feed with a real owner.

Lane: GREEN (read-only detection + attribution). Autonomy: L0 (observe + report).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Observability owner for ops-assurance runs. Ops Watchdog (Kavya) owns platform
# automation-health surfacing. Module constant so attribution is explicit and
# testable (NOT a new persona — one of the canonical 31).
_OWNER_MEMBER = "kavya"

# Ownership for infra signals that are NOT a scheduled JOB_META row (so the
# registry job-owner map cannot resolve them), keyed to a real registry persona:
#   - queue backlog / DLQ reliability -> Pranav (SRE_AGENT, "reliability score")
#   - backup freshness                -> Hermes (INFRA_HANDLER, whose
#     infra_handler engine owns the ``_check_backups`` reader)
# Each is re-validated against the LIVE registry at scan time and falls back to
# "owner" if the persona ever disappears (honest, never a dangling attribution).
_INFRA_OWNER = {
    "queue": "pranav",
    "dlq": "pranav",
    "backup": "hermes",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _registry_map() -> tuple[dict[str, str], set[str]]:
    """Return (job -> owning-agent-id, valid-agent-ids) from the LIVE registry.

    The job map is the reverse of ``JOB_META.owner`` already computed inside
    ``AgentContract.jobs`` by ``build_registry`` — the single canonical owner
    truth. Read-only. Never raises (degrades to empty map + empty id-set)."""
    owner_map: dict[str, str] = {}
    ids: set[str] = set()
    try:
        from app.platform import agent_registry

        reg = agent_registry.build_registry()
        ids = set(reg.keys())
        for contract in reg.values():
            for job in getattr(contract, "jobs", ()) or ():
                owner_map[str(job)] = str(contract.id)
    except Exception as exc:
        logger.debug("ops_assurance _registry_map err: %s", exc)
    return owner_map, ids


def _resolve(agent_id: str, valid_ids: set[str]) -> str:
    """Resolve an owner to a real registry id, else the human 'owner'. No raise."""
    aid = str(agent_id or "").strip()
    if aid and aid in valid_ids:
        return aid
    return "owner"


def _read_health() -> dict[str, Any]:
    """Read-only automation-health snapshot (overdue jobs + queue/DLQ). Never
    raises — degrades to an empty dict so downstream collectors just find no
    signal instead of exploding."""
    try:
        from app.platform import automation_health

        h = automation_health.health()
        return h if isinstance(h, dict) else {}
    except Exception as exc:
        logger.debug("ops_assurance _read_health err: %s", exc)
        return {}


def _scheduler_issues(
    health: dict[str, Any], owner_map: dict[str, str], valid_ids: set[str]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Overdue / never-ran scheduled jobs, each mapped to its owning agent via the
    registry job-owner truth. Read-only. Never raises."""
    issues: list[dict[str, Any]] = []
    counts = {"overdue": 0, "never_ran": 0}
    try:
        overdue = [str(j) for j in (health.get("overdue") or [])]
        never_ran = [str(j) for j in (health.get("never_ran") or [])]
        # last_run lookup for evidence in the detail string
        jobs_index: dict[str, dict[str, Any]] = {}
        for j in health.get("jobs") or []:
            try:
                jobs_index[str(j.get("job"))] = j
            except Exception:
                continue
        for job in overdue:
            last_run = (jobs_index.get(job) or {}).get("last_run")
            issues.append(
                {
                    "type": "scheduler_overdue",
                    "detail": f"scheduled job '{job}' is overdue (dead-man); last_run={last_run}",
                    "owner_agent": _resolve(owner_map.get(job, ""), valid_ids),
                }
            )
        counts["overdue"] = len(overdue)
        for job in never_ran:
            issues.append(
                {
                    "type": "scheduler_never_ran",
                    "detail": f"scheduled job '{job}' has not run in the current window",
                    "owner_agent": _resolve(owner_map.get(job, ""), valid_ids),
                }
            )
        counts["never_ran"] = len(never_ran)
    except Exception as exc:
        logger.debug("ops_assurance _scheduler_issues err: %s", exc)
    return issues, counts


def _queue_issues(
    health: dict[str, Any], valid_ids: set[str]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Celery backlog + DLQ (dead / retry-exhausted) depth, mapped to SRE (Pranav).

    Relies on ``health()``'s already-computed booleans (``queue_backlogged`` /
    ``dead_tasks_present`` / ``retryable_failed_present``) so a ``-1`` (Redis
    unreachable, unknown) depth is NEVER mis-read as a real backlog. Read-only,
    never raises."""
    issues: list[dict[str, Any]] = []
    counts = {"queue_backlog": 0, "dlq_dead": 0, "dlq_retryable": 0}
    try:
        q = health.get("queue") or {}
        celery = q.get("celery")
        heavy = q.get("heavy")
        dead = q.get("dead")
        retryable = q.get("dlq")

        if health.get("queue_backlogged"):
            issues.append(
                {
                    "type": "queue_backlog",
                    "detail": f"celery queue backlogged (celery={celery}, heavy={heavy})",
                    "owner_agent": _resolve(_INFRA_OWNER["queue"], valid_ids),
                }
            )
            counts["queue_backlog"] = 1

        if health.get("dead_tasks_present") or (isinstance(dead, int) and dead > 0):
            issues.append(
                {
                    "type": "dlq_dead",
                    "detail": f"{dead} task(s) in dlq:dead (retry-exhausted, manual attention)",
                    "owner_agent": _resolve(_INFRA_OWNER["dlq"], valid_ids),
                }
            )
            counts["dlq_dead"] = int(dead) if isinstance(dead, int) and dead > 0 else 1

        if health.get("retryable_failed_present") or (isinstance(retryable, int) and retryable > 0):
            issues.append(
                {
                    "type": "dlq_retryable",
                    "detail": f"{retryable} task(s) in dlq:failed_tasks (awaiting DLQ retry sweep)",
                    "owner_agent": _resolve(_INFRA_OWNER["dlq"], valid_ids),
                }
            )
            counts["dlq_retryable"] = (
                int(retryable) if isinstance(retryable, int) and retryable > 0 else 1
            )
    except Exception as exc:
        logger.debug("ops_assurance _queue_issues err: %s", exc)
    return issues, counts


def _backup_issues(valid_ids: set[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Backup staleness via the read-only ``infra_handler._check_backups`` file-age
    reader, mapped to Hermes (INFRA_HANDLER). ``ok is None`` (dir not visible /
    unknown) is skipped gracefully — only ``ok is False`` (genuinely stale) is an
    issue. Read-only, never raises."""
    issues: list[dict[str, Any]] = []
    counts = {"backup_stale": 0}
    try:
        from app.platform import infra_handler

        fn = getattr(infra_handler, "_check_backups", None)
        if callable(fn):
            b = fn() or {}
            if b.get("ok") is False:
                issues.append(
                    {
                        "type": "backup_stale",
                        "detail": (
                            f"newest backup '{b.get('newest')}' is stale "
                            f"(age_hours={b.get('age_hours')})"
                        ),
                        "owner_agent": _resolve(_INFRA_OWNER["backup"], valid_ids),
                    }
                )
                counts["backup_stale"] = 1
    except Exception as exc:
        logger.debug("ops_assurance _backup_issues err: %s", exc)
    return issues, counts


def scan_ops(limit: int = 200) -> dict[str, Any]:
    """READ-ONLY platform-ops assurance scan. AgentRunResult-shaped.

    Detects (never mutates) overdue/dead-man scheduler jobs, Celery/DLQ backlog
    and stale backups, and MAPS each issue to the responsible agent via the
    canonical ``agent_registry`` job-owner truth. Emits one observability event
    (kavya). Never raises — returns a shaped record with ``status='error'`` +
    ``error`` string on unexpected failure.
    """
    run_id = str(uuid.uuid4())
    started = _now()
    result: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": "ops_assurance",
        "domain": "platform_ops",
        "lane": "GREEN",
        "status": "success",
        "started_at": _iso(started),
        "completed_at": None,
        "latency_ms": 0,
        "issues": [],
        "counts": {
            "overdue": 0,
            "never_ran": 0,
            "queue_backlog": 0,
            "dlq_dead": 0,
            "dlq_retryable": 0,
            "backup_stale": 0,
            "total": 0,
        },
        "error": None,
    }
    try:
        owner_map, valid_ids = _registry_map()
        health = _read_health()

        issues: list[dict[str, Any]] = []
        counts = dict(result["counts"])

        for collector in (
            _scheduler_issues(health, owner_map, valid_ids),
            _queue_issues(health, valid_ids),
            _backup_issues(valid_ids),
        ):
            sub_issues, sub_counts = collector
            issues.extend(sub_issues)
            for k, v in sub_counts.items():
                counts[k] = counts.get(k, 0) + int(v)

        counts["total"] = len(issues)
        # severest-first: scheduler dead-man before queue/DLQ before backup; stable
        _order = {
            "scheduler_overdue": 0,
            "dlq_dead": 1,
            "queue_backlog": 2,
            "dlq_retryable": 3,
            "scheduler_never_ran": 4,
            "backup_stale": 5,
        }
        issues.sort(key=lambda it: _order.get(str(it.get("type")), 99))

        result["issues"] = issues[: max(1, int(limit))]
        result["counts"] = counts
    except Exception as exc:
        logger.warning("ops_assurance scan err: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)

    completed = _now()
    result["completed_at"] = _iso(completed)
    result["latency_ms"] = int((completed - started).total_seconds() * 1000)

    # observability — one team event under the ops-watchdog owner (no new persona)
    try:
        from app.platform import team

        total = int(result["counts"].get("total", 0))
        if result["status"] != "success":
            ev_status = "error"
        elif total:
            ev_status = "warn"
        else:
            ev_status = "ok"
        detail = f"ops assurance: {total} issue(s) across scheduler/queue/backup"
        team.log_event(
            _OWNER_MEMBER,
            "ops_assurance_scan",
            detail[:160],
            status=ev_status,
            meta={
                "run_id": run_id,
                "total": total,
                "overdue": result["counts"].get("overdue"),
                "dlq_dead": result["counts"].get("dlq_dead"),
                "backup_stale": result["counts"].get("backup_stale"),
            },
        )
    except Exception as exc:
        logger.debug("ops_assurance observability skip: %s", exc)

    return result


def ops_summary() -> dict[str, Any]:
    """Compact admin-readable rollup (counts + per-owner / per-type breakdown +
    a trimmed issue view). Read-only wrapper over ``scan_ops``."""
    scan = scan_ops()
    issues = scan.get("issues") or []
    by_owner: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for it in issues:
        owner = str(it.get("owner_agent") or "owner")
        itype = str(it.get("type") or "unknown")
        by_owner[owner] = by_owner.get(owner, 0) + 1
        by_type[itype] = by_type.get(itype, 0) + 1
    return {
        "generated_at": scan.get("completed_at"),
        "status": scan.get("status"),
        "total_issues": len(issues),
        "counts": scan.get("counts"),
        "by_owner": by_owner,
        "by_type": by_type,
        "issues": [
            {
                "type": it.get("type"),
                "owner_agent": it.get("owner_agent"),
                "detail": it.get("detail"),
            }
            for it in issues[:50]
        ],
    }


__all__ = [
    "scan_ops",
    "ops_summary",
]
