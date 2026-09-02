"""Canonical multi-registry scheduler parity — single source for contract tests.

Inventories (not identical by design — intentional exceptions below):
  * STAFF_JOBS          — Celery/in-process executable job IDs
  * JOB_META            — admin label/cadence/owner
  * team_scheduler._last_ran — in-process slot markers
  * EXPECTED_GAP_MIN    — dead-man / automation_health
  * JOB_INFO            — /app Aaj tab Hinglish labels
  * Celery beat_schedule staff-* entries → run_staff_job args

Do NOT invent a second scheduler. This module only audits wiring.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Intentional exceptions — every non-parity membership needs a reason.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryException:
    job_id: str
    registry: str  # which registry is the exception relative to STAFF_JOBS
    relation: str  # "extra" | "missing"
    reason: str
    owner: str
    safety: str


INTENTIONAL_EXCEPTIONS: tuple[RegistryException, ...] = (
    RegistryException(
        job_id="self_improve",
        registry="EXPECTED_GAP_MIN",
        relation="extra",
        reason=(
            "Self-improve is a continuous Celery chain (self_improve_tick), "
            "not a STAFF_JOBS / JOB_META cron job. Dead-man still watches it."
        ),
        owner="boss",
        safety="Chain has own slot + daily cap; exclude from staff beat parity",
    ),
)

# Jobs that MUST stay in RUN_DUE_EXCLUDE (unsafe catch-up).
REQUIRED_RUN_DUE_EXCLUDE: frozenset[str] = frozenset(
    {
        "platform_dial",
        "email_outreach",
        "email_followup",
        "digest",
        "sales_autopilot",
        "hq_auto_chase",
        "reply_auto_send",
    }
)

# Customer / provider contact risk lanes for staff jobs.
CUSTOMER_CONTACT_JOBS: frozenset[str] = frozenset(
    {
        "email_outreach",
        "email_followup",
        "platform_dial",
        "sales_autopilot",
        "approval_email_sweep",
        "social_drain",
        "digest",  # internal owner email — still outbound SMTP
        "readiness_digest",
        "call_kpi_digest",
        "hq_auto_chase",
        "reply_auto_send",
        "trial_nudge",
    }
)

PROVIDER_CONTACT_JOBS: frozenset[str] = frozenset(
    {
        "platform_dial",  # Vobiz
        "social_drain",  # Postiz/Meta
        "email_outreach",
        "email_followup",
        "sales_autopilot",
        "approval_email_sweep",
        "hq_auto_chase",
        "reply_auto_send",
        "trial_nudge",
        "prospect",
        "midday_prospect",
        "evening_prospect",
        "content",
        "afternoon_content",
        "blog",
        "kb_refresh",
    }
)


@dataclass
class JobParityRow:
    job_id: str
    owner: str = ""
    label: str = ""
    cadence: str = ""
    in_staff_jobs: bool = False
    in_job_meta: bool = False
    in_last_ran: bool = False
    in_expected_gap: bool = False
    in_job_info: bool = False
    beat_keys: list[str] = field(default_factory=list)
    run_due_excluded: bool = False
    customer_contact: bool = False
    provider_contact: bool = False
    gap_min: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _staff_beat_map() -> dict[str, list[str]]:
    """job_id -> list of beat schedule keys that dispatch it."""
    from app.worker import celery_app

    out: dict[str, list[str]] = {}
    for key, entry in (celery_app.conf.beat_schedule or {}).items():
        if not str(key).startswith("staff-"):
            continue
        task = str((entry or {}).get("task") or "")
        args = (entry or {}).get("args") or ()
        if task.endswith("self_improve_tick") or "selfimprove" in str(key).replace("-", ""):
            # revive beat — not a STAFF_JOB arg
            continue
        if not args:
            continue
        job = str(args[0])
        out.setdefault(job, []).append(str(key))
    return out


def collect_registry_sets() -> dict[str, set[str]]:
    from app.platform.automation_health import EXPECTED_GAP_MIN
    from app.platform.scheduler_config import JOB_META, RUN_DUE_EXCLUDE
    from app.platform.team_scheduler import _last_ran
    from app.platform.today_overview import JOB_INFO
    from app.tasks.staff_jobs import STAFF_JOBS

    beat = _staff_beat_map()
    return {
        "STAFF_JOBS": set(STAFF_JOBS),
        "JOB_META": set(JOB_META),
        "last_ran": set(_last_ran),
        "EXPECTED_GAP_MIN": set(EXPECTED_GAP_MIN),
        "JOB_INFO": set(JOB_INFO),
        "beat_staff_jobs": set(beat),
        "RUN_DUE_EXCLUDE": set(RUN_DUE_EXCLUDE),
    }


def intentional_exception_index() -> dict[tuple[str, str, str], RegistryException]:
    return {(e.job_id, e.registry, e.relation): e for e in INTENTIONAL_EXCEPTIONS}


def unexplained_diffs() -> list[str]:
    """Return human-readable unexplained set differences (should be empty)."""
    sets = collect_registry_sets()
    staff = sets["STAFF_JOBS"]
    idx = intentional_exception_index()
    problems: list[str] = []

    def _check(name: str, other: set[str], *, allow_extra: set[str] | None = None) -> None:
        allow_extra = allow_extra or set()
        missing = staff - other
        extra = other - staff - allow_extra
        for j in sorted(missing):
            if (j, name, "missing") not in idx:
                problems.append(f"{name} missing staff job '{j}' (no intentional exception)")
        for j in sorted(extra):
            if (j, name, "extra") not in idx:
                problems.append(
                    f"{name} has extra '{j}' not in STAFF_JOBS (no intentional exception)"
                )

    _check("JOB_META", sets["JOB_META"])
    _check("last_ran", sets["last_ran"])
    _check("JOB_INFO", sets["JOB_INFO"])
    _check("beat_staff_jobs", sets["beat_staff_jobs"])
    # EXPECTED_GAP may include self_improve
    allow = {
        e.job_id
        for e in INTENTIONAL_EXCEPTIONS
        if e.registry == "EXPECTED_GAP_MIN" and e.relation == "extra"
    }
    _check("EXPECTED_GAP_MIN", sets["EXPECTED_GAP_MIN"], allow_extra=allow)

    for j in sorted(REQUIRED_RUN_DUE_EXCLUDE - sets["RUN_DUE_EXCLUDE"]):
        problems.append(f"RUN_DUE_EXCLUDE missing required '{j}'")

    return problems


def build_parity_table() -> list[JobParityRow]:
    from app.platform.automation_health import EXPECTED_GAP_MIN
    from app.platform.scheduler_config import JOB_META, RUN_DUE_EXCLUDE
    from app.platform.team_scheduler import _last_ran
    from app.platform.today_overview import JOB_INFO
    from app.tasks.staff_jobs import STAFF_JOBS

    beat = _staff_beat_map()
    rows: list[JobParityRow] = []
    for job in sorted(STAFF_JOBS):
        meta = JOB_META.get(job) or {}
        rows.append(
            JobParityRow(
                job_id=job,
                owner=str(meta.get("owner") or ""),
                label=str(meta.get("label") or ""),
                cadence=str(meta.get("cadence") or ""),
                in_staff_jobs=True,
                in_job_meta=job in JOB_META,
                in_last_ran=job in _last_ran,
                in_expected_gap=job in EXPECTED_GAP_MIN,
                in_job_info=job in JOB_INFO,
                beat_keys=sorted(beat.get(job) or []),
                run_due_excluded=job in RUN_DUE_EXCLUDE,
                customer_contact=job in CUSTOMER_CONTACT_JOBS,
                provider_contact=job in PROVIDER_CONTACT_JOBS,
                gap_min=EXPECTED_GAP_MIN.get(job),
            )
        )
    return rows


def beat_task_targets_ok() -> list[str]:
    """Every staff-* beat entry (except selfimprove revive) must target run_staff_job
    with a STAFF_JOBS arg, OR be an explicitly allowed revive task."""
    from app.tasks.staff_jobs import STAFF_JOBS
    from app.worker import celery_app

    staff = set(STAFF_JOBS)
    problems: list[str] = []
    for key, entry in (celery_app.conf.beat_schedule or {}).items():
        if not str(key).startswith("staff-"):
            continue
        task = str((entry or {}).get("task") or "")
        args = (entry or {}).get("args") or ()
        if "selfimprove" in str(key).replace("-", "") or task.endswith("self_improve_tick"):
            if task not in {
                "app.tasks.staff_jobs.self_improve_tick",
                "app.tasks.staff_jobs.self_improve_revive",
            }:
                problems.append(f"beat '{key}' selfimprove key but unexpected task={task}")
            continue
        if task != "app.tasks.staff_jobs.run_staff_job":
            problems.append(f"beat '{key}' task={task} expected run_staff_job")
            continue
        if not args or str(args[0]) not in staff:
            problems.append(f"beat '{key}' args={args} not in STAFF_JOBS")
    return problems


def summarize() -> dict[str, Any]:
    sets = collect_registry_sets()
    rows = build_parity_table()
    return {
        "staff_job_count": len(sets["STAFF_JOBS"]),
        "job_meta_count": len(sets["JOB_META"]),
        "last_ran_count": len(sets["last_ran"]),
        "expected_gap_count": len(sets["EXPECTED_GAP_MIN"]),
        "job_info_count": len(sets["JOB_INFO"]),
        "beat_staff_job_count": len(sets["beat_staff_jobs"]),
        "run_due_exclude": sorted(sets["RUN_DUE_EXCLUDE"]),
        "required_run_due_exclude": sorted(REQUIRED_RUN_DUE_EXCLUDE),
        "intentional_exceptions": [asdict(e) for e in INTENTIONAL_EXCEPTIONS],
        "unexplained": unexplained_diffs(),
        "beat_problems": beat_task_targets_ok(),
        "customer_contact_jobs": sorted(CUSTOMER_CONTACT_JOBS),
        "jobs": [r.to_dict() for r in rows],
    }


_BEAT_KEY_RE = re.compile(r"^staff-[a-z0-9-]+$")
