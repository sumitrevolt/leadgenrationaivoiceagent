from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_TICK_S = 60

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
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
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
            # exists — stale ya dead-pid ho to steal karo
            try:
                age = datetime.now().timestamp() - os.path.getmtime(_LOCK_PATH)
                pid = int((open(_LOCK_PATH).read().strip() or "0") or 0)
            except Exception:
                age, pid = 9999, 0
            if age > _LOCK_STALE_S or (pid and not _pid_alive(pid)) or pid == 0:
                try:
                    with open(_LOCK_PATH, "w") as f:
                        f.write(str(os.getpid()))
                    _have_lock = True
                    return True
                except Exception:
                    return False
            return False
    except Exception:
        # lock-fs issue — fail-open (chalne do; single-worker dev me theek)
        _have_lock = True
        return True


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
}


async def _run_job(job: str) -> None:
    """Heartbeat wrapper — har run automation_health me record hota (dead-man
    switch: job chupchaap band ho jaye to overdue-alert). In-process + Celery
    dono path isi se guzarte. Wrapper KABHI behaviour change nahi karta."""
    import time as _time

    _t0 = _time.monotonic()
    _ok = True
    try:
        await _run_job_inner(job)
    except Exception:
        _ok = False
        raise
    finally:
        try:
            from app.platform import automation_health

            automation_health.record_run(job, _ok, _time.monotonic() - _t0)
        except Exception:
            pass


async def _run_job_inner(job: str) -> None:
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
        elif job == "ops":
            await staff.run_ops()
        elif job == "qa":
            await staff.run_qa()
        elif job == "trainer":
            await staff.run_trainer()
        elif job == "digest":
            await staff.run_digest()
            from app.platform import revenue_digest

            await revenue_digest.maybe_run_weekly()  # Monday-only weekly MRR digest (gated REVENUE_DIGEST)
            from app.platform import client_health

            await client_health.run_check()  # churn-risk scan (alert gated CLIENT_HEALTH_ALERTS)
            from app.billing import usage_alerts

            await usage_alerts.run_check()  # 80%/100% minute upsell triggers (gated USAGE_ALERTS)
            from app.agents import growth_optimizer

            await growth_optimizer.optimize()  # daily self-healing profit loop (gated GROWTH_OPTIMIZER)
            try:
                from app.billing import payment_recon

                await payment_recon.run_if_enabled()  # Razorpay vs invoices recon (gated PAYMENT_RECON)
            except Exception:
                pass
            try:
                # Speed-to-lead accountability line (READ-only metric) — Boss event me.
                from app.platform import speed_to_lead, team

                _stl = speed_to_lead.summary(7)
                if _stl.get("ok") and _stl.get("verdict"):
                    team.log_event("boss", "speed_to_lead", f"⚡ {_stl['verdict']}")
            except Exception:
                pass
        elif job == "content":
            from app.marketing import auto_content

            await auto_content.run_daily_content()
            from app.marketing import content_schedule

            await content_schedule.run_due()  # date-scheduled posts auto-prepare
            from app.tasks.reporting import run_social_autopost

            # Publish 'ready' posts to connected Meta accounts (MOCK unless
            # SOCIAL_AUTOPOST=1 + a Page/IG token — inert/safe otherwise).
            await run_social_autopost()
            from app.marketing import wa_campaign_runner

            await wa_campaign_runner.run_due()  # WhatsApp drip/reactivation (inert without creds)
            from app.marketing import cadence

            await cadence.run_due()  # omnichannel cadence advance (gated CADENCE_ENGINE; inert off)
            from app.marketing import sales_pipeline

            await sales_pipeline.run_pipeline()  # sales deals auto next-action (gated SALES_ENGINE)
            from app.billing import dunning

            await dunning.run_due()  # payment-recovery sweep (gated DUNNING_ENGINE; inert off)
            from app.marketing import lifecycle_nurture

            await lifecycle_nurture.run_due()  # signup->paid nurture (gated LIFECYCLE_NURTURE; inert off)
            from app.marketing import channel_experiments

            await channel_experiments.run_daily(3)  # naye approach-channel experiments (gated CHANNEL_EXPERIMENTS)
            from app.platform import booking_reminders

            await booking_reminders.run_due()  # kal ki bookings ke reminders (gated BOOKING_REMINDERS)
            from app.marketing import review_monitor

            await review_monitor.run_check()  # naye Google reviews -> AI reply drafts (gated REVIEW_MONITOR)
            try:
                from app.marketing import customer_crm

                await customer_crm.run_wishes_if_enabled()  # birthday/anniversary wish DRAFTS (gated CUSTOMER_WISHES)
            except Exception:
                pass
            try:
                from app.platform import service_reminders

                await service_reminders.run_due_if_enabled()  # repeat-service WA reminder DRAFTS (gated SERVICE_REMINDERS)
            except Exception:
                pass
            try:
                from app.platform import rank_tracker

                await rank_tracker.run_if_enabled()  # local rank tracking sweep (gated RANK_TRACKER, cap lookups)
            except Exception:
                pass
            try:
                from app.platform import memory_vault

                await memory_vault.sync_if_enabled()  # compounding memory tail-sync (gated MEMORY_VAULT, no LLM)
            except Exception:
                pass
            try:
                from app.platform import live_notes

                await live_notes.refresh_if_enabled()  # topic live-notes refresh (gated LIVE_NOTES, max 5/day)
            except Exception:
                pass
            try:
                from app.agents import sales_team

                await sales_team.run_auto(3)  # 5-agent prospect deep-dives on hot leads (gated SALES_TEAM)
            except Exception:
                pass
            try:
                # White-label monthly client report — mahine ki 1 tarikh ko hi.
                # Email sirf CLIENT_REPORTS=1 pe jata (warna file-only) — run_monthly khud gate karta.
                from datetime import datetime as _dt

                if _dt.now().day == 1:
                    from app.marketing import client_report

                    await client_report.run_monthly()
            except Exception:
                pass
        elif job == "blog":
            from app.marketing import seo_blog

            await seo_blog.run_daily_blog(3)
            try:
                from app.marketing import indexnow

                await indexnow.submit_sitemap_if_enabled()  # naye URLs Bing/Yandex pe (gated INDEXNOW)
            except Exception:
                pass
        elif job == "prospect":
            # NICHE_ROTATION=1 → all-42-niches round-robin (niche_prospector); warna
            # default 4-niche prospector (aaj jaisa). Gated = zero behaviour change.
            if os.environ.get("NICHE_ROTATION", "0").strip().lower() in ("1", "true", "yes"):
                from app.platform import niche_prospector

                await niche_prospector.run(batch=8)
            else:
                from app.platform import prospector

                await prospector.run_prospecting()
            # Multi-source harvest sweep (websearch/opendata/enrich) — gated
            # LEAD_HARVESTER=1, gated sources bina key inert. Legal-only sources.
            try:
                from app.platform import lead_harvester

                await lead_harvester.run_loop_sweep()
            except Exception:
                pass
        elif job == "email_outreach":
            from app.platform import auto_outreach

            await auto_outreach.run_email_outreach()
            await auto_outreach.run_email_followups()
        elif job == "reply_triage":
            from app.platform import reply_agent

            await reply_agent.run_reply_triage()
        elif job == "watchdog":
            from app.platform import ops_watchdog

            await ops_watchdog.run_watchdog()
            from app.platform import deliverability_monitor

            await deliverability_monitor.run_check()  # SPF/DMARC + blacklist (alert gated DELIVERABILITY_MONITOR)
            from app.platform import automation_health

            await automation_health.run_watch()  # dead-man switch: overdue jobs alert (gated AUTOMATION_HEALTH_ALERTS)
            from app.telephony import telephony_readiness

            await telephony_readiness.run_watch()  # Tara: calling-launch readiness score (alert gated TELEPHONY_READY_ALERTS)
            from app.platform import dlq_retry

            await dlq_retry.run_sweep()  # failed staff-jobs auto-retry+backoff (gated DLQ_AUTO_RETRY; off = no-op)
            from app.platform import integration_health

            await integration_health.run_watch()  # integration silent-failure alert (gated INTEGRATION_ALERTS; off = sirf counters)
            from app.agents import self_improve

            self_improve.ensure_alive()  # continuous-loop dead-man revive (gated SELF_IMPROVE_LOOP; sirf Celery enqueue, inline kabhi nahi)
            try:
                from app.platform import proposal_tracking

                proposal_tracking.sweep_new_opens()  # "proposal khola" event sweep (file-IO only, no send)
            except Exception:
                pass
        elif job == "onboard":
            from app.marketing import onboarding

            await onboarding.run_onboarding_sweep()
        elif job == "standup":
            # Boss daily standup — hierarchical team coordination (gated AGENT_STANDUP).
            if os.environ.get("AGENT_STANDUP", "0").strip().lower() in ("1", "true", "yes"):
                from app.agents import coordinator

                await coordinator.coordinate_hierarchical(
                    "Aaj ka team plan: growth (naye leads + outreach) aur ops (system health + QA) — "
                    "priorities aur next-actions nikalo"
                )
    except Exception as e:
        logger.warning(f"[team-scheduler] job {job} failed: {e}")


async def scheduler_loop() -> None:
    logger.info("[team-scheduler] loop started (growth 15min + dailies)")
    _boot_seeded = False
    while True:
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
                    "digest": ((8, 30), (10, 30)),
                    "prospect": ((9, 30), (11, 30)),
                    "email_outreach": ((10, 30), (12, 30)),
                }
                for _jk, (_lo, _hi) in _heavy.items():
                    if _lo <= hm < _hi:
                        _last_ran[_jk] = day_key
                        logger.info(f"[team-scheduler] boot-grace: {_jk} skipped this boot (window active)")

            slot_min = (now.minute // 15) * 15
            slot_key = now.strftime("%Y-%m-%d %H:") + f"{slot_min:02d}"
            if _last_ran.get("growth") != slot_key:
                _last_ran["growth"] = slot_key
                await _run_job("growth")

            if now.minute >= 5 and _last_ran["ops"] != hour_key:
                _last_ran["ops"] = hour_key
                await _run_job("ops")
            if (2, 30) <= hm < (4, 0) and _last_ran["qa"] != day_key:
                _last_ran["qa"] = day_key
                await _run_job("qa")
            if (3, 0) <= hm < (4, 30) and _last_ran["trainer"] != day_key:
                _last_ran["trainer"] = day_key
                await _run_job("trainer")
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
            if (10, 30) <= hm < (12, 30) and _last_ran["email_outreach"] != day_key:
                _last_ran["email_outreach"] = day_key
                await _run_job("email_outreach")
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
            # Boss daily standup — morning hierarchical coordination (gated AGENT_STANDUP).
            if (8, 0) <= hm < (9, 30) and _last_ran["standup"] != day_key:
                _last_ran["standup"] = day_key
                await _run_job("standup")
        except asyncio.CancelledError:
            logger.info("[team-scheduler] loop cancelled")
            raise
        except Exception as e:
            logger.warning(f"[team-scheduler] tick failed: {e}")
        await asyncio.sleep(_TICK_S)


def start_scheduler() -> asyncio.Task[Any] | None:
    try:
        flag = "1"
        try:
            from app.config import settings

            flag = str(getattr(settings, "team_automation", None) or os.environ.get("TEAM_AUTOMATION", "1"))
        except Exception:
            flag = os.environ.get("TEAM_AUTOMATION", "1")
        if flag.strip() == "0":
            logger.info("[team-scheduler] TEAM_AUTOMATION=0 — scheduler OFF")
            return None
        # Single-instance: sirf EK worker scheduler chalaye (warna double jobs).
        if not _acquire_lock():
            logger.info("[team-scheduler] another worker owns the scheduler — skip (single-instance)")
            return None
        task = asyncio.create_task(scheduler_loop(), name="team-scheduler")
        try:
            from app.platform import team

            team.log_event("manager", "automation_started", "Team scheduler on (growth 15min + dailies)")
        except Exception:
            pass
        logger.info("[team-scheduler] started")
        return task
    except Exception as e:
        logger.warning(f"[team-scheduler] start failed: {e}")
        return None


__all__ = ["scheduler_loop", "start_scheduler"]
