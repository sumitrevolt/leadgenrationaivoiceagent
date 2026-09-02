"""Automation health / dead-man switch (Cronitor/healthchecks.io-pattern, free).

PROBLEM: koi scheduled job chupchaap chalna band ho jaye (jaise scheduler bug,
worker crash, import error) to pata hi nahi chalta — automation "chal raha
hoga" maan ke baith jaate hain. Yeh module har job-run HEARTBEAT record karta
(team_scheduler._run_job wrapper se — in-process YA Celery dono path cover) aur
expected cadence se compare karke OVERDUE jobs pakadta.

`run_watch()` watchdog-job me wired: overdue mile to email alert (gated
`AUTOMATION_HEALTH_ALERTS=1`; off = sirf log). Store: data/job_runs.jsonl
(latest-per-job snapshot data/job_heartbeats.json). Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

from app.platform.today_overview import _WEEKLY_ON, _job_due_today, _job_due_yet  # noqa: E402


def _RUNS() -> str:
    """Scheduler job-run jsonl — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="automation.job_runs",
            legacy_path=Path("data") / "job_runs.jsonl",
            target_segments=("automation", "job_runs.jsonl"),
        )
    )


def _BEATS() -> str:
    """Latest-per-job heartbeat snapshot — sibling under the same store family."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="automation.job_runs",
            legacy_path=Path("data") / "job_heartbeats.json",
            target_segments=("automation", "job_heartbeats.json"),
        )
    )


# job -> max-gap (minutes) jiske baad OVERDUE (cadence + generous grace)
EXPECTED_GAP_MIN = {
    "growth": 60,  # 15-min job, 1h grace
    "ops": 180,  # hourly
    "reply_triage": 180,
    "watchdog": 180,
    "onboard": 180,
    "standup": 30 * 60,  # daily 08:00 IST
    "engineer_sre": 180,  # hourly :45
    "mcp_engineer": 180,  # hourly :40 (gated MCP_ENGINEER) — dead-man parity with STAFF_JOBS
    "engineer_finops": 30 * 60,
    "engineer_security": 30 * 60,
    "engineer_dbre": 30 * 60,
    "engineer_dataquality": 30 * 60,
    "engineer_deps": 8 * 24 * 60,
    "readiness_digest": 30 * 60,
    "qa": 30 * 60,  # daily (30h)
    "trainer": 30 * 60,
    "blog": 30 * 60,
    "content": 30 * 60,
    "hot_queue_brief": 30 * 60,  # daily 08:15 IST, health-gated revenue brief
    "hot_queue_owner_pack": 30 * 60,  # daily 09:00 IST, CSV+MD+nfty for owner 1-click close
    "digest": 30 * 60,
    "prospect": 30 * 60,
    "email_outreach": 24
    * 60,  # hourly 9am-7pm; overnight ~14h gap → 24h grace (90h was a dead-man blind spot)
    "pipeline": 30 * 60,
    "email_followup": 24 * 60,  # hourly 9am-7pm; overnight ~14h gap → 24h grace
    "kb_refresh": 8 * 24 * 60,  # weekly Sun
    "midday_prospect": 30 * 60,  # daily 14:30
    "evening_wrap": 30 * 60,
    "weekly_marketing": 8 * 24 * 60,
    "saturday_hygiene": 8 * 24 * 60,
    "meter_watch": 180,  # hourly :55 (gated METER_ALERTS), 3h grace
    "process_autostart": 30 * 60,  # daily ~11:30 IST (gated PROCESS_AUTOSTART)
    "obsidian_push": 30
    * 60,  # daily ~02:15 IST: second-brain compact + git push (_run_job heartbeats daily; job body no-ops unless OBSIDIAN_SYNC=1)
    "revenue_snapshot": 30 * 60,  # daily ~00:15 IST: B1 MRR/churn snapshot (gated REVENUE_TRENDS)
    "gsc_rank": 30
    * 60,  # daily ~00:30 IST: Google Search Console rank snapshot (gated GSC_ENABLED)
    "flow_cron": 30,  # every 5 min: Flow Runner cron scan (self-gates; beat always heartbeats)
    "afternoon_content": 30 * 60,  # daily 15:00 IST: 2nd content-gen pass (gated AFTERNOON_CONTENT)
    "evening_prospect": 30
    * 60,  # daily 17:00 IST: 3rd free lead-harvest pass (gated EVENING_PROSPECT)
    "self_improve": 30,  # ~20-min tick; 30-min grace — watchdog now flags stale loop (dead-man trio complete)
    "platform_dial": 30
    * 60,  # daily 11:30 IST: self-sale AI cold-call batch (gated PLATFORM_DIAL_DAILY)
    "daily_video": 30
    * 60,  # daily 09:45 IST: per-client video producer (gated DAILY_VIDEO_ENABLED; beat heartbeats regardless)
    "call_kpi_digest": 30 * 60,  # daily 19:30 IST: Lekha call-KPI digest
    "product_one_health": 180,  # hourly :20 (2026-07-08): Product 1 Customer Health/Approval Reminder/SLA Recovery sweep, 3h grace like meter_watch
    "approval_email_sweep": 180,  # hourly pending-approval EMAIL (gated APPROVAL_EMAIL_NOTIFY); was scheduled but missing from dead-man
    "social_drain": 180,  # hourly :10 native social queue drain (gated SOCIAL_ENGINE); 3h grace
    "task_lease_reap": 180,  # hourly :05 expired agent-task lease reclaim (gated AGENT_TASK_LEASE_REAP); 3h grace like meter_watch
    "sales_autopilot": 180,  # hourly :25 Sales Autopilot (gated SALES_AUTOPILOT_ENABLED); RUN_DUE_EXCLUDE; 3h dead-man grace
    "hq_auto_chase": 180,  # hourly :28 Hot Queue EMAIL chase (gated HQ_AUTO_CHASE); 3h grace
    "reply_auto_send": 180,  # hourly :30 known-prospect auto-reply (gated REPLY_AUTO_SEND); 3h grace
    "content_approval_sweep": 30 * 60,  # daily 04:30 orphaned-pending retirement (dry_run default)
    "daily_owner_brief": 30
    * 60,  # daily 08:10 owner brief + ntfy push (gated DAILY_OWNER_BRIEF_NTFY)
    "trial_nudge": 30
    * 60,  # daily 09:50 IST trial expiry/expired UPI nudge email (gated TRIAL_NUDGE_ENABLED; BLK-02)
}


# --------------------------------------------------------------------------- #
# PRODUCTIVITY dead-man (as opposed to the LIVENESS dead-man above)
#
# `record_run` captures that a job RAN and did not raise: {job, ok, s,
# duration_ms, note, at, trigger, started_at}. It captures nothing about whether
# the job DID anything. A job can therefore run daily, take 154s, report
# ok=True, produce zero output, and every dashboard stays green.
#
# That is not hypothetical. 2026-08-09 postmortem: `video_ad_cycle` was gated
# inert by a flag-alias bug for 15 days (2026-07-22 -> 2026-08-06) while the
# `content` job it rides heartbeat green throughout. What actually gave it away
# was that `video_ads.jsonl` stopped growing.
#
# So this registry watches the OUTPUT, not the job — which needs no change to
# any of the 44 staff jobs. Adding a producer here is how you make its silent
# death visible; that is deliberately a one-line change.
#
# `resolver` is a callable so it re-resolves at check time and uses the SAME
# path the producer writes (runtime root vs legacy `data/` differ per store).
# --------------------------------------------------------------------------- #
def _video_ads_store() -> str:
    from app.marketing import video_ad_cycle

    return str(video_ad_cycle._FILE)


def _content_approvals_store() -> str:
    from app.marketing import content_approval

    return str(content_approval._FILE())


OUTPUT_FRESHNESS: dict[str, dict[str, Any]] = {
    "video_ad_cycle": {
        "resolver": _video_ads_store,
        "max_stale_days": 8,  # 5-day cadence + grace; the real outage ran to 15
        "why": "per-client AI video ads — the 2026-08-09 silent 15-day outage",
        "owner_hint": "Video engine chup ho gaya — /app/automation ka video tab dekho",
    },
    "content_approvals": {
        "resolver": _content_approvals_store,
        "max_stale_days": 3,  # daily content engine; 3 days = two missed passes
        "why": "content engine output — nothing to approve means nothing was generated",
        "owner_hint": "Content banna band ho gaya — Isha ka daily job check karo",
    },
}


def stale_outputs() -> list[dict[str, Any]]:
    """Producers whose output store has not moved within its budget.

    A missing store counts as stale ONLY if it was expected to exist; an
    unreadable/absent path yields `age_days: None` and is reported as
    `unknown` rather than raising a false alarm, because a fresh deployment
    legitimately has no file yet. Never raises.
    """
    out: list[dict[str, Any]] = []
    now = _now()
    for name, spec in OUTPUT_FRESHNESS.items():
        try:
            path = spec["resolver"]()
            if not path or not os.path.isfile(path):
                out.append(
                    {
                        "producer": name,
                        "store": str(path or "?"),
                        "age_days": None,
                        "status": "unknown",
                        "max_stale_days": spec["max_stale_days"],
                        "why": spec["why"],
                        "owner_hint": spec.get("owner_hint", ""),
                    }
                )
                continue
            age_days = (now.timestamp() - os.path.getmtime(path)) / 86400.0
            if age_days > float(spec["max_stale_days"]):
                out.append(
                    {
                        "producer": name,
                        "store": path,
                        "age_days": round(age_days, 1),
                        "status": "stale",
                        "max_stale_days": spec["max_stale_days"],
                        "why": spec["why"],
                        "owner_hint": spec.get("owner_hint", ""),
                    }
                )
        except Exception as e:
            logger.debug("[automation-health] freshness check skip for %s: %s", name, e)
    return out


def _SKIPS() -> str:
    """Budget-skip ledger — SAME store family as job_runs.

    Deliberately resolved through ``runtime_data_authority`` like its siblings:
    a hardcoded ``data/...`` path would be written to the LEGACY location while
    live automation state lives under the runtime root, so the new signal would
    be invisible in prod for exactly the reason a stale ``data/job_heartbeats.json``
    fooled an audit on 2026-08-09.
    """
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="automation.job_runs",
            legacy_path=Path("data") / "job_engine_skips.jsonl",
            target_segments=("automation", "job_engine_skips.jsonl"),
        )
    )


def record_engine_skip(
    job: str, engine: str, reason: str = "budget_exhausted", **extra: Any
) -> None:
    """Record that a mega-job SKIPPED one of its engines. Never raises.

    Why this exists: `team_scheduler._run_content_engine` closes the coroutine and
    returns False when the wall-clock budget is gone — with no exception and no
    line naming the engine. Prod evidence 2026-08-09: the `content` job exceeded
    its 420s budget on **15 consecutive daily runs** (2026-07-18 → 2026-08-01,
    452–530s each), silently dropping every engine queued behind the overrun, and
    nothing anywhere recorded which ones. That is an entire class of "automation
    quietly stopped" that no dashboard could show.

    The warning is emitted BEFORE any persistence attempt on purpose: the write
    path below is best-effort, and a storage failure must not also swallow the
    signal we are adding precisely to stop silent loss.
    """
    job_s = str(job or "?")[:40]
    engine_s = str(engine or "?")[:40]
    reason_s = str(reason or "")[:60]
    logger.warning(
        "[automation-health] job '%s' SKIPPED engine '%s' (%s) - work did not run",
        job_s,
        engine_s,
        reason_s,
    )
    try:
        rec: dict[str, Any] = {
            "job": job_s,
            "engine": engine_s,
            "reason": reason_s,
            "at": _now().isoformat(timespec="seconds"),
        }
        for k, v in (extra or {}).items():
            rec[str(k)[:24]] = v if isinstance(v, int | float | bool) else str(v)[:120]
        path = _SKIPS()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[automation-health] engine-skip record failed: %s", e)


def recent_engine_skips(hours: int = 48, limit: int = 200) -> list[dict[str, Any]]:
    """Engine skips within the window, newest last. Never raises."""
    out: list[dict[str, Any]] = []
    try:
        cutoff = _now() - timedelta(hours=max(1, int(hours or 48)))
        for line in _tail_lines(_SKIPS(), max(1, min(int(limit or 200), 2000))):
            line = (line or "").strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            try:
                at = datetime.fromisoformat(str(rec.get("at") or ""))
                if at.tzinfo is None:
                    at = at.replace(tzinfo=timezone.utc)
                if at < cutoff:
                    continue
            except Exception:
                pass
            out.append(rec)
    except Exception as e:
        logger.debug("[automation-health] recent_engine_skips skip: %s", e)
    return out


def engine_skip_summary(hours: int = 48) -> dict[str, Any]:
    """`{engine: count}` rollup an operator can act on. Never raises."""
    rows = recent_engine_skips(hours=hours)
    by_engine: dict[str, int] = {}
    by_job: dict[str, int] = {}
    for r in rows:
        e = str(r.get("engine") or "?")
        j = str(r.get("job") or "?")
        by_engine[e] = by_engine.get(e, 0) + 1
        by_job[j] = by_job.get(j, 0) + 1
    return {
        "window_hours": int(hours),
        "total": len(rows),
        "by_engine": by_engine,
        "by_job": by_job,
        "latest": rows[-5:],
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _alerts_enabled() -> bool:
    return os.environ.get("AUTOMATION_HEALTH_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def record_run(
    job: str,
    ok: bool = True,
    seconds: float = 0.0,
    note: str = "",
    *,
    error_class: str = "",
    error_message: str = "",
    trigger: str = "",
    started_at: str = "",
) -> None:
    """Job-run heartbeat (scheduler wrapper se). KABHI raise nahi, fast.

    Enriched fields (additive, keyword-only) — sirf non-empty pe jsonl record me
    likhe jaate hain taaki PURANE records (bina in fields ke) readable rahein aur
    old positional callers (`record_run(job, ok, sec, note)`) unchanged chalein:
      - error_class    : exception ka type-name (ya "job_reported_failure" jab inner
                         ne sirf False diya, detail bina)
      - error_message  : str(exception), ~300 char cap
      - trigger        : run ka source ("scheduler" etc.)
      - started_at     : run start ISO-UTC (duration `s` ke saath timeline reconstruct)
    """
    try:  # W1.13: per-job Prometheus counters (independent try — heartbeat pe asar na ho)
        from app.platform import job_metrics

        job_metrics.record(job, ok, seconds)
    except Exception:
        pass
    try:
        rec = {
            "job": (job or "?")[:30],
            "ok": bool(ok),
            "s": round(float(seconds), 2),
            "duration_ms": round(float(seconds) * 1000),
            "note": (note or "")[:120],
            "at": _now().isoformat(timespec="seconds"),
        }
        # additive fields — sirf non-empty pe (purane records + snapshot readable rahein)
        if error_class:
            rec["error_class"] = str(error_class)[:60]
        if error_message:
            rec["error_message"] = str(error_message)[:300]
        if trigger:
            rec["trigger"] = str(trigger)[:20]
        if started_at:
            rec["started_at"] = str(started_at)[:40]
        # Resolver at each I/O site — binding to a local unbinds the allowlist (A3).
        os.makedirs(os.path.dirname(_RUNS()) or ".", exist_ok=True)
        with open(_RUNS(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # latest-per-job snapshot (fast reads) — READ-MODIFY-WRITE, isliye
        # cross-process lock + atomic replace (web 2 workers + celery workers
        # ek saath record_run kar sakte = snapshot corrupt ho sakta tha).
        from app.utils.file_lock import file_lock

        with file_lock(_BEATS()):
            beats: dict[str, Any] = {}
            try:
                if os.path.exists(_BEATS()):
                    with open(_BEATS(), encoding="utf-8") as f:
                        beats = json.load(f) or {}
            except Exception:
                beats = {}
            beats[rec["job"]] = rec
            tmp = f"{_BEATS()}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(beats, f, ensure_ascii=False)
            os.replace(tmp, _BEATS())
    except Exception:
        pass


def _tail_lines(path: str, max_lines: int) -> list[str]:
    """File ke END se ~max_lines lines — bounded read (chunk-wise backward), file
    kitni bhi badi ho poora load NAHI karta. Kabhi raise nahi, fail = []."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            block = 65536
            data = b""
            while pos > 0 and data.count(b"\n") <= max_lines:
                read_size = min(block, pos)
                pos -= read_size
                f.seek(pos)
                data = f.read(read_size) + data
                if len(data) > 4 * 1024 * 1024:  # 4MB hard cap — runaway se bacho
                    break
        return data.decode("utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception:
        return []


def run_history(
    job: str = "",
    status: str = "",
    limit: int = 100,
    failures_first: bool = False,
) -> list[dict[str, Any]]:
    """Per-run history (data/job_runs.jsonl) — NEWEST-FIRST, filtered. Read-side of
    record_run (jsonl pehle write-only tha, koi padhta hi nahi tha).

    - job     : substring match (case-insensitive) on job name ("" = all)
    - status  : "ok" | "failed" (aur "fail") | "" = all
    - limit   : max records (1..500 cap)
    - failures_first : failed runs ko top pe le aao (stable — group ke andar newest-first)
    File na ho / corrupt line = gracefully skip. Kabhi raise nahi."""
    try:
        limit = max(1, min(int(limit or 100), 500))
    except Exception:
        limit = 100
    if not os.path.exists(_RUNS()):
        return []
    job_f = (job or "").strip().lower()
    status_f = (status or "").strip().lower()
    # tail se limit ka multiple padho (bounded) taaki filter ke baad bhi kaafi bache
    hard = max(limit * 5, 500) if failures_first else max(limit * 3, limit)
    raw = _tail_lines(_RUNS(), min(hard, 5000))
    out: list[dict[str, Any]] = []
    for line in reversed(raw):  # file chronological => reversed = newest-first
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        if job_f and job_f not in str(rec.get("job", "")).lower():
            continue
        if status_f == "ok" and not rec.get("ok"):
            continue
        if status_f in ("failed", "fail") and rec.get("ok"):
            continue
        out.append(rec)
        # failures_first ke liye thoda extra chahiye (sort ke baad top-limit); warna
        # newest-first me pehle limit hi kaafi hai.
        if not failures_first and len(out) >= limit:
            break
        if failures_first and len(out) >= max(limit * 3, 300):
            break
    if failures_first:
        # stable sort: failed (0) pehle, ok (1) baad — group ke andar newest-first bana rahe
        out.sort(key=lambda r: 0 if not r.get("ok") else 1)
    return out[:limit]


def queue_depth() -> dict[str, Any]:
    """Celery queue backlog (Redis llen). Backlog badhta jaye = worker mar gaya/slow.
    Redis na ho to {-1} (unknown). Kabhi raise nahi."""
    out = {"celery": -1, "heavy": -1, "dlq": -1, "dead": -1}
    try:
        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
        out["celery"] = int(r.llen("celery") or 0)
        out["heavy"] = int(r.llen("heavy") or 0)  # heavy staff-jobs queue (CELERY_HEAVY_QUEUE)
        out["dlq"] = int(r.llen("dlq:failed_tasks") or 0)
        out["dead"] = int(r.llen("dlq:dead") or 0)  # dlq_retry: retry-exhausted/unknown
    except Exception:
        pass
    return out


QUEUE_BACKLOG_ALERT = 50  # itne pending tasks = worker problem


def wiring_gaps() -> list[dict[str, Any]]:
    """'Flag ON but backend missing' — armed automation jo silently no-op kar
    rahi hai (config gap, not a runtime outage). Surfaced so admin can see
    "ON" flags that are not actually connected. Kabhi raise nahi."""
    gaps: list[dict[str, Any]] = []

    def _on(flag: str) -> bool:
        return (os.getenv(flag, "0") or "0").strip().lower() in ("1", "true", "yes")

    # CRM sync: armed but no provider wired (Zoho refresh token / HubSpot key)
    if _on("CRM_SYNC") or _on("CRM_SYNC_PULL"):
        try:
            from app.platform import crm_sync

            st = crm_sync.status() or {}
            if str(st.get("provider") or "none") == "none":
                gaps.append(
                    {
                        "key": "CRM_SYNC",
                        "flag_on": True,
                        "missing": "zoho_refresh_token / hubspot_api_key",
                        "note": "CRM sync armed but no provider wired — qualified leads CRM me push nahi ho rahe",
                    }
                )
        except Exception:
            pass

    # GSC: armed but no usable service-account creds. Reuse gsc.enabled() — the
    # canonical gate — so the `google_sheets_credentials` fallback and the
    # `os.path.exists(creds)` check are honoured instead of re-implemented here
    # (a manual GSC_SERVICE_ACCOUNT_JSON-only check would FALSE-ALARM when the
    # owner wires GSC through the fallback source).
    if _on("GSC_ENABLED"):
        try:
            from app.integrations import gsc

            if not gsc.enabled():
                gaps.append(
                    {
                        "key": "GSC_ENABLED",
                        "flag_on": True,
                        "missing": "GSC_SERVICE_ACCOUNT_JSON / google_sheets_credentials",
                        "note": "Google Search Console rank tracking armed but no usable service-account creds",
                    }
                )
        except Exception:
            pass

    # Social engine: armed but no Postiz key AND no WhatsApp backend
    if _on("SOCIAL_ENGINE"):
        try:
            from app.integrations import whatsapp_selfhost as ws
            from app.marketing import postiz_publish

            has_postiz = postiz_publish.enabled()
            has_whatsapp = ws.is_active_provider()
            if not has_postiz and not has_whatsapp:
                gaps.append(
                    {
                        "key": "SOCIAL_ENGINE",
                        "flag_on": True,
                        "missing": "POSTIZ_API_KEY / WAHA",
                        "note": "Social engine armed but no publish backend (Postiz key + WAHA dono missing)",
                    }
                )
        except Exception:
            pass

    # WhatsApp auto-send: armed but WAHA not the active configured provider
    if _on("WHATSAPP_AUTO_SEND"):
        try:
            from app.config import settings
            from app.integrations import whatsapp_selfhost as ws

            cloud_token = bool(getattr(settings, "whatsapp_business_token", "") or "")
            if not ws.is_active_provider() and not cloud_token:
                gaps.append(
                    {
                        "key": "WHATSAPP_AUTO_SEND",
                        "flag_on": True,
                        "missing": "WAHA_BASE_URL / whatsapp_business_token",
                        "note": "WhatsApp auto-send armed but no WA backend configured",
                    }
                )
        except Exception:
            pass

    return gaps


def health() -> dict[str, Any]:
    """Per-job: last run, ok, overdue? + overall status. Kabhi raise nahi."""
    beats: dict[str, Any] = {}
    try:
        if os.path.exists(_BEATS()):
            with open(_BEATS(), encoding="utf-8") as f:
                beats = json.load(f) or {}
    except Exception:
        beats = {}
    # ONE authoritative instant for the whole evaluation.
    #
    # `marker_still_active(now=_now())` already used the injected seam, but
    # `_job_due_today()` / `_job_due_yet()` read the wall clock independently —
    # so a single classification could combine two different instants, and (since
    # they answer weekday/window questions) two different DAYS. That made the
    # result depend on when the process happened to run, which is why
    # test_same_day_boot_grace_after_window_is_recoverable began failing on a
    # real-world date change rather than on any code change.
    now = _now()
    jobs: list[dict[str, Any]] = []
    overdue: list[str] = []
    never_ran: list[str] = []
    for job, gap_min in EXPECTED_GAP_MIN.items():
        b = beats.get(job)
        # User mandate HARD OFF (CLAUDE §5): platform_dial must not cry wolf as
        # never_ran/overdue while intentionally killed. Surface mandate_paused.
        if job == "platform_dial":
            try:
                from app.platform import platform_dial as _pd

                if not _pd.enabled():
                    jobs.append(
                        {
                            "job": job,
                            "last_run": (b or {}).get("at") if b else None,
                            "status": "mandate_paused",
                            "note": "platform_dial disabled (env/state) — compliance gates unchanged",
                        }
                    )
                    continue
            except Exception:
                pass
        if not b and (not _job_due_today(job, now=now) or not _job_due_yet(job, now=now)):
            jobs.append(
                {
                    "job": job,
                    "last_run": None,
                    "status": "scheduled_off",
                }
            )
            continue
        if not b:
            never_ran.append(job)
            jobs.append({"job": job, "last_run": None, "status": "never_ran"})
            continue
        try:
            last = datetime.fromisoformat(str(b.get("at")))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            # A worker boot inside a heavy-job restart-protection window
            # intentionally skips and defers the job. Keep that event visible
            # as scheduled_off ONLY while the heavy window is still active.
            # After the window ends, a lone boot_grace marker usually means the
            # deferred countdown was lost (recreate/broker) — force overdue even
            # if the daily EXPECTED_GAP has not elapsed yet, so run_due recovers
            # the same day (content gap is 30h — without this, miss stays silent).
            if str(b.get("note") or "") == "boot_grace":
                try:
                    from app.platform.boot_grace import marker_still_active

                    if marker_still_active(job, last, now=now) and _job_due_today(job, now=now):
                        jobs.append(
                            {
                                "job": job,
                                "last_run": b.get("at"),
                                "last_ok": b.get("ok"),
                                "duration_s": b.get("s"),
                                "status": "scheduled_off",
                                "note": "boot_grace",
                            }
                        )
                        continue
                    if _job_due_today(job, now=now) and _job_due_yet(job, now=now):
                        overdue.append(job)
                        jobs.append(
                            {
                                "job": job,
                                "last_run": b.get("at"),
                                "last_ok": b.get("ok"),
                                "duration_s": b.get("s"),
                                "status": "overdue",
                                "note": "boot_grace_lost_defer",
                            }
                        )
                        continue
                except Exception:
                    pass
            # Captured instant, not a fresh read: re-reading here would let a
            # long evaluation compare different jobs against different "now"s.
            is_over = now - last > timedelta(minutes=gap_min)
            status = "overdue" if is_over else ("ok" if b.get("ok") else "last_failed")
            if is_over:
                overdue.append(job)
            jobs.append(
                {
                    "job": job,
                    "last_run": b.get("at"),
                    "last_ok": b.get("ok"),
                    "duration_s": b.get("s"),
                    "status": status,
                    "note": b.get("note") or "",
                }
            )
        except Exception:
            jobs.append({"job": job, "status": "unknown"})
    q = queue_depth()
    # Redis unreachable → depths stay -1. Must NOT read as healthy/empty queues
    # on the UI (false-green zeros). Do NOT use `v or -1` — 0 is a valid depth.
    queue_unknown = any(int(q.get(k, -1)) < 0 for k in ("celery", "heavy", "dlq", "dead"))
    backlogged = (
        q.get("celery", -1) > QUEUE_BACKLOG_ALERT or q.get("heavy", -1) > QUEUE_BACKLOG_ALERT
    )
    # ADR-104 Phase B (2026-07-15): queue_depth() already tracks dlq/dead
    # counts but NOTHING read them here — this function's overall status/ok
    # could claim "healthy"/True even with dead=4 sitting in dlq:dead
    # (retry-exhausted via dlq_retry.py, needs manual attention) or terminal
    # failures sitting in dlq:failed_tasks (dlq_retry sweeps these, but a
    # disabled flag / queue-flood-defer / missed sweep can leave them stuck).
    # These are a DIFFERENT signal from `backlogged` (live-queue depth = worker
    # slow/dead) — a dead/dlq item is a standing incident regardless of how
    # fast the live queues are draining, and the admin's "green = dead=0,
    # retryable_failed=0" expectation was silently unmet. -1 means "Redis
    # unreachable, unknown" and must NOT read as "0 dead" (that would recreate
    # the exact false-green bug this fixes) — only a positive count counts.
    dead_present = q.get("dead", -1) > 0
    retryable_failed_present = q.get("dlq", -1) > 0
    # Obsidian staging health
    _obs_ok = False
    _obs_detail = "OBSIDIAN_SYNC not enabled"
    try:
        from pathlib import Path

        if os.getenv("OBSIDIAN_SYNC", "0") in ("1", "true"):
            _vault = Path("data/obsidian_staging")
            if _vault.exists():
                _files = list(_vault.rglob("*.md"))
                _obs_ok = len(_files) > 0
                _obs_detail = f"{len(_files)} notes in staging"
            else:
                _obs_detail = "staging dir missing"
    except Exception as e:
        _obs_detail = str(e)[:100]
    # Engines silently dropped by a mega-job's wall-clock budget. This is a REAL
    # outage class (work simply did not run) that no previous field exposed, so it
    # counts toward `unhealthy` — otherwise the dashboard keeps saying "healthy"
    # while an engine has been skipped every day for two weeks.
    try:
        skips = engine_skip_summary(hours=48)
    except Exception:
        skips = {"total": 0, "by_engine": {}, "by_job": {}, "latest": []}
    engines_skipped = bool(skips.get("total"))
    # A producer that is green but has stopped producing is an outage the
    # liveness dead-man cannot see (2026-08-09: 15 days of it). Only genuinely
    # STALE entries degrade health — "unknown" (store absent yet) must not.
    try:
        outputs = stale_outputs()
    except Exception:
        outputs = []
    outputs_stale = any(o.get("status") == "stale" for o in outputs)
    unhealthy = bool(
        overdue
        or backlogged
        or dead_present
        or retryable_failed_present
        or engines_skipped
        or outputs_stale
    )
    return {
        "engine_skips": skips,
        "engines_skipped_recently": engines_skipped,
        "stale_outputs": outputs,
        "outputs_stale": outputs_stale,
        "status": ("degraded" if unhealthy else ("warming_up" if never_ran else "healthy")),
        # Explicit boolean truth for consumers — pehle sirf `status` string tha, jisse
        # `h.get("ok")` KABHI None deta tha (team_pulse._kavya `h.get("ok", True)` = hamesha
        # "OK" bolta tha even jab jobs overdue/queue-backlogged the → false-healthy). Ab
        # additive `ok` = degraded ka inverse (warming_up abhi-boot = ok, alarm nahi).
        # Phase B (2026-07-15): dead/retryable_failed ab isi inverse me shaamil —
        # dead tasks ya stuck DLQ failures ho to `ok` False hona CHAHIYE.
        # ADR-114: Redis unknown (-1) does NOT force ok=False (ADR-104 contract) —
        # but queue_available=false so UI must not paint DLQ/celery as 0.
        "ok": not unhealthy,
        "overdue": overdue,
        "never_ran": never_ran,
        "queue": q,
        "queue_available": not queue_unknown,
        "queue_backlogged": backlogged,
        "dead_tasks_present": dead_present,
        "retryable_failed_present": retryable_failed_present,
        "jobs": jobs,
        "wiring_gaps": wiring_gaps(),
        "obsidian_sync": {"ok": _obs_ok, "detail": _obs_detail},
        "at": _now().isoformat(timespec="seconds"),
    }


async def run_watch() -> dict[str, Any]:
    """Watchdog hook: overdue jobs → (gated) email alert. Kabhi raise nahi."""
    try:
        h = health()
        if h.get("queue_backlogged") and _alerts_enabled():
            notify = os.environ.get("NOTIFY_EMAIL", "").strip()
            if notify:
                try:
                    from app.integrations.email_sender import email_sender

                    await email_sender.send_email(
                        [notify],
                        f"⚠️ Celery backlog: {h['queue'].get('celery')} tasks pending",
                        "Worker slow/mar gaya lagta hai. Check: docker logs leadgen_worker (automation_health)",
                    )
                except Exception:
                    pass
        if h["overdue"] and _alerts_enabled():
            notify = os.environ.get("NOTIFY_EMAIL", "").strip()
            if notify:
                try:
                    from app.integrations.email_sender import email_sender

                    await email_sender.send_email(
                        [notify],
                        f"⚠️ Automation DEAD-MAN alert: {len(h['overdue'])} job(s) overdue",
                        "Yeh scheduled jobs expected time pe NAHI chale:\n\n- "
                        + "\n- ".join(h["overdue"])
                        + "\n\nCelery worker/scheduler containers check karo: docker ps | grep leadgen. "
                        "(automation_health dead-man switch)",
                    )
                except Exception as e:
                    logger.warning(f"[automation_health] alert failed: {e}")
        try:
            from app.platform import team

            team.log_event(
                "kavya",
                "automation_health",
                f"{h['status']}: {len(h['overdue'])} overdue, {len(h['never_ran'])} never-ran",
                status="ok" if h["status"] == "healthy" else "warn",
            )
        except Exception:
            pass
        return h
    except Exception as e:
        logger.warning(f"[automation_health] run_watch failed: {e}")
        return {"error": str(e)}
