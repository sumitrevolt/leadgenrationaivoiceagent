"""Contract tests for app.platform.ops_assurance (read-only platform-ops assurance).

Hermetic: automation_health.health, infra_handler._check_backups and
team.log_event are monkeypatched, but the REAL agent_registry is used to prove
each detected issue is mapped to the correct owning agent (registry job-owner
truth). Covers: overdue -> correct owner, empty/healthy case, never-raises when a
signal source blows up, DLQ/backup -> infra owner, and the AgentRunResult shape.
"""

from __future__ import annotations

from typing import Any

import app.platform.ops_assurance as oa
from app.platform import agent_registry, automation_health, infra_handler, team


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _fake_health(
    overdue: list[str] | None = None,
    never_ran: list[str] | None = None,
    queue: dict[str, int] | None = None,
    backlogged: bool = False,
    dead: bool = False,
    retryable: bool = False,
) -> dict[str, Any]:
    overdue = overdue or []
    return {
        "status": "degraded" if (overdue or backlogged or dead or retryable) else "healthy",
        "ok": not (overdue or backlogged or dead or retryable),
        "overdue": overdue,
        "never_ran": never_ran or [],
        "jobs": [
            {"job": j, "last_run": "2026-07-20T10:00:00+00:00", "status": "overdue"}
            for j in overdue
        ],
        "queue": queue or {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0},
        "queue_available": True,
        "queue_backlogged": backlogged,
        "dead_tasks_present": dead,
        "retryable_failed_present": retryable,
    }


def _owner_of(job: str) -> str | None:
    """Owner agent id for a job, straight from the REAL registry (job-owner truth)."""
    for c in agent_registry.build_registry().values():
        if job in (c.jobs or ()):
            return c.id
    return None


def _patch_common(monkeypatch, health: dict[str, Any], backups: dict[str, Any] | None = None):
    """Patch the three side-effecting sources; leave the registry REAL."""
    monkeypatch.setattr(automation_health, "health", lambda: health)
    monkeypatch.setattr(
        infra_handler,
        "_check_backups",
        lambda: backups if backups is not None else {"ok": True, "newest": "x", "age_hours": 1.0},
    )
    events: list[tuple[Any, Any]] = []
    monkeypatch.setattr(team, "log_event", lambda *a, **k: events.append((a, k)))
    return events


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_overdue_job_mapped_to_correct_owner(monkeypatch):
    # 'watchdog' is a real JOB_META job owned by kavya in the live registry.
    expected = _owner_of("watchdog")
    assert expected == "kavya", "sanity: watchdog job should belong to kavya"

    events = _patch_common(monkeypatch, _fake_health(overdue=["watchdog"]))
    scan = oa.scan_ops()

    overdue_issues = [i for i in scan["issues"] if i["type"] == "scheduler_overdue"]
    assert len(overdue_issues) == 1
    issue = overdue_issues[0]
    assert issue["owner_agent"] == expected == "kavya"
    assert "watchdog" in issue["detail"]
    assert scan["counts"]["overdue"] == 1
    assert scan["counts"]["total"] == 1
    # exactly one observability event under kavya, status=warn (issues present)
    assert len(events) == 1
    assert events[0][0][0] == "kavya"
    assert events[0][1].get("status") == "warn"


def test_multiple_owners_mapped_independently(monkeypatch):
    # engineer_sre -> pranav, engineer_security -> arnav (real registry truth)
    assert _owner_of("engineer_sre") == "pranav"
    assert _owner_of("engineer_security") == "arnav"

    _patch_common(monkeypatch, _fake_health(overdue=["engineer_sre", "engineer_security"]))
    scan = oa.scan_ops()
    owners = {i["owner_agent"] for i in scan["issues"] if i["type"] == "scheduler_overdue"}
    assert owners == {"pranav", "arnav"}


def test_empty_healthy_case(monkeypatch):
    events = _patch_common(monkeypatch, _fake_health())
    scan = oa.scan_ops()
    assert scan["status"] == "success"
    assert scan["issues"] == []
    assert scan["counts"]["total"] == 0
    # healthy scan still emits exactly one event, status=ok
    assert len(events) == 1
    assert events[0][0][0] == "kavya"
    assert events[0][1].get("status") == "ok"


def test_queue_and_dlq_mapped_to_sre(monkeypatch):
    health = _fake_health(
        queue={"celery": 500, "heavy": 0, "dlq": 3, "dead": 2},
        backlogged=True,
        dead=True,
        retryable=True,
    )
    _patch_common(monkeypatch, health)
    scan = oa.scan_ops()
    by_type = {i["type"]: i for i in scan["issues"]}
    assert "queue_backlog" in by_type
    assert "dlq_dead" in by_type
    assert "dlq_retryable" in by_type
    # all queue/DLQ issues attributed to the SRE persona (pranav) — a real id
    assert by_type["queue_backlog"]["owner_agent"] == "pranav"
    assert by_type["dlq_dead"]["owner_agent"] == "pranav"
    assert "pranav" in agent_registry.build_registry()
    assert scan["counts"]["dlq_dead"] == 2
    assert scan["counts"]["dlq_retryable"] == 3


def test_backup_stale_mapped_to_hermes(monkeypatch):
    _patch_common(
        monkeypatch,
        _fake_health(),
        backups={"ok": False, "newest": "db-20260701.sql.gz", "age_hours": 99.0},
    )
    scan = oa.scan_ops()
    backup_issues = [i for i in scan["issues"] if i["type"] == "backup_stale"]
    assert len(backup_issues) == 1
    assert backup_issues[0]["owner_agent"] == "hermes"
    assert "hermes" in agent_registry.build_registry()
    assert scan["counts"]["backup_stale"] == 1


def test_unknown_queue_depth_is_not_a_false_positive(monkeypatch):
    # Redis unreachable -> depths -1, health booleans all False. Must yield no issue.
    _patch_common(
        monkeypatch,
        _fake_health(queue={"celery": -1, "heavy": -1, "dlq": -1, "dead": -1}),
    )
    scan = oa.scan_ops()
    assert scan["issues"] == []
    assert scan["counts"]["total"] == 0


def test_never_raises_when_health_source_fails(monkeypatch):
    def _boom():
        raise RuntimeError("automation_health exploded")

    monkeypatch.setattr(automation_health, "health", _boom)
    monkeypatch.setattr(
        infra_handler, "_check_backups", lambda: (_ for _ in ()).throw(RuntimeError("backups boom"))
    )
    # log_event also blows up — the scan must still not raise.
    monkeypatch.setattr(
        team, "log_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
    )

    scan = oa.scan_ops()  # must not raise
    assert isinstance(scan, dict)
    # sources are independently guarded -> scan itself still 'success', 0 issues
    assert scan["status"] == "success"
    assert scan["issues"] == []


def test_structured_agentrunresult_shape(monkeypatch):
    _patch_common(monkeypatch, _fake_health(overdue=["ops"]))
    scan = oa.scan_ops()
    for key in (
        "run_id",
        "agent_id",
        "domain",
        "lane",
        "status",
        "started_at",
        "completed_at",
        "latency_ms",
        "issues",
        "counts",
        "error",
    ):
        assert key in scan, f"missing key {key}"
    assert scan["agent_id"] == "ops_assurance"
    assert scan["domain"] == "platform_ops"
    assert scan["lane"] == "GREEN"
    assert isinstance(scan["issues"], list)
    assert isinstance(scan["counts"], dict)
    assert isinstance(scan["latency_ms"], int)
    # every issue is a structured {type, detail, owner_agent}
    for it in scan["issues"]:
        assert set(it.keys()) >= {"type", "detail", "owner_agent"}


def test_ops_summary_shape(monkeypatch):
    _patch_common(monkeypatch, _fake_health(overdue=["watchdog"]))
    summary = oa.ops_summary()
    assert summary["total_issues"] == 1
    assert summary["by_owner"].get("kavya") == 1
    assert summary["by_type"].get("scheduler_overdue") == 1
    assert isinstance(summary["issues"], list)
