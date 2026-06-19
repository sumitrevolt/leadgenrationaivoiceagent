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
    # F.5 engineer agents — gated by per-role flag inside run_X() (INERT default).
    "engineer_sre": None,       # hourly: Pranav reliability score
    "engineer_finops": None,    # daily: Vidya margin score
    "engineer_security": None,  # daily: Arnav compliance posture
    "readiness_digest": None,   # G.3: daily activation-readiness ntfy digest (OPS_ALERTS gated)
    "pipeline": None,           # daily: lead rescore + hot-lead surfacing (Neha/Rohan)
    "email_followup": None,     # daily afternoon: Day-3/7 followups only
    "kb_refresh": None,         # weekly Sun: contextual KB re-ingest (gated)
    "midday_prospect": None,    # daily 14:30: 2nd free lead-supply pass (gated MIDDAY_PROSPECT)
    "evening_wrap": None,       # daily 18:30: EOD summary + hot recap
    "weekly_marketing": None,   # Wed 12:30: S-tier niche pack bank
    "saturday_hygiene": None,   # Sat 04:00: DLQ + celery trim (gated SCHEDULER_HYGIENE)
    "meter_watch": None,        # hourly :55: billing meter-failure watcher (gated METER_ALERTS)
    "process_autostart": None,  # daily ~11:30 IST: process-engine auto-start (gated PROCESS_AUTOSTART)
    "revenue_snapshot": None,   # daily ~00:15 IST: B1 MRR/churn snapshot (gated REVENUE_TRENDS)
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
            # Self-improve in-process fallback —
            # Celery mode me Celery tasks handle karte hain.
            # In-process mode (RUN_IN_PROCESS_SCHEDULER=1) me Celery tick kabhi fire nahi
            # hota, isliye yahan directly run_once() call karo (15-min cadence = theek hai).
            try:
                from app.agents import self_improve

                _celery_off = os.environ.get("RUN_IN_PROCESS_SCHEDULER", "1").strip() in ("1", "true", "yes")
                if _celery_off and self_improve.enabled():
                    result = await self_improve.run_once()
                    logger.debug(f"[scheduler] self_improve in-process: {result.get('action','?')} ok={result.get('ok')}")
            except Exception as _si_e:
                logger.debug(f"[scheduler] self_improve in-process skip: {_si_e}")
            # Process engine in-process tick —
            # Celery pe `process_tick` Celery task handle karta hai.
            # In-process mode me RUNNING processes (non-breakpoint steps) yahan advance hote hain.
            try:
                _celery_off2 = os.environ.get("RUN_IN_PROCESS_SCHEDULER", "1").strip() in ("1", "true", "yes")
                if _celery_off2:
                    from app.agents.process_engine import list_runs, advance

                    _running = [r for r in list_runs() if r.get("status") == "running"]
                    for _pr in _running[:3]:  # max 3 per tick — no runaway
                        try:
                            await advance(_pr["run_id"], max_steps=3)
                        except Exception:
                            pass
            except Exception as _pe_e:
                logger.debug(f"[scheduler] process_engine tick skip: {_pe_e}")
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

                    _rep = await asyncio.wait_for(run_suite(_vfactory), timeout=300)
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
                import json as _json_eval
                from pathlib import Path

                from app.agents import eval_gate, eval_metrics
                from app.platform import team

                _tdir = Path("data/call_transcripts")
                convos: list[list] = []
                if _tdir.is_dir():
                    for fp in sorted(_tdir.glob("*.jsonl"))[-5:]:
                        try:
                            for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
                                line = line.strip()
                                if not line:
                                    continue
                                rec = _json_eval.loads(line)
                                msgs = rec.get("messages")
                                if isinstance(msgs, list) and msgs:
                                    convos.append(msgs)
                        except Exception:
                            continue
                if not convos:
                    convos = [[
                        {"role": "assistant", "content": "Main LeadGen AI se ek AI assistant hoon."},
                        {"role": "user", "content": "haan boliye"},
                    ]]
                scores = [eval_metrics.transcript_quality(m) for m in convos]
                mean = round(sum(scores) / len(scores), 4) if scores else 1.0
                gate = eval_gate.score_and_gate("voice_transcript", mean, meta={"n": len(convos)})
                team.log_event(
                    "arjun",
                    "voice_eval_guardrail",
                    f"📊 transcript quality {mean:.2f} · gate {gate.get('decision', 'ok')}",
                    status="ok" if gate.get("decision") != "reject" else "warn",
                )
            except Exception:
                pass
        elif job == "trainer":
            await staff.run_trainer()
            try:
                # Guru: project skills → KB ingest (semantic recall; gated SKILL_PACK)
                from app.platform import skill_pack, team

                if skill_pack.enabled():
                    res = skill_pack.ingest_to_kb()
                    if res.get("ok"):
                        team.log_event("guru", "skill_ingest", f"📚 {res.get('skills', 0)} skills → KB ({res.get('chunks', 0)} chunks, {res.get('backend')})")
            except Exception:
                pass
            try:
                # Dev/Meera: nightly ML training (intent classifier + lead scorer +
                # prompt-opt + A/B variants) — dormant engine wire, gated
                # ML_NIGHTLY_TRAINING. Internally try/excepted; hard deadline 900s.
                if os.environ.get("ML_NIGHTLY_TRAINING", "0").strip().lower() in ("1", "true", "yes"):
                    from app.ml.auto_trainer import auto_trainer
                    from app.platform import team

                    _ml = await asyncio.wait_for(auto_trainer.run_nightly_training(), timeout=900)
                    team.log_event(
                        "dev",
                        "ml_training",
                        f"🧠 nightly ML train: {_ml.get('status')} ({float(_ml.get('duration_seconds') or 0):.0f}s)",
                        status="ok" if _ml.get("status") == "success" else "warn",
                    )
            except Exception:
                pass
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
            # payment_recon removed 2026-06-18 — Razorpay gateway gone (manual UPI).
            try:
                # Speed-to-lead accountability line (READ-only metric) — Boss event me.
                from app.platform import speed_to_lead, team

                _stl = speed_to_lead.summary(7)
                if _stl.get("ok") and _stl.get("verdict"):
                    team.log_event("boss", "speed_to_lead", f"⚡ {_stl['verdict']}")
            except Exception:
                pass
            try:
                from app.platform import brand_pulse

                await brand_pulse.run_weekly_if_enabled()  # brand mention scan + drafts (gated BRAND_PULSE; LLM-free scan)
            except Exception:
                pass
            try:
                from app.platform import team_report

                await team_report.run_weekly_if_enabled()  # client-facing AI-staff weekly narrative (gated TEAM_REPORT)
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
            try:
                from app.marketing import telegram_publish

                await telegram_publish.run_due()  # Telegram channel auto-publish (gated TELEGRAM_AUTO_PUBLISH; inert off)
            except Exception:
                pass
            try:
                from app.marketing import content_distribute

                await content_distribute.publish_ready_to_telegram()  # SP5 self-brand 'ready'->Telegram (gated CONTENT_AUTOPUBLISH; inert off)
            except Exception:
                pass
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
                from app.marketing import newsletter

                await newsletter.run_due_if_enabled()  # monthly client-newsletter (gated NEWSLETTER_ENGINE; month-dedupe)
            except Exception:
                pass
            try:
                from app.platform import winback

                await winback.run_due_if_enabled()  # inactive win-back DRAFTS (gated WINBACK_ENGINE)
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
            from app.platform import infra_handler

            await infra_handler.run_watch()  # Hermes: full infra score+actions (alert gated INFRA_HANDLER; off = no-op)
            from app.platform import llm_metrics

            await llm_metrics.run_capacity_watch()  # LLM gateway capacity/fallback alert (gated LLM_CAPACITY_ALERTS; #1 bottleneck self-flag)
            from app.platform import dlq_retry

            await dlq_retry.run_sweep()  # failed staff-jobs auto-retry+backoff (gated DLQ_AUTO_RETRY; off = no-op)
            from app.platform import integration_health

            await integration_health.run_watch()  # integration silent-failure alert (gated INTEGRATION_ALERTS; off = sirf counters)
            from app.agents import self_improve

            self_improve.ensure_alive()  # continuous-loop dead-man revive (gated SELF_IMPROVE_LOOP; sirf Celery enqueue, inline kabhi nahi)
            try:
                from app.agents import process_engine

                process_engine.ensure_alive()  # stale RUNNING workflows → process_tick revive
            except Exception:
                pass
            try:
                from app.platform import proposal_tracking

                proposal_tracking.sweep_new_opens()  # "proposal khola" event sweep (file-IO only, no send)
            except Exception:
                pass
            try:
                from app.agents import code_upgrader

                await code_upgrader.run_if_enabled()  # Vikram: code-upgrade proposals (gated CODE_UPGRADER; off = no-op)
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
            if os.environ.get("MIDDAY_PROSPECT", "1").strip().lower() in ("1", "true", "yes"):
                from app.platform import lead_harvester, team

                _h = await lead_harvester.run_harvest()
                if _h.get("ok"):
                    team.log_event(
                        "rohan",
                        "midday_harvest",
                        f"🌾 midday +{_h.get('new_leads', 0)} leads (dedup {_h.get('deduped', 0)})",
                        status="ok",
                    )
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
        elif job == "process_autostart":
            from app.platform import process_autostart

            await process_autostart.run_due()  # gated PROCESS_AUTOSTART; idempotent
        elif job == "standup":
            # Boss daily standup — hierarchical team coordination (gated AGENT_STANDUP).
            if os.environ.get("AGENT_STANDUP", "0").strip().lower() in ("1", "true", "yes"):
                from app.agents import coordinator

                await coordinator.coordinate_hierarchical(
                    "Aaj ka team plan: growth (naye leads + outreach) aur ops (system health + QA) — "
                    "priorities aur next-actions nikalo"
                )
        elif job == "revenue_snapshot":
            # B1: daily MRR/churn/LTV snapshot for the admin revenue trend chart.
            if os.environ.get("REVENUE_TRENDS", "0").strip().lower() in ("1", "true", "yes"):
                from app.platform import revenue_snapshots

                await revenue_snapshots.snapshot_today()
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
                    "pipeline": ((11, 0), (12, 0)),
                    "email_followup": ((16, 0), (17, 30)),
                    "kb_refresh": ((5, 0), (6, 30)),
                    "midday_prospect": ((14, 30), (15, 30)),
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
                        logger.info(f"[team-scheduler] boot-grace: {_jk} skipped this boot (window active)")
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

            if now.minute >= 5 and _last_ran["ops"] != hour_key:
                _last_ran["ops"] = hour_key
                await _run_job("ops")
            if (0, 5) <= hm < (0, 35) and _last_ran["revenue_snapshot"] != day_key:
                _last_ran["revenue_snapshot"] = day_key
                await _run_job("revenue_snapshot")  # B1 daily MRR snapshot (light, gated REVENUE_TRENDS)
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
            if (11, 0) <= hm < (12, 0) and _last_ran["pipeline"] != day_key:
                _last_ran["pipeline"] = day_key
                await _run_job("pipeline")
            if (16, 0) <= hm < (17, 30) and _last_ran["email_followup"] != day_key:
                _last_ran["email_followup"] = day_key
                await _run_job("email_followup")
            # 14:30–15:30 IST — 2nd free lead-supply pass (harvest). Gated MIDDAY_PROSPECT.
            if (14, 30) <= hm < (15, 30) and _last_ran["midday_prospect"] != day_key:
                _last_ran["midday_prospect"] = day_key
                await _run_job("midday_prospect")
            if (18, 30) <= hm < (19, 30) and _last_ran["evening_wrap"] != day_key:
                _last_ran["evening_wrap"] = day_key
                await _run_job("evening_wrap")
            if now.weekday() == 2 and (12, 30) <= hm < (13, 30) and _last_ran["weekly_marketing"] != day_key:
                _last_ran["weekly_marketing"] = day_key
                await _run_job("weekly_marketing")
            if now.weekday() == 5 and (4, 0) <= hm < (5, 30) and _last_ran["saturday_hygiene"] != day_key:
                _last_ran["saturday_hygiene"] = day_key
                await _run_job("saturday_hygiene")
            # Sunday 05:00–06:30 IST — weekly KB contextual re-ingest (gated).
            week_key = now.strftime("%Y-W%W")
            if now.weekday() == 6 and (5, 0) <= hm < (6, 30) and _last_ran["kb_refresh"] != week_key:
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
            # SP1 billing meter-failure watcher — hourly :55 (INERT unless METER_ALERTS=1).
            if now.minute >= 55 and _last_ran.get("meter_watch") != hour_key:
                _last_ran["meter_watch"] = hour_key
                await _run_job("meter_watch")
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
            # F.5 Vidya FinOps — daily morning margin score (engine INERT unless FINOPS_AGENT=1).
            if (9, 0) <= hm < (10, 0) and _last_ran["engineer_finops"] != day_key:
                _last_ran["engineer_finops"] = day_key
                await _run_job("engineer_finops")
            # F.5 Arnav Security — daily morning compliance posture (engine INERT unless SECURITY_AGENT=1).
            if (9, 30) <= hm < (10, 30) and _last_ran["engineer_security"] != day_key:
                _last_ran["engineer_security"] = day_key
                await _run_job("engineer_security")
            # G.3 daily activation-readiness digest — quiet ntfy unless BLOCKER present.
            if (8, 30) <= hm < (9, 30) and _last_ran["readiness_digest"] != day_key:
                _last_ran["readiness_digest"] = day_key
                await _run_job("readiness_digest")
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
