"""Dedicated DSH orchestration task and regular-queue governed capability task."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from app.platform.safe_ai_payload import SafePayloadError, mask_customer_data, validate_no_secrets
from app.platform.workforce_runtime import run_store, tokens
from app.worker import celery_app

try:
    from app.integrations import dsh as dsh_integration
except Exception:  # pragma: no cover
    dsh_integration = None  # type: ignore

logger = logging.getLogger(__name__)

DSH_QUEUE = "dsh"
DOMAIN_QUEUE = "celery"
RUNTIME_BINARY = "/usr/local/bin/dsh-jsonrpc-agent"
RUNTIME_CONFIG = "/usr/local/bin/cordis.yml"
RUNTIME_VERSION = "47f943859bef"  # pragma: allowlist secret -- pinned upstream SHA prefix
# DSH_CORDIS_CONFIG + HOME: pkg SEA uses argv[2] for user args and rejects /etc
# existsSync; HOME pins scratch under the read-only worker root.
CHILD_ENV_NAMES = frozenset(
    {"DSH_RUN_TOKEN", "DSH_MCP_URL", "DSH_LLM_BASE_URL", "DSH_CORDIS_CONFIG", "HOME"}
)


def _flag_on(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return bool(value) and value not in {"0", "false", "no", "off"}


def _digest(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _safe_prompt(run: dict[str, Any]) -> str:
    raw_payload = dict(run.get("input_payload") or {})
    try:
        validate_no_secrets(raw_payload)
    except SafePayloadError as exc:
        raise RuntimeError("secret_material_refused") from exc
    masked = mask_customer_data(raw_payload)
    safe_input = json.dumps(masked, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    mode = "SHADOW_PROPOSAL_ONLY" if run.get("shadow") else "GOVERNED_AUTHORITY"
    return (
        f"Mode={mode}. Run={run['run_id']}. Agent={run['agent_id']}. "
        f"Requested capability={run['action']}. "
        "Use only tools presented by the server. Never invent identity, approval, "
        "customer data, or side-effect success. In shadow mode, make no capability "
        "submission. A refusal is final. Bounded masked input follows: "
        f"{safe_input[:12000]}"
    )


def _allowed_tools(run: dict[str, Any]) -> list[str]:
    allowed = ["dsh_llm_chat", "dsh_heartbeat"]
    if not run.get("shadow"):
        # DSH's OpenAI adapter can only expose generic function-tool names to
        # the model. The exact capability authority remains enforced by
        # /capabilities/{capability}/submissions via the scoped
        # dsh_capability_submit:<capability> binding below. Without the generic
        # name the LLM proxy rejects the model's schema before the bounded
        # runtime can call the only side-effect tool, causing turn_complete
        # timeouts instead of a governed submission.
        allowed.extend(
            [
                "dsh_capability_status",
                "dsh_capability_wait",
                "dsh_approval_proposal",
                "dsh_capability_submit",
                f"dsh_capability_submit:{run['action']}",
            ]
        )
    return allowed


def _child_env(token: str, *, mcp_url: str, llm_base_url: str) -> dict[str, str]:
    env = {
        "DSH_RUN_TOKEN": str(token),
        "DSH_MCP_URL": str(mcp_url),
        "DSH_LLM_BASE_URL": str(llm_base_url),
        "DSH_CORDIS_CONFIG": RUNTIME_CONFIG,
        "HOME": "/tmp",  # nosec B108 -- container tmpfs, read-only root
    }
    if set(env) != CHILD_ENV_NAMES:
        raise RuntimeError("dsh_child_env_contract_changed")
    return env


async def _drain_stderr(stream: asyncio.StreamReader | None, counter: list[int]) -> None:
    if stream is None:
        return
    while await stream.readline():
        counter[0] += 1


def _assistant_text(message: dict[str, Any]) -> str:
    if message.get("method") != "session.event":
        return ""
    event = (message.get("params") or {}).get("event") or {}
    if event.get("type") != "assistant/message":
        return ""
    content = ((event.get("data") or {}).get("message") or {}).get("content") or []
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    text = "\n".join(part for part in parts if part).strip()
    if not text:
        return ""
    safe = mask_customer_data(text)
    try:
        validate_no_secrets(safe)
    except SafePayloadError:
        return "[MODEL OUTPUT REFUSED]"
    return str(safe)[:4000]


async def _terminate(proc: asyncio.subprocess.Process) -> float:
    if proc.returncode is not None:
        return 0.0
    started = time.monotonic()
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
    return time.monotonic() - started


async def _cancel_requested(run: dict[str, Any]) -> tuple[bool, str]:
    try:
        from app.platform import agent_runtime_cancellation as cancellation

        check = await asyncio.to_thread(
            cancellation.is_requested,
            str(run["agent_id"]),
            str(run["run_id"]),
        )
        if check.status == "store_unavailable":
            return True, "cancellation_store_unavailable"
        return bool(check.requested), "cancel_requested" if check.requested else ""
    except Exception:
        return True, "cancellation_store_unavailable"


async def _run_jsonrpc(run: dict[str, Any]) -> dict[str, Any]:
    if os.name != "posix":
        raise RuntimeError("dsh_linux_only")
    if not dsh_integration:
        raise RuntimeError("dsh_integration_unavailable")
    if not (dsh_integration.is_dsh_runtime_enabled() or dsh_integration.is_dsh_shadow_enabled()):
        raise RuntimeError("dsh_runtime_disabled")
    
    # Allowlist check (fail-closed).
    agent_id = str(run.get("agent_id", "")).strip().lower()
    tool_token = None  # Optional: "<name>@<version>" for per-tool allowlist refinement.
    if not dsh_integration.is_dsh_allowed(agent_id=agent_id, tool_token=tool_token):
        raise RuntimeError("dsh_allowlist_denied")

    binary = Path(os.getenv("DSH_RUNTIME_BINARY") or RUNTIME_BINARY)
    config = Path(os.getenv("DSH_RUNTIME_CONFIG") or RUNTIME_CONFIG)
    if not binary.is_file() or not config.is_file():
        raise RuntimeError("dsh_runtime_artifact_missing")

    now = time.time()
    deadline = min(float(run.get("deadline") or (now + 300)), now + 540)
    token, _binding = await asyncio.to_thread(
        tokens.issue,
        run_id=str(run["run_id"]),
        tenant_id=str(run.get("tenant_id") or ""),
        agent_id=str(run["agent_id"]),
        allowed_tools=_allowed_tools(run),
        deadline=deadline,
        ttl_s=max(30, int(deadline - now) + 5),
    )
    try:
        child_env = _child_env(
            token,
            mcp_url=os.getenv("DSH_MCP_URL") or "http://app:8080/internal/dsh/mcp",
            llm_base_url=os.getenv("DSH_LLM_BASE_URL") or "http://app:8080/internal/dsh/v1",
        )
    except Exception:
        await asyncio.to_thread(tokens.revoke, token)
        raise

    try:
        Path("/run/dsh").mkdir(parents=True, exist_ok=True)
    except Exception:
        await asyncio.to_thread(tokens.revoke, token)
        raise
    proc: asyncio.subprocess.Process | None = None
    stderr_count = [0]
    stderr_task: asyncio.Task[None] | None = None
    pending: list[dict[str, Any]] = []
    try:
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            str(config),
            cwd="/run/dsh",
            env=child_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.to_thread(
            run_store.update_run,
            str(run["run_id"]),
            pid=int(proc.pid or 0),
            runtime_version=RUNTIME_VERSION,
        )
        stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, stderr_count))

        async def send(payload: dict[str, Any]) -> None:
            if proc is None or proc.stdin is None:
                raise RuntimeError("dsh_stdin_unavailable")
            proc.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
            await proc.stdin.drain()

        async def receive_until(
            predicate,
            *,
            timeout_s: float,
            label: str,
        ) -> dict[str, Any]:
            local_deadline = min(deadline, time.time() + timeout_s)
            for index, value in enumerate(pending):
                if predicate(value):
                    return pending.pop(index)
            while time.time() < local_deadline:
                cancelled, reason = await _cancel_requested(run)
                if cancelled:
                    raise asyncio.CancelledError(reason)
                await asyncio.to_thread(run_store.heartbeat, str(run["run_id"]))
                if proc is None or proc.stdout is None:
                    raise RuntimeError("dsh_stdout_unavailable")
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=0.5)
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        raise RuntimeError(f"dsh_exited:{proc.returncode}")
                    continue
                if not raw:
                    raise RuntimeError(f"dsh_eof_before:{label}")
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict) and predicate(value):
                    return value
                if isinstance(value, dict):
                    pending.append(value)
            raise TimeoutError(f"dsh_timeout:{label}")

        await send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "cwd": "/run/dsh",
                    "provider": "leadgen-internal",
                    "model": "leadgen-free",
                    "maxTokens": 512,
                },
            }
        )
        initialized = await receive_until(
            lambda value: value.get("id") == 1, timeout_s=30, label="init"
        )
        if initialized.get("error"):
            raise RuntimeError("dsh_initialize_refused")

        await send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": str(run["run_id"]),
                    "contentBlocks": [{"type": "text", "text": _safe_prompt(run)}],
                },
            }
        )
        receipt = await receive_until(
            lambda value: value.get("id") == 2,
            timeout_s=20,
            label="prompt_receipt",
        )
        if receipt.get("error"):
            raise RuntimeError("dsh_prompt_refused")

        seen_running = False
        final_text = ""

        def completed(value: dict[str, Any]) -> bool:
            nonlocal seen_running, final_text
            text = _assistant_text(value)
            if text:
                final_text = text
            if value.get("method") == "session.status":
                status = (value.get("params") or {}).get("status")
                if status == "running":
                    seen_running = True
                if status == "idle" and seen_running:
                    return True
            return False

        await receive_until(
            completed, timeout_s=max(1, deadline - time.time()), label="turn_complete"
        )
        submission_id = run_store.submission_id_for(
            str(run["run_id"]),
            str(run["action"]),
        )
        submission = await asyncio.to_thread(run_store.get_submission, submission_id)
        if run.get("shadow"):
            if submission is not None:
                raise RuntimeError("dsh_shadow_side_effect_detected")
        elif submission is None:
            raise RuntimeError("dsh_authority_no_capability_submission")
        await send({"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
        shutdown = await receive_until(
            lambda value: value.get("id") == 3,
            timeout_s=10,
            label="shutdown",
        )
        if shutdown.get("error"):
            raise RuntimeError("dsh_shutdown_refused")
        shutdown_seconds = await _terminate(proc)
        if shutdown_seconds > 5.0:
            raise RuntimeError("dsh_shutdown_bound_exceeded")
        return {
            "summary": final_text,
            "runtime_version": RUNTIME_VERSION,
            "stderr_line_count": stderr_count[0],
            "shutdown_seconds": round(shutdown_seconds, 3),
            "shadow": bool(run.get("shadow")),
            "submission_id": "" if run.get("shadow") else submission_id,
            "submission_status": (
                "" if submission is None else str(submission.get("status") or "")
            ),
        }
    except asyncio.CancelledError as exc:
        if proc is not None:
            await _terminate(proc)
        reason = str(exc.args[0] if exc.args else "cancel_requested")
        raise RuntimeError(reason) from exc
    finally:
        await asyncio.to_thread(tokens.revoke, token)
        if proc is not None and proc.returncode is None:
            await _terminate(proc)
        if stderr_task is not None:
            try:
                await asyncio.wait_for(stderr_task, timeout=1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                stderr_task.cancel()


@celery_app.task(
    name="app.tasks.dsh_jobs.run_dsh_workforce",
    bind=True,
    acks_late=True,
    max_retries=0,
    soft_time_limit=540,
    time_limit=570,
)
def run_dsh_workforce(self, run_id: str) -> dict[str, Any]:
    """One dedicated-worker task owns exactly one hardened DSH child process."""
    run = run_store.get_run(run_id, include_private=True)
    if run is None:
        return {"ok": False, "run_id": run_id, "reason": "run_not_found"}
    run, claimed = run_store.claim_run(run_id)
    if not claimed:
        status = str(run.get("status") or "unknown")
        return {
            "ok": status == "succeeded",
            "run_id": run_id,
            "status": status,
            "reason": "duplicate_in_progress" if status == "running" else "duplicate_terminal",
        }
    run_store.append_event(run_id, "dsh_process_start", {"queue": DSH_QUEUE})
    try:
        output = asyncio.run(_run_jsonrpc(run))
        run_store.update_run(
            run_id,
            status="succeeded",
            reason="",
            result=output,
            heartbeat_at=run_store.now_iso(),
        )
        run_store.append_event(run_id, "dsh_process_succeeded", {"shadow": bool(run.get("shadow"))})
        return {"ok": True, "run_id": run_id, "status": "succeeded", "result": output}
    except Exception as exc:
        reason = str(exc)[:160] or type(exc).__name__
        status = "cancelled" if "cancel" in reason else "failed"
        run_store.update_run(
            run_id,
            status=status,
            reason=reason,
            result=None,
            heartbeat_at=run_store.now_iso(),
        )
        run_store.append_event(
            run_id,
            "dsh_process_failed",
            {"status": status, "error_class": type(exc).__name__, "reason": reason},
        )
        logger.warning("[dsh_jobs] run failed run_id=%s class=%s", run_id, type(exc).__name__)
        return {"ok": False, "run_id": run_id, "status": status, "reason": reason}


@celery_app.task(
    name="app.tasks.dsh_jobs.execute_governed_capability",
    bind=True,
    acks_late=True,
    max_retries=0,
    soft_time_limit=480,
    time_limit=510,
)
def execute_governed_capability(
    self,
    *,
    run_id: str,
    submission_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Regular worker executes through the production policy/idempotency spine."""
    run = run_store.get_run(run_id, include_private=True)
    submission = run_store.get_submission(submission_id)
    if run is None or submission is None:
        raise RuntimeError("governed_submission_not_found")
    submission, claimed = run_store.claim_submission(submission_id)
    if not claimed:
        status = str(submission.get("status") or "unknown")
        return {
            "ok": status == "succeeded",
            "submission_id": submission_id,
            "status": status,
            "reason": "duplicate_in_progress" if status == "running" else "duplicate_terminal",
            "result_digest": str(submission.get("result_digest") or ""),
        }
    run_store.update_submission(
        submission_id,
        queue_task_id=str(getattr(getattr(self, "request", None), "id", "") or ""),
    )
    try:
        from app.platform import agent_runtime
        from app.platform.agent_runtime_workforce import ensure_workforce_registered

        ensure_workforce_registered()
        task = agent_runtime.AgentTask(
            agent_id=str(run["agent_id"]),
            action=str(run["action"]),
            payload=dict(run.get("input_payload") or {}),
            tenant_id=str(run.get("tenant_id") or ""),
            approval_ref=str(run.get("approval_ref") or ""),
            idempotency_key=str(run.get("idempotency_key") or f"dsh_{run_id}"),
            trigger=f"dsh:{run.get('trigger') or 'runtime'}",
            timeout_s=run.get("timeout_s"),
            task_id=str(task_id),
        )
        result = asyncio.run(agent_runtime.run_task(task))
        digest = _digest(
            {
                "task_id": result.task_id,
                "status": result.status,
                "reason": result.reason,
                "attempts": result.attempts,
            }
        )
        run_store.update_submission(
            submission_id,
            status=result.status,
            reason=str(result.reason or "")[:160],
            result_digest=digest,
        )
        run_store.append_event(
            run_id,
            "domain_capability_terminal",
            {
                "submission_id": submission_id,
                "status": result.status,
                "reason": str(result.reason or "")[:160],
            },
        )
        return {
            "ok": result.status == "succeeded",
            "submission_id": submission_id,
            "status": result.status,
            "reason": result.reason,
            "result_digest": digest,
        }
    except Exception as exc:
        # Unknown external/customer outcome is never auto-retried. The durable
        # fail record and global Celery DLQ require explicit owner review.
        run_store.update_submission(
            submission_id,
            status="unknown_outcome",
            reason=f"{type(exc).__name__}:{str(exc)[:120]}",
        )
        run_store.append_event(
            run_id,
            "domain_capability_unknown",
            {"submission_id": submission_id, "error_class": type(exc).__name__},
        )
        raise


__all__ = [
    "CHILD_ENV_NAMES",
    "DOMAIN_QUEUE",
    "DSH_QUEUE",
    "execute_governed_capability",
    "run_dsh_workforce",
]
