"""
Calling Tasks
Background tasks for call management
"""

import asyncio
from datetime import datetime, timedelta

from celery import shared_task

from app.billing.idempotency import seen_before_sync
from app.config import settings
from app.models.base import get_db_session
from app.models.call_log import CallLog, CallOutcome
from app.models.lead import Lead, LeadStatus
from app.telephony.call_manager import CallManager, CallRequest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _run_async(coro):
    """Run an async coroutine in a Celery (sync) task with proper teardown.

    asyncio.run-style cleanup (cancel pending + shutdown_asyncgens before close)
    so leftover transports don't log "Event loop is closed" on GC.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        finally:
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass


@shared_task(bind=True, max_retries=3, rate_limit="20/m")
def make_call_task(self, call_request_data: dict):
    """
    Background task to make a single call
    """
    try:
        logger.info(f"Processing call request: {call_request_data.get('lead_id')}")

        # idempotency: dedup by lead_id:campaign_id key prevents retry double-dialing
        # (max_retries=3 without this guard would triple-dial the same lead on Celery retry)
        lead_id = call_request_data.get("lead_id", "")
        campaign_id = call_request_data.get("campaign_id", "nocampaign")
        idem_key = f"make_call:{lead_id}:{campaign_id}"
        if seen_before_sync(idem_key, ttl_s=3600):
            logger.info(f"make_call_task duplicate skipped: {idem_key}")
            return {"status": "duplicate", "call_id": None, "outcome": "skipped"}

        call_manager = CallManager()

        # Create CallRequest from dict
        request = CallRequest(
            lead_id=call_request_data["lead_id"],
            phone_number=call_request_data["phone_number"],
            campaign_id=call_request_data.get("campaign_id"),
            niche=call_request_data.get("niche", "general"),
            client_name=call_request_data.get("client_name", ""),
            client_service=call_request_data.get("client_service", ""),
            script_name=call_request_data.get("script_name"),
            lead_data=call_request_data.get("lead_data", {}),
            priority=call_request_data.get("priority", 5),
        )

        # Enqueue the call onto the (compliance-gated, Redis-backed) priority queue.
        # NOTE: CallManager has no `initiate_call`; the public API is `queue_call()`
        # (enqueue) drained by `start_call_processor()` (long-running). The old name
        # raised AttributeError if legacy beat fired this task — fixed to queue_call.
        call_id = _run_async(call_manager.queue_call(request))

        # queue_call returns a sentinel id ("compliance_blocked_*", "out_of_*") when
        # the call was rejected by the compliance/billing gate rather than queued.
        blocked = bool(call_id) and (
            call_id.startswith("compliance_") or call_id.startswith("out_of_")
        )
        logger.info(f"Call enqueued: {call_id} (blocked={blocked})")

        return {
            "status": "blocked" if blocked else "queued",
            "call_id": call_id,
            "outcome": "blocked" if blocked else "queued",
        }

    except Exception as e:
        logger.error(f"Call task failed: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task
def process_queue(max_seconds: int = 50):
    """
    Drain the call queue for a bounded window (legacy beat path).

    CallManager exposes `start_call_processor()` (an infinite loop), NOT a
    one-shot `process_queue()` — calling the old name AttributeError'd. We run
    the processor under a timeout so a periodic Celery task drains pending calls
    without blocking the worker forever. Each queued call is compliance-gated in
    queue_call(), so this only dispatches already-vetted requests.

    # idempotency: compliance gate in queue_call() deduplicates by lead+window;
    # make_call_task (downstream) has its own dedup key, so re-runs are safe.
    """
    logger.info("Processing call queue")

    call_manager = CallManager()

    async def _drain():
        try:
            await asyncio.wait_for(
                call_manager.start_call_processor(), timeout=max(1, int(max_seconds))
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Expected: the processor loops forever; we stop it after the window.
            pass

    # Run async processing in sync context (proper teardown)
    _run_async(_drain())

    return {"status": "completed", "processed_at": datetime.now().isoformat()}


@shared_task
def process_callbacks():
    """
    Process scheduled callbacks.

    # idempotency: DB-level dedup via CallLog.initiated_at window — leads are only
    # re-queued if next_call_at is within the current hour window; lead.last_called_at
    # is updated on queue to prevent duplicate scheduling across concurrent task runs.
    """
    logger.info("Processing scheduled callbacks")

    callbacks_queued = 0
    now = datetime.utcnow()

    try:
        with get_db_session() as db:
            # Get leads with scheduled callbacks that are due
            leads_with_callbacks = (
                db.query(Lead)
                .filter(
                    Lead.status == LeadStatus.CALLBACK,
                    Lead.next_call_at <= now,
                    Lead.next_call_at >= now - timedelta(hours=1),  # Within the last hour window
                )
                .limit(50)
                .all()
            )

            for lead in leads_with_callbacks:
                # Queue the callback
                call_request_data = {
                    "lead_id": lead.id,
                    "phone_number": lead.phone,
                    "campaign_id": lead.campaign_id,
                    "niche": lead.niche,
                    "lead_data": {
                        "company_name": lead.company_name,
                        "contact_name": lead.contact_name,
                        "is_callback": True,
                        "previous_notes": lead.notes,
                    },
                    "priority": 3,  # Higher priority for callbacks
                }

                make_call_task.delay(call_request_data)
                callbacks_queued += 1

                # Update lead to prevent re-queuing. `or 0` guards a NULL
                # call_attempts (reachable — see the coalesce fix on the
                # campaign dial path above): a plain `+= 1` TypeErrors on
                # None, which aborts this whole loop's db.commit() below —
                # losing last_called_at for every lead already dispatched via
                # make_call_task.delay() this run (already-fired side effect,
                # never-committed dedup marker) and leaving them re-queuable
                # on the next tick.
                lead.last_called_at = now
                lead.call_attempts = (lead.call_attempts or 0) + 1

            db.commit()

    except Exception as e:
        logger.error(f"Error processing callbacks: {e}")

    logger.info(f"Queued {callbacks_queued} callbacks for calling")
    return {"status": "completed", "callbacks_queued": callbacks_queued}


@shared_task
def process_voice_followups(limit: int = 20):
    """Drain due VOICE_FOLLOWUP scheduled callbacks (transactional, consented)."""
    logger.info("Processing voice follow-up callbacks")
    try:
        from app.telephony import voice_followup

        return _run_async(voice_followup.run_due(limit=max(1, int(limit))))
    except Exception as e:
        logger.error(f"voice followup task failed: {e}")
        return {"ok": False, "error": str(e)}


@shared_task
def retry_failed_calls():
    """
    Retry failed calls that are eligible for retry.

    # idempotency: DB-level dedup via call.retry_count < max_retries gate and
    # retry_delay window filter; call.retry_count is incremented before commit
    # to prevent duplicate retries across concurrent task runs.
    """
    logger.info("Retrying failed calls")

    retries_queued = 0
    max_retries = settings.call_retry_attempts
    retry_delay = timedelta(minutes=settings.call_retry_delay_minutes)
    now = datetime.utcnow()

    try:
        with get_db_session() as db:
            # Get failed calls eligible for retry
            failed_calls = (
                db.query(CallLog)
                .filter(
                    CallLog.outcome.in_(
                        [CallOutcome.NO_ANSWER, CallOutcome.BUSY, CallOutcome.FAILED]
                    ),
                    CallLog.retry_count < max_retries,
                    CallLog.created_at <= now - retry_delay,  # Wait before retry
                )
                .limit(30)
                .all()
            )

            for call in failed_calls:
                # Get the lead for this call
                lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
                if not lead:
                    continue

                # Skip if lead is already processed
                if lead.status in [
                    LeadStatus.APPOINTMENT,
                    LeadStatus.CONVERTED,
                    LeadStatus.NOT_INTERESTED,
                ]:
                    continue

                # Queue retry call
                call_request_data = {
                    "lead_id": lead.id,
                    "phone_number": lead.phone,
                    "campaign_id": call.campaign_id,
                    "niche": lead.niche,
                    "lead_data": {
                        "company_name": lead.company_name,
                        "contact_name": lead.contact_name,
                        "is_retry": True,
                        "retry_count": call.retry_count + 1,
                        "original_call_id": call.id,
                    },
                    "priority": 7,  # Lower priority for retries
                }

                make_call_task.delay(call_request_data)
                retries_queued += 1

                # Update call retry count
                call.retry_count += 1

            db.commit()

    except Exception as e:
        logger.error(f"Error retrying failed calls: {e}")

    logger.info(f"Queued {retries_queued} calls for retry")
    return {"status": "completed", "retries_queued": retries_queued}


@shared_task
def cleanup_stale_calls():
    """
    Clean up calls that are stuck in 'initiated' or 'ringing' status.

    # idempotency: DB-level dedup — only calls with status 'initiated'/'ringing'
    # are touched; status is set to 'failed' so re-runs skip already-cleaned rows.
    """
    logger.info("Cleaning up stale calls")

    stale_threshold = datetime.utcnow() - timedelta(minutes=10)
    cleaned = 0

    try:
        with get_db_session() as db:
            stale_calls = (
                db.query(CallLog)
                .filter(
                    CallLog.status.in_(["initiated", "ringing"]),
                    CallLog.initiated_at < stale_threshold,
                )
                .all()
            )

            for call in stale_calls:
                call.status = "failed"
                call.outcome = CallOutcome.FAILED
                call.error_message = "Call timed out - no response"
                call.ended_at = datetime.utcnow()
                cleaned += 1

            db.commit()

    except Exception as e:
        logger.error(f"Error cleaning stale calls: {e}")

    logger.info(f"Cleaned up {cleaned} stale calls")
    return {"status": "completed", "cleaned": cleaned}


# --------------------------------------------------------------------------- #
# Durable admin campaign launch (2026-07-02) — replaces the web-process
# asyncio-subprocess path in app/api/admin_ops.py::launch_campaign (which ran
# scripts/fire_calls.py as a child process INSIDE the 2-worker web process,
# holding a worker for up to 320s per launch). Same compliance gates (shared
# via app/telephony/campaign_compliance.py — one source of truth with the CLI
# script) and same Vobiz call path (start_stream_call, unchanged) — this only
# changes HOW the campaign is triggered/run, never what it does or how it's
# gated. Status written to the SAME Redis key the admin UI already polls
# (/api/admin/campaign/status), so the frontend needs zero changes.
# --------------------------------------------------------------------------- #
_CAMPAIGN_STATUS_KEY = "admin:campaign:last_run"
_CAMPAIGN_LOCK_KEY = "admin:campaign:lock"


def _campaign_redis():
    try:
        import os as _os

        import redis as _redis_lib

        url = (_os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()
        client = _redis_lib.Redis.from_url(url, socket_connect_timeout=2, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _campaign_status_set(data: dict) -> None:
    try:
        r = _campaign_redis()
        if r:
            import json as _json

            r.setex(_CAMPAIGN_STATUS_KEY, 86400, _json.dumps(data))
    except Exception:
        pass


def acquire_campaign_lock(ttl_s: int = 400) -> bool:
    """True if this caller now holds the single-flight campaign lock (SET NX EX).
    Never raises — a Redis outage fails OPEN (returns True) so a broken lock
    can't permanently block campaign launches; the compliance gates below are
    the real safety net, not this dedup."""
    try:
        r = _campaign_redis()
        if not r:
            return True
        return bool(r.set(_CAMPAIGN_LOCK_KEY, "1", nx=True, ex=ttl_s))
    except Exception:
        return True


def release_campaign_lock() -> None:
    try:
        r = _campaign_redis()
        if r:
            r.delete(_CAMPAIGN_LOCK_KEY)
    except Exception:
        pass


def campaign_lock_held() -> bool:
    try:
        r = _campaign_redis()
        if not r:
            return False
        return bool(r.exists(_CAMPAIGN_LOCK_KEY))
    except Exception:
        return False


def _get_campaign_prospects(db, limit: int, niche: str) -> list:
    """Uncontacted-with-phone leads — same WHERE/ORDER as scripts/fire_calls.py
    get_prospects() and admin_ops.py _leads_ready(), via the ORM (provider-
    agnostic, unlike the CLI script's raw psycopg2)."""
    from sqlalchemy import func, or_

    q = db.query(Lead).filter(Lead.phone.isnot(None), Lead.phone != "")
    q = q.filter(or_(Lead.call_attempts.is_(None), Lead.call_attempts == 0))
    # "all"/"any"/"*" = no niche filter — platform (self-sale) campaigns can dial
    # the whole harvested pool, not just leads already tagged 'ai_marketing'
    # (the pitch itself is chosen per-call in _dial_vobiz_campaign, not here).
    if niche and niche.strip().lower() not in ("all", "any", "*"):
        q = q.filter(func.lower(Lead.niche) == niche.strip().lower())
    q = q.order_by(Lead.lead_score.desc(), Lead.created_at.desc())
    return q.limit(max(1, min(limit, 200))).all()


async def _dial_vobiz_campaign(
    db, prospects: list, dry_run: bool, call_type: str, client_id: str, platform: bool
) -> dict:
    import re

    from app.api.telephony_vobiz import start_stream_call
    from app.telephony import voice_launch as vl
    from app.telephony.vobiz_handler import VobizClient

    client = VobizClient()
    if not dry_run and not client.available():
        return {"ok": 0, "skip": 0, "fail": 0, "placed_ids": [], "error": "vobiz_not_configured"}

    # ── Controlled-launch safety spine (2026-07-17, app/telephony/voice_launch.py) ──
    # spine_on = VOICE_LAUNCH_CAMPAIGN=1 → full enforcement (per-lead fail-closed
    # eligibility + atomic daily cap + 30-call training pause + circuit breaker +
    # recording gate). Default OFF = INERT: existing behaviour UNCHANGED (only the
    # always-safe global admin kill switch, default off, is honoured). Composes ON
    # TOP of the existing compliance/dial_gate layers — never replaces them.
    spine_on = vl.campaign_enabled()
    kind = "campaign"
    session_id: str | None = None

    if not dry_run and vl.admin_kill_engaged():
        await vl.set_campaign_state(vl.CampaignState.PAUSED_BY_ADMIN)
        return {
            "ok": 0,
            "skip": len(prospects),
            "fail": 0,
            "placed_ids": [],
            "state": vl.CampaignState.PAUSED_BY_ADMIN.value,
            "error": "admin_kill_switch",
        }

    if spine_on and not dry_run:
        rec_ok, rec_reason = vl.recording_gate_ok()
        if not rec_ok:
            await vl.trip_circuit(rec_reason)
            await vl.set_campaign_state(vl.CampaignState.PAUSED_BY_CIRCUIT_BREAKER)
            return {
                "ok": 0,
                "skip": len(prospects),
                "fail": 0,
                "placed_ids": [],
                "state": vl.CampaignState.PAUSED_BY_CIRCUIT_BREAKER.value,
                "error": rec_reason,
            }
        if await vl.circuit_open():
            await vl.set_campaign_state(vl.CampaignState.PAUSED_BY_CIRCUIT_BREAKER)
            return {
                "ok": 0,
                "skip": len(prospects),
                "fail": 0,
                "placed_ids": [],
                "state": vl.CampaignState.PAUSED_BY_CIRCUIT_BREAKER.value,
                "error": "circuit_open",
            }
        # ── Session binding (exactly VOICE_CALLS_PER_SESSION per session) ──
        # Operator Fire (launch_campaign) = canonical create_voice_session = naya
        # counter. Worker/scheduler restart counter reset NAHI karta. Loop kabhi
        # EXISTING session ka count reset nahi karta; sirf koi session hi nahi hai
        # to canonical lifecycle se create karta hai.
        session_id = await vl.current_session_id()
        if not session_id:
            session_id = await vl.create_voice_session(owner="system", niche="", label="auto")
        if not session_id:
            return {
                "ok": 0,
                "skip": len(prospects),
                "fail": 0,
                "placed_ids": [],
                "state": vl.CampaignState.SESSION_STOPPED.value,
                "error": "no_session",
            }
        if await vl.session_is_stopped(session_id):
            await vl.set_campaign_state(vl.CampaignState.SESSION_STOPPED)
            return {
                "ok": 0,
                "skip": len(prospects),
                "fail": 0,
                "placed_ids": [],
                "state": vl.CampaignState.SESSION_STOPPED.value,
                "error": "session_stopped",
            }
        await vl.set_campaign_state(vl.CampaignState.RUNNING)

    ok = skip = fail = 0
    placed_ids: list[str] = []
    stop_state = None
    for p in prospects:
        p10 = re.sub(r"\D", "", (p.phone or "").strip())[-10:]
        niche = "ai_marketing" if platform else (p.niche or "general")
        cid = "" if platform else client_id
        if dry_run:
            continue
        if not p10 or len(p10) != 10:
            skip += 1
            continue

        # per-lead fail-closed eligibility + atomic daily-cap reservation +
        # session-cap reservation + session idempotency (dispatch boundary)
        slot = None
        sslot = None
        if spine_on:
            elig = await vl.is_lead_eligible_for_voice_call("+91" + p10, call_type)
            if not elig.eligible:
                skip += 1
                await vl.record_disposition(vl.VoiceDisposition.SKIPPED, kind)
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.SKIPPED)
                logger.info(f"[voice_launch] lead {p.id} ineligible: {elig.reason}")
                continue
            slot = await vl.reserve_call_slot(kind)
            if not slot.ok:
                # daily_limit_reached OR counter_unavailable (fail-CLOSED) → stop dialing
                stop_state = (
                    vl.CampaignState.DAILY_LIMIT_REACHED
                    if slot.reason == "daily_limit_reached"
                    else vl.CampaignState.PAUSED_BY_CIRCUIT_BREAKER
                )
                logger.warning(f"[voice_launch] stop dialing — {slot.reason}")
                break
            sslot = await vl.reserve_session_slot(session_id)
            if not sslot.ok:
                # session exhausted (attempt cap+1) / stopped / no_session / redis down
                # → roll back the daily slot we just claimed (didn't dispatch), stop.
                await vl.release_call_slot(kind)
                if sslot.reason == "session_limit_reached":
                    stop_state = vl.CampaignState.SESSION_LIMIT_REACHED
                elif sslot.reason == "session_stopped":
                    stop_state = vl.CampaignState.SESSION_STOPPED
                else:
                    stop_state = vl.CampaignState.PAUSED_BY_CIRCUIT_BREAKER
                logger.warning(f"[voice_launch] stop dialing — {sslot.reason}")
                break
            # Idempotency BEFORE provider dispatch: worker crash/retry ya is run me
            # duplicate lead → claim already held → at-most-once per session.
            if not await vl.session_idem_claim(session_id, f"lead:{p.id}"):
                await vl.release_call_slot(kind)
                await vl.release_session_slot(session_id)
                await vl.record_session_retry_blocked(session_id)
                skip += 1
                logger.info(f"[voice_launch] lead {p.id} already dispatched this session — skip")
                continue

        # lead_id threads the CRM id to the WS teardown that writes the CallLog
        # (2026-08-06). Without it every campaign row was lead_id=NULL, so calls
        # were unattributable AND niche_database.update_after_call() — the only
        # DND / NOT_INTERESTED / QUALIFIED / CALLBACK transition — never ran.
        result = await start_stream_call(
            to="+91" + p10,
            niche=niche,
            call_type=call_type,
            client_id=cid or None,
            lead_id=str(p.id or ""),
        )
        if result.get("placed"):
            ok += 1
            placed_ids.append(p.id)
            if spine_on:
                await vl.record_provider_result(True)
            # mark_called INLINE, right after each placed call — same
            # crash-safety as fire_calls.py's per-lead mark_called(). A
            # batched-after-the-loop update would lose every already-dialed
            # lead's call_attempts if the task is killed mid-run (e.g.
            # campaign/stop's revoke(terminate=True) SIGTERM), so a relaunch
            # would silently re-dial everyone already contacted this run.
            try:
                from sqlalchemy import func

                # coalesce: the prospect query admits call_attempts IS NULL
                # (fresh/never-called leads) — plain `Lead.call_attempts + 1`
                # compiles to SQL `NULL + 1 = NULL`, silently no-op'ing the
                # increment for exactly that common case and leaving the lead
                # eligible to be re-selected (and re-dialed) next run.
                db.query(Lead).filter(Lead.id == p.id).update(
                    {
                        Lead.call_attempts: func.coalesce(Lead.call_attempts, 0) + 1,
                        Lead.last_called_at: datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
                db.commit()
            except Exception as e:
                logger.warning(f"campaign mark_called failed for lead {p.id}: {e}")
                db.rollback()
        elif result.get("error") == "compliance_blocked":
            skip += 1
            if spine_on and slot is not None:
                # provider-side compliance block = NOT a provider-accepted attempt →
                # roll back the reserved slots so they don't consume the caps.
                await vl.release_call_slot(kind)
                await vl.record_disposition(vl.VoiceDisposition.SKIPPED, kind)
                await vl.release_session_slot(session_id)
                await vl.session_idem_release(session_id, f"lead:{p.id}")
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.SKIPPED)
        else:
            fail += 1
            if spine_on:
                # provider failure IS a provider-accepted attempt → keep slot (counts);
                # feed the circuit breaker (trips on a consecutive-failure spike).
                await vl.record_disposition(vl.VoiceDisposition.FAILED, kind)
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.FAILED)
                if await vl.record_provider_result(False, str(result.get("error") or "")):
                    stop_state = vl.CampaignState.PAUSED_BY_CIRCUIT_BREAKER
                    logger.warning("[voice_launch] circuit breaker tripped — pausing campaign")
                    break

        # 30-call training pause boundary — ATOMIC via the reservation counter
        # (slot.count is a single Redis INCR, so exactly one worker crosses 30/60/90).
        if (
            spine_on
            and slot is not None
            and result.get("placed")
            and vl.training_pause_due(slot.count)
        ):
            stop_state = vl.CampaignState.PAUSED_FOR_TRAINING
            logger.info(f"[voice_launch] training pause at call {slot.count}")
            try:
                from app.voice_agent.postcall_qa import (
                    propose_training_correction,
                    training_loop_enabled,
                )

                if training_loop_enabled():
                    propose_training_correction(
                        batch_count=int(slot.count),
                        qa_summary={
                            "reason": "training_boundary",
                            "placed_ids_tail": list(placed_ids)[-5:],
                        },
                    )
            except Exception as _te:
                logger.debug(f"[voice_launch] training proposal skip: {_te}")
            break

        await asyncio.sleep(4)

    if spine_on and not dry_run:
        if stop_state is not None:
            await vl.set_campaign_state(stop_state)
        elif not await vl.circuit_open():
            await vl.set_campaign_state(vl.CampaignState.RUNNING)

    out = {"ok": ok, "skip": skip, "fail": fail, "placed_ids": placed_ids}
    if stop_state is not None:
        out["state"] = stop_state.value
    return out


@shared_task(bind=True)
def run_campaign_task(
    self,
    limit: int = 10,
    dry_run: bool = False,
    niche: str = "",
    client_id: str = "",
    platform: bool = False,
    transactional: bool = False,
):
    """Durable outbound-campaign launch — see module docstring above."""
    from app.telephony.campaign_compliance import call_type_for, readiness_ok, trai_window_ok

    call_type = call_type_for(transactional)
    started_at = datetime.utcnow().timestamp()
    _campaign_status_set(
        {
            "status": "running",
            "limit": limit,
            "dry_run": dry_run,
            "niche": niche,
            "platform": platform,
            "started_at": started_at,
            "via": "celery",
            "task_id": self.request.id,
            "output": "",
        }
    )
    try:
        if not dry_run:
            ok, reason = trai_window_ok(transactional)
            if not ok:
                _campaign_status_set(
                    {
                        "status": "blocked",
                        "reason": reason,
                        "limit": limit,
                        "finished_at": datetime.utcnow().timestamp(),
                        "via": "celery",
                    }
                )
                return {"status": "blocked", "reason": reason}

            ready, score, actions = readiness_ok()
            if not ready:
                reason = f"Telephony readiness {score}/100 below threshold"
                _campaign_status_set(
                    {
                        "status": "blocked",
                        "reason": reason,
                        "actions": actions,
                        "limit": limit,
                        "finished_at": datetime.utcnow().timestamp(),
                        "via": "celery",
                    }
                )
                return {"status": "blocked", "reason": reason}

        with get_db_session() as db:
            # platform default stays 'ai_marketing' (tagged/warm leads) — but an
            # explicit niche ("coaching", or "all" for the whole pool) now overrides
            # it, so the self-sale pitch can reach every harvested prospect.
            niche_filter = (niche or "ai_marketing") if platform else niche
            prospects = _get_campaign_prospects(db, limit, niche_filter)

            if not prospects:
                _campaign_status_set(
                    {
                        "status": "done",
                        "limit": limit,
                        "dry_run": dry_run,
                        "finished_at": datetime.utcnow().timestamp(),
                        "output": "No uncontacted leads found.",
                        "via": "celery",
                    }
                )
                try:
                    from app.platform import team

                    team.log_event(
                        "swara",
                        "platform_campaign" if platform else "outbound_campaign",
                        f"📞 campaign — 0 uncontacted leads (niche={niche_filter or 'all'})",
                        status="warn",
                    )
                except Exception:
                    pass
                return {"status": "done", "ok": 0, "skip": 0, "fail": 0}

            result = _run_async(
                _dial_vobiz_campaign(db, prospects, dry_run, call_type, client_id, platform)
            )
            # mark_called already committed inline per-lead inside
            # _dial_vobiz_campaign (crash-safe) — nothing to batch here.

        output = (
            f"placed/queued={result.get('ok', 0)} blocked/skipped={result.get('skip', 0)} "
            f"failed={result.get('fail', 0)}"
        )
        if result.get("error"):
            output = result["error"]
        # Office/team visibility (2026-07-02): campaign runs were invisible on
        # /app/office & /app/team — attribute to Swara (telecaller). Never raises.
        try:
            from app.platform import team

            team.log_event(
                "swara",
                "platform_campaign" if platform else "outbound_campaign",
                ("🧪 dry-run: " if dry_run else "📞 ")
                + f"campaign — {output} (niche={niche_filter or 'all'})",
                status="warn" if result.get("error") else "ok",
            )
        except Exception:
            pass
        _campaign_status_set(
            {
                "status": "done",
                "limit": limit,
                "dry_run": dry_run,
                "niche": niche,
                "finished_at": datetime.utcnow().timestamp(),
                "output": output,
                "via": "celery",
            }
        )
        return {"status": "done", **{k: v for k, v in result.items() if k != "placed_ids"}}
    except Exception as e:
        logger.error(f"run_campaign_task failed: {e}")
        _campaign_status_set(
            {
                "status": "error",
                "error": str(e),
                "limit": limit,
                "finished_at": datetime.utcnow().timestamp(),
                "via": "celery",
            }
        )
        return {"status": "error", "error": str(e)}
    finally:
        release_campaign_lock()
