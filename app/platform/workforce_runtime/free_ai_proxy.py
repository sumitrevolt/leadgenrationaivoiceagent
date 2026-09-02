"""Sanitized, server-routed OpenAI completion seam for DSH only."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Iterable

from app.platform.safe_ai_payload import SafePayloadError, mask_customer_data, validate_no_secrets
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

PUBLIC_MODEL_ID = "leadgen-free"
MAX_MESSAGES = 32
MAX_INPUT_CHARS = 24_000
MAX_TOOLS = 16
KNOWN_DSH_MCP_TOOLS = {
    "dsh_capability_submit",
    "dsh_capability_status",
    "dsh_capability_wait",
    "dsh_approval_proposal",
    "dsh_heartbeat",
}


class ProxyRefused(ValueError):
    """Input violated the DSH minimization or tool contract."""


class ProxyUnavailable(RuntimeError):
    """No bounded free-provider completion succeeded."""


def _token_cap() -> int:
    try:
        return max(32, min(int(os.getenv("DSH_LLM_MAX_TOKENS", "512") or "512"), 2048))
    except ValueError:
        return 512


def sanitize_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES:
        raise ProxyRefused("messages_invalid")
    clean: list[dict[str, str]] = []
    total = 0
    for item in messages:
        if not isinstance(item, dict):
            raise ProxyRefused("message_invalid")
        role = str(item.get("role") or "")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ProxyRefused("message_role_invalid")
        content = item.get("content")
        if not isinstance(content, str):
            raise ProxyRefused("message_content_invalid")
        total += len(content)
        if total > MAX_INPUT_CHARS:
            raise ProxyRefused("message_budget_exceeded")
        try:
            validate_no_secrets(content)
        except SafePayloadError as exc:
            raise ProxyRefused("secret_material_refused") from exc
        masked = mask_customer_data(content)
        clean.append({"role": role, "content": str(masked or "")})
    validate_no_secrets(clean)
    return clean


def _tool_name_allowed(name: str, allowed_tools: Iterable[str]) -> bool:
    allowed = set(allowed_tools)
    return name in allowed or (
        name == "dsh_capability_submit"
        and any(item.startswith("dsh_capability_submit:") for item in allowed)
    )


def sanitize_tools(tools: Any, *, allowed_tools: Iterable[str]) -> list[dict[str, Any]]:
    if tools in (None, []):
        return []
    if not isinstance(tools, list) or len(tools) > MAX_TOOLS:
        raise ProxyRefused("tools_invalid")
    clean: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise ProxyRefused("tool_shape_invalid")
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ProxyRefused("tool_function_invalid")
        name = str(function.get("name") or "")
        # Capability submit is generic at MCP-schema level; the endpoint still
        # checks the exact dsh_capability_submit:<capability> token binding.
        if not _tool_name_allowed(name, allowed_tools):
            raise ProxyRefused("model_tool_not_allowed")
        rendered = json.dumps(tool, ensure_ascii=True, separators=(",", ":"))
        if len(rendered) > 16_000:
            raise ProxyRefused("tool_schema_too_large")
        try:
            validate_no_secrets(tool)
        except SafePayloadError as exc:
            raise ProxyRefused("secret_material_refused") from exc
        clean.append(tool)
    return clean


def validate_response_tools(value: Any, *, allowed_tools: Iterable[str]) -> None:
    """Refuse provider-invented tool calls even when request schemas were bounded."""
    if not isinstance(value, dict):
        raise ProxyRefused("provider_response_invalid")
    for choice in value.get("choices") or []:
        if not isinstance(choice, dict):
            raise ProxyRefused("provider_response_invalid")
        message = choice.get("message") or {}
        if not isinstance(message, dict):
            raise ProxyRefused("provider_response_invalid")
        for call in message.get("tool_calls") or []:
            function = call.get("function") if isinstance(call, dict) else None
            name = str((function or {}).get("name") or "")
            if not name or not _tool_name_allowed(name, allowed_tools):
                raise ProxyRefused("model_tool_not_allowed")


def _ensure_forced_submit_tool_call(value: Any) -> None:
    """Force-submit fallback for providers that ignore required tool_choice.

    The scoped submission endpoint ignores model-supplied arguments and re-checks
    the run token's dsh_capability_submit:<capability> binding, so synthesising
    the generic tool call here does not grant any new authority; it only repairs
    provider protocol non-compliance where finish_reason='stop' arrives with no
    tool_calls despite an explicit required dsh_capability_submit tool_choice.
    """
    if not isinstance(value, dict):
        raise ProxyRefused("provider_response_invalid")
    choices = value.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProxyRefused("provider_response_invalid")
    for idx, choice in enumerate(choices):
        if not isinstance(choice, dict):
            raise ProxyRefused("provider_response_invalid")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProxyRefused("provider_response_invalid")
        if message.get("tool_calls"):
            continue
        message["content"] = None
        message["tool_calls"] = [
            {
                "id": f"call_dsh_submit_{idx}",
                "type": "function",
                "function": {"name": "dsh_capability_submit", "arguments": "{}"},
            }
        ]
        choice["finish_reason"] = "tool_calls"


async def complete(
    *,
    messages: Any,
    tools: Any,
    allowed_tools: Iterable[str],
    max_tokens: int = 512,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Return one normalized OpenAI response; provider identity stays server-side."""
    safe_messages = sanitize_messages(messages)
    safe_tools = sanitize_tools(tools, allowed_tools=allowed_tools)
    token_cap = _token_cap()
    bounded_tokens = max(1, min(int(max_tokens or token_cap), token_cap))
    bounded_temperature = max(0.0, min(float(temperature or 0.0), 1.0))

    try:
        from app.llm import budget_guard

        if budget_guard.active():
            allowed, _detail = await budget_guard.allow("dsh_runtime")
            if not allowed:
                raise ProxyRefused("llm_budget_denied")
    except ProxyRefused:
        raise
    except Exception as exc:
        raise ProxyUnavailable("llm_budget_check_unavailable") from exc

    # Reuse the canonical free-provider chain without exposing any provider key,
    # URL, model choice, or client object to the DSH child.
    from app.voice_agent import free_ai

    chain = free_ai._build_llm_chain("bulk")  # type: ignore[attr-defined]
    for provider, model in chain:
        if free_ai._provider_down(provider):  # type: ignore[attr-defined]
            continue
        client = free_ai._client(provider)  # type: ignore[attr-defined]
        if client is None:
            continue
        started = time.monotonic()
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": safe_messages,
                "max_tokens": bounded_tokens,
                "temperature": bounded_temperature,
            }
            submit_tool = None
            if safe_tools:
                kwargs["tools"] = safe_tools
                submit_tool = next(
                    (
                        tool
                        for tool in safe_tools
                        if ((tool.get("function") or {}).get("name") == "dsh_capability_submit")
                    ),
                    None,
                )
                # Authoritative DSH runs are not a chat surface: when the scoped
                # capability-submit tool is present, require the model to emit
                # that tool call instead of ending the turn with prose. This
                # keeps shadow runs unaffected (no submit tool exposed) and
                # prevents the canary failure mode where LLM=200 but zero
                # governed submission reaches the runtime.
                if submit_tool is not None:
                    kwargs["tool_choice"] = {
                        "type": "function",
                        "function": {"name": "dsh_capability_submit"},
                    }
                else:
                    kwargs["tool_choice"] = "auto"
            response = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=60,
            )
            value = response.model_dump(mode="json")
            if submit_tool is not None:
                _ensure_forced_submit_tool_call(value)
            validate_response_tools(value, allowed_tools=allowed_tools)
            value["model"] = PUBLIC_MODEL_ID
            value.pop("system_fingerprint", None)
            for choice in value.get("choices", []):
                msg = choice.get("message", {})
                if "content" in msg and msg["content"] is not None:
                    msg["content"] = mask_customer_data(msg["content"])
            safe_value = value
            validate_no_secrets(safe_value)
            free_ai._reset_cooldown_streak(provider)  # type: ignore[attr-defined]
            try:
                from app.platform import llm_metrics

                llm_metrics.record(provider, True, (time.monotonic() - started) * 1000)
            except Exception:
                pass
            return safe_value
        except (ProxyRefused, SafePayloadError):
            raise
        except Exception as exc:
            try:
                free_ai._trip_cooldown(provider, type(exc).__name__)  # type: ignore[attr-defined]
            except Exception:
                pass
            logger.warning("[dsh_llm_proxy] provider attempt failed: %s", type(exc).__name__)
            continue
    raise ProxyUnavailable("free_ai_chain_exhausted")


__all__ = [
    "PUBLIC_MODEL_ID",
    "ProxyRefused",
    "ProxyUnavailable",
    "complete",
    "sanitize_messages",
    "sanitize_tools",
    "validate_response_tools",
]
