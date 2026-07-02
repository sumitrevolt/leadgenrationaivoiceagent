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
        logger.debug("[post_call] meter_call_completion skip: %s", e)
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
        out_dir = os.path.join("data", "call_transcripts")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, ended.strftime("%Y-%m-%d") + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("[post_call] persist_transcript skip: %s", e)


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
                "voice", niche or "general", _rl_reward.voice_reward(q),
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
        await apply_qualified_downstream(
            q,
            client_id=str(client_id or ""),
            phone=phone or "",
            client_name=client_name or "",
            call_id=str(call_id or ""),
            niche=niche or "",
            city=city or "",
        )
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
) -> Any | None:
    """Construct an UNSAVED ``CallLog`` row from call metadata + optional
    qualification. Pure (no DB/session) so the score/outcome mapping is unit
    testable. Returns None when CALL_LOG_DB is off or the model is unavailable.

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
            {**(q or {}), "raw_client_id": client_id or "", "raw_phone": phone or ""},
            ensure_ascii=False,
        )
    except Exception:
        qual_json = None
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
    )
    if row is None:
        return

    def _insert_sync() -> None:
        from app.models.base import get_db_session
        from app.models.call_log import CallLog

        with get_db_session() as db:
            # Idempotency: skip if a row for this call_sid already exists.
            if row.call_sid:
                exists = (
                    db.query(CallLog.id).filter(CallLog.call_sid == row.call_sid).first()
                )
                if exists:
                    return
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
            db.add(row)  # get_db_session commits on context exit

    try:
        await asyncio.to_thread(_insert_sync)
    except Exception as e:
        logger.debug("[post_call] persist_call_log skip: %s", e)


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
) -> None:
    """Meter + transcript + qualify — one call for WS stream cleanup paths."""
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
]
