from __future__ import annotations

import asyncio
import json
import os
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_TICK_S = 60

# Soft-limit headroom for the Celery staff-job that runs ``prospect`` (~540s soft).
# Keep this in sync with the 480s wall used below when computing post-prospect remain.
_PROSPECT_SOFT_BUDGET_S = 480.0


def post_prospect_harvest_timeout(remain_s: float) -> float | None:
    """Seconds to give the inline post-prospect harvest, or None to skip.

    WS3 (2026-08-07): after D1 raised Places query fan-out, the nested harvest
    still died under a hard ``min(remain-20, 120)`` outer wait_for while
    ``run_harvest_loop_safe`` independently defaulted ``HARVEST_LOOP_TIMEOUT_S``
    to 120 — websearch/opendata (the bulk of 08-05 lead yield) never finished.
    Midday/evening harvest jobs still run; this only fixes the morning nest.

    Env:
      PROSPECT_INLINE_HARVEST — default ON; set 0 to skip (midday covers).
      PROSPECT_POST_HARVEST_BUDGET_S — default 240, clamped 30..300.
    """
    if os.environ.get("PROSPECT_INLINE_HARVEST", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return None
    if remain_s < 45.0:
        return None
    try:
        budget = float(os.environ.get("PROSPECT_POST_HARVEST_BUDGET_S", "240") or "240")
    except Exception:
        budget = 240.0
    budget = max(30.0, min(budget, 300.0))
    return min(max(0.0, remain_s - 30.0), budget)


# Active wall-clock budget for mega-jobs that fan out via `_run_content_engine`.
_active_job_budget: ContextVar[Any] = ContextVar("active_job_budget", default=None)

# --------------------------------------------------------------------------- #
# Single-instance lock — uvicorn --workers 2 dono workers scheduler start karte
# the → har job 2 baar chalta tha (double emails/content!). Lock file se sirf
# EK worker scheduler chalata hai. Heartbeat (mtime) + dead-PID reclaim:
# - lock free/stale (>180s) ya PID dead → acquire karo
# - warna skip (dusra worker owner hai)
# Loop har tick lock ka mtime refresh karta hai (heartbeat).
# --------------------------------------------------------------------------- #
_LOCK_PATH = os.path.join("data", ".scheduler.lock")
_LOCK_STALE_S = 180
_have_lock = False


def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness check. ⚠️ Windows pe os.kill(pid, 0) KABHI nahi —
    signal 0 == CTRL_C_EVENT → apne hi console group ko Ctrl+C chala jata hai
    (pytest/dev-runs randomly KeyboardInterrupt se marte the). POSIX pe hi os.kill."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _acquire_lock() -> bool:
    """True agar is process ne scheduler-lock le liya. Atomic + stale-reclaim."""
    global _have_lock
    try:
        os.makedirs(os.path.dirname(_LOCK_PATH) or ".", exist_ok=True)
        try:
            fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            _have_lock = True
            return True
        except FileExistsError:
            # exists — steal SIRF proven-stale (mtime purana = heartbeat nahi) ya
            # proven-dead owner pe. Unreadable/empty lock proof NAHI hai — empty
            # file dusre worker ke os.open→os.write ke beech ki race-window hai;
            # wahan steal = dono worker scheduler chalate (double emails/content).
            # Crashed-mid-write owner ka reclaim mtime-staleness se ho jata hai
            # (heartbeat _refresh_lock har tick mtime update karta hai).
            stale = False
            try:
                stale = (datetime.now().timestamp() - os.path.getmtime(_LOCK_PATH)) > _LOCK_STALE_S
            except Exception as le:
                stale = False  # mtime unreadable → stale PROVE nahi hua
                logger.warning(
                    "[team-scheduler] lock mtime unreadable — fail-closed skip "
                    "(no steal without proof): %s",
                    le,
                )
            dead = False
            if not stale:
                try:
                    pid = int(open(_LOCK_PATH).read().strip() or "0")
                    dead = pid > 0 and not _pid_alive(pid)
                except Exception as le:
                    dead = False  # pid unreadable → dead PROVE nahi hua
                    logger.warning(
                        "[team-scheduler] lock pid unreadable — fail-closed skip "
                        "(no steal without proof): %s",
                        le,
                    )
            if stale or dead:
                try:
                    with open(_LOCK_PATH, "w") as f:
                        f.write(str(os.getpid()))
                    _have_lock = True
                    return True
                except Exception:
                    return False
            return False
    except Exception as e:
        # lock-fs issue — FAIL-CLOSED (W1.1): is worker ko lock NAHI dena. Purana
        # fail-open dono uvicorn workers ko same FS-error pe scheduler start karwa
        # deta tha → har job double-fire (double emails/content/spend + ban-risk).
        # NOTE: _acquire_lock() boot-once hai (sirf start_scheduler) — yahan skip ka
        # matlab is worker pe scheduler process-restart tak DOWN (koi next-tick retry
        # nahi). Isiliye loud warn = ops ke liye recovery signal.
        logger.warning(
            "[team-scheduler] lock acquire failed — FAIL-CLOSED, scheduler NOT "
            "starting on this worker (avoids double-fire): %s",
            e,
        )
        _have_lock = False
        return False


def _refresh_lock() -> None:
    """Heartbeat — lock file ka mtime update (owner zinda hai)."""
    if not _have_lock:
        return
    try:
        os.utime(_LOCK_PATH, None)
    except Exception:
        pass


_last_ran: dict[str, str | None] = {
    "growth": None,
    "ops": None,
    "qa": None,
    "trainer": None,
    "prospect": None,
    "digest": None,
    "content": None,
    "email_outreach": None,
    "blog": None,
    "reply_triage": None,
    "watchdog": None,
    "onboard": None,
    "standup": None,
    "hot_queue_brief": None,  # daily 08:15: health-gated Office HQ revenue brief
    "hot_queue_owner_pack": None,  # daily 09:00: CSV+MD+nfty — owner 1-click close (ADR-OWNER-1)
    # F.5 engineer agents — gated by per-role flag inside run_X() (INERT default).
    "engineer_sre": None,  # hourly: Pranav reliability score
    "engineer_finops": None,  # daily: Vidya margin score
    "engineer_security": None,  # daily: Arnav compliance posture
    "engineer_dbre": None,  # daily 10:00: Kabir Postgres reliability (gated DBRE_AGENT)
    "engineer_dataquality": None,  # daily 10:30: Diya lead/CRM integrity (gated DATA_INTEGRITY_AGENT)
    "engineer_deps": None,  # weekly Sun 04:30: Aryan dependency CVE audit (gated DEPS_AGENT)
    "mcp_engineer": None,  # council 2026-06-26: Arya MCP health pulse (hourly, gated MCP_ENGINEER)
    "readiness_digest": None,  # G.3: daily activation-readiness ntfy digest (OPS_ALERTS gated)
    "pipeline": None,  # daily: lead rescore + hot-lead surfacing (Neha/Rohan)
    "email_followup": None,  # daily afternoon: Day-3/7 followups only
    "kb_refresh": None,  # weekly Sun: contextual KB re-ingest (gated)
    "midday_prospect": None,  # daily 14:30: 2nd free lead-supply pass (gated MIDDAY_PROSPECT)
    "evening_wrap": None,  # daily 18:30: EOD summary + hot recap
    "call_kpi_digest": None,  # daily 19:30: Lekha call-KPI digest (fixes missing log_event wiring)
    "weekly_marketing": None,  # Wed 12:30: S-tier niche pack bank
    "saturday_hygiene": None,  # Sat 04:00: DLQ + celery trim (gated SCHEDULER_HYGIENE)
    "meter_watch": None,  # hourly :55: billing meter-failure watcher (gated METER_ALERTS)
    "process_autostart": None,  # daily ~11:30 IST: process-engine auto-start (gated PROCESS_AUTOSTART)
    "revenue_snapshot": None,  # daily ~00:15 IST: B1 MRR/churn snapshot (gated REVENUE_TRENDS)
    "flow_cron": None,  # every 5 min: Flow Runner cron scan (gated FLOW_RUNNER + FLOW_AUTO_TRIGGERS)
    "afternoon_content": None,  # daily 15:00: 2nd content-gen pass (gated AFTERNOON_CONTENT)
    "evening_prospect": None,  # daily 17:00: 3rd free lead-harvest pass (gated EVENING_PROSPECT)
    "obsidian_push": None,  # daily 02:15 IST: compact + git push to Obsidian vault (gated OBSIDIAN_SYNC)
    "daily_video": None,  # daily 09:45 IST: per-client video producer, enqueue-only (gated DAILY_VIDEO_ENABLED)
    "platform_dial": None,  # daily 11:30 IST: LeadGen AI self-sale outbound calls (gated PLATFORM_DIAL_DAILY)
    "product_one_health": None,  # hourly :20: Product 1 Customer Health + Approval Reminder + SLA Recovery sweep (ungated safety-net, mirrors watchdog/onboard)
    "approval_email_sweep": None,  # hourly :40: bounded pending-approval EMAIL sweep (gated APPROVAL_EMAIL_NOTIFY, single-flight)
    "social_drain": None,  # hourly :10: native social queue drain (gated SOCIAL_ENGINE)
    "sales_autopilot": None,  # hourly :25: Sales Autopilot canary tick (gated SALES_AUTOPILOT_ENABLED; INERT off)
    "task_lease_reap": None,  # hourly :05: expired agent-task lease reclaim (gated AGENT_TASK_LEASE_REAP; INERT off)
    "gsc_rank": None,  # daily 00:30 IST: Google Search Console rank snapshot (gated GSC_ENABLED)
    "hq_auto_chase": None,  # hourly: unactioned inquiry cards -> automated EMAIL follow-up (gated HQ_AUTO_CHASE; INERT off)
    "reply_auto_send": None,  # hourly :30: safe known-prospect auto-reply sweep (gated REPLY_AUTO_SEND; INERT off)
    "content_approval_sweep": None,  # daily 04:30: orphaned-pending approval retirement (gated CONTENT_APPROVAL_SWEEP; dry_run default)
    "daily_owner_brief": None,  # daily 08:10: owner brief + ntfy push (gated DAILY_OWNER_BRIEF_NTFY)
    "trial_nudge": None,  # daily 09:50: trial expiry/expired Starter UPI nudge EMAIL (gated TRIAL_NUDGE_ENABLED)
    "whatsapp_automation": None,  # hourly: WhatsApp automation (gated WHATSAPP_AUTO_SEND; INERT off)
    "heartbeat": None,  # every 5m: owner alive heartbeat
    "content_approval_notify": None,  # hourly :40: pending-approval notify (gated CONTENT_APPROVAL_NOTIFY; INERT off)
}


# W1.7: _last_ran ko disk pe persist karo — in-memory dict restart pe reset ho jata tha,
# jisse hourly/slot jobs (ops/growth/flow_cron) same window me RE-FIRE karte the. File
# data/ me (already gitignored via `data/*`, .scheduler.lock jaisa runtime-state). Sirf
# in-process/rollback scheduler ke liye (prod = Celery beat). Load boot pe, save har
# badle-hue tick pe. (Behaviour-change: ek failed period-job ab restart pe us window me
# retry NAHI hoga — durable marker; dead-man switch (W1.2) failure surface karta hai.)
_LAST_RAN_PATH = os.path.join("data", "scheduler_last_ran.json")

# In-process-only day key — intentionally outside _last_ran (parity / Aaj tab).
_renewal_reminders_day: str | None = None


def _save_last_ran() -> None:
    """_last_ran atomic-write (tmp + os.replace) — corrupt file se bacho. Fail-safe."""
    try:
        os.makedirs(os.path.dirname(_LAST_RAN_PATH) or ".", exist_ok=True)
        tmp = _LAST_RAN_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_last_ran, f)
        os.replace(tmp, _LAST_RAN_PATH)
    except Exception as e:
        logger.debug("[team-scheduler] last_ran persist failed: %s", e)


def _load_last_ran() -> None:
    """Boot pe persisted markers load karo — sirf known keys + str values merge
    (unknown/garbage ignore). File na ho ya corrupt ho to defaults (all-None) rahein."""
    try:
        with open(_LAST_RAN_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:
        logger.debug("[team-scheduler] last_ran load failed: %s", e)
        return
    if isinstance(data, dict):
        for k in _last_ran:
            v = data.get(k)
            if isinstance(v, str):
                _last_ran[k] = v


async def _run_job(
    job: str,
    retry_count: int = 0,
    *,
    idempotency_key: str = "",
) -> bool:
    """Use workforce dispatch for allowlisted safe jobs; otherwise direct rollback."""
    try:
        from app.platform.workforce_runtime.scheduled import maybe_dispatch

        routed = await maybe_dispatch(
            job,
            retry_count=retry_count,
            idempotency_key=idempotency_key,
        )
        if routed is not None:
            logger.info(
                "[team-scheduler] workforce routed job=%s provider=%s status=%s",
                job,
                routed.provider,
                routed.status,
            )
            return routed.status not in {"failed", "enqueue_failed"}
    except Exception as exc:
        # A configured DSH route may have an unknown outcome. Never fall through
        # to a second execution that could duplicate a side effect.
        logger.warning(
            "[team-scheduler] workforce dispatch failed job=%s error=%s",
            job,
            type(exc).__name__,
        )
        return False
    return await _run_job_direct(job, retry_count=retry_count)


async def _run_job_direct(job: str, retry_count: int = 0) -> bool:
    """Heartbeat wrapper — har run automation_health me record hota (dead-man
    switch: job chupchaap band ho jaye to overdue-alert). In-process + Celery
    dono path isi se guzarte. Wrapper KABHI behaviour change nahi karta.
    `retry_count` = Celery `run_staff_job` se aata (in-process path = 0) taaki
    admin Automation Runs panel me is run ka attempt-number dikhe (ADR-065 p2)."""
    import time as _time

    # Owner OS global scheduler kill + V1.1 per-agent scheduled/drain/claim gates.
    # Already-running tasks are not preempted here; resume does not catch-up.
    try:
        from app.platform.owner_os import record_scheduler_skip, scheduler_dispatch_allowed

        allowed, reason = scheduler_dispatch_allowed(job=job)
        if not allowed:
            record_scheduler_skip(job, reason, source="team_scheduler._run_job")
            logger.info(f"[team-scheduler] job '{job}' skipped — {reason}")
            return True
    except Exception:
        pass  # FAIL-OPEN — store blip pe job normal chalega
    try:
        from app.platform import owner_agent_execution as oae
        from app.platform.owner_os import record_scheduler_skip

        claim_ok, claim_reason = oae.claim_allowed(job=job)
        if not claim_ok:
            record_scheduler_skip(job, claim_reason, source="team_scheduler._run_job_claim")
            logger.info(f"[team-scheduler] job '{job}' claim blocked — {claim_reason}")
            return True
    except Exception:
        pass

    # Admin scheduler toggle (scheduler_config, FAIL-OPEN): admin ne job PAUSE
    # kiya ho to skip — heartbeat "admin_paused" note ke saath record hota
    # taaki dead-man overdue alert na bajaye. Dono paths (in-process + Celery)
    # isi choke-point se guzarte, isliye toggle universal hai.
    try:
        from app.platform import scheduler_config as _sc

        if not _sc.is_enabled(job):
            from app.platform import automation_health as _ah

            _ah.record_run(job, True, 0.0, note="admin_paused")
            try:
                from app.platform.automation_log_service import log_event as _log_auto

                _log_auto(
                    client_id="",
                    job_type=job,
                    status="skipped",
                    output_summary="admin_paused",
                    triggered_by="scheduler",
                    meta_json={"phase": "skipped", "reason": "admin_paused"},
                )
            except Exception:
                pass
            logger.info(f"[team-scheduler] job '{job}' skipped — admin paused")
            return True
    except Exception:
        pass  # FAIL-OPEN — config error pe job normal chalega

    from datetime import datetime as _dt
    from datetime import timezone as _tz

    _t0 = _time.monotonic()
    _started_at = _dt.now(_tz.utc).isoformat(timespec="seconds")  # run start (ISO-UTC)
    _ok = True
    _err_class = ""
    _err_msg = ""
    _log_id = ""
    try:
        from app.platform.automation_log_service import log_event as _log_auto

        _log_id = _log_auto(
            client_id="",
            job_type=job,
            status="running",
            started_at=_started_at,
            triggered_by="scheduler",
            meta_json={"phase": "start"},
        )
    except Exception:
        pass
    # --- Paperclip Routine Bridge: every cron run → auditable AgentTask ---
    # Unconditional until 2026-08-06 — one row per job invocation, ~700/day,
    # with no retention/prune anywhere in the codebase. `begin()` below stops
    # those rows LEAKING as `pending`, but they are still written: the fix turns
    # an unbounded leak into unbounded correct growth (~255k rows/year), and the
    # real outcome of every one of these jobs is already in `automation_logs`.
    # ROUTINE_TASK_LEDGER defaults ON = current behaviour preserved; set 0 to
    # stop writing the duplicate ledger without touching the jobs themselves.
    _routine_task_id = None
    try:
        from app.platform import agent_task_queue as atq

        _rt = (
            await atq.assign(
                job,
                f"Scheduled routine: {job}",
                delegated_by="scheduler",
            )
            if atq.routine_ledger_enabled()
            else {}
        )
        _routine_task_id = _rt.get("id") if _rt.get("ok") else None
        if _routine_task_id:
            # begin() = pending -> running. This used to call start(), which
            # requires `claimed` — a state a self-assigned routine never enters
            # because nothing calls claim_next() for a job-name pseudo-agent.
            # So start() no-op'd, complete() (claimed|running) no-op'd too, and
            # every SUCCEEDING routine leaked a `pending` row forever while only
            # FAILING ones closed (fail() accepts pending). 12,631 orphans by
            # 2026-08-06.
            await atq.begin(_routine_task_id)
    except Exception:
        pass

    try:
        # W1.2: _run_job_inner ab bool deta — False = job-level fail (dead-man
        # switch ko real status jaana chahiye). Re-raise NAHI: scheduler_loop poore
        # tick ko ek hi try me chalata hai, to yahan raise = is tick ke baaki jobs skip.
        _res = await _run_job_inner(job)
        _ok = _res is not False

        # Routine bridge: complete task
        if _routine_task_id:
            try:
                if _ok:
                    await atq.complete(_routine_task_id, result=f"routine {job} ok")
                else:
                    await atq.fail(_routine_task_id, f"routine {job} returned False")
            except Exception:
                pass
        if _res is False:
            # inner ne apna exception khud pakad ke sirf False diya — yahan detail
            # nahi milti (inner ke internals refactor nahi karte), isliye generic marker.
            _err_class = "job_reported_failure"
    except Exception as _e:
        # inner apna Exception khud pakadta hai (return False) — yahan aana truly
        # unexpected. Fail record karo, par tick crash mat karo (BaseException/
        # Cancelled propagate hote — woh yahan catch nahi). 2026-07-07: capture
        # error_class/message instead of discarding — job-log schema audit found
        # this was caught, logged, then thrown away right before record_run().
        _ok = False
        _err_class = type(_e).__name__
        _err_msg = str(_e)
        logger.warning(f"[team-scheduler] job '{job}' raised unexpectedly", exc_info=True)
        # Routine bridge: mark failed on exception
        if _routine_task_id:
            try:
                await atq.fail(_routine_task_id, f"{_err_class}: {_err_msg[:200]}")
            except Exception:
                pass
    finally:
        _duration = _time.monotonic() - _t0
        try:
            from app.platform import automation_health

            try:
                automation_health.record_run(
                    job,
                    _ok,
                    _duration,
                    error_class=_err_class,
                    error_message=_err_msg,
                    trigger="scheduler",
                    started_at=_started_at,
                )
            except TypeError:
                # record_run ka narrow/legacy signature (sirf test-mocks) — enriched
                # kwargs reject karega. record_run KHUD kabhi raise nahi karta (poora
                # body try/except me), isliye TypeError = purani signature. Basic call
                # se degrade karo (heartbeat na chhoote). Prod me yeh branch DEAD hai.
                automation_health.record_run(job, _ok, _duration)
        except Exception:
            pass
        # Update AutomationLog status (ADR-064)
        try:
            from app.platform.automation_log_service import log_event as _log_auto2

            _log_auto2(
                client_id="",
                job_type=job,
                status="success" if _ok else "failed",
                started_at=_started_at,
                duration_ms=int(_duration * 1000),
                # output_summary column ADR-064 se hai par scheduler path isse kabhi
                # bharta nahi tha → admin logs me har success row blank dikhta. inner
                # sirf bool deta (internals refactor nahi karte), isliye concise
                # human-readable status. Fail pe error_class jaata hai.
                output_summary=(
                    "success in %dms" % int(_duration * 1000)
                    if _ok
                    else (_err_class or "job_reported_failure")
                ),
                error_message=_err_msg[:2000] if _err_msg else "",
                retry_count=int(retry_count or 0),
                triggered_by="scheduler",
                meta_json=(
                    {"phase": "finish", "start_log_id": _log_id} if _log_id else {"phase": "finish"}
                ),
            )
        except Exception:
            pass

    return _ok


async def _run_content_engine(name: str, coro, budget=None) -> bool:
    """W1.3: `content` mega-job ke har engine ko isolate karo. Pehle 12 engines ek
    hi try me chain the — pehla throw (e.g. auto_content) baaki engines ko silently
    skip kar deta tha. Ab har engine ka failure logged + contained; cycle aage chalta.
    Optional ``budget`` / contextvar: SoftTimeLimit se pehle remaining engines skip."""
    try:
        b = budget if budget is not None else _active_job_budget.get()
        if b is not None and not b.ok():
            try:
                coro.close()
            except Exception:
                pass
            # Until 2026-08-09 this returned False with NO exception and NO line
            # naming the engine — so an engine could stop running for weeks and
            # nothing anywhere said so. Prod proof: `content` blew its 420s budget
            # on 15 consecutive daily runs (2026-07-18 → 2026-08-01, 452–530s),
            # silently dropping every engine queued behind the overrun.
            try:
                from app.platform import automation_health

                snap = b.snapshot() if hasattr(b, "snapshot") else {}
                automation_health.record_engine_skip(
                    str(getattr(b, "label", "") or "job"),
                    name,
                    "budget_exhausted",
                    elapsed_s=snap.get("elapsed_s"),
                    limit_s=snap.get("limit_s"),
                )
            except Exception as e:
                logger.warning("[team-scheduler] engine-skip record failed for '%s': %s", name, e)
            return False
        await coro
        return True
    except Exception as e:
        logger.warning(
            "[team-scheduler] content engine '%s' failed (isolated, cycle continues): %s",
            name,
            e,
        )
        return False


def _recover_due_jobs() -> dict[str, Any]:
    """Bounded, safe scheduler recovery used by the hourly watchdog.

    ``scheduler_config.run_due`` owns the eligibility and side-effect exclusion
    policy; this wrapper only keeps a recovery-path fault from breaking the
    rest of the watchdog safety checks.
    """
    try:
        from app.platform import scheduler_config

        return scheduler_config.run_due(max_jobs=3)
    except Exception as exc:
        logger.warning("[team-scheduler] watchdog due-job recovery failed: %s", exc)
        return {"ok": False, "error": type(exc).__name__}


async def _run_job_inner(job: str) -> bool:
    try:
        from app.agents import staff

        logger.info(f"[team-scheduler] running job: {job}")
        if job == "growth":
            from app.platform import growth_engine

            await growth_engine.pulse()
            # Team heartbeat — har 15-min cycle pe under-active staff ke cheap
            # real monitors chalao (dashboard pe zinda dikhe, sirf daily-spike nahi).
            try:
                from app.platform import team

                team.team_pulse(max_members=4)
            except Exception:
                pass
            # Self-improve in-process fallback —
            # Celery mode me Celery tasks handle karte hain.
            # In-process mode (RUN_IN_PROCESS_SCHEDULER=1) me Celery tick kabhi fire nahi
            # hota, isliye yahan directly run_once() call karo (15-min cadence = theek hai).
            try:
                from app.agents import self_improve

                _celery_off = os.environ.get("RUN_IN_PROCESS_SCHEDULER", "1").strip() in (
                    "1",
                    "true",
                    "yes",
                )
                if _celery_off and self_improve.enabled():
                    result = await self_improve.run_once()
                    logger.debug(
                        f"[scheduler] self_improve in-process: {result.get('action', '?')} ok={result.get('ok')}"
                    )
            except Exception as _si_e:
                logger.debug(f"[scheduler] self_improve in-process skip: {_si_e}")
            # Process engine in-process tick —
            # Celery pe `process_tick` Celery task handle karta hai.
            # In-process mode me RUNNING processes (non-breakpoint steps) yahan advance hote hain.
            try:
                _celery_off2 = os.environ.get("RUN_IN_PROCESS_SCHEDULER", "1").strip() in (
                    "1",
                    "true",
                    "yes",
                )
                if _celery_off2:
                    from app.agents.process_engine import advance, list_runs

                    _running = [r for r in list_runs() if r.get("status") == "running"]
                    for _pr in _running[:3]:  # max 3 per tick — no runaway
                        try:
                            await advance(_pr["run_id"], max_steps=3)
                        except Exception:
                            pass
            except Exception as _pe_e:
                logger.debug(f"[scheduler] process_engine tick skip: {_pe_e}")
            # Cadence advance on growth pulse (15-min) — CADENCE_ENGINE gated.
            # Content-job (daily 07:00) pe bhi chalega; yahan Anika starve na ho
            # jab pehle N file rows already ``done`` hon (run_due active-limit fix).
            try:
                from app.marketing import cadence

                await cadence.run_due(limit=50)
            except Exception as _cd_e:
                logger.debug(f"[scheduler] cadence growth-pulse skip: {_cd_e}")
        elif job == "ops":
            await staff.run_ops()
        elif job == "qa":
            await staff.run_qa()
            try:
                # Arjun/Swara: voice agent persona eval suite — dormant engine wire,
                # gated VOICE_EVAL_AUTO. brain=None = LLM-free rule-based smoke
                # (regression catch: double/repeat/pushy/goodbye). Off-loop deadline.
                if os.environ.get("VOICE_EVAL_AUTO", "0").strip().lower() in ("1", "true", "yes"):
                    from app.platform import team
                    from app.voice_agent.eval_suite import run_suite
                    from app.voice_agent.natural_dialog import NaturalDialogManager

                    def _vfactory():
                        return NaturalDialogManager(niche="solar", brain=None)

                    # QA's own LLM turns are bounded in ``staff.run_qa``. Keep this
                    # optional suite bounded too, so their combined work remains
                    # below Celery's 540s soft limit.
                    _rep = await asyncio.wait_for(run_suite(_vfactory), timeout=120)
                    _tot = _rep.passed + _rep.failed
                    team.log_event(
                        "arjun",
                        "voice_eval",
                        f"🎙️ persona suite {_rep.passed}/{_tot} pass ({_rep.pass_rate:.0%})",
                        status="ok" if _rep.pass_rate >= 0.7 else "warn",
                    )
            except Exception:
                pass
            try:
                # P4-3: score the last 5 LIVE call transcripts (voice_turn_score +
                # D-13 qa_checks) and feed the mean to eval_gate. (Replaces a broken
                # eval_gate.score_and_gate call that silently TypeError'd.)
                from app.agents import live_eval
                from app.platform import team

                res = live_eval.eval_recent_calls(5)
                mean = res.get("mean_score", 1.0)
                decision = (res.get("gate") or {}).get("decision", "ok")
                team.log_event(
                    "arjun",
                    "voice_eval_guardrail",
                    f"📊 live-call quality {mean:.2f} · {res.get('n', 0)} calls · "
                    f"{res.get('total_qa_findings', 0)} QA findings · gate {decision}",
                    status="ok" if decision != "reject" else "warn",
                )
            except Exception:
                pass
        elif job == "trainer":
            await staff.run_trainer()
            try:
                # Guru: project skills → KB ingest (semantic recall; gated SKILL_PACK)
                from app.platform import skill_pack, team

                # SKILL_PACK enables lightweight prompt lookup. KB ingestion builds
                # embeddings and can cold-start for several minutes, so it gets a
                # separate explicit gate and must never hold the daily trainer task
                # hostage to Celery's 10-minute hard limit. Bounded: off-thread +
                # 200s cap (leaves headroom for ML training's 360s window inside
                # the 600s hard / 540s soft limit).
                if skill_pack.enabled() and os.environ.get(
                    "SKILL_PACK_KB_INGEST", "0"
                ).strip().lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    try:
                        res = await asyncio.wait_for(
                            asyncio.to_thread(skill_pack.ingest_to_kb), timeout=200
                        )
                        if res.get("ok"):
                            team.log_event(
                                "guru",
                                "skill_ingest",
                                f"📚 {res.get('skills', 0)} skills → KB ({res.get('chunks', 0)} chunks, {res.get('backend')})",
                            )
                        else:
                            team.log_event(
                                "guru",
                                "skill_ingest",
                                f"⚠️ skill ingest failed: {res.get('error', 'unknown')}",
                                status="warn",
                            )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "skill KB ingest exceeded 200s budget — skipping; trainer job continues"
                        )
                        team.log_event(
                            "guru",
                            "skill_ingest",
                            "⚠️ skill KB ingest skipped: exceeded 200s budget",
                            status="warn",
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"skill KB ingest error: {e}")
            except Exception:
                pass
            try:
                # Dev/Meera: nightly ML training (intent classifier + lead scorer +
                # prompt-opt + A/B variants) — dormant engine wire, gated
                # ML_NIGHTLY_TRAINING. Internally try/excepted; leave headroom for
                # transcript analysis and telemetry before Celery's 540s soft limit.
                if os.environ.get("ML_NIGHTLY_TRAINING", "0").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    from app.ml.auto_trainer import auto_trainer
                    from app.platform import team

                    _ml = await asyncio.wait_for(auto_trainer.run_nightly_training(), timeout=360)
                    team.log_event(
                        "dev",
                        "ml_training",
                        f"🧠 nightly ML train: {_ml.get('status')} ({float(_ml.get('duration_seconds') or 0):.0f}s)",
                        status="ok" if _ml.get("status") == "success" else "warn",
                    )
            except Exception:
                pass
        elif job == "digest":
            _digest_result = await staff.run_digest()
            # Obsidian — write daily session note with actual digest content.
            try:
                import datetime as _dt

                from app.platform import obsidian_sync as _obs

                _date = _dt.datetime.utcnow().strftime("%Y-%m-%d")
                _digest_text = (_digest_result or {}).get("text") or (
                    f"inquiries_24h={(_digest_result or {}).get('inquiries_24h', '?')} "
                    f"prospects_ready={(_digest_result or {}).get('prospects_ready', '?')} "
                    f"qa_issues={(_digest_result or {}).get('qa_issues_24h', '?')}"
                )
                _obs.write_daily_session(
                    _date,
                    f"# Daily Digest\n\n{_digest_text}",
                )
                _obs.append_note(
                    "Sessions", _date, f"[digest] {_digest_text[:300]}", member="team_scheduler"
                )
            except Exception:
                pass
            # HARDENING (audit 2026-07-07): ye 4 revenue-relevant engines pehle unguarded
            # chain the — pehla throw (e.g. revenue_digest) baaki 3 (client_health churn-scan,
            # usage_alerts billing upsell, growth_optimizer profit-loop) ko skip kar deta tha.
            # Ab har engine `_run_content_engine` se isolated (content-job W1.3 pattern jaisa).
            from app.platform import revenue_digest

            await _run_content_engine(
                "revenue_digest", revenue_digest.maybe_run_weekly()
            )  # Monday-only weekly MRR digest (gated REVENUE_DIGEST)
            from app.platform import client_health

            await _run_content_engine(
                "client_health", client_health.run_check()
            )  # churn-risk scan (alert gated CLIENT_HEALTH_ALERTS)
            from app.billing import usage_alerts

            await _run_content_engine(
                "usage_alerts", usage_alerts.run_check()
            )  # 80%/100% minute upsell triggers (gated USAGE_ALERTS)
            from app.agents import growth_optimizer

            await _run_content_engine(
                "growth_optimizer", growth_optimizer.optimize()
            )  # daily self-healing profit loop (gated GROWTH_OPTIMIZER)
            try:
                from app.agents import campaign_optimizer

                await (
                    campaign_optimizer.optimize()
                )  # Kiran weekly/threshold (gated CAMPAIGN_OPTIMIZER)
            except Exception:
                pass
            try:
                from app.platform import objection_extractor

                await objection_extractor.scan_recent_transcripts(10)
            except Exception:
                pass
            # payment_recon removed 2026-06-18 — Razorpay gateway gone (manual UPI).
            try:
                # Speed-to-lead accountability line (READ-only metric) — Boss event me.
                from app.platform import speed_to_lead, team

                _stl = speed_to_lead.summary(7)
                if _stl.get("ok") and _stl.get("verdict"):
                    # STAFF key is "manager" (display name "Boss") — "boss" is not a
                    # registered key, so this event was previously invisible on /app/team
                    # (team_status() only looks up last_event by STAFF key). Fixed 2026-07-01.
                    team.log_event("manager", "speed_to_lead", f"⚡ {_stl['verdict']}")
            except Exception:
                pass
            try:
                from app.platform import brand_pulse

                await (
                    brand_pulse.run_weekly_if_enabled()
                )  # brand mention scan + drafts (gated BRAND_PULSE; LLM-free scan)
            except Exception:
                pass
            try:
                from app.platform import team_report

                await (
                    team_report.run_weekly_if_enabled()
                )  # client-facing AI-staff weekly narrative (gated TEAM_REPORT)
            except Exception:
                pass
        elif job == "call_kpi_digest":
            from app.voice_agent import call_analytics

            call_analytics.run_daily_digest()
        elif job == "content":
            from app.marketing import auto_content
            from app.platform.job_time_budget import JobBudget

            # SoftTimeLimit (540s) se pehle partial-ok — content SoftTimeLimit DLQ (2026-07-23).
            _content_budget = JobBudget.from_env("CONTENT_TIME_BUDGET_S", label="content")
            _budget_tok = _active_job_budget.set(_content_budget)
            try:
                # W1.3: har engine _run_content_engine se guzarta hai — ek engine ka throw
                # baaki engines ko skip nahi karta (pehle poora chain ek hi try me tha).
                await _run_content_engine("auto_content", auto_content.run_daily_content())
                from app.marketing import video_ad_cycle

                # AI video-ad cycle: har 5 din naya video (build_reel) -> client approval ->
                # multi-channel publish. run_cycle khud interval/publish/regen handle karta
                # (gated VIDEO_AD_CYCLE or VIDEO_DAILY_SCHEDULER_ENABLED; off = inert).
                # Scheduler/worker context = heavy OK.
                await _run_content_engine("video_ad_cycle", video_ad_cycle.run_cycle())
                from app.marketing import content_schedule

                await _run_content_engine(
                    "content_schedule", content_schedule.run_due()
                )  # date-scheduled posts auto-prepare
                from app.tasks.reporting import run_social_autopost

                # Publish 'ready' posts to connected Meta accounts (MOCK unless
                # SOCIAL_AUTOPOST=1 + a Page/IG token — inert/safe otherwise).
                await _run_content_engine("social_autopost", run_social_autopost())
                from app.marketing import wa_campaign_runner

                await _run_content_engine(
                    "wa_campaign_runner", wa_campaign_runner.run_due()
                )  # WhatsApp drip/reactivation (inert without creds)
                from app.marketing import cadence

                await _run_content_engine(
                    "cadence", cadence.run_due()
                )  # omnichannel cadence advance (gated CADENCE_ENGINE; inert off)
                from app.marketing import sales_pipeline

                await _run_content_engine(
                    "sales_pipeline", sales_pipeline.run_pipeline()
                )  # sales deals auto next-action (gated SALES_ENGINE)
                from app.billing import dunning

                await _run_content_engine(
                    "dunning", dunning.run_due()
                )  # payment-recovery sweep (gated DUNNING_ENGINE; inert off)
                from app.marketing import lifecycle_nurture

                await _run_content_engine(
                    "lifecycle_nurture", lifecycle_nurture.run_due()
                )  # signup->paid nurture (gated LIFECYCLE_NURTURE; inert off)
                from app.telephony import voice_followup

                await _run_content_engine(
                    "voice_followup", voice_followup.run_due()
                )  # trial day8/9 + interested follow-up calls (gated VOICE_FOLLOWUP; inert off)
                from app.marketing import channel_experiments

                await _run_content_engine(
                    "channel_experiments", channel_experiments.run_daily(3)
                )  # naye approach-channel experiments (gated CHANNEL_EXPERIMENTS)
                from app.platform import booking_reminders

                await _run_content_engine(
                    "booking_reminders", booking_reminders.run_due()
                )  # kal ki bookings ke reminders (gated BOOKING_REMINDERS)
                from app.marketing import review_monitor

                await _run_content_engine(
                    "review_monitor", review_monitor.run_check()
                )  # naye Google reviews -> AI reply drafts (gated REVIEW_MONITOR)
                try:
                    from app.marketing import customer_crm

                    if _content_budget.ok():
                        await (
                            customer_crm.run_wishes_if_enabled()
                        )  # birthday/anniversary wish DRAFTS (gated CUSTOMER_WISHES)
                except Exception:
                    pass
                try:
                    from app.platform import service_reminders

                    if _content_budget.ok():
                        await (
                            service_reminders.run_due_if_enabled()
                        )  # repeat-service WA reminder DRAFTS (gated SERVICE_REMINDERS)
                except Exception:
                    pass
                try:
                    from app.marketing import newsletter

                    if _content_budget.ok():
                        await (
                            newsletter.run_due_if_enabled()
                        )  # monthly client-newsletter (gated NEWSLETTER_ENGINE; month-dedupe)
                except Exception:
                    pass
                try:
                    from app.platform import winback

                    if _content_budget.ok():
                        await (
                            winback.run_due_if_enabled()
                        )  # inactive win-back DRAFTS (gated WINBACK_ENGINE)
                except Exception:
                    pass
                try:
                    from app.platform import rank_tracker

                    if _content_budget.ok():
                        await (
                            rank_tracker.run_if_enabled()
                        )  # local rank tracking sweep (gated RANK_TRACKER, cap lookups)
                except Exception:
                    pass
                try:
                    from app.platform import customer_autopilot

                    # per-client hands-free drafts: evergreen recycle / NPS survey / stale-inquiry
                    # nudge / daily owner-brief. Har sub-job apne flag ke peeche (EVERGREEN_RECYCLE /
                    # NPS_AUTO / STALE_INQUIRY_NUDGE / OWNER_BRIEF_DAILY) — all DEFAULT-OFF, draft-only.
                    if _content_budget.ok():
                        await customer_autopilot.run_all()
                except Exception:
                    pass
                try:
                    from app.platform import memory_vault

                    if _content_budget.ok():
                        await (
                            memory_vault.sync_if_enabled()
                        )  # compounding memory tail-sync (gated MEMORY_VAULT, no LLM)
                except Exception:
                    pass
                try:
                    from app.platform import memory_stack

                    if _content_budget.ok():
                        # prospective memory (L6): lease-recover + atomically claim due
                        # rows, phir normal agent_task_queue me dispatch. Gated
                        # MEMORY_STACK_ENABLED; durable store missing = fail-CLOSED
                        # (zero dispatch). No LLM on this path.
                        await memory_stack.drain_if_enabled()
                except Exception:
                    pass
                try:
                    from app.platform import live_notes

                    if _content_budget.ok():
                        await (
                            live_notes.refresh_if_enabled()
                        )  # topic live-notes refresh (gated LIVE_NOTES, max 5/day)
                except Exception:
                    pass
                try:
                    from app.agents import sales_team

                    if _content_budget.ok():
                        await sales_team.run_auto(
                            3
                        )  # 5-agent prospect deep-dives on hot leads (gated SALES_TEAM)
                except Exception:
                    pass
                try:
                    # White-label monthly client report — mahine ki 1 tarikh ko hi.
                    # Email sirf CLIENT_REPORTS=1 pe jata (warna file-only) — run_monthly khud gate karta.
                    from datetime import datetime as _dt

                    if _content_budget.ok() and _dt.now().day == 1:
                        from app.marketing import client_report

                        await client_report.run_monthly()
                except Exception:
                    pass
            finally:
                _active_job_budget.reset(_budget_tok)
        elif job == "blog":
            from app.marketing import seo_blog

            _blog_result = await seo_blog.run_daily_blog(3)
            try:
                import datetime as _dt_obs_blog

                from app.platform import obsidian_sync as _obs_blog

                _blog_date = _dt_obs_blog.datetime.utcnow().strftime("%Y-%m-%d")
                _blog_n = (_blog_result or {}).get("published", 0)
                _blog_slugs = ", ".join((_blog_result or {}).get("slugs") or [])
                _blog_summary = f"published={_blog_n} slugs=[{_blog_slugs[:200]}]"
                _obs_blog.append_note(
                    "Sessions", _blog_date, f"[blog] {_blog_summary}", member="team_scheduler"
                )
            except Exception:
                pass
            try:
                from datetime import datetime as _dt_blog

                # Monday: programmatic SEO landing batch (Ravi — organic inbound).
                if _dt_blog.now(_IST).weekday() == 0:
                    from app.marketing import seo_pages
                    from app.platform import team

                    _seo = await seo_pages.generate_batch(limit=5)
                    if (_seo or {}).get("ok"):
                        team.log_event(
                            "ravi",
                            "seo_batch",
                            f"🌐 {len((_seo or {}).get('pages') or [])} programmatic SEO pages",
                            status="ok",
                        )
            except Exception:
                pass
            try:
                from app.marketing import indexnow

                await (
                    indexnow.submit_sitemap_if_enabled()
                )  # naye URLs Bing/Yandex pe (gated INDEXNOW)
            except Exception:
                pass
        elif job == "prospect":
            # NICHE_ROTATION=1 → all-42-niches round-robin (niche_prospector); warna
            # default 4-niche prospector (aaj jaisa). Gated = zero behaviour change.
            import time as _time_prospect

            _prospect_t0 = _time_prospect.monotonic()
            if os.environ.get("NICHE_ROTATION", "0").strip().lower() in ("1", "true", "yes"):
                from app.platform import niche_prospector

                _prospect_result = await niche_prospector.run(batch=4)
            else:
                from app.platform import prospector

                _prospect_result = await prospector.run_prospecting()
            try:
                import datetime as _dt_obs_prospect

                from app.platform import obsidian_sync as _obs_prospect

                _prospect_date = _dt_obs_prospect.datetime.utcnow().strftime("%Y-%m-%d")
                _pr = _prospect_result or {}
                _prospect_summary = (
                    f"new={_pr.get('new', '?')} "
                    f"queries_run={_pr.get('queries_run', '?')} "
                    f"scraper={_pr.get('scraper', '?')} "
                    f"niches={list((_pr.get('by_niche') or {}).keys())[:10]}"
                )
                _obs_prospect.append_note(
                    "Sessions",
                    _prospect_date,
                    f"[prospect] {_prospect_summary[:300]}",
                    member="team_scheduler",
                )
            except Exception:
                pass
            # Multi-source harvest sweep (websearch/opendata/enrich) — gated
            # LEAD_HARVESTER=1. MUST stay inside Celery soft-limit (~540s).
            # 2026-07-20: unbounded GTM×niche_prospector after niche scrape → SoftTimeLimit.
            # 2026-08-07 D2: hard outer 120s + inner HARVEST_LOOP_TIMEOUT_S=120 starved
            # opendata/websearch after Places; align one budget (default 240) under remain.
            try:
                _elapsed = _time_prospect.monotonic() - _prospect_t0
                _remain = max(0.0, _PROSPECT_SOFT_BUDGET_S - _elapsed)
                _harvest_timeout = post_prospect_harvest_timeout(_remain)
                if _harvest_timeout is None:
                    logger.warning(
                        "[team-scheduler] skip harvest after prospect — "
                        f"remain={_remain:.0f}s inline="
                        f"{os.environ.get('PROSPECT_INLINE_HARVEST', '1')!r}"
                    )
                else:
                    from scripts import harvest_safety_wrapper

                    # Avoid nested niche_prospector inside harvest (already scraped above).
                    _prev_skip = os.environ.get("SKIP_HARVEST_PROSPECTOR_SRC")
                    _prev_hlt = os.environ.get("HARVEST_LOOP_TIMEOUT_S")
                    os.environ["SKIP_HARVEST_PROSPECTOR_SRC"] = "1"
                    # Drive the wrapper's own wait_for — do not double-cap below it.
                    os.environ["HARVEST_LOOP_TIMEOUT_S"] = str(int(_harvest_timeout))
                    try:
                        _h = await harvest_safety_wrapper.run_harvest_loop_safe()
                        _hr = _h if isinstance(_h, dict) else {}
                        logger.info(
                            "[team-scheduler] post-prospect harvest "
                            f"timeout={_harvest_timeout:.0f}s "
                            f"truncated={bool(_hr.get('truncated'))} "
                            f"leads_total={_hr.get('leads_total', _hr.get('new_leads', '?'))} "
                            f"error={str(_hr.get('error') or '')[:80]!r}"
                        )
                    finally:
                        if _prev_skip is None:
                            os.environ.pop("SKIP_HARVEST_PROSPECTOR_SRC", None)
                        else:
                            os.environ["SKIP_HARVEST_PROSPECTOR_SRC"] = _prev_skip
                        if _prev_hlt is None:
                            os.environ.pop("HARVEST_LOOP_TIMEOUT_S", None)
                        else:
                            os.environ["HARVEST_LOOP_TIMEOUT_S"] = _prev_hlt
            except Exception:
                logger.warning(
                    "[team-scheduler] harvest after prospect failed",
                    exc_info=True,
                )
        elif job == "email_outreach":
            from app.platform import auto_outreach

            _outreach_result = await auto_outreach.run_email_outreach()
            try:
                import datetime as _dt_obs_outreach

                from app.platform import obsidian_sync as _obs_outreach

                _outreach_date = _dt_obs_outreach.datetime.utcnow().strftime("%Y-%m-%d")
                _or = _outreach_result or {}
                _outreach_summary = (
                    f"sent={_or.get('sent', '?')} "
                    f"failed={_or.get('failed', '?')} "
                    f"skipped_no_email={_or.get('skipped_no_email', '?')} "
                    f"cap={_or.get('cap', '?')}"
                    + (f" skip_reason={_or['skipped']}" if _or.get("skipped") else "")
                )
                _obs_outreach.append_note(
                    "Sessions",
                    _outreach_date,
                    f"[email_outreach] {_outreach_summary[:300]}",
                    member="team_scheduler",
                )
            except Exception:
                pass
        elif job == "reply_triage":
            from app.platform import reply_agent

            await reply_agent.run_reply_triage()
            # Multi-channel orchestration: email-openers ko WhatsApp follow-up links
            try:
                from app.platform import auto_outreach

                auto_outreach.multi_channel_followup(limit=25)
            except Exception:
                pass
            # Auto-forward positive replies to calling queue
            try:
                from app.platform import reply_agent

                reply_agent.auto_forward_positive_replies(limit=10)
            except Exception:
                pass
        elif job == "watchdog":
            # HARDENING (audit 2026-07-07): pehle ye 9 critical safety-net checks EK
            # unguarded chain me the — pehla throw (e.g. ops_watchdog network hiccup)
            # baaki SAB skip kar deta tha, INCLUDING dead-man alert (automation_health.
            # run_watch), self_improve revive aur dlq_retry. Matlab ek asambandhit
            # sub-check failure poore safety-net ko us ghante ke liye chup kar sakta tha.
            # Ab har async check `_run_content_engine` se ISOLATED (W1.3 pattern) — ek
            # fail hone par logged + contained, baaki checks (khaas kar dead-man + revive)
            # phir bhi chalte. Order preserve — behaviour same, resilience upgrade.
            from app.platform import ops_watchdog

            await _run_content_engine("ops_watchdog", ops_watchdog.run_watchdog())
            from app.platform import deliverability_monitor

            await _run_content_engine(
                "deliverability_monitor", deliverability_monitor.run_check()
            )  # SPF/DMARC + blacklist (alert gated DELIVERABILITY_MONITOR)
            from app.platform import automation_health

            await _run_content_engine(
                "automation_health_watch", automation_health.run_watch()
            )  # dead-man switch: overdue jobs alert (gated AUTOMATION_HEALTH_ALERTS)
            # Alert ke saath recovery bhi zaroori hai: overdue/never-ran safe
            # jobs bounded Celery dispatch se recover hote hain. Exclude-list
            # email/digest/platform_dial jaise side-effectful jobs ko auto-replay
            # nahi karne deta. Pehle helper bana hua tha par watchdog se wired nahi
            # tha, isliye restart ke baad jobs sirf overdue alert hote the.
            _recover_due_jobs()
            from app.telephony import telephony_readiness

            await _run_content_engine(
                "telephony_readiness_watch", telephony_readiness.run_watch()
            )  # Tara: calling-launch readiness score (alert gated TELEPHONY_READY_ALERTS)
            from app.platform import infra_handler

            await _run_content_engine(
                "infra_handler_watch", infra_handler.run_watch()
            )  # Hermes: full infra score+actions (alert gated INFRA_HANDLER; off = no-op)
            from app.platform import llm_metrics

            await _run_content_engine(
                "llm_capacity_watch", llm_metrics.run_capacity_watch()
            )  # LLM gateway capacity/fallback alert (gated LLM_CAPACITY_ALERTS; #1 bottleneck self-flag)
            from app.platform import dlq_retry

            await _run_content_engine(
                "dlq_retry_sweep", dlq_retry.run_sweep()
            )  # failed staff-jobs auto-retry+backoff (gated DLQ_AUTO_RETRY; off = no-op)
            from app.platform import integration_health

            await _run_content_engine(
                "integration_health_watch", integration_health.run_watch()
            )  # integration silent-failure alert (gated INTEGRATION_ALERTS; off = sirf counters)
            try:
                # Product 1 Integration Health Agent (2026-07-08): maps the SAME
                # integration failures + automation_health.health()'s overdue-job/
                # queue-backlog signal to the SPECIFIC paid customers affected +
                # logs an internal `integration_failed` ledger event per affected
                # customer. Sync + never-raises by design, but isolated anyway
                # (W1.3 pattern) so it can never block the rest of the watchdog.
                from app.marketing import product_one_delivery

                product_one_delivery.integration_readiness()
            except Exception as _ih_e:
                logger.warning(f"[team-scheduler] watchdog integration_readiness failed: {_ih_e}")
            try:
                from app.agents import self_improve

                self_improve.ensure_alive()  # continuous-loop dead-man revive (gated SELF_IMPROVE_LOOP; sirf Celery enqueue, inline kabhi nahi)
            except Exception as _si_e:
                # SYNC call — _run_content_engine (await) nahi chalega. Loud warn (pass NAHI):
                # revive safety-net ka failure chhupana nahi chahiye.
                logger.warning(
                    f"[team-scheduler] watchdog self_improve.ensure_alive failed: {_si_e}"
                )
            try:
                from app.agents import process_engine

                process_engine.ensure_alive()  # stale RUNNING workflows → process_tick revive
            except Exception:
                pass
            try:
                from app.agents import dag_engine

                dag_engine.ensure_alive()  # stale RUNNING dag flows → process_tick revive (separate index, no double-revive)
            except Exception:
                pass
            try:
                from app.platform import proposal_tracking

                proposal_tracking.sweep_new_opens()  # "proposal khola" event sweep (file-IO only, no send)
            except Exception:
                pass
            try:
                from app.agents import code_upgrader

                await (
                    code_upgrader.run_if_enabled()
                )  # Vikram: code-upgrade proposals (gated CODE_UPGRADER; off = no-op)
            except Exception:
                pass
            try:
                from app.telephony import consent_ledger

                consent_ledger.retention_sweep()  # 90-din recording retention (delete gated RECORDING_RETENTION; off = report-only, dir absent = no-op)
            except Exception:
                pass
        elif job == "engineer_sre":
            # F.5: Pranav SRE reliability score. INERT until SRE_AGENT=1 (engine
            # itself returns "disabled" result so this never blocks the loop).
            from app.platform import engineer_agents

            engineer_agents.run_sre()
        elif job == "engineer_finops":
            from app.platform import engineer_agents

            engineer_agents.run_finops()
        elif job == "engineer_security":
            from app.platform import engineer_agents

            engineer_agents.run_security()
        elif job == "engineer_dbre":
            # council: Kabir DB reliability. INERT until DBRE_AGENT=1 (engine
            # returns "disabled" result so this never blocks the loop).
            from app.platform import engineer_agents

            engineer_agents.run_dbre()
        elif job == "engineer_dataquality":
            # council: Diya lead/CRM data integrity (report-only). INERT until
            # DATA_INTEGRITY_AGENT=1.
            from app.platform import engineer_agents

            engineer_agents.run_dataquality()
        elif job == "engineer_deps":
            # council: Aryan dependency/supply-chain CVE audit (proposal-only).
            # INERT until DEPS_AGENT=1.
            from app.platform import engineer_agents

            engineer_agents.run_deps()
        elif job == "mcp_engineer":
            # council 2026-06-26: Arya MCP health pulse (3-layer surface).
            # INERT until MCP_ENGINEER=1 (engine returns disabled result so
            # this never blocks the loop).
            from app.platform import mcp_engineer

            mcp_engineer.run_mcp()
        elif job == "readiness_digest":
            # G.3: daily activation-readiness digest. INERT until OPS_ALERTS=1 +
            # ntfy creds set; ops_alerts.daily_readiness_digest itself is the
            # single source of truth on cooldown / threshold logic.
            from app.platform import ops_alerts

            ops_alerts.daily_readiness_digest()
        elif job == "onboard":
            from app.marketing import onboarding

            await onboarding.run_onboarding_sweep()
        elif job == "pipeline":
            from app.platform import pipeline_ops

            await pipeline_ops.run_daily()
        elif job == "email_followup":
            from app.platform import pipeline_ops

            await pipeline_ops.run_afternoon_followups()
        elif job == "kb_refresh":
            from app.platform import kb_refresh

            await kb_refresh.run_weekly_if_enabled()
        elif job == "midday_prospect":
            # 2nd daily lead-supply pass — FREE harvest (websearch/opendata/enrich),
            # different niche/city rotation than 09:30 prospect. Gated MIDDAY_PROSPECT
            # (default ON; no paid Places API — lead_harvester respects LEAD_HARVESTER).
            # Uses safety wrapper for P1 pool cleanup (2026-07-11).
            if os.environ.get("MIDDAY_PROSPECT", "1").strip().lower() in ("1", "true", "yes"):
                from app.platform import team
                from scripts import harvest_safety_wrapper

                _h = await harvest_safety_wrapper.run_harvest_safe()
                if _h.get("ok"):
                    team.log_event(
                        "rohan",
                        "midday_harvest",
                        f"🌾 midday +{_h.get('new_leads', 0)} leads (dedup {_h.get('deduped', 0)})",
                        status="ok",
                    )
        elif job == "platform_dial":
            # Own-product outbound (2026-07-02): Product-2 voice agent Product-1 bechta
            # hai — daily batch of AI cold-calls with the ai_marketing platform pitch.
            # Gated PLATFORM_DIAL_DAILY env OR data/platform_dial.json (default OFF;
            # env "0" = hard kill-switch — see app/platform/platform_dial.py).
            # Single-flight = the SAME campaign lock the admin launch uses (double-dial
            # impossible); TRAI window / DND / readiness gates enforce inside
            # run_campaign_task + VobizClient per call.
            from app.platform import platform_dial as _pd

            if _pd.enabled():
                from app.platform import team
                from app.tasks.calling import (
                    acquire_campaign_lock,
                    campaign_lock_held,
                    release_campaign_lock,
                )

                _limit = _pd.dial_limit()
                _dial_niche = _pd.dial_niche()
                if campaign_lock_held():
                    team.log_event(
                        "swara",
                        "platform_campaign",
                        "⏸️ daily self-sale dial skipped — ek campaign pehle se chal rahi",
                        status="warn",
                    )
                elif acquire_campaign_lock(ttl_s=max(400, _limit * 8 + 120)):
                    try:
                        from app.telephony import voice_launch as _vl

                        await _vl.create_voice_session(
                            owner="platform_dial", niche=_dial_niche, label="auto_daily"
                        )

                        from app.worker import celery_app

                        celery_app.send_task(
                            "app.tasks.calling.run_campaign_task",
                            kwargs={
                                "limit": _limit,
                                "dry_run": False,
                                "niche": _dial_niche,
                                "client_id": "",
                                "platform": True,
                                "transactional": False,
                            },
                        )
                        team.log_event(
                            "swara",
                            "platform_campaign",
                            f"📞 Swara ki daily self-sale campaign queue hui — {_limit} calls (niche={_dial_niche})",
                            status="ok",
                        )
                    except Exception:
                        # enqueue fail → lock turant chhodo, warna TTL tak manual launch bhi blocked
                        release_campaign_lock()
                        raise
        elif job == "evening_wrap":
            from app.platform import scheduled_ops

            await scheduled_ops.run_evening_wrap()
        elif job == "weekly_marketing":
            from app.platform import scheduled_ops

            await scheduled_ops.run_weekly_marketing()
        elif job == "saturday_hygiene":
            from app.platform import scheduled_ops

            await scheduled_ops.run_saturday_hygiene()
        elif job == "meter_watch":
            from app.billing import meter_watch

            meter_watch.check_meter_failures()  # sync, never raises; gated METER_ALERTS
        elif job == "product_one_health":
            from app.marketing import product_one_delivery

            # Product 1 Customer Deliverability layer (2026-07-08): Customer
            # Health + Approval Reminder + SLA Recovery combined sweep — read
            # from delivery_ledger/content/approval stores, idempotent
            # ledger writes only, never sends WhatsApp/email. Ungated
            # safety-net (same convention as watchdog/onboard).
            await product_one_delivery.run_health_and_recovery_sweep()
            # Monthly billing-cycle deliverable seed (2026-08-07). Rides this
            # existing per-client sweep instead of adding a job: the work is
            # idempotent, cheap, and belongs to the same Product-1 delivery
            # surface. INERT unless DELIVERABLE_CYCLE_SEED=1.
            #
            # WHY: initialize_deliverables_for_client is called ONLY from
            # billing/usage.py on plan activation, so nothing ever creates the
            # NEXT month's rows. Prod held 20 rows, all 2026-07, newest created
            # 2026-07-18 — the paying customer was 30+ days into a paid month
            # with no current-cycle ledger for sync_customer_deliverable_status
            # to attach to. DB rows only; no content generation, no sends.
            if product_one_delivery.cycle_seed_enabled():
                _seed = await asyncio.to_thread(
                    product_one_delivery.seed_current_cycle_deliverables, None, 200, False
                )
                logger.info(f"[team-scheduler] deliverable_cycle_seed: {_seed}")
        elif job == "approval_email_sweep":
            from app.platform import approval_notifier

            # Bounded, single-flight pending-approval EMAIL sweep. INERT unless
            # APPROVAL_EMAIL_NOTIFY=1 (run_approval_email_sweep no-ops when off).
            # Never sends without customer consent + provider success; audit +
            # DB idempotency key make repeated runs safe.
            await approval_notifier.run_approval_email_sweep()
        elif job == "task_lease_reap":
            from app.platform import agent_task_queue as _atq

            # Expired claim-lease close-out. `stale_tasks()` only SURFACES stuck work by
            # design, so a worker that dies mid-task strands its lease forever. INERT
            # unless AGENT_TASK_LEASE_REAP=1 — "surface, don't auto-fix" stays default.
            # TERMINAL only (marks failed, never requeues): complete()/fail() don't guard
            # on checkout_version, so a requeue could double-run this job's side effects.
            # No sends, no customer mutation.
            if _atq.lease_reap_enabled():
                _reaped = await _atq.reap_stale_leases(dry_run=False)
                logger.info(f"[team-scheduler] task_lease_reap: {_reaped}")
            # Orphan-ledger sweep — DISJOINT population from the lease reap
            # above (pending + claimed_at IS NULL, which that predicate cannot
            # match on either clause). Separate gate AGENT_TASK_ORPHAN_REAP=1;
            # bounded, backed up to JSONL first, closed as `cancelled` (they did
            # not fail — automation_logs holds the real outcome), never requeued.
            if _atq.orphan_reap_enabled():
                _orph = await _atq.reap_orphan_routines(dry_run=False)
                logger.info(f"[team-scheduler] task_orphan_reap: {_orph}")
        elif job == "sales_autopilot":
            from app.platform.sales_autopilot import scheduler as _sales_ap

            # Canary tick. INERT unless SALES_AUTOPILOT_ENABLED=1 (run_tick
            # returns {enabled:False} immediately). Dry-run default; calling
            # HARD OFF; Estique/manual_owner_confirmed fail-closed in eligibility.
            await _sales_ap.run_tick()
        elif job == "daily_video":
            # DAILY per-client video producer. Its own job on purpose: inside the
            # `content` chain it sat behind auto_content under CONTENT_TIME_BUDGET_S
            # and got silently budget-skipped (prod: 15-day generation gap on a
            # 5-day interval). LIGHT — enqueues to the video queue, never renders.
            # Gated DAILY_VIDEO_ENABLED + fail-closed DAILY_VIDEO_CLIENTS allowlist.
            from app.marketing import daily_video

            await daily_video.run_daily()
        elif job == "hq_auto_chase":
            # Hot Queue auto-chase — unactioned inquiry cards pe automated EMAIL
            # follow-up. INERT unless HQ_AUTO_CHASE=1 (run_auto_chase no-ops).
            # Email-only: WhatsApp/call remain owner 1-click human (ban-safety).
            from app.platform import hq_auto_chase as _hqc

            await _hqc.run_auto_chase()
        elif job == "reply_auto_send":
            # Safe known-prospect auto-reply sweep — DECOUPLED from IMAP triage
            # so replies still go out even if IMAP is down/gated. INERT unless
            # REPLY_AUTO_SEND=1 (+ HARD_OFF override checked inside).
            from app.platform import reply_agent as _reply_agent

            await _reply_agent.run_auto_reply_backlog()
        elif job == "content_approval_sweep":
            # Orphaned-pending approval retirement — dry_run by default (reports
            # counts, writes nothing). CONTENT_APPROVAL_SWEEP_LIVE=1 actuates the
            # write. Clears dead-client pendings (prod: 321 of 422).
            from app.marketing import content_approval as _ca

            live = os.environ.get("CONTENT_APPROVAL_SWEEP_LIVE", "0").strip().lower() in (
                "1",
                "true",
                "yes",
            )
            await asyncio.to_thread(_ca.retire_orphaned_pending, dry_run=not live)
        elif job == "daily_owner_brief":
            from app.agents import staff as _staff

            return await _staff.run_daily_owner_brief()
        elif job == "social_drain":
            from app.social_engine import engine as _social_engine

            # Native social queue drain (Postiz/X/…). INERT unless SOCIAL_ENGINE
            # on (process_queue no-ops). Also recovers stale `processing` jobs.
            await _social_engine.process_queue(30)
        elif job == "obsidian_push":
            from app.platform import obsidian_sync as _obs

            _obs.compact_folder("Leads")
            _obs.compact_folder("Agents")
            _obs.push_to_git()  # sync, never raises; no-op if OBSIDIAN_SYNC unset
        elif job == "process_autostart":
            from app.platform import process_autostart

            await process_autostart.run_due()  # gated PROCESS_AUTOSTART; idempotent
        elif job == "flow_cron":
            from app.automation import flow_triggers

            flow_triggers.run_cron_due()  # sync, never-raise, self-gated (FLOW_RUNNER + FLOW_AUTO_TRIGGERS)
        elif job == "standup":
            # Boss daily standup — hierarchical team coordination (gated AGENT_STANDUP).
            if os.environ.get("AGENT_STANDUP", "0").strip().lower() in ("1", "true", "yes"):
                from app.agents import coordinator

                await coordinator.coordinate_hierarchical(
                    "Aaj ka team plan: growth (naye leads + outreach) aur ops (system health + QA) — "
                    "priorities aur next-actions nikalo"
                )
        elif job == "hot_queue_brief":
            from app.platform import office_briefing

            result = await office_briefing.run_scheduled()
            if result.get("ok") is False:
                return False
        elif job == "hot_queue_owner_pack":
            # ADR-OWNER-1: 09:00 IST daily — build CSV+MD from hot_queue + ntfy push
            from app.platform import hot_queue_owner_pack as _hqop

            r = await _hqop.build_owner_pack(limit=200, push_ntfy=True)
            from app.platform import team

            team.log_event(
                "boss",
                "hot_queue_owner_pack",
                f"Owner action pack built: rows={r.get('rows', 0)} "
                f"ntfy={r.get('ntfy', 'skipped')}",
                status="ok" if r.get("ok") else "warn",
                meta={"rows": r.get("rows"), "csv": r.get("csv"), "md": r.get("md")},
            )
        elif job == "revenue_snapshot":
            # B1: daily MRR/churn/LTV snapshot for the admin revenue trend chart.
            if os.environ.get("REVENUE_TRENDS", "0").strip().lower() in ("1", "true", "yes"):
                from app.platform import revenue_snapshots

                await revenue_snapshots.snapshot_today()
        elif job == "gsc_rank":
            # SEO rank observability: daily Search Console snapshot (free API).
            # INERT — job body no-ops unless GSC_ENABLED=1 + service-account creds.
            from app.integrations import gsc

            await gsc.run_daily_async()
        elif job == "trial_nudge":
            # Trial-to-paid nudge — expiring/expired trials ko Starter UPI link
            # email (BLK-02 2026-08-23). INERT unless TRIAL_NUDGE_ENABLED=1
            # (job body no-ops; TRIAL_NUDGE_HARD_OFF=1 always blocks).
            # Email-only: WhatsApp text sirf OWNER 1-click human ke liye.
            from app.billing import trial_nudge as _tn

            await _tn.run_trial_nudge()
        elif job == "whatsapp_automation":
            # WhatsApp auto-outreach/nudge (gated WHATSAPP_AUTO_SEND=1)
            from app.tasks.whatsapp_automation import run_whatsapp_automation

            await asyncio.to_thread(run_whatsapp_automation)
        elif job == "afternoon_content":
            # 2nd daily content-generation pass (afternoon) — Isha extra social
            # batch (self + clients). Gated AFTERNOON_CONTENT (default OFF; LLM cost).
            # FOCUSED: sirf content-gen (full marketing bundle 07:00 'content' job me).
            if os.environ.get("AFTERNOON_CONTENT", "0").strip().lower() in ("1", "true", "yes"):
                from app.marketing import auto_content
                from app.platform import team

                await auto_content.run_daily_content()
                team.log_event(
                    "isha",
                    "afternoon_content",
                    "✍️ afternoon content pass (2nd daily batch generated)",
                    status="ok",
                )
        elif job == "evening_prospect":
            # 3rd daily FREE lead-supply pass (evening) — extra niche/city rotation
            # via lead_harvester (websearch/opendata/enrich, no paid Places API).
            # Gated EVENING_PROSPECT (default OFF; LEAD_HARVESTER bhi on hona chahiye).
            # Uses safety wrapper for P1 pool cleanup (2026-07-11).
            if os.environ.get("EVENING_PROSPECT", "0").strip().lower() in ("1", "true", "yes"):
                from app.platform import team
                from scripts import harvest_safety_wrapper

                _h = await harvest_safety_wrapper.run_harvest_safe()
                if _h.get("ok"):
                    team.log_event(
                        "rohan",
                        "evening_harvest",
                        f"🌙 evening +{_h.get('new_leads', 0)} leads (dedup {_h.get('deduped', 0)})",
                        status="ok",
                    )
    except Exception as e:
        # W1.2: job-level failure ko SWALLOW mat karo — return False taaki caller
        # (_run_job) dead-man switch me real status (ok=False) record kare. Warna
        # har run "success" record hota raha aur overdue-alert kabhi fire nahi karta.
        logger.warning(f"[team-scheduler] job {job} failed: {e}")
        return False
    return True


async def scheduler_loop() -> None:
    logger.info("[team-scheduler] loop started (growth 15min + dailies)")
    # W1.7: persisted last-run markers boot pe load — MUST boot-grace se PEHLE chale
    # (warna load boot-grace ke in-window skip-marks ko stale values se overwrite karke
    # heavy job ko boot pe chala dega = prod-000 boot-storm). Reorder mat karo.
    _load_last_ran()
    _boot_seeded = False
    while True:
        _snap = dict(_last_ran)  # W1.7: tick ke baad koi marker badla to persist karenge
        try:
            _refresh_lock()  # heartbeat — owner zinda hai
            now = datetime.now(_IST)
            hour_key = now.strftime("%Y-%m-%d %H")
            day_key = now.strftime("%Y-%m-%d")
            hm = (now.hour, now.minute)

            # BOOT GRACE (one-time): agar restart kisi HEAVY daily job ke window me
            # hua, to use is boot pe SKIP karo (mark done). Warna boot pe qa/content
            # jaisa heavy job event-loop block karke HTTP starve karta tha (prod 000
            # during 2:30-4:00 IST qa window). Daily job apne next din normal chalega;
            # growth(15min)/hourly jobs unaffected.
            if not _boot_seeded:
                _boot_seeded = True
                _heavy = {
                    "qa": ((2, 30), (4, 0)),
                    "trainer": ((3, 0), (4, 30)),
                    "blog": ((6, 30), (8, 30)),
                    "content": ((7, 0), (9, 0)),
                    "hot_queue_brief": ((8, 15), (9, 15)),
                    "digest": ((8, 30), (10, 30)),
                    "prospect": ((9, 30), (11, 30)),
                    "email_outreach": ((10, 30), (12, 30)),
                    "pipeline": ((11, 0), (12, 0)),
                    "email_followup": ((16, 0), (17, 30)),
                    "kb_refresh": ((5, 0), (6, 30)),
                    "midday_prospect": ((14, 30), (15, 30)),
                    "afternoon_content": ((15, 0), (16, 0)),
                    "evening_prospect": ((17, 0), (18, 0)),
                    "evening_wrap": ((18, 30), (19, 30)),
                    "weekly_marketing": ((12, 30), (13, 30)),
                    "saturday_hygiene": ((4, 0), (5, 30)),
                }
                for _jk, (_lo, _hi) in _heavy.items():
                    if _lo <= hm < _hi:
                        if _jk == "kb_refresh":
                            _last_ran[_jk] = now.strftime("%Y-W%W")
                        else:
                            _last_ran[_jk] = day_key
                        logger.info(
                            f"[team-scheduler] boot-grace: {_jk} skipped this boot (window active)"
                        )
                        try:  # SP3: make the silent skip visible (gated LOOP_SUPERVISOR)
                            from app.platform import loop_supervisor as _ls

                            _ls.alert_boot_grace_skip(_jk)
                        except Exception:
                            pass

            slot_min = (now.minute // 15) * 15
            slot_key = now.strftime("%Y-%m-%d %H:") + f"{slot_min:02d}"
            if _last_ran.get("growth") != slot_key:
                _last_ran["growth"] = slot_key
                await _run_job("growth")

            # Flow Runner cron scan — 5-min slot (in-process / rollback path; durable = beat)
            fc_min = (now.minute // 5) * 5
            fc_slot = now.strftime("%Y-%m-%d %H:") + f"{fc_min:02d}"
            if _last_ran.get("flow_cron") != fc_slot:
                _last_ran["flow_cron"] = fc_slot
                await _run_job("flow_cron")

            if now.minute >= 5 and _last_ran["ops"] != hour_key:
                _last_ran["ops"] = hour_key
                await _run_job("ops")
            if (0, 5) <= hm < (0, 35) and _last_ran["revenue_snapshot"] != day_key:
                _last_ran["revenue_snapshot"] = day_key
                await _run_job(
                    "revenue_snapshot"
                )  # B1 daily MRR snapshot (light, gated REVENUE_TRENDS)
            if (0, 30) <= hm < (1, 0) and _last_ran["gsc_rank"] != day_key:
                _last_ran["gsc_rank"] = day_key
                await _run_job("gsc_rank")  # GSC rank snapshot (light, gated GSC_ENABLED)
            if (9, 50) <= hm < (10, 50) and _last_ran["trial_nudge"] != day_key:
                _last_ran["trial_nudge"] = day_key
                await _run_job(
                    "trial_nudge"
                )  # trial UPI nudge email (light, gated TRIAL_NUDGE_ENABLED)
            if (2, 30) <= hm < (4, 0) and _last_ran["qa"] != day_key:
                _last_ran["qa"] = day_key
                await _run_job("qa")
            if (3, 0) <= hm < (4, 30) and _last_ran["trainer"] != day_key:
                _last_ran["trainer"] = day_key
                await _run_job("trainer")
            if (8, 15) <= hm < (9, 15) and _last_ran["hot_queue_brief"] != day_key:
                _last_ran["hot_queue_brief"] = day_key
                await _run_job("hot_queue_brief")
            if (8, 30) <= hm < (10, 30) and _last_ran["digest"] != day_key:
                _last_ran["digest"] = day_key
                await _run_job("digest")
            if (6, 30) <= hm < (8, 30) and _last_ran["blog"] != day_key:
                _last_ran["blog"] = day_key
                await _run_job("blog")
            if (7, 0) <= hm < (9, 0) and _last_ran["content"] != day_key:
                _last_ran["content"] = day_key
                await _run_job("content")
            if (9, 30) <= hm < (11, 30) and _last_ran["prospect"] != day_key:
                _last_ran["prospect"] = day_key
                await _run_job("prospect")
            _email_hour_key = f"{day_key}:{now.hour}"
            if (
                9 <= now.hour <= 19
                and hm[1] < 20
                and _last_ran["email_outreach"] != _email_hour_key
            ):
                _last_ran["email_outreach"] = _email_hour_key
                await _run_job("email_outreach")
            if (11, 0) <= hm < (12, 0) and _last_ran["pipeline"] != day_key:
                _last_ran["pipeline"] = day_key
                await _run_job("pipeline")
            if (
                9 <= now.hour <= 19
                and hm[1] >= 20
                and _last_ran["email_followup"] != _email_hour_key
            ):
                _last_ran["email_followup"] = _email_hour_key
                await _run_job("email_followup")
            # 11:30–12:30 IST — daily self-sale AI cold-call batch. Gated PLATFORM_DIAL_DAILY.
            if (11, 30) <= hm < (12, 30) and _last_ran["platform_dial"] != day_key:
                _last_ran["platform_dial"] = day_key
                await _run_job("platform_dial")
            # 14:30–15:30 IST — 2nd free lead-supply pass (harvest). Gated MIDDAY_PROSPECT.
            if (14, 30) <= hm < (15, 30) and _last_ran["midday_prospect"] != day_key:
                _last_ran["midday_prospect"] = day_key
                await _run_job("midday_prospect")
            # 15:00–16:00 IST — 2nd content-gen pass (Isha). Gated AFTERNOON_CONTENT.
            if (15, 0) <= hm < (16, 0) and _last_ran["afternoon_content"] != day_key:
                _last_ran["afternoon_content"] = day_key
                await _run_job("afternoon_content")
            # 17:00–18:00 IST — 3rd FREE lead-harvest pass (Rohan). Gated EVENING_PROSPECT.
            if (17, 0) <= hm < (18, 0) and _last_ran["evening_prospect"] != day_key:
                _last_ran["evening_prospect"] = day_key
                await _run_job("evening_prospect")
            if (18, 30) <= hm < (19, 30) and _last_ran["evening_wrap"] != day_key:
                _last_ran["evening_wrap"] = day_key
                await _run_job("evening_wrap")
            if (19, 30) <= hm < (20, 30) and _last_ran["call_kpi_digest"] != day_key:
                _last_ran["call_kpi_digest"] = day_key
                await _run_job("call_kpi_digest")
            if (
                now.weekday() == 2
                and (12, 30) <= hm < (13, 30)
                and _last_ran["weekly_marketing"] != day_key
            ):
                _last_ran["weekly_marketing"] = day_key
                await _run_job("weekly_marketing")
            if (
                now.weekday() == 5
                and (4, 0) <= hm < (5, 30)
                and _last_ran["saturday_hygiene"] != day_key
            ):
                _last_ran["saturday_hygiene"] = day_key
                await _run_job("saturday_hygiene")
            # Sunday 05:00–06:30 IST — weekly KB contextual re-ingest (gated).
            week_key = now.strftime("%Y-W%W")
            if (
                now.weekday() == 6
                and (5, 0) <= hm < (6, 30)
                and _last_ran["kb_refresh"] != week_key
            ):
                _last_ran["kb_refresh"] = week_key
                await _run_job("kb_refresh")
            # AI reply triage — hourly (read inbox replies, classify, draft). Gated by REPLY_AGENT.
            if now.minute >= 20 and _last_ran["reply_triage"] != hour_key:
                _last_ran["reply_triage"] = hour_key
                await _run_job("reply_triage")
            # AI ops watchdog — hourly (monitor + diagnose + alert). Gated by OPS_WATCHDOG.
            if now.minute >= 35 and _last_ran["watchdog"] != hour_key:
                _last_ran["watchdog"] = hour_key
                await _run_job("watchdog")
            # Auto client onboarding — hourly sweep (un-setup active clients). Gated AUTO_ONBOARD.
            if now.minute >= 50 and _last_ran["onboard"] != hour_key:
                _last_ran["onboard"] = hour_key
                await _run_job("onboard")
            # Obsidian nightly push — 02:15–03:00 IST (INERT unless OBSIDIAN_SYNC=1).
            if (2, 15) <= hm < (3, 0) and _last_ran.get("obsidian_push") != day_key:
                _last_ran["obsidian_push"] = day_key
                await _run_job("obsidian_push")
            # SP1 billing meter-failure watcher — hourly :55 (INERT unless METER_ALERTS=1).
            if now.minute >= 55 and _last_ran.get("meter_watch") != hour_key:
                _last_ran["meter_watch"] = hour_key
                await _run_job("meter_watch")
            # Product 1 Customer Health + Approval Reminder + SLA Recovery sweep — hourly :20.
            if now.minute >= 20 and _last_ran.get("product_one_health") != hour_key:
                _last_ran["product_one_health"] = hour_key
                await _run_job("product_one_health")
            # Renewal reminders — private day-key (NOT _last_ran / STAFF_JOBS).
            # Body no-ops when DUNNING_ENGINE covers renewals. Celery prod
            # (RUN_IN_PROCESS_SCHEDULER=0) never enters this loop.
            global _renewal_reminders_day
            if _renewal_reminders_day != day_key:
                _renewal_reminders_day = day_key
                try:
                    from app.billing import dunning

                    await dunning.send_renewal_reminders()
                except Exception:
                    pass
            # Bounded pending-approval EMAIL sweep — hourly :40 (INERT unless APPROVAL_EMAIL_NOTIFY=1).
            if now.minute >= 40 and _last_ran.get("approval_email_sweep") != hour_key:
                _last_ran["approval_email_sweep"] = hour_key
                await _run_job("approval_email_sweep")
            if now.minute >= 25 and _last_ran.get("sales_autopilot") != hour_key:
                _last_ran["sales_autopilot"] = hour_key
                await _run_job("sales_autopilot")
            # Hot Queue auto-chase — hourly :28 (INERT unless HQ_AUTO_CHASE=1).
            if now.minute >= 28 and _last_ran.get("hq_auto_chase") != hour_key:
                _last_ran["hq_auto_chase"] = hour_key
                await _run_job("hq_auto_chase")
            # Safe known-prospect auto-reply — hourly :30 (INERT unless REPLY_AUTO_SEND=1).
            if now.minute >= 30 and _last_ran.get("reply_auto_send") != hour_key:
                _last_ran["reply_auto_send"] = hour_key
                await _run_job("reply_auto_send")
            # Orphaned-pending approval retirement — daily 04:30 (dry_run default;
            # CONTENT_APPROVAL_SWEEP_LIVE=1 actuates writes).
            if (4, 30) <= hm < (5, 30) and _last_ran.get("content_approval_sweep") != day_key:
                _last_ran["content_approval_sweep"] = day_key
                await _run_job("content_approval_sweep")
            # Daily owner brief + ntfy push — 08:10 IST (gated DAILY_OWNER_BRIEF_NTFY).
            if (8, 10) <= hm < (9, 10) and _last_ran.get("daily_owner_brief") != day_key:
                _last_ran["daily_owner_brief"] = day_key
                await _run_job("daily_owner_brief")
            # Expired agent-task lease reclaim — hourly :05 (INERT unless AGENT_TASK_LEASE_REAP=1).
            if now.minute >= 5 and _last_ran.get("task_lease_reap") != hour_key:
                _last_ran["task_lease_reap"] = hour_key
                await _run_job("task_lease_reap")
            # Native social queue drain — hourly :10 (INERT unless SOCIAL_ENGINE=1).
            if now.minute >= 10 and _last_ran.get("social_drain") != hour_key:
                _last_ran["social_drain"] = hour_key
                await _run_job("social_drain")
            # D V1.1 process-engine auto-start — daily 11:30–13:00 IST (INERT unless PROCESS_AUTOSTART=1).
            if (11, 30) <= hm < (13, 0) and _last_ran.get("process_autostart") != day_key:
                _last_ran["process_autostart"] = day_key
                await _run_job("process_autostart")
            # Boss daily standup — morning hierarchical coordination (gated AGENT_STANDUP).
            if (8, 0) <= hm < (9, 30) and _last_ran["standup"] != day_key:
                _last_ran["standup"] = day_key
                await _run_job("standup")
            # F.5 Pranav SRE — reliability score, hourly (engine INERT unless SRE_AGENT=1).
            if now.minute >= 45 and _last_ran["engineer_sre"] != hour_key:
                _last_ran["engineer_sre"] = hour_key
                await _run_job("engineer_sre")
            # council 2026-06-26: Arya MCP Engineer — hourly :40 health pulse
            # (engine INERT unless MCP_ENGINEER=1). Offset from :45 (Pranav SRE)
            # so they don't slam the same minute on the in-process scheduler.
            if now.minute >= 40 and _last_ran.get("mcp_engineer") != hour_key:
                _last_ran["mcp_engineer"] = hour_key
                await _run_job("mcp_engineer")
            # F.5 Vidya FinOps — daily morning margin score (engine INERT unless FINOPS_AGENT=1).
            if (9, 0) <= hm < (10, 0) and _last_ran["engineer_finops"] != day_key:
                _last_ran["engineer_finops"] = day_key
                await _run_job("engineer_finops")
            # F.5 Arnav Security — daily morning compliance posture (engine INERT unless SECURITY_AGENT=1).
            if (9, 30) <= hm < (10, 30) and _last_ran["engineer_security"] != day_key:
                _last_ran["engineer_security"] = day_key
                await _run_job("engineer_security")
            # council: Kabir DB reliability — daily 10:00 (engine INERT unless DBRE_AGENT=1).
            if (10, 0) <= hm < (11, 0) and _last_ran.get("engineer_dbre") != day_key:
                _last_ran["engineer_dbre"] = day_key
                await _run_job("engineer_dbre")
            # council: Diya lead/CRM data integrity — daily 10:30 (engine INERT unless DATA_INTEGRITY_AGENT=1).
            if (10, 30) <= hm < (11, 30) and _last_ran.get("engineer_dataquality") != day_key:
                _last_ran["engineer_dataquality"] = day_key
                await _run_job("engineer_dataquality")
            # council: Aryan dependency CVE audit — weekly Sun 04:30 (engine INERT unless DEPS_AGENT=1).
            if (
                now.weekday() == 6
                and (4, 30) <= hm < (5, 0)
                and _last_ran.get("engineer_deps") != week_key
            ):
                _last_ran["engineer_deps"] = week_key
                await _run_job("engineer_deps")
            # G.3 daily activation-readiness digest — quiet ntfy unless BLOCKER present.
            if (8, 30) <= hm < (9, 30) and _last_ran["readiness_digest"] != day_key:
                _last_ran["readiness_digest"] = day_key
                await _run_job("readiness_digest")
        except asyncio.CancelledError:
            logger.info("[team-scheduler] loop cancelled")
            raise
        except Exception as e:
            logger.warning(f"[team-scheduler] tick failed: {e}")
        if _last_ran != _snap:  # W1.7: is tick me koi marker badla → disk pe persist
            _save_last_ran()
        await asyncio.sleep(_TICK_S)


def start_scheduler() -> asyncio.Task[Any] | None:
    try:
        flag = "1"
        try:
            from app.config import settings

            flag = str(
                getattr(settings, "team_automation", None) or os.environ.get("TEAM_AUTOMATION", "1")
            )
        except Exception:
            flag = os.environ.get("TEAM_AUTOMATION", "1")
        if flag.strip() == "0":
            logger.info("[team-scheduler] TEAM_AUTOMATION=0 — scheduler OFF")
            return None
        # Single-instance: sirf EK worker scheduler chalaye (warna double jobs).
        if not _acquire_lock():
            logger.info(
                "[team-scheduler] another worker owns the scheduler — skip (single-instance)"
            )
            return None
        task = asyncio.create_task(scheduler_loop(), name="team-scheduler")
        try:
            from app.platform import team

            team.log_event(
                "manager", "automation_started", "Team scheduler on (growth 15min + dailies)"
            )
        except Exception:
            pass
        logger.info("[team-scheduler] started")
        return task
    except Exception as e:
        logger.warning(f"[team-scheduler] start failed: {e}")
        return None


__all__ = ["scheduler_loop", "start_scheduler"]
