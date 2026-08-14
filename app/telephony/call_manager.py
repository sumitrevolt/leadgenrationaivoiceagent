"""
Call Manager
Unified call orchestration for Vobiz
"""

import asyncio
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from app.config import settings
from app.telephony.call_state import get_call_store
from app.utils.dnd_checker import DNDChecker
from app.utils.logger import setup_logger
from app.voice_agent.agent import CallContext, CallStatus, VoiceAgent

logger = setup_logger(__name__)


class TelephonyProvider(Enum):
    """Supported telephony providers"""

    VOBIZ = "vobiz"


@dataclass
class CallRequest:
    """Request to make a call"""

    lead_id: str
    phone_number: str
    campaign_id: str
    niche: str
    client_name: str
    client_service: str
    script_name: str
    lead_data: dict[str, Any]
    client_id: str = ""  # marketing client (prepaid minute metering/enforcement)
    call_type: str = "promotional"  # "transactional" for consented inbound callbacks
    priority: int = 5  # 1 = highest, 10 = lowest
    retry_count: int = 0
    scheduled_time: datetime | None = None


@dataclass
class CallResult:
    """Result of a completed call"""

    call_id: str
    lead_id: str
    phone_number: str
    status: str
    duration_seconds: int
    outcome: str  # interested, not_interested, callback, appointment, no_answer
    lead_score: int
    qualification_data: dict[str, Any]
    transcript: list[dict[str, str]]
    recording_url: str | None
    appointment_details: dict[str, Any] | None
    callback_time: str | None
    completed_at: datetime


class CallManager:
    """
    Unified Call Manager

    Handles:
    - Call queue management (Redis-backed for multi-worker scaling)
    - Concurrent call limiting
    - DND checking
    - Retry logic
    - Call result processing
    """

    def __init__(self, provider: str | None = None):
        provider = (provider or settings.default_telephony or "vobiz").strip().lower()

        # Defensive: an unknown/stale provider (e.g. legacy "exotel"/"twilio" still
        # sitting in .env) must NEVER crash the whole app — fall back to Vobiz (the
        # only supported provider) with a warning.
        if provider != "vobiz":
            logger.warning(f"Unknown telephony provider '{provider}' — falling back to vobiz.")
            provider = "vobiz"

        from app.telephony.vobiz_handler import VobizClient

        self.handler = VobizClient()

        self.provider = TelephonyProvider(provider)
        self.voice_agent = VoiceAgent()
        self.dnd_checker = DNDChecker()

        # Distributed call state — the priority queue + an active-call REGISTRY live
        # in Redis (when available) so multiple workers share them (stateless scaling).
        # Live VoiceAgent CallContext objects can't be serialized, so they stay
        # worker-local in self.active_calls.
        self.call_state = get_call_store()
        self.active_calls: dict[str, CallContext] = {}  # local live contexts
        self.completed_calls: list[CallResult] = []

        # Concurrency control
        self.max_concurrent_calls = settings.max_concurrent_calls
        self.semaphore = asyncio.Semaphore(self.max_concurrent_calls)
        # Strong refs to in-flight call tasks — CPython only weakly references a
        # running task, so a fire-and-forget create_task() can be GC'd mid-call.
        self._inflight: set[asyncio.Task] = set()

        # Stats
        self.calls_made = 0
        self.calls_connected = 0
        self.calls_failed = 0

        logger.info(f"📞 Call Manager initialized with {provider}")

    # ----------------------------------------------------------------- #
    # CallRequest <-> serializable payload (for the Redis-backed queue)
    # ----------------------------------------------------------------- #
    @staticmethod
    def _request_to_payload(request: CallRequest) -> dict:
        """Serialize a CallRequest to a JSON-safe dict (datetime -> isoformat)."""
        d = asdict(request)
        st = d.get("scheduled_time")
        d["scheduled_time"] = st.isoformat() if isinstance(st, datetime) else None
        return d

    @staticmethod
    def _payload_to_request(payload: dict) -> CallRequest:
        """Rebuild a CallRequest from a queue payload (isoformat -> datetime)."""
        p = dict(payload)
        st = p.get("scheduled_time")
        if isinstance(st, str):
            try:
                p["scheduled_time"] = datetime.fromisoformat(st)
            except Exception:
                p["scheduled_time"] = None
        return CallRequest(**p)

    @staticmethod
    def _status_webhook_url() -> str | None:
        """Public Vobiz status-callback URL."""
        base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("SITE_BASE") or "").rstrip("/")
        if not base:
            return None
        return f"{base}/api/webhooks/vobiz/status"

    @staticmethod
    def _answer_url(to: str = "") -> str | None:
        """Public answer_url for Vobiz outbound calls.

        Vobiz fetches this URL when the call connects and expects VobizXML back.
        The dedicated conversational path is the Vobiz stream WS
        (/api/telephony/vobiz/stream/{token}); this best-effort answer_url points
        at the status webhook host so place_call always has a destination. Calls
        are DLT/recharge-blocked right now, so this is structural (not call-tested).
        """
        base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("SITE_BASE") or "").rstrip("/")
        if not base:
            return None
        url = f"{base}/api/webhooks/vobiz/answer"
        # Sign the dialled number into the answer-url so the webhook can verify a
        # press-9 opt-out belongs to a call WE placed (else any anon POST could
        # suppress an arbitrary number). Best-effort: unsigned still returns a URL.
        _to = str(to or "").strip()
        if _to:
            try:
                from urllib.parse import urlencode

                from app.telephony.answer_token import sign

                sig, exp = sign(_to)
                url += "?" + urlencode({"to": _to, "exp": exp, "sig": sig})
            except Exception:
                pass
        return url

    async def queue_call(self, request: CallRequest) -> str:
        """
        Add a call to the queue

        Returns:
            Call ID for tracking
        """
        call_id = str(uuid.uuid4())

        # COMPLIANCE GATE — single chokepoint (DND + 10-19 IST window + DLT/140).
        # Automated outbound = promotional, so a number that is not provably
        # compliant is NEVER queued (TCCCPR; penalty up to ₹10L). Fixes the old
        # dead `dnd_checker.check()` call (that method never existed).
        try:
            from app.telephony.compliance import CallType, get_compliance_gate

            # Consented inbound callbacks are transactional (looser gate: window only);
            # everything else is promotional (DND + DLT/140 + window).
            ct = (
                CallType.TRANSACTIONAL
                if str(getattr(request, "call_type", "")).lower() == "transactional"
                else CallType.PROMOTIONAL
            )
            decision = await get_compliance_gate().check(request.phone_number, ct)
            if not decision.allowed:
                logger.warning(
                    f"Call to {request.phone_number} blocked by compliance: {decision.reasons}"
                )
                return f"compliance_blocked_{call_id}"
        except Exception as e:
            logger.error(
                f"Compliance gate error for {request.phone_number} ({e}) — blocking promo call."
            )
            return f"compliance_error_{call_id}"

        # Prepaid minute enforcement — block a promo call if the client has used up
        # their included calling minutes (Advanced tier). Fail-open: no client_id, or
        # a non-metered plan, or any error -> do NOT block here.
        try:
            if request.client_id:
                from app.billing.usage import has_minutes

                if not has_minutes(request.client_id):
                    logger.warning(
                        f"Call to {request.phone_number} blocked — client "
                        f"{request.client_id} out of prepaid minutes."
                    )
                    return f"out_of_minutes_{call_id}"
        except Exception as e:
            logger.debug(f"minute-enforcement skipped: {e}")

        # Voice-product (ADR-009) qualified-lead quota enforcement — voice plan ke
        # client ka quota khatam => naye campaign calls block (top-up pack message).
        # FAIL-OPEN: no client_id / non-voice plan / error -> block nahi.
        try:
            if request.client_id:
                from app.billing.lead_usage import has_lead_quota

                _plan = getattr(request, "plan_id", None) or getattr(request, "plan", None)
                if not _plan:
                    from app.marketing import clients_store

                    _plan = (clients_store.get_client(request.client_id) or {}).get("plan")
                if not has_lead_quota(request.client_id, _plan):
                    logger.warning(
                        f"Call to {request.phone_number} blocked — client "
                        f"{request.client_id} out of qualified-lead quota (voice plan)."
                    )
                    return f"out_of_lead_quota_{call_id}"
        except Exception as e:
            logger.debug(f"lead-quota enforcement skipped: {e}")

        # Lead-score gate (CALL_MIN_SCORE, default 0 = off). Scores low-quality
        # leads out before queueing a call. Fail-open: error -> never block.
        _min_score = 0
        try:
            _min_score = int(os.environ.get("CALL_MIN_SCORE", "0") or "0")
        except Exception:
            pass
        if _min_score > 0 and request.lead_data:
            try:
                from app.platform.lead_scoring import score_lead

                _score = score_lead(request.lead_data)
                if _score < _min_score:
                    logger.info(
                        f"Call to {request.phone_number} blocked — lead score "
                        f"{_score} < CALL_MIN_SCORE {_min_score}."
                    )
                    return f"below_min_score_{call_id}"
            except Exception as _e:
                logger.debug(f"lead-score gate skipped: {_e}")

        # Add to the (Redis-backed) priority queue (lower number = higher priority).
        await self.call_state.enqueue(request.priority, call_id, self._request_to_payload(request))

        logger.info(f"Call queued: {call_id} to {request.phone_number}")
        return call_id

    async def start_call_processor(self):
        """
        Start processing calls from queue
        Call this in a background task
        """
        logger.info("🚀 Call processor started")

        while True:
            try:
                # Pull next call from the (Redis-backed) queue — non-blocking poll.
                item = await self.call_state.dequeue()
                if item is None:
                    await asyncio.sleep(1)
                    continue
                priority, call_id, payload = item
                request = self._payload_to_request(payload)

                # Check if scheduled for later
                if request.scheduled_time and datetime.now() < request.scheduled_time:
                    # Re-queue for later
                    await self.call_state.enqueue(priority, call_id, payload)
                    await asyncio.sleep(60)  # Check again in 1 minute
                    continue

                # Process call with concurrency limit. Keep a strong ref so the
                # task isn't garbage-collected mid-call (CPython weak-refs tasks).
                _t = asyncio.create_task(self._process_call(call_id, request))
                self._inflight.add(_t)
                _t.add_done_callback(self._inflight.discard)

            except asyncio.CancelledError:
                logger.info("Call processor stopped")
                break
            except Exception as e:
                logger.error(f"Call processor error: {e}")
                await asyncio.sleep(5)

    async def _process_call(self, call_id: str, request: CallRequest):
        """Process a single call"""
        async with self.semaphore:
            try:
                logger.info(f"📞 Making call {call_id} to {request.phone_number}")
                self.calls_made += 1

                # Initialize voice agent for this call
                context = await self.voice_agent.start_call(
                    lead_id=request.lead_id,
                    phone_number=request.phone_number,
                    campaign_id=request.campaign_id,
                    niche=request.niche,
                    client_name=request.client_name,
                    client_service=request.client_service,
                    script_name=request.script_name,
                    lead_data=request.lead_data,
                )

                self.active_calls[call_id] = context  # local live context
                # Mirror a serializable snapshot into the shared registry (Redis).
                await self.call_state.register(
                    call_id,
                    {
                        "call_id": call_id,
                        "lead_id": request.lead_id,
                        "phone": request.phone_number,
                        "campaign_id": request.campaign_id,
                        "status": "dialing",
                        "started_at": datetime.now().isoformat(),
                    },
                )

                # Make the actual call — Vobiz: place_call(to, answer_url, ...).
                # VobizClient never raises; success = status_code in 200/201/202,
                # sid = body["id"]. The compliance gate already ran in queue_call(),
                # so skip the duplicate gate here (skip_compliance=True).
                answer_url = (
                    self._answer_url(to=request.phone_number) or self._status_webhook_url() or ""
                )
                # ENTERPRISE FIX (2026-07-10): pehle call_id Vobiz ko bheja hi nahi
                # jaata tha — status webhook me "CallbackData" field KHAALI aata tha,
                # handle_call_completed hamesha "No context found for call X" debug-log
                # karta tha, aur voice-minute billing, lead-qualification, aur CRM sync
                # sab SILENTLY skip ho rahe the. Ab CallbackData bhej rahe hain taaki
                # Vobiz status callback me wahi value echo ho aur active_calls se match
                # ho sake. call_type aur CallbackData dono Vobiz API ke extra kwargs
                # me forward hote hain (vobiz_handler.py:142 payload.update(extra)).
                result = await self.handler.place_call(
                    to=request.phone_number,
                    answer_url=answer_url,
                    call_type=str(getattr(request, "call_type", "") or "promotional"),
                    CallbackData=call_id,
                    skip_compliance=True,
                )
                if result.get("status_code") in (200, 201, 202):
                    call_sid = str((result.get("body") or {}).get("id") or call_id)
                else:
                    call_sid = None

                if call_sid:
                    context.status = CallStatus.RINGING
                    # Reverse-map: Vobiz CallSid → internal call_id so webhook can
                    # resolve even if CallbackData field is empty/truncated.
                    await self.call_state._sid_map_set(call_sid, call_id)
                    self.calls_connected += 1
                    logger.info(f"Call {call_id} connected: {call_sid}")
                else:
                    await self._handle_call_failure(call_id, request, "Failed to connect")

            except Exception as e:
                logger.error(f"Call {call_id} failed: {e}")
                await self._handle_call_failure(call_id, request, str(e))

    async def _handle_call_failure(self, call_id: str, request: CallRequest, error: str):
        """Handle failed call with retry logic"""
        self.calls_failed += 1

        if request.retry_count < settings.call_retry_attempts:
            # Schedule retry
            request.retry_count += 1
            request.priority += 2  # Lower priority on retry
            request.scheduled_time = datetime.now() + timedelta(
                minutes=settings.call_retry_delay_minutes * request.retry_count
            )

            await self.call_state.enqueue(
                request.priority,
                f"{call_id}_retry{request.retry_count}",
                self._request_to_payload(request),
            )

            logger.info(f"Call {call_id} scheduled for retry #{request.retry_count}")
        else:
            logger.warning(f"Call {call_id} failed after {request.retry_count} retries")

            # Record as failed
            self.completed_calls.append(
                CallResult(
                    call_id=call_id,
                    lead_id=request.lead_id,
                    phone_number=request.phone_number,
                    status="failed",
                    duration_seconds=0,
                    outcome="failed",
                    lead_score=0,
                    qualification_data={},
                    transcript=[],
                    recording_url=None,
                    appointment_details=None,
                    callback_time=None,
                    completed_at=datetime.now(),
                )
            )
            # Clear any registry snapshot for this call.
            await self.call_state.unregister(call_id)

    async def handle_call_completed(
        self, call_id: str, duration: int, recording_url: str | None = None
    ) -> CallResult:
        """
        Handle a completed call
        Called by webhook handler
        """
        context = self.active_calls.get(call_id)
        if not context:
            logger.warning(f"No context found for call {call_id}")
            # Still clear any shared-registry snapshot (may live on another worker).
            await self.call_state.unregister(call_id)
            return None

        # End call in voice agent
        summary = await self.voice_agent.end_call(call_id)

        # Determine outcome
        outcome = self._determine_outcome(summary)

        # Opt-out → suppression ledger (covers every voice path, agent handler ke
        # alawa bhi). Idempotent + best-effort — kabhi completion block nahi karta.
        if outcome == "opt_out":
            try:
                from app.telephony.consent_ledger import record_opt_out

                record_opt_out(
                    context.phone_number,
                    reason="call_outcome",
                    channel="voice",
                    call_id=str(call_id),
                )
            except Exception:
                pass

        result = CallResult(
            call_id=call_id,
            lead_id=context.lead_id,
            phone_number=context.phone_number,
            status="completed",
            duration_seconds=duration,
            outcome=outcome,
            lead_score=summary.get("lead_score", 0),
            qualification_data=summary.get("qualification_answers", {}),
            transcript=summary.get("conversation_transcript", []),
            recording_url=recording_url,
            appointment_details=summary.get("appointment_details"),
            callback_time=summary.get("callback_time"),
            completed_at=datetime.now(),
        )

        self.completed_calls.append(result)
        self.active_calls.pop(call_id, None)
        await self.call_state.unregister(call_id)

        # Meter this call's minutes against the client's prepaid balance (best-effort;
        # client_id resolved from the call context / client_name). Never blocks.
        try:
            from app.billing.usage import record_call_usage

            record_call_usage(
                client_id=getattr(context, "client_id", "") or "",
                duration_seconds=duration,
                campaign_id=getattr(context, "campaign_id", None),
                client_name=getattr(context, "client_name", "") or "",
            )
        except Exception:
            pass

        # Post-call AI qualification (Expedify-style "qualify leads 24/7") — GATED
        # AUTO_QUALIFY_CALLS=1 (default off = zero change). Best-effort: call
        # completion ko kabhi block/affect nahi karta. Result -> jsonl (dashboard/1-click).
        try:
            import os as _os

            if _os.environ.get("AUTO_QUALIFY_CALLS", "0").strip().lower() in ("1", "true", "yes"):
                _tx = result.transcript or []
                _txt = "\n".join(
                    f"{m.get('role', '?')}: {m.get('content', '')}"
                    for m in _tx
                    if isinstance(m, dict)
                )
                if len(_txt) >= 10:
                    import json as _json

                    from app.voice_agent.call_qualifier import qualify_transcript

                    _q = await qualify_transcript(
                        _txt,
                        {
                            "name": getattr(context, "client_name", "") or "",
                            "phone": context.phone_number,
                        },
                    )
                    _os.makedirs("data", exist_ok=True)
                    with open(
                        _os.path.join("data", "call_qualifications.jsonl"), "a", encoding="utf-8"
                    ) as _f:
                        _f.write(
                            _json.dumps(
                                {"call_id": call_id, "lead_id": context.lead_id, **_q},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    logger.info(
                        f"[call_qualifier] {call_id}: score={_q.get('interest_score')} "
                        f"qualified={_q.get('qualified')}"
                    )
                    # call.report.ready customer webhook — every report (qualified or
                    # not); customer opted in via subscription. Inert w/o CUSTOMER_WEBHOOKS.
                    try:
                        from app.telephony.post_call_hooks import emit_call_report

                        emit_call_report(
                            _q,
                            client_id=getattr(context, "client_id", "") or "",
                            phone=context.phone_number,
                            call_id=str(call_id),
                            niche=getattr(context, "niche", "") or "",
                            city=getattr(context, "city", "") or "",
                        )
                    except Exception:
                        pass
                    # Voice product (ADR-009) lead-quota meter: qualified lead =
                    # billable unit. Best-effort, FAIL-OPEN (lead_usage kabhi raise nahi).
                    if _q.get("qualified"):
                        try:
                            from app.billing import lead_usage as _lead_usage

                            _cid = getattr(context, "client_id", "") or ""
                            if _cid:
                                _lead_usage.record_qualified_lead(_cid, ref=str(call_id))
                        except Exception:
                            pass
                        # Native CRM sync (Zoho/HubSpot) — qualified lead client ke
                        # apne CRM me. GATED CRM_SYNC=1, best-effort, never blocks.
                        try:
                            from app.platform import crm_sync as _crm

                            if _crm.auto_enabled():
                                await _crm.push_lead(
                                    {
                                        "business_name": getattr(context, "client_name", "") or "",
                                        "phone": context.phone_number,
                                        "source": "AI Voice Agent",
                                        "score": _q.get("interest_score") or 0,
                                    },
                                    client_id=getattr(context, "client_id", "") or "",
                                    note=(
                                        f"Qualified by AI voice agent (call {call_id}).\n"
                                        f"Score: {_q.get('interest_score')}/100\n"
                                        f"Summary: {_q.get('summary', '')}\n"
                                        f"Next action: {_q.get('next_action', '')}"
                                    ),
                                )
                        except Exception:
                            pass
                        # Sales pipeline: qualified voice call = "interested" deal stage.
                        # Prospect ek baar call me qualified hua = warm deal. Best-effort.
                        try:
                            from app.marketing import sales_pipeline as _sp

                            _sp.upsert_deal(
                                {
                                    "phone": context.phone_number,
                                    "business_name": getattr(context, "client_name", "") or "",
                                    "source": "AI Voice Call",
                                    "score": _q.get("interest_score") or 0,
                                    "summary": _q.get("summary") or "",
                                },
                                stage="interested",
                            )
                        except Exception:
                            pass
                        # Cadence enroll: qualified voice lead = omnichannel follow-up
                        # sequence me daalo (email→sms→wa→linkedin). Gated CADENCE_ENGINE=1.
                        try:
                            import os as _os2

                            if _os2.environ.get("CADENCE_ENGINE", "").strip() in (
                                "1",
                                "true",
                                "yes",
                            ):
                                from app.marketing import cadence as _cad

                                _cad.enroll(
                                    {
                                        "phone": context.phone_number,
                                        "business_name": getattr(context, "client_name", "") or "",
                                        "niche": getattr(context, "niche", "") or "",
                                        "city": getattr(context, "city", "") or "",
                                        "email": "",
                                        "source": "AI Voice Call",
                                    }
                                )
                        except Exception:
                            pass
        except Exception as _qe:
            logger.debug(f"[call_qualifier] auto-qualify skip: {_qe}")

        logger.info(f"✅ Call {call_id} completed. Outcome: {outcome}, Score: {result.lead_score}")

        # ── CallLog DB persist ────────────────────────────────────────────────
        # Har completed call → call_logs table row (analytics _db_calls() isi se
        # padhta hai). Best-effort, kabhi result return block nahi karta.
        try:
            import uuid as _uuid

            from app.models.base import get_db_session
            from app.models.call_log import CallDirection as _CD
            from app.models.call_log import CallLog as _CL
            from app.models.call_log import CallOutcome as _CO

            _outcome_map = {
                "appointment": "APPOINTMENT",
                "callback": "CALLBACK",
                "interested": "INTERESTED",
                "not_interested": "NOT_INTERESTED",
                "opt_out": "DND",
                "no_answer": "NO_ANSWER",
                "failed": "FAILED",
                "busy": "BUSY",
                "wrong_number": "WRONG_NUMBER",
            }
            _co_val = _outcome_map.get(outcome, "FAILED")
            _co_enum = _CO[_co_val] if _co_val in _CO.__members__ else _CO.FAILED
            with get_db_session() as _db:
                _row = _CL(
                    id=str(_uuid.uuid4()),
                    call_sid=str(call_id),
                    provider=getattr(context, "provider", "vobiz"),
                    direction=_CD.OUTBOUND,
                    lead_id=getattr(context, "lead_id", None) or None,
                    campaign_id=getattr(context, "campaign_id", None) or None,
                    client_id=getattr(context, "client_id", None) or None,
                    from_number=getattr(context, "caller_id", None) or None,
                    to_number=context.phone_number,
                    duration_seconds=duration,
                    outcome=_co_enum,
                    lead_score=result.lead_score or 0,
                    ended_at=result.completed_at,
                )
                _db.add(_row)
                _db.commit()
        except Exception as _cl_e:
            logger.debug(f"[call_manager] CallLog DB persist skip: {_cl_e}")

        # ── analytics_store.record_call (in-memory, fast dashboard) ──────────
        try:
            from app.api.analytics import analytics_store as _ast

            _ast.record_call(
                {
                    "completed_at": result.completed_at,
                    "duration_seconds": duration,
                    "status": "completed" if duration > 0 else "failed",
                    "outcome": outcome,
                    "lead_score": result.lead_score or 0,
                    "campaign_id": getattr(context, "campaign_id", None) or "unknown",
                    "agent_id": getattr(context, "agent_id", None) or "unassigned",
                }
            )
        except Exception as _ast_e:
            logger.debug(f"[call_manager] analytics_store.record_call skip: {_ast_e}")

        # ── outbound webhook: call_completed event ────────────────────────────
        try:
            import asyncio as _a

            from app.platform import outbound_webhooks as _ow_cm

            # NOTE: the public API is outbound_webhooks.emit(event, payload, client_id)
            # — there is no fire_event(); the old name silently AttributeError'd under
            # the except below, so this event never actually fired. Use emit().
            _a.create_task(
                _ow_cm.emit(
                    "call_completed",
                    {
                        "call_id": str(call_id),
                        "outcome": outcome,
                        "duration_seconds": duration,
                        "lead_score": result.lead_score or 0,
                        "phone": context.phone_number,
                        "campaign_id": getattr(context, "campaign_id", None) or "",
                    },
                    client_id=getattr(context, "client_id", "") or "",
                )
            )
        except Exception:
            pass

        # ── niche_database post-call update ──────────────────────────────────
        # Har call ke baad niche_database me lead status update karo — call attempts,
        # next_call_at, qualification_data, etc. Best-effort, kabhi block nahi karta.
        # outcome mapping: call_manager outcomes → niche_database outcome codes
        try:
            _lead_id = getattr(context, "lead_id", "") or ""
            if _lead_id:
                _OUTCOME_MAP = {
                    "appointment": "qualified",
                    "interested": "qualified",
                    "callback": "callback",
                    "not_interested": "not_interested",
                    "opt_out": "dnd",
                    "no_answer": "voicemail",
                    "failed": "voicemail",
                }
                _niche_outcome = _OUTCOME_MAP.get(outcome, "voicemail")
                _cb_hours = 24
                if result.callback_time:
                    try:
                        from datetime import datetime as _dt

                        _cb_dt = _dt.fromisoformat(result.callback_time)
                        _diff = (_cb_dt - _dt.now()).total_seconds() / 3600
                        _cb_hours = max(1, int(_diff))
                    except Exception:
                        pass
                import asyncio as _asyncio

                from app.platform.niche_database import update_after_call as _ndb_update

                _asyncio.create_task(
                    _ndb_update(
                        lead_id=_lead_id,
                        outcome=_niche_outcome,
                        notes=result.qualification_data.get("summary", ""),
                        niche_data=result.qualification_data or None,
                        callback_hours=_cb_hours,
                    )
                )
        except Exception as _ndb_e:
            logger.debug(f"[call_manager] niche_db post-call update skip: {_ndb_e}")

        return result

    def _determine_outcome(self, summary: dict[str, Any]) -> str:
        """Determine call outcome from summary"""
        if summary.get("appointment_scheduled"):
            return "appointment"
        elif summary.get("callback_requested"):
            return "callback"
        elif summary.get("detected_intent") == "interested":
            return "interested"
        elif summary.get("detected_intent") == "not_interested":
            return "not_interested"
        elif summary.get("detected_intent") == "opt_out":
            return "opt_out"
        else:
            return "no_answer"

    def get_stats(self) -> dict[str, Any]:
        """Get call statistics"""
        return {
            "calls_made": self.calls_made,
            "calls_connected": self.calls_connected,
            "calls_failed": self.calls_failed,
            "active_calls": len(self.active_calls),
            "queued_calls": self.call_state.local_qsize(),  # local approx (use Redis for total)
            "completed_calls": len(self.completed_calls),
            "connection_rate": self.calls_connected / self.calls_made if self.calls_made > 0 else 0,
            "outcomes": self._get_outcome_stats(),
        }

    def _get_outcome_stats(self) -> dict[str, int]:
        """Get outcome breakdown"""
        outcomes = {}
        for call in self.completed_calls:
            outcomes[call.outcome] = outcomes.get(call.outcome, 0) + 1
        return outcomes

    async def get_hot_leads(self, min_score: int = 70) -> list[CallResult]:
        """Get high-scoring leads from completed calls"""
        return [call for call in self.completed_calls if call.lead_score >= min_score]

    async def get_callbacks(self) -> list[CallResult]:
        """Get all callback requests"""
        return [
            call
            for call in self.completed_calls
            if call.outcome == "callback" and call.callback_time
        ]

    async def get_appointments(self) -> list[CallResult]:
        """Get all booked appointments"""
        return [
            call
            for call in self.completed_calls
            if call.outcome == "appointment" and call.appointment_details
        ]
