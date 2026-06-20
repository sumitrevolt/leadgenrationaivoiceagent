"""Shared post-call lifecycle hooks — parity across telephony paths.

The LIVE Vobiz stream WS path does not register CallManager.active_calls, so
status-webhook → handle_call_completed often no-ops. These helpers let stream
cleanup mirror call_manager metering + qualified-lead downstream actions.

Never raises. All side-effects are best-effort and flag-gated where applicable.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


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

        return record_call_usage(
            client_id=client_id or "",
            duration_seconds=int(duration_seconds or 0),
            campaign_id=campaign_id,
            client_name=client_name or "",
        )
    except Exception as e:
        logger.debug("[post_call] meter_call_completion skip: %s", e)
        return False


async def apply_qualified_downstream(
    q: dict[str, Any],
    *,
    client_id: str = "",
    phone: str = "",
    client_name: str = "",
    call_id: str = "",
    niche: str = "",
    city: str = "",
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
) -> None:
    """Post-call qualify + report webhook + billing + CRM/cadence (stream paths)."""
    try:
        if os.environ.get("AUTO_QUALIFY_CALLS", "0").strip().lower() not in ("1", "true", "yes"):
            return
        if not history:
            return
        txt = "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')}" for m in history if isinstance(m, dict)
        )
        if len(txt) < 10:
            return
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
    except Exception as e:
        logger.debug("[post_call] auto_qualify skip: %s", e)


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
) -> None:
    """Meter + transcript + qualify — one call for WS stream cleanup paths."""
    ended = ended_at or datetime.now(timezone.utc)
    started = started_at or ended
    dur = max(0.0, (ended - started).total_seconds())
    turns = len([m for m in history if m.get("role") == "user"])
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
    await auto_qualify_and_downstream(
        history,
        call_id=str(call_id or ""),
        client_id=str(client_id or ""),
        client_name=client_name or "",
        phone=phone or "",
        niche=niche or "",
        ended_at=ended,
    )


__all__ = [
    "meter_call_completion",
    "apply_qualified_downstream",
    "emit_call_report",
    "persist_transcript",
    "auto_qualify_and_downstream",
    "finalize_stream_session",
]
