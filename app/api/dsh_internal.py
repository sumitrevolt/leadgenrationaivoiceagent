"""Token-bound internal DSH MCP and OpenAI-compatible gateway operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.platform.safe_ai_payload import SafePayloadError, mask_customer_data, validate_no_secrets
from app.platform.workforce_runtime import free_ai_proxy, run_store, tokens
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/internal/dsh", tags=["DSH Internal"])

MCP_OPERATION_IDS = (
    "dsh_capability_submit",
    "dsh_capability_status",
    "dsh_capability_wait",
    "dsh_approval_proposal",
    "dsh_heartbeat",
)
FORBIDDEN_DECISION_TERMS = frozenset(
    {"billing", "payment", "upi", "call", "dial", "voice", "whatsapp", "cold_outbound"}
)


class WaitIn(BaseModel):
    timeout_s: float = Field(2.0, ge=0.1, le=5.0)


class ApprovalProposalIn(BaseModel):
    decision_type: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    title: str = Field("", max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(..., min_length=8, max_length=128)


class HeartbeatIn(BaseModel):
    phase: str = Field("running", max_length=40, pattern=r"^[a-z0-9_-]+$")


class ChatCompletionIn(BaseModel):
    model: str = Field("leadgen-free", max_length=80)
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    stream: bool = False
    max_tokens: int = Field(512, ge=1, le=2048)
    temperature: float = Field(0.2, ge=0.0, le=1.0)


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "").strip()
    if not auth.startswith("Bearer ") or len(auth) <= 39:
        raise HTTPException(status_code=401, detail="run_token_required")
    return auth[7:].strip()


def authenticate_request(
    request: Request,
    *,
    required_tool: str = "",
) -> tokens.RunTokenBinding:
    try:
        return tokens.authenticate(_bearer(request), required_tool=required_tool)
    except tokens.TokenStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="run_token_store_unavailable") from exc
    except PermissionError as exc:
        reason = str(exc)
        status = 403 if reason == "tool_not_allowed" else 401
        raise HTTPException(status_code=status, detail=reason) from exc


def _bound_run(binding: tokens.RunTokenBinding, *, private: bool = False) -> dict[str, Any]:
    try:
        run = run_store.get_run(binding.run_id, include_private=private)
    except run_store.RunStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="run_store_unavailable") from exc
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    if (
        str(run.get("agent_id") or "") != binding.agent_id
        or str(run.get("tenant_id") or "") != binding.tenant_id
    ):
        raise HTTPException(status_code=403, detail="run_binding_mismatch")
    return run


def _submission_for(binding: tokens.RunTokenBinding, submission_id: str) -> dict[str, Any]:
    try:
        row = run_store.get_submission(submission_id)
    except (ValueError, run_store.RunStoreUnavailable) as exc:
        raise HTTPException(status_code=503, detail="submission_store_unavailable") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="submission_not_found")
    if str(row.get("run_id") or "") != binding.run_id:
        raise HTTPException(status_code=403, detail="submission_binding_mismatch")
    return row


@router.post(
    "/capabilities/{capability}/submissions",
    operation_id="dsh_capability_submit",
)
async def capability_submit(capability: str, request: Request) -> dict[str, Any]:
    """Submit one server-bound capability; child-supplied identity/payload is ignored."""
    cap = str(capability or "").strip()
    binding = authenticate_request(request, required_tool=f"dsh_capability_submit:{cap}")
    run = _bound_run(binding, private=True)
    if cap != str(run.get("action") or ""):
        raise HTTPException(status_code=403, detail="capability_binding_mismatch")
    submission_id = run_store.submission_id_for(binding.run_id, cap)
    task_id = run_store.submission_task_id_for(binding.run_id, cap)
    try:
        row, created = run_store.create_submission(
            submission_id=submission_id,
            run_id=binding.run_id,
            capability=cap,
            task_id=task_id,
        )
        if created:
            from app.tasks.dsh_jobs import DOMAIN_QUEUE, execute_governed_capability

            queued = execute_governed_capability.apply_async(
                kwargs={
                    "run_id": binding.run_id,
                    "submission_id": submission_id,
                    "task_id": task_id,
                },
                queue=DOMAIN_QUEUE,
                task_id=task_id,
            )
            row = run_store.update_submission(
                submission_id,
                queue_task_id=str(queued.id or task_id),
            )
            run_store.append_event(
                binding.run_id,
                "domain_capability_queued",
                {"submission_id": submission_id, "capability": cap},
            )
        return {
            "ok": True,
            "created": created,
            "submission_id": submission_id,
            "status": row.get("status"),
            "reason": row.get("reason") or "",
        }
    except run_store.RunStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="submission_store_unavailable") from exc
    except Exception as exc:
        logger.warning("[dsh_internal] capability enqueue failed: %s", type(exc).__name__)
        try:
            run_store.update_submission(
                submission_id,
                status="enqueue_failed",
                reason=type(exc).__name__,
            )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="capability_enqueue_failed") from exc


@router.get(
    "/submissions/{submission_id}",
    operation_id="dsh_capability_status",
)
async def capability_status(submission_id: str, request: Request) -> dict[str, Any]:
    binding = authenticate_request(request, required_tool="dsh_capability_status")
    row = _submission_for(binding, submission_id)
    return {"ok": True, "submission": row}


@router.post(
    "/submissions/{submission_id}/wait",
    operation_id="dsh_capability_wait",
)
async def capability_wait(
    submission_id: str,
    body: WaitIn,
    request: Request,
) -> dict[str, Any]:
    binding = authenticate_request(request, required_tool="dsh_capability_wait")
    deadline = asyncio.get_running_loop().time() + body.timeout_s
    row = _submission_for(binding, submission_id)
    while (
        row.get("status") in {"queued", "running"} and asyncio.get_running_loop().time() < deadline
    ):
        await asyncio.sleep(0.1)
        row = _submission_for(binding, submission_id)
    return {"ok": True, "submission": row, "timed_out": row.get("status") in {"queued", "running"}}


@router.post(
    "/approval-proposals",
    operation_id="dsh_approval_proposal",
)
async def approval_proposal(body: ApprovalProposalIn, request: Request) -> dict[str, Any]:
    binding = authenticate_request(request, required_tool="dsh_approval_proposal")
    _bound_run(binding)
    decision_type = body.decision_type.lower()
    if any(term in decision_type for term in FORBIDDEN_DECISION_TERMS):
        raise HTTPException(status_code=403, detail="decision_type_never_delegated_to_dsh")
    try:
        validate_no_secrets(body.payload)
    except SafePayloadError as exc:
        raise HTTPException(status_code=422, detail="secret_material_refused") from exc
    if mask_customer_data(body.payload) != body.payload:
        raise HTTPException(status_code=422, detail="raw_customer_data_refused_use_opaque_refs")

    key = json.dumps(
        [binding.run_id, decision_type, body.idempotency_key],
        separators=(",", ":"),
    )
    digest = hashlib.sha256(key.encode()).hexdigest()
    submission_id = f"dapr_{digest[:20]}"
    row, created = run_store.create_submission(
        submission_id=submission_id,
        run_id=binding.run_id,
        capability="approval_proposal",
        task_id=f"dapr_task_{digest[20:36]}",
    )
    if not created:
        return {"ok": True, "created": False, "proposal": row}

    from app.platform import boss_decision_governance as governance

    result = governance.propose_decision(
        tenant_id=binding.tenant_id,
        agent_id=binding.agent_id,
        decision_type=decision_type,
        title=body.title,
        payload=body.payload,
        proposed_by=f"dsh:{binding.agent_id}",
    )
    if result.get("inert"):
        row = run_store.update_submission(
            submission_id,
            status="skipped",
            reason="boss_decision_governance_disabled",
        )
    elif result.get("ok"):
        row = run_store.update_submission(
            submission_id,
            status="proposed",
            approval_id=str(result.get("decision_id") or ""),
        )
    else:
        row = run_store.update_submission(
            submission_id,
            status="blocked",
            reason=str(result.get("error") or "proposal_refused")[:160],
        )
    run_store.append_event(
        binding.run_id,
        "approval_proposal_terminal",
        {"submission_id": submission_id, "status": row.get("status")},
    )
    return {"ok": bool(result.get("ok")), "created": True, "proposal": row}


@router.post("/heartbeat", operation_id="dsh_heartbeat")
async def dsh_heartbeat(body: HeartbeatIn, request: Request) -> dict[str, Any]:
    binding = authenticate_request(request, required_tool="dsh_heartbeat")
    _bound_run(binding)
    try:
        row = run_store.heartbeat(binding.run_id)
        run_store.append_event(binding.run_id, "dsh_heartbeat", {"phase": body.phase})
        return {"ok": True, "run_id": binding.run_id, "heartbeat_at": row.get("heartbeat_at")}
    except run_store.RunStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="run_store_unavailable") from exc


def _stream_response(value: dict[str, Any]):
    choice = (value.get("choices") or [{}])[0]
    message = dict(choice.get("message") or {})
    delta: dict[str, Any] = {"role": message.get("role") or "assistant"}
    if message.get("content") is not None:
        delta["content"] = message.get("content")
    if message.get("tool_calls") is not None:
        import copy

        tcs = copy.deepcopy(message.get("tool_calls"))
        for i, tc in enumerate(tcs):
            tc["index"] = i
        delta["tool_calls"] = tcs
    chunk = {
        "id": value.get("id") or "chatcmpl-dsh",
        "object": "chat.completion.chunk",
        "created": value.get("created") or 0,
        "model": free_ai_proxy.PUBLIC_MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
    }
    terminal = {
        **chunk,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": choice.get("finish_reason") or "stop",
            }
        ],
        "usage": value.get("usage"),
    }
    yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
    yield f"data: {json.dumps(terminal, separators=(',', ':'))}\n\n"
    yield "data: [DONE]\n\n"


def _record_llm_outcome(
    binding: tokens.RunTokenBinding,
    value: dict[str, Any],
    *,
    stream: bool,
) -> None:
    """Persist only protocol shape so failed tool handoffs are diagnosable."""
    try:
        choice = (value.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_names = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else {}
            name = str((function or {}).get("name") or "")
            if name:
                tool_names.append(name[:80])
        run_store.append_event(
            binding.run_id,
            "dsh_llm_outcome",
            {
                "finish_reason": str(choice.get("finish_reason") or "")[:40],
                "tool_call_count": len(tool_names),
                "tool_names": tool_names[:16],
                "content_present": bool(message.get("content")),
                "stream": bool(stream),
            },
        )
    except Exception as exc:
        logger.warning("[dsh_internal] LLM outcome audit failed: %s", type(exc).__name__)


@router.post("/v1/chat/completions", operation_id="dsh_llm_chat")
async def chat_completions(body: ChatCompletionIn, request: Request):
    binding = authenticate_request(request, required_tool="dsh_llm_chat")
    _bound_run(binding)
    if body.model != free_ai_proxy.PUBLIC_MODEL_ID:
        raise HTTPException(status_code=422, detail="model_not_allowed")
    try:
        result = await free_ai_proxy.complete(
            messages=body.messages,
            tools=body.tools,
            allowed_tools=binding.allowed_tools,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        )
    except free_ai_proxy.ProxyRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except free_ai_proxy.ProxyUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _record_llm_outcome(binding, result, stream=body.stream)
    if body.stream:
        return StreamingResponse(_stream_response(result), media_type="text/event-stream")
    return JSONResponse(result)


__all__ = [
    "MCP_OPERATION_IDS",
    "authenticate_request",
    "router",
]
