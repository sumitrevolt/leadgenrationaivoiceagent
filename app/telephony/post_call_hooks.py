"""Shared post-call lifecycle hooks — parity across telephony paths.

The LIVE Vobiz stream WS path does not register CallManager.active_calls, so
status-webhook → handle_call_completed often no-ops. These helpers let stream
cleanup mirror call_manager metering + qualified-lead downstream actions.

Never raises. All side-effects are best-effort and flag-gated where applicable.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _CALL_TRANSCRIPTS_DIR() -> str:
    """Call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return str(call_transcripts_dir())


def classify_stream_outcome(
    *,
    user_turns: int,
    turn_metrics: list[dict[str, Any]] | None = None,
) -> str:
    """Normalize WS-call result so dead/no-audio sessions are not marked completed."""
    metrics = [str((r or {}).get("outcome") or "").strip().lower() for r in (turn_metrics or [])]
    if any(m == "ok" for m in metrics):
        return "completed"
    if int(user_turns or 0) <= 0:
        return "no_answer"
    if any(m in {"think_timeout", "no_reply", "empty_stt"} for m in metrics):
        return "failed"
    return "completed"


async def meter_call_completion(
    call_id: str,
    *,
    client_id: str = "",
    client_name: str = "",
    duration_seconds: int,
    campaign_id: str | None = None,
) -> bool:
    """Idempotent minute metering + customer `call.completed` webhook fan-out."""
    cid_key = (call_id or "").strip()
    if not cid_key and duration_seconds <= 0:
        return False
    try:
        from app.billing import idempotency as _idem

        if cid_key and await _idem.seen_before(f"call_meter:{cid_key}"):
            logger.debug("[post_call] duplicate meter skip call_id=%s", cid_key)
            return False
    except Exception:
        pass
    try:
        from app.billing.usage import record_call_usage

        result = record_call_usage(
            client_id=client_id or "",
            duration_seconds=int(duration_seconds or 0),
            campaign_id=campaign_id,
            client_name=client_name or "",
        )
    except Exception as e:
        # ENTERPRISE FIX (2026-07-10): call-minute billing failure WAS debug-level —
        # invisible in production. Ab WARNING so ops knows immediately (call completed
        # but billing ledger never got the record = revenue leakage).
        logger.warning(
            "[post_call] meter_call_completion FAILED — billing record LOST for call_id=%s duration=%s (%s: %s)",
            cid_key,
            duration_seconds,
            type(e).__name__,
            e,
        )
        return False

    # Obsidian second-brain — append call summary (INERT if OBSIDIAN_SYNC unset).
    try:
        from app.platform import obsidian_sync as _obs

        phone_slug = (call_id or "unknown")[:20]
        _obs.append_note(
            "Leads",
            phone_slug,
            f"call completed — {duration_seconds}s client={client_name or client_id or '?'} campaign={campaign_id or '?'}",
            tags=["call"],
        )
    except Exception:
        pass

    return result


async def apply_qualified_downstream(
    q: dict[str, Any],
    *,
    client_id: str = "",
    phone: str = "",
    client_name: str = "",
    call_id: str = "",
    niche: str = "",
    city: str = "",
    campaign_variant_id: str = "",
) -> None:
    """CRM sync, sales pipeline, cadence — mirrors call_manager qualify block."""
    if not q.get("qualified"):
        return
    # Native CRM sync (Zoho/HubSpot) — GATED CRM_SYNC=1
    try:
        from app.platform import crm_sync as _crm

        if _crm.auto_enabled():
            await _crm.push_lead(
                {
                    "business_name": client_name or "",
                    "phone": phone or "",
                    "source": "AI Voice Agent",
                    "score": q.get("interest_score") or 0,
                },
                client_id=client_id or "",
                note=(
                    f"Qualified by AI voice agent (call {call_id}).\n"
                    f"Score: {q.get('interest_score')}/100\n"
                    f"Summary: {q.get('summary', '')}\n"
                    f"Next action: {q.get('next_action', '')}"
                ),
            )
    except Exception:
        pass
    # Sales pipeline: qualified voice call → interested stage
    try:
        from app.marketing import sales_pipeline as _sp

        _sp.upsert_deal(
            {
                "phone": phone or "",
                "business_name": client_name or "",
                "source": "AI Voice Call",
                "score": q.get("interest_score") or 0,
                "summary": q.get("summary") or "",
            },
            stage="interested",
        )
    except Exception:
        pass
    # Cadence enroll — GATED CADENCE_ENGINE=1
    try:
        if os.environ.get("CADENCE_ENGINE", "").strip().lower() in ("1", "true", "yes"):
            from app.marketing import cadence as _cad

            _cad.enroll(
                {
                    "phone": phone or "",
                    "business_name": client_name or "",
                    "niche": niche or "",
                    "city": city or "",
                    "email": "",
                    "source": "AI Voice Call",
                }
            )
    except Exception:
        pass
    # Post-call WhatsApp to the interested lead (audit 2026-07-04 owner-ask:
    # "agar customer interested hai to uske WhatsApp pe message bhejo call ke
    # baad"). The lead just spoke with our AI and showed interest, so a follow-up
    # to their number with the trial link is consented/transactional, not bulk.
    # Best-effort, no-ops until the WA engine is armed. Gated POST_CALL_WHATSAPP
    # (default ON). Never raises.
    if (phone or "").strip() and os.environ.get("POST_CALL_WHATSAPP", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        try:
            from app.integrations.whatsapp import get_whatsapp_sender

            _biz = client_name or "aapke business"
            _msg = (
                f"Namaste! Abhi humari AI se aapki baat hui — dhanyavaad. 🙏\n\n"
                f"{_biz} ke liye LeadGen AI: roz ki marketing posts, Google par upar "
                "aana, aur leads — sab automatic.\n\n"
                "FREE 7-din trial (koi card nahi): https://leadsgenai.in/start\n"
                "Koi sawaal ho to isi number pe reply karein."
            )
            _sender = get_whatsapp_sender()
            if _sender is not None:
                await _sender.send_text_message(phone, _msg)
        except Exception:
            pass


def emit_call_report(
    q: dict[str, Any],
    *,
    client_id: str = "",
    phone: str = "",
    call_id: str = "",
    niche: str = "",
    city: str = "",
    report_ready_at: str = "",
) -> None:
    """Fire-and-forget `call.report.ready` customer webhook once a post-call AI
    qualification report is available.

    Unlike `lead.qualified` (a billing-meter event with a minimal payload), this
    carries the FULL report (score/summary/next_action) so a customer's CRM or
    automation can act without polling. Fires for EVERY call that produced a
    report (qualified or not) — the customer opted in by subscribing to this
    event; the subscription model does the filtering.

    INERT without CUSTOMER_WEBHOOKS + a matching subscription. Never raises.
    """
    cid = (client_id or "").strip()
    if not cid:
        return
    try:
        from app.platform import customer_webhooks as _cw

        payload = {
            "client_id": cid,
            "call_id": str(call_id or ""),
            "phone": phone or "",
            "niche": niche or "",
            "city": city or "",
            "qualified": bool(q.get("qualified")),
            "interest_score": q.get("interest_score"),
            "summary": q.get("summary") or "",
            "next_action": q.get("next_action") or "",
            "report_ready_at": report_ready_at or "",
        }
        _cw.fire_emit(cid, "call.report.ready", payload)
    except Exception as e:
        logger.debug("[post_call] emit_call_report skip: %s", e)


def persist_transcript(
    history: list[dict[str, Any]],
    *,
    call_id: str = "",
    niche: str = "",
    client_id: str = "",
    client_name: str = "",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_s: float = 0.0,
    user_turns: int = 0,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append call transcript JSONL — shared by vobiz_stream + phone_stream."""
    if not history:
        return
    try:
        ended = ended_at or datetime.now(timezone.utc)
        rec: dict[str, Any] = {
            "ts": ended.isoformat(timespec="seconds"),
            "started_at": (started_at or ended).isoformat(timespec="seconds"),
            "duration_s": round(float(duration_s), 1),
            "stream_sid": call_id,
            "call_sid": call_id,
            "niche": niche,
            "client_id": client_id,
            "client_name": client_name,
            "user_turns": user_turns,
            "messages": history,
        }
        if extra:
            rec.update(extra)
        out_dir = _CALL_TRANSCRIPTS_DIR()
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, ended.strftime("%Y-%m-%d") + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(
            "[post_call] persist_transcript FAILED for call_id=%s — transcript LOST (%s: %s)",
            str(call_id or "")[:40],
            type(e).__name__,
            e,
        )


async def auto_qualify_and_downstream(
    history: list[dict[str, Any]],
    *,
    call_id: str = "",
    client_id: str = "",
    client_name: str = "",
    phone: str = "",
    niche: str = "",
    city: str = "",
    ended_at: datetime | None = None,
    call_duration_s: float = 0.0,
) -> dict[str, Any] | None:
    """Post-call qualify + report webhook + billing + CRM/cadence (stream paths)."""
    try:
        if os.environ.get("AUTO_QUALIFY_CALLS", "0").strip().lower() not in ("1", "true", "yes"):
            return None
        if not history:
            return None
        txt = "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')}" for m in history if isinstance(m, dict)
        )
        if len(txt) < 10:
            return None
        from app.voice_agent.call_qualifier import qualify_transcript

        ended = ended_at or datetime.now(timezone.utc)
        q = await qualify_transcript(txt, {"name": client_name or "", "phone": phone or ""})
        rec = {
            "call_id": call_id,
            "lead_id": phone,
            "client_id": client_id or "",
            "niche": niche,
            "ts": ended.isoformat(timespec="seconds"),
            **q,
        }
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "call_qualifications.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # RL reward spine (Phase 0) — voice outcome → unified reward log.
        try:
            from app.agents.rl import reward as _rl_reward

            _rl_reward.record_reward(
                "voice",
                niche or "general",
                _rl_reward.voice_reward(q),
                ref=str(call_id or rec.get("ts", "")),
                context={"niche": niche, "city": city},
            )
        except Exception:
            pass
        emit_call_report(
            q,
            client_id=str(client_id or ""),
            phone=phone or "",
            call_id=str(call_id or ""),
            niche=niche or "",
            city=city or "",
            report_ready_at=rec["ts"],
        )
        if q.get("qualified") and client_id:
            try:
                from app.billing import lead_usage as _lead_usage

                _lead_usage.record_qualified_lead(client_id, ref=str(call_id))
            except Exception:
                pass
        # ADR-027 self-improve loop: qualifier ne bot/IVR CONFIRM kiya -> number+
        # prefix dial_blocklist me seekho + prospect dial_block tag (in-call
        # IVR-strike hook ka post-call parity — ADR-006 cross-path rule).
        try:
            if q.get("bot_suspected") and str(q.get("bot_reason") or "").startswith("ivr_phrase"):
                from app.telephony import call_feedback

                call_feedback.record_ivr_confirmed(
                    phone or "",
                    source="post_call_bot",
                    call_sid=str(call_id or ""),
                    detail=str(q.get("bot_reason") or "")[:80],
                )
        except Exception:
            pass
        await apply_qualified_downstream(
            q,
            client_id=str(client_id or ""),
            phone=phone or "",
            client_name=client_name or "",
            call_id=str(call_id or ""),
            niche=niche or "",
            city=city or "",
        )
        # AI post-call summary → WhatsApp (qualified calls only). Gated
        # POST_CALL_SUMMARY (default OFF) + WHATSAPP_AUTO_SEND. Best-effort.
        if q.get("qualified"):
            try:
                from app.voice_agent.call_summary_formatter import send_post_call_summary

                await send_post_call_summary(
                    q,
                    phone=phone or "",
                    client_name=client_name or "",
                    niche=niche or "",
                    call_duration_s=float(call_duration_s or 0.0),
                    call_id=str(call_id or ""),
                )
            except Exception as exc:
                logger.debug("[post_call] summary send skip: %s", exc)
        return q
    except Exception as e:
        logger.debug("[post_call] auto_qualify skip: %s", e)
        return None


def _map_call_outcome(stream_outcome: str, q: dict[str, Any] | None, user_turns: int):
    """Map (classify_stream_outcome string + qualification dict) → CallOutcome enum.
    Returns None when nothing definitive is known (column is nullable)."""
    try:
        from app.models.call_log import CallOutcome
    except Exception:
        return None
    so = (stream_outcome or "").strip().lower()
    if so == "test_session":
        # WS test/dev session (no lead phone) — koi real outcome mat gadho
        # (qualifier agent-monologue se "interested" tak hallucinate kar deta —
        # 2026-07-02 me hua); column nullable hai, analytics phone='unknown' +
        # null-outcome se filter kare. Yeh check appointment/qualified se PEHLE.
        return None
    if q and q.get("bot_suspected"):
        # IVR/answering-bot suspect (2026-07-05 lesson) — na interested na
        # not_interested gadho; NULL = "unknown/unverified", analytics filter kare.
        return None
    if q and q.get("appointment_requested"):
        return CallOutcome.APPOINTMENT
    if q and q.get("qualified"):
        return CallOutcome.INTERESTED
    if so == "no_answer" or int(user_turns or 0) <= 0:
        return CallOutcome.NO_ANSWER
    if so == "failed":
        return CallOutcome.FAILED
    if q is not None and not q.get("qualified"):
        return CallOutcome.NOT_INTERESTED
    return None


def crm_sync_enabled() -> bool:
    """CALL_LEAD_CRM_SYNC — write the call outcome back onto the lead row.

    Default OFF. Read at call time, never frozen at import.
    """
    return os.getenv("CALL_LEAD_CRM_SYNC", "0").strip().lower() in {"1", "true", "yes", "on"}


# CallOutcome enum name -> niche_database.update_after_call outcome code.
# Deliberately derived from the SAME classifier that fills call_logs.outcome
# (_map_call_outcome) so the analytics row and the lead row can never disagree.
_NICHE_OUTCOME_BY_CALL_OUTCOME = {
    "APPOINTMENT": "qualified",
    "INTERESTED": "qualified",
    "NOT_INTERESTED": "not_interested",
    "NO_ANSWER": "voicemail",
    "FAILED": "voicemail",
}


def niche_outcome_for(
    *,
    stream_outcome: str,
    q: dict[str, Any] | None,
    user_turns: int,
    phone: str = "",
) -> str:
    """Pick the lead bucket for a finished call.

    Ordering matters:

    1. **DND wins over everything.** Read from ``consent_ledger`` — the
       authoritative cross-channel suppression store written by the agent's own
       ``_handle_opt_out``. Never inferred from LLM output.
    2. Otherwise defer to ``_map_call_outcome``.
    3. ``None`` from that classifier means "unknown / bot-suspected", and maps
       to ``voicemail`` — a RETRYABLE bucket, never a terminal one. Marking an
       IVR tree ``not_interested`` would silently burn the lead (2026-07-05).
    """
    if phone:
        try:
            from app.telephony import consent_ledger

            if consent_ledger.is_suppressed(phone):
                return "dnd"
        except Exception:
            pass
    mapped = _map_call_outcome(stream_outcome, q, user_turns)
    name = getattr(mapped, "name", "") if mapped is not None else ""
    return _NICHE_OUTCOME_BY_CALL_OUTCOME.get(name, "voicemail")


async def sync_lead_after_call(
    *,
    lead_id: str,
    phone: str = "",
    outcome: str = "",
    q: dict[str, Any] | None = None,
    user_turns: int = 0,
) -> dict[str, Any]:
    """Apply the call result to the lead row (status / hot flag / next_call_at).

    Thin adapter over the already-built ``niche_database.update_after_call``,
    which owns every actual mutation:

        qualified      -> QUALIFIED + is_hot_lead + score+20   ("important")
        callback       -> CALLBACK + next_call_at
        not_interested -> NOT_INTERESTED
        dnd            -> DND + tag
        voicemail      -> CONTACTED + retry in 24h             ("old lead")

    GATED ``CALL_LEAD_CRM_SYNC`` (default OFF). Never raises.
    """
    lid = (lead_id or "").strip()
    if not lid:
        return {"ok": False, "skipped": "no_lead_id"}
    if not crm_sync_enabled():
        return {"ok": False, "skipped": "flag_off"}

    bucket = niche_outcome_for(stream_outcome=outcome, q=q, user_turns=user_turns, phone=phone)
    try:
        from app.platform.niche_database import update_after_call

        res = await update_after_call(
            lead_id=lid,
            outcome=bucket,
            notes=str((q or {}).get("summary") or ""),
            niche_data=q or None,
        )
        logger.info(
            "[post_call] lead %s -> bucket=%s status=%s",
            lid,
            bucket,
            (res or {}).get("status"),
        )
        return {"ok": bool((res or {}).get("ok")), "bucket": bucket, "result": res}
    except Exception as e:
        logger.debug("[post_call] sync_lead_after_call skip: %s", e)
        return {"ok": False, "error": str(e), "bucket": bucket}


def build_call_log(
    *,
    call_id: str,
    provider: str,
    phone: str,
    client_id: str = "",
    client_name: str = "",
    niche: str = "",
    duration_s: float = 0.0,
    user_turns: int = 0,
    outcome: str = "",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    q: dict[str, Any] | None = None,
    caller_id: str = "",
    direction: str = "outbound",
    lead_id: str = "",
) -> Any | None:
    """Construct an UNSAVED ``CallLog`` row from call metadata + optional
    qualification. Pure (no DB/session) so the score/outcome mapping is unit
    testable. Returns None when CALL_LOG_DB is off or the model is unavailable.

    ``lead_id`` (2026-08-06) is the CRM ``leads.id`` threaded down from the
    dialer. Set optimistically here; ``persist_call_log`` re-checks the row
    actually exists before committing the FK, same as ``client_id``.

    ``q`` is the ``call_qualifier.qualify_transcript`` dict (interest_score 1-5,
    qualified, appointment_requested, summary, ...) or None when qualification
    was skipped (AUTO_QUALIFY_CALLS off) — the row is still useful for
    outcome/duration analytics.
    """
    if os.environ.get("CALL_LOG_DB", "1").strip().lower() not in ("1", "true", "yes"):
        return None
    try:
        from app.models.call_log import CallDirection, CallLog
    except Exception:
        return None
    ended = ended_at or datetime.now(timezone.utc)
    started = started_at or ended
    score = 0
    summary = ""
    appt = False
    if q:
        try:
            # qualify_transcript returns a 1-5 interest_score; CallLog.lead_score is 0-100.
            score = max(0, min(100, int(q.get("interest_score") or 0) * 20))
        except Exception:
            score = 0
        summary = str(q.get("summary") or "")[:1000]
        appt = bool(q.get("appointment_requested"))
    try:
        qual_json = json.dumps(
            {
                **(q or {}),
                "raw_client_id": client_id or "",
                "raw_phone": phone or "",
                "raw_lead_id": lead_id or "",
            },
            ensure_ascii=False,
        )
    except Exception:
        qual_json = None
    # Cost metering (2026-07-05 gap: call_cost hamesha 0 tha — spend invisible).
    # Paise me, per-minute ceil billing — env VOBIZ_COST_PAISE_PER_MIN (default 45
    # = Vobiz ₹0.45/min ladder). Sirf real dials (phone + >0s) pe.
    cost_paise = 0
    try:
        if (phone or "").strip() and float(duration_s or 0) > 0:
            import math

            rate = int(os.environ.get("VOBIZ_COST_PAISE_PER_MIN", "45") or 45)
            cost_paise = int(math.ceil(float(duration_s) / 60.0)) * max(0, rate)
    except Exception:
        cost_paise = 0
    return CallLog(
        id=uuid.uuid4().hex,
        call_sid=(str(call_id or "").strip() or None),
        provider=(str(provider or "")[:20] or None),
        direction=(
            CallDirection.INBOUND
            if str(direction or "").strip().lower() == "inbound"
            else CallDirection.OUTBOUND
        ),
        to_number=(str(phone or "").strip()[:20] or "unknown"),  # column is NOT NULL
        from_number=(str(caller_id or "").strip()[:20] or None),
        lead_id=(str(lead_id or "").strip() or None),
        initiated_at=started,
        answered_at=(started if int(user_turns or 0) > 0 else None),
        ended_at=ended,
        duration_seconds=int(duration_s or 0),
        talk_duration=int(duration_s or 0),
        status="completed",
        outcome=_map_call_outcome(outcome, q, user_turns),
        lead_score=score,
        is_hot_lead=score >= 70,
        qualification_data=qual_json,
        summary=(summary or None),
        appointment_scheduled=appt,
        call_cost=cost_paise,
        detected_intent=("bot_suspected" if (q or {}).get("bot_suspected") else None),
    )


async def persist_call_log(
    *,
    call_id: str,
    provider: str,
    phone: str,
    client_id: str = "",
    client_name: str = "",
    niche: str = "",
    duration_s: float = 0.0,
    user_turns: int = 0,
    outcome: str = "",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    q: dict[str, Any] | None = None,
    caller_id: str = "",
    direction: str = "outbound",
    lead_id: str = "",
) -> None:
    """Write ONE structured ``call_logs`` row so the (already-built) DB-backed
    analytics dashboard (`/api/analytics/*`, /app/analytics) lights up with real
    data instead of falling back to the empty in-memory store.

    Independent of AUTO_QUALIFY_CALLS — fires for EVERY completed call (q optional).
    Off-loop sync INSERT (`asyncio.to_thread`, never blocks the event loop),
    idempotent on ``call_sid``, FK-safe (``client_id`` linked only when it exists
    in ``clients``). GATED CALL_LOG_DB (default ON). Never raises.
    """
    row = build_call_log(
        call_id=call_id,
        provider=provider,
        phone=phone,
        client_id=client_id,
        client_name=client_name,
        niche=niche,
        duration_s=duration_s,
        user_turns=user_turns,
        outcome=outcome,
        started_at=started_at,
        ended_at=ended_at,
        q=q,
        caller_id=caller_id,
        direction=direction,
        lead_id=lead_id,
    )
    if row is None:
        return

    def _insert_sync() -> str:
        """Insert the row; return the FK-verified lead id, or "" when there is
        nothing new to sync (duplicate call_sid, or unknown/absent lead)."""
        from app.models.base import get_db_session
        from app.models.call_log import CallLog

        with get_db_session() as db:
            # Idempotency: skip if a row for this call_sid already exists.
            # Returning "" here is what makes the CRM sync idempotent too — a
            # replayed status callback must not re-apply a status transition.
            if row.call_sid:
                exists = db.query(CallLog.id).filter(CallLog.call_sid == row.call_sid).first()
                if exists:
                    return ""
            # FK-safe: link client_id only when it really exists in `clients`,
            # else leave NULL (raw id is already in qualification_data).
            cid = (client_id or "").strip()
            if cid:
                try:
                    from app.models.client import Client

                    if db.get(Client, cid) is not None:
                        row.client_id = cid
                except Exception:
                    pass
            # Same FK-safety for lead_id: build_call_log set it optimistically,
            # but a stale/unknown id must NOT abort the whole analytics INSERT.
            # Raw value survives in qualification_data.raw_lead_id either way.
            lid = (lead_id or "").strip()
            if lid:
                try:
                    from app.models.lead import Lead

                    row.lead_id = lid if db.get(Lead, lid) is not None else None
                except Exception:
                    row.lead_id = None
            db.add(row)  # get_db_session commits on context exit
            return str(row.lead_id or "")

    try:
        synced_lead_id = await asyncio.to_thread(_insert_sync)
    except Exception as e:
        logger.debug("[post_call] persist_call_log skip: %s", e)
        return

    # CRM bucket sync — the lead row itself (status / next_call_at / hot flag).
    # Lives HERE and not in call_manager because CallManager.active_calls is an
    # in-process dict: campaign calls are placed by the Celery worker while the
    # status callback lands on the web container, so handle_call_completed()
    # always logs "No context found for call X" and its niche_database update
    # never runs. persist_call_log is the one hook the live stream path does
    # reach, and (since the lead_id rail landed) the one that knows which lead.
    if synced_lead_id:
        await sync_lead_after_call(
            lead_id=synced_lead_id,
            phone=phone or "",
            outcome=outcome,
            q=q,
            user_turns=user_turns,
        )


async def finalize_stream_session(
    history: list[dict[str, Any]],
    *,
    call_id: str = "",
    client_id: str = "",
    client_name: str = "",
    phone: str = "",
    niche: str = "",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    extra_transcript: dict[str, Any] | None = None,
    campaign_variant_id: str = "",
    turn_metrics: list[dict[str, Any]] | None = None,
    lead_id: str = "",
) -> None:
    """Meter + transcript + qualify — one call for WS stream cleanup paths.

    ``lead_id`` mirrors ``persist_call_log``: this helper currently has no
    callers in-tree, but it wraps the same writer, so leaving it without the
    parameter would silently reintroduce the ``lead_id=NULL`` bug the moment a
    cleanup path starts using it.
    """
    ended = ended_at or datetime.now(timezone.utc)
    started = started_at or ended
    dur = max(0.0, (ended - started).total_seconds())
    turns = len([m for m in history if m.get("role") == "user"])
    outcome = classify_stream_outcome(user_turns=turns, turn_metrics=turn_metrics)
    persist_transcript(
        history,
        call_id=call_id,
        niche=niche,
        client_id=client_id or "",
        client_name=client_name or "",
        started_at=started,
        ended_at=ended,
        duration_s=dur,
        user_turns=turns,
        extra=extra_transcript,
    )
    await meter_call_completion(
        str(call_id or ""),
        client_id=str(client_id or ""),
        client_name=client_name or "",
        duration_seconds=int(dur),
    )
    q = await auto_qualify_and_downstream(
        history,
        call_id=str(call_id or ""),
        client_id=str(client_id or ""),
        client_name=client_name or "",
        phone=phone or "",
        niche=niche or "",
        ended_at=ended,
        call_duration_s=dur,
    )
    # DB-backed call analytics row (mirrors JSONL into the structured call_logs
    # table the analytics dashboard reads). Covers phone_stream cleanup path.
    await persist_call_log(
        call_id=str(call_id or ""),
        provider="phone",
        phone=phone or "",
        client_id=str(client_id or ""),
        client_name=client_name or "",
        niche=niche or "",
        duration_s=dur,
        user_turns=turns,
        outcome=outcome,
        started_at=started,
        ended_at=ended,
        q=q,
        lead_id=lead_id,
    )
    if campaign_variant_id:
        try:
            from app.platform import voice_opening_variants as vov

            await vov.record_outcome(
                campaign_variant_id,
                answered=turns > 0,
                interested=bool(q and q.get("qualified")),
            )
        except Exception:
            pass
    try:
        from app.platform import interaction_log

        await interaction_log.record(
            channel="voice",
            direction="out",
            phone=phone or "",
            client_id=str(client_id or ""),
            body_summary=f"call {int(dur)}s · {turns} user turns",
            outcome=outcome,
            campaign_variant_id=campaign_variant_id,
            meta={"call_id": call_id, "niche": niche, "source": "stream_session"},
        )
    except Exception:
        pass
    try:
        from app.platform import objection_extractor

        await objection_extractor.extract_from_transcript(
            history,
            niche=niche or "general",
            call_id=str(call_id or ""),
        )
    except Exception:
        pass
    try:
        from app.telephony import voice_followup

        close_signal = bool((extra_transcript or {}).get("close_signal"))
        await voice_followup.run_post_call_workflows(
            call_id=str(call_id or ""),
            phone=phone or "",
            client_id=str(client_id or ""),
            client_name=client_name or "",
            niche=niche or "",
            q=q,
            close_signal=close_signal,
            not_interested=bool(q is not None and not q.get("qualified") and turns > 0),
        )
    except Exception:
        pass


__all__ = [
    "meter_call_completion",
    "apply_qualified_downstream",
    "emit_call_report",
    "persist_transcript",
    "auto_qualify_and_downstream",
    "classify_stream_outcome",
    "finalize_stream_session",
    "build_call_log",
    "persist_call_log",
    "crm_sync_enabled",
    "niche_outcome_for",
    "sync_lead_after_call",
]
