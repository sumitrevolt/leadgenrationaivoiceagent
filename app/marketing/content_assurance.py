"""Content / Approval Assurance — read-only content-publishing risk detection (GREEN lane).

WHY (2026-07-20, Agent-OS assurance slice — Isha/Zara content domain): the
content-publishing primitives all existed but were never composed into one
admin-readable answer to *"which content is stuck, which paid customer's
content pipeline has gone quiet, and which posts are silently failing to
publish?"*
  - ``content_approval.list_all()`` = per-approval latest-state records (raw)
  - ``auto_content.list_queue(cid)`` = per-client content queue (raw items)
  - ``social_engine.store.list_jobs(status=..)`` = publish-job queue (raw jobs)
None of these returned an evidence-backed, tenant-safe list of the problems
that matter for a paying customer's content deliverable. This module composes
those existing readers into that one missing report. It mirrors the shape and
safety contract of ``delivery_assurance.py`` (sibling module).

SAFETY CONTRACT (enforced by tests):
  - PURE READ. Calls only read functions (``list_all`` / ``list_queue`` /
    ``list_jobs`` / ``list_clients``). NEVER submits, approves, publishes,
    enqueues, marks, or mutates any store / client record. Real publish + state
    changes stay in the existing ``content_approval`` / ``auto_content`` /
    ``social_engine`` write paths, which this module does NOT touch.
  - TENANT-SAFE. Every client id is normalised through
    ``clients_store.canonical_client_id`` (resolves billing/login alias ->
    marketing id, e.g. d79d690f61b3 -> jiya-makeover) so a customer is never
    mis-attributed or double-counted.
  - NEVER RAISES. Every category + every record is best-effort; one bad record
    or one failing reader cannot sink the scan.
  - VOICE-FREE. Imports no telephony / STT / TTS / call-runtime module; strictly
    marketing content-publishing domain (out of scope: the voice calling stack).

OBSERVABILITY: a scan emits ONE ``team.log_event`` under ``isha`` (content
owner — she already owns the ``content_approval`` activity feed) so the run is
visible on the existing team feed with a real owner (no new persona invented).

Lane: GREEN (read-only detection + report). Autonomy: L0/L1 (observe + recommend).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Observability owner for content-assurance runs. Content/approval ops = Isha's
# lane (she already owns content_approval's team feed). Module constant so the
# attribution is explicit + testable (NOT a new persona — one of the 31).
_OWNER_MEMBER = "isha"

# Approval statuses that are already resolved — never "stuck".
_APPROVAL_TERMINAL = frozenset({"published", "cancelled", "rejected"})
# Approval statuses that mean "waiting on the client to review".
_AWAITING_CLIENT = frozenset({"pending", "ready_for_review", "changes_requested"})
# Approval statuses that mean "past client-approval, publish step owes us a post".
_PUBLISH_INFLIGHT = frozenset({"publishing", "partially_published"})

# Defaults (env-overridable at call time — read-only, no state).
_DEFAULT_APPROVAL_STALE_HOURS = 48  # pending/awaiting-client older than this = stuck
_DEFAULT_PUBLISH_GRACE_HOURS = 24  # approved/publishing older than this = stuck
_DEFAULT_QUEUE_STALE_DAYS = 7  # no fresh content in this many days = stale


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _env_int(name: str, default: int) -> int:
    """Read a positive int env override at call-time. Never raises."""
    try:
        val = int(str(os.getenv(name, "")).strip())
        return val if val >= 0 else default
    except Exception:
        return default


def _parse_ts(value: Any) -> datetime | None:
    """Best-effort parse of an ISO / date string to a tz-aware UTC datetime.
    Handles trailing 'Z', naive (assumed UTC) and date-only forms. Never raises."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
            except Exception:
                continue
        return None


def _age_hours(value: Any) -> float | None:
    """Age in hours (positive = in the past) of an ISO timestamp. None if unparseable."""
    dt = _parse_ts(value)
    if dt is None:
        return None
    return (_now() - dt).total_seconds() / 3600.0


def _canonical_id(cid: Any) -> str:
    """Normalise any id/alias to the marketing client id. Never raises."""
    try:
        from app.marketing import clients_store

        return str(clients_store.canonical_client_id(cid) or cid or "").strip()
    except Exception:
        return str(cid or "").strip()


def _approval_title(rec: dict[str, Any]) -> str:
    content = (rec or {}).get("content") or {}
    return str(content.get("title") or content.get("occasion") or rec.get("id") or "")[:120]


def _paid_active_clients() -> list[dict[str, Any]]:
    """Active clients that are delivery-eligible paid customers. Read-only.
    Mirrors delivery_assurance so 'paid' means the same thing across assurance."""
    try:
        from app.marketing import clients_store, customer_delivery

        out: list[dict[str, Any]] = []
        for c in clients_store.list_clients(status="active"):
            try:
                if customer_delivery.has_paid_evidence(c):
                    out.append(c)
            except Exception:
                try:
                    if customer_delivery.is_paid_client(c):
                        out.append(c)
                except Exception:
                    continue
        return out
    except Exception as exc:
        logger.warning("content_assurance _paid_active_clients err: %s", exc)
        return []


def _list_approvals(limit: int) -> list[dict[str, Any]]:
    """All approvals (latest-state). Read-only. Degrades to [] on any error."""
    try:
        from app.marketing import content_approval

        rows = content_approval.list_all(limit=limit)
        return list(rows) if rows else []
    except Exception as exc:
        logger.warning("content_assurance _list_approvals err: %s", exc)
        return []


def _list_queue(cid: str) -> list[dict[str, Any]]:
    """One client's content queue (latest 200). Read-only. Degrades to [] on error."""
    try:
        from app.marketing import auto_content

        rows = auto_content.list_queue(cid, limit=200)
        return list(rows) if rows else []
    except Exception as exc:
        logger.debug("content_assurance _list_queue skip (%s): %s", cid, exc)
        return []


def _list_failed_jobs(limit: int) -> list[dict[str, Any]]:
    """Failed + dead publish jobs from the social queue. Read-only. Never raises."""
    jobs: list[dict[str, Any]] = []
    try:
        from app.social_engine import store as social_store

        for st in ("failed", "dead"):
            try:
                rows = social_store.list_jobs(status=st, limit=limit)
                if rows:
                    jobs.extend(rows)
            except Exception:
                continue
    except Exception as exc:
        logger.warning("content_assurance _list_failed_jobs err: %s", exc)
    return jobs


def detect_stuck_approvals(approvals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Approvals stuck mid-flow: awaiting client too long, approved-but-not-published,
    scheduled-time already passed, or publish left in-flight. Read-only, never raises."""
    stale_hours = _env_int("CONTENT_ASSURANCE_APPROVAL_STALE_HOURS", _DEFAULT_APPROVAL_STALE_HOURS)
    grace_hours = _env_int("CONTENT_ASSURANCE_PUBLISH_GRACE_HOURS", _DEFAULT_PUBLISH_GRACE_HOURS)
    out: list[dict[str, Any]] = []
    for rec in approvals or []:
        try:
            if not isinstance(rec, dict):
                continue
            status = str(rec.get("status") or "").strip().lower()
            if status in _APPROVAL_TERMINAL:
                continue
            age = _age_hours(rec.get("decided_at") or rec.get("created_at"))
            reason: str | None = None
            if status in _AWAITING_CLIENT:
                if age is not None and age > stale_hours:
                    reason = "awaiting_client_over_threshold"
            elif status == "approved":
                if age is None or age > grace_hours:
                    reason = "approved_not_published"
            elif status == "scheduled":
                sched = rec.get("scheduled_time") or rec.get("scheduled_date")
                if not sched:
                    sched = (rec.get("schedule") or {}).get("scheduled_time")
                sched_age = _age_hours(sched)
                if sched_age is not None and sched_age > grace_hours:
                    reason = "scheduled_time_passed"
            elif status in _PUBLISH_INFLIGHT:
                if age is None or age > grace_hours:
                    reason = "publish_incomplete"
            if reason:
                out.append(
                    {
                        "id": str(rec.get("id") or ""),
                        "client_id": _canonical_id(rec.get("client_id")),
                        "status": status,
                        "reason": reason,
                        "age_hours": round(age, 1) if age is not None else None,
                        "title": _approval_title(rec),
                    }
                )
        except Exception:
            continue
    return out


def detect_stale_content_queues(clients: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Paid clients whose content queue is empty or has no fresh content in N days.
    Read-only, tenant-safe, never raises."""
    stale_days = _env_int("CONTENT_ASSURANCE_QUEUE_STALE_DAYS", _DEFAULT_QUEUE_STALE_DAYS)
    out: list[dict[str, Any]] = []
    for c in (clients or [])[: max(1, int(limit))]:
        try:
            raw_id = str((c or {}).get("id") or "").strip()
            cid = _canonical_id(raw_id) or raw_id
            if not cid:
                continue
            items = _list_queue(cid)
            base = {
                "client_id": cid,
                "name": (c or {}).get("business_name"),
                "plan": (c or {}).get("plan"),
            }
            if not items:
                out.append(
                    {
                        **base,
                        "empty": True,
                        "last_content_at": None,
                        "days_stale": None,
                        "reason": "empty_queue",
                    }
                )
                continue
            latest: datetime | None = None
            for it in items:
                ts = _parse_ts((it or {}).get("created_at")) or _parse_ts((it or {}).get("date"))
                if ts and (latest is None or ts > latest):
                    latest = ts
            if latest is None:
                # Can't date the queue — do NOT flag (avoid false positives).
                continue
            days = (_now() - latest).days
            if days > stale_days:
                out.append(
                    {
                        **base,
                        "empty": False,
                        "last_content_at": _iso(latest),
                        "days_stale": days,
                        "reason": "stale_queue",
                    }
                )
        except Exception:
            continue
    return out


def detect_publish_failures(jobs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Failed / dead publish jobs from the social queue. Read-only, never raises."""
    out: list[dict[str, Any]] = []
    for j in (jobs or [])[: max(1, int(limit))]:
        try:
            if not isinstance(j, dict):
                continue
            out.append(
                {
                    "id": str(j.get("id") or ""),
                    "client_id": _canonical_id(j.get("client_id")),
                    "platform": str(j.get("platform") or ""),
                    "status": str(j.get("status") or ""),
                    "attempts": j.get("attempts"),
                    "last_error": str(j.get("last_error") or "")[:160],
                }
            )
        except Exception:
            continue
    return out


def scan_content_assurance(limit: int = 200) -> dict[str, Any]:
    """READ-ONLY aggregator: structured, tenant-safe, evidence-backed list of
    content-publishing risks (stuck approvals, stale/empty content queues,
    publish failures). AgentRunResult-shaped.

    No sends, no publishing, no state mutation. Emits one observability event
    (isha). Never raises — returns a shaped record with status='error' + error
    string on unexpected failure.
    """
    run_id = str(uuid.uuid4())
    started = _now()
    result: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": "content_assurance",
        "domain": "content_publishing",
        "lane": "GREEN",
        "status": "success",
        "started_at": _iso(started),
        "completed_at": None,
        "latency_ms": 0,
        "checked": 0,
        "issues": [],
        "counts": {},
        "error": None,
    }
    try:
        lim = max(1, int(limit))
    except Exception:
        lim = 200

    checked_approvals = 0
    checked_clients = 0
    checked_jobs = 0
    stuck: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    try:
        # 1) stuck approvals
        try:
            approvals = _list_approvals(lim)
            checked_approvals = len(approvals)
            stuck = detect_stuck_approvals(approvals)
        except Exception as exc:
            logger.warning("content_assurance stuck-approvals category err: %s", exc)

        # 2) stale / empty content queues (paid clients only)
        try:
            clients = _paid_active_clients()
            checked_clients = len(clients)
            stale = detect_stale_content_queues(clients, lim)
        except Exception as exc:
            logger.warning("content_assurance stale-queue category err: %s", exc)

        # 3) publish failures
        try:
            jobs = _list_failed_jobs(lim)
            checked_jobs = len(jobs)
            failures = detect_publish_failures(jobs, lim)
        except Exception as exc:
            logger.warning("content_assurance publish-failure category err: %s", exc)

        issues: list[dict[str, Any]] = []
        if stuck:
            issues.append({"type": "stuck_approval", "count": len(stuck), "sample": stuck[:5]})
        if stale:
            issues.append({"type": "stale_content_queue", "count": len(stale), "sample": stale[:5]})
        if failures:
            issues.append(
                {"type": "publish_failure", "count": len(failures), "sample": failures[:5]}
            )

        result["issues"] = issues
        result["counts"] = {
            "stuck_approvals": len(stuck),
            "stale_content_queues": len(stale),
            "publish_failures": len(failures),
            "checked_approvals": checked_approvals,
            "checked_clients": checked_clients,
            "checked_jobs": checked_jobs,
        }
        result["checked"] = checked_approvals + checked_clients + checked_jobs
    except Exception as exc:
        logger.warning("content_assurance scan err: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)

    completed = _now()
    result["completed_at"] = _iso(completed)
    result["latency_ms"] = int((completed - started).total_seconds() * 1000)

    # observability — one team event under the content owner (no new persona)
    try:
        from app.platform import team

        problems = len(stuck) + len(stale) + len(failures)
        status = "ok" if result["status"] == "success" else "error"
        if problems and status == "ok":
            status = "warn"
        detail = (
            f"content assurance: {len(stuck)} stuck / {len(stale)} stale-queue / "
            f"{len(failures)} publish-fail of {result['checked']} checked"
        )
        team.log_event(
            _OWNER_MEMBER,
            "content_assurance_scan",
            detail[:160],
            status=status,
            meta={
                "run_id": run_id,
                "stuck_approvals": len(stuck),
                "stale_content_queues": len(stale),
                "publish_failures": len(failures),
                "checked": result["checked"],
            },
        )
    except Exception as exc:
        logger.debug("content_assurance observability skip: %s", exc)

    return result


def content_assurance_summary() -> dict[str, Any]:
    """Compact admin-readable summary (counts + issue types). Read-only."""
    scan = scan_content_assurance()
    counts = scan.get("counts") or {}
    return {
        "generated_at": scan["completed_at"],
        "status": scan["status"],
        "checked": scan["checked"],
        "stuck_approvals": counts.get("stuck_approvals", 0),
        "stale_content_queues": counts.get("stale_content_queues", 0),
        "publish_failures": counts.get("publish_failures", 0),
        "issues": [{"type": i["type"], "count": i["count"]} for i in scan.get("issues", [])],
    }


__all__ = [
    "detect_stuck_approvals",
    "detect_stale_content_queues",
    "detect_publish_failures",
    "scan_content_assurance",
    "content_assurance_summary",
]
