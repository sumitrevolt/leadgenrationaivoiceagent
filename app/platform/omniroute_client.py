"""OmniRoute dev-tooling gateway — optional additive AI-routing fallback.

Audit 2026-07-12 (see docs/OMNIROUTE_ENGINEERING_RUNBOOK.md for full context).

STATUS: INERT by default. `OMNIROUTE_ENABLED` unset/0 = this module is never called
by anything in the request path. free_ai.py's existing provider chain is completely
unmodified and unconditional — this file does NOT replace or wrap it.

Why INERT: the local OmniRoute instance (WSL, v3.8.46, http://127.0.0.1:20128) has
authenticated dashboard and data-plane access, but LeadGen intentionally does not
inherit that access unless an operator explicitly enables this optional adapter in a
local process. This module remains a ready-but-disabled integration point: it must
never become a mandatory dependency or a production customer-data route.

Once Sumit completes setup and an OMNIROUTE_API_KEY exists (Windows user env var,
never committed), this module is the additive hook LeadGen code MAY optionally call
— it must NOT become mandatory, and free_ai.py's existing fallback chain must keep
working even if OmniRoute is fully down (degraded mode, not a hard dependency).

Usage (only after a sanitized dev-only route is verified and explicitly enabled):
    from app.platform.omniroute_client import generate, omniroute_available

    if omniroute_available():
        result = await generate("leadgen.coding_primary", messages, "INTERNAL_SANITIZED")
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.platform.safe_ai_payload import SafePayloadError, mask_customer_data, validate_no_secrets
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OMNIROUTE_BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1")
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503}
_DEFAULT_MAX_OUTPUT_TOKENS = 1024


def _provider_label(requested_model: str, resolved_model: str | None = None) -> str:
    """Honest provider tag for logs/metrics.

    Gateway combo ids (e.g. ``leadgen-free-first``) have no ``provider/`` prefix —
    do NOT pretend the combo name is a provider. Prefer the gateway-resolved
    model when it carries ``provider/model``; else label bare/combo ids ``combo``.
    """
    for candidate in (resolved_model, requested_model):
        text = str(candidate or "").strip()
        if "/" in text:
            return text.split("/", 1)[0] or "unknown"
    if str(requested_model or "").strip():
        return "combo"
    return "unknown"


@dataclass(frozen=True)
class OmniRouteRoute:
    """One approved, sanitized local-development route."""

    primary_model: str
    fallback_model: str | None
    privacy_class: str


@dataclass(frozen=True)
class OmniRouteResult:
    """Sanitized result metadata. Raw request content is intentionally omitted."""

    text: str
    task_type: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    fallback_reason: str | None = None


# Only models proven by a real, sanitized Responses API call belong here. The
# catalogued Gemini 2.5 Flash entry was rejected upstream as retired on 2026-07-14.
#
# 2026-07-16 (fresh WSL Ubuntu-24.04 reinstall, gateway v3.8.48): purane
# provider-connected model IDs (groq/llama-3.3-70b-versatile, mistral/
# mistral-small-latest) fresh instance me EXIST nahi karte (providers reconnect
# nahi hue) — un pe request = 404. User-mandate: OmniRoute ke bundled FREE-token
# models use karne hain. `auto/coding:free` + `auto/best-free` dono REAL sanitized
# /v1/responses PONG calls se proven (HTTP 200, output_text + usage sahi shape).
# Ye auto-aliases hain — gateway khud free pool me se resolve karta hai, isliye
# kisi ek free provider ke retire hone pe route nahi tootta.
# 2026-07-16 (same-day update 2): user ne dashboard me ~25 provider accounts
# reconnect kiye aur custom combo `leadgen-free-first` banaya (strategy=priority,
# 4-deep gateway-side failover: opencode/deepseek-v4-flash-free FREE →
# groq/llama-3.3-70b-versatile → mistral/mistral-small-latest →
# gemini/gemini-flash-latest). Combo id REAL sanitized /v1/responses PONG se
# proven (HTTP 200, free model ne resolve kiya). Routes ab combo PRIMARY +
# auto/coding:free client-side FALLBACK — free-tokens mandate + deep failover.
_TASK_ROUTES: dict[str, OmniRouteRoute] = {
    "leadgen.coding_primary": OmniRouteRoute(
        primary_model="leadgen-free-first",
        fallback_model="auto/coding:free",
        privacy_class="INTERNAL_SANITIZED",
    ),
    "leadgen.coding_fast": OmniRouteRoute(
        primary_model="leadgen-free-first",
        fallback_model="auto/coding:free",
        privacy_class="INTERNAL_SANITIZED",
    ),
    "leadgen.repo_analysis": OmniRouteRoute(
        primary_model="leadgen-free-first",
        fallback_model="auto/best-free",
        privacy_class="INTERNAL_SANITIZED",
    ),
    "leadgen.test_generation": OmniRouteRoute(
        primary_model="leadgen-free-first",
        fallback_model="auto/coding:free",
        privacy_class="INTERNAL_SANITIZED",
    ),
    # ADR-108 (2026-07-16): staff-agent bulk work (content/analysis/digests) — user
    # explicitly approved agent-enable. Realtime/voice hot-path is NOT routed here
    # (free_ai.chat hook engages only for profile=bulk). Payload is sanitized by
    # generate() (mask_customer_data + validate_no_secrets) before any network call.
    "leadgen.agent_ops": OmniRouteRoute(
        primary_model="leadgen-free-first",
        fallback_model="auto/best-free",
        privacy_class="INTERNAL_SANITIZED",
    ),
    # ADR-108 voice extension (2026-07-17): Swara live turn — masked customer
    # speech only (mask_customer_data + validate_no_secrets before network).
    # Gated by OMNIROUTE_VOICE=1; streaming via omniroute_voice.py.
    # 2026-07-18 latency fix: leadgen-free-first's first model
    # (opencode/deepseek-v4-flash-free) burns the whole voice max_tokens budget on
    # reasoning_content and returns HTTP 200 with zero `content` deltas — combo
    # never fails over, Swara gets empty streams (canary: 5/6 empty, 4.5s first
    # token on the 1 success). Voice hot-path now uses the dedicated gateway combo
    # `leadgen-swara-live` (groq -> mistral -> gemini, no reasoning-only models);
    # direct groq is the client-side fallback. Coding/bulk routes stay free-first.
    # 2026-08-23 OWNER DIRECTIVE: Swara (test-call + live calls) flagship combo
    # `leadgen-swara-flagship` use kare — antigravity Gemini 3.1 Pro / Claude
    # Opus 4.6 head (bunny + sunny accounts), smoke-verified 200 same day.
    # Old swara-live combo DB me untouched fallback ke liye preserved hai.
    "leadgen.swara_live": OmniRouteRoute(
        primary_model="leadgen-swara-flagship",
        fallback_model="groq/openai/gpt-oss-120b",
        privacy_class="CUSTOMER_MASKED",
    ),
}


def omniroute_enabled() -> bool:
    """Master flag check — mirrors the AUTOMATION_FLAGS registry entry."""
    return os.getenv("OMNIROUTE_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def omniroute_available() -> bool:
    """True only if the flag is on AND an access token is present.

    Deliberately conservative: an enabled-but-keyless config must not be treated as
    available (would just 401 on every call and burn a retry budget for nothing).
    """
    if not omniroute_enabled():
        return False
    if not os.getenv("OMNIROUTE_API_KEY"):
        logger.warning(
            "[omniroute_client] OMNIROUTE_ENABLED=1 but OMNIROUTE_API_KEY is not set — "
            "treating as unavailable (fail-open, existing free_ai chain handles the call)."
        )
        return False
    return True


def agents_enabled() -> bool:
    """ADR-108 double gate: master flag+key available AND agent opt-in flag ON."""
    if os.getenv("OMNIROUTE_AGENTS", "0").strip().lower() not in ("1", "true", "yes"):
        return False
    return omniroute_available()


def resolve_agent_task(agent_key: str | None = None, product: str | None = None) -> str | None:
    """Pick OmniRoute task for a staff agent, or None if policy forbids.

    Unknown/sensitive agents return None → caller stays on free_ai (fail-open).
    """
    try:
        from app.platform.agent_os_routing import get_agent_policy, omniroute_allowed_for_agent
    except Exception:  # pragma: no cover — defensive import
        return "leadgen.agent_ops" if agent_key is None else None

    if not agent_key:
        # Generic bulk hook (free_ai) — shared sanitized ops route only.
        return "leadgen.agent_ops"
    if not omniroute_allowed_for_agent(agent_key, product):
        logger.info(
            "[omniroute_decision] agent=%s action=skip reason=policy_forbids",
            agent_key,
        )
        return None
    return get_agent_policy(agent_key, product).omniroute_task


def _log_route_decision(
    *,
    task_type: str,
    privacy_class: str,
    provider: str | None,
    model: str | None,
    latency_ms: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
    fallback_reason: str | None,
    ok: bool,
    agent_key: str | None = None,
    skip_reason: str | None = None,
) -> None:
    """Structured, PII-free route decision line for admin/ops grepping."""
    logger.info(
        "[omniroute_decision] ok=%s task=%s privacy=%s agent=%s provider=%s model=%s "
        "latency_ms=%s in_tok=%s out_tok=%s fallback=%s skip=%s",
        ok,
        task_type,
        privacy_class,
        agent_key or "-",
        provider or "-",
        model or "-",
        latency_ms if latency_ms is not None else "-",
        input_tokens if input_tokens is not None else "-",
        output_tokens if output_tokens is not None else "-",
        fallback_reason or "-",
        skip_reason or "-",
    )


async def try_agent_chat(
    messages: list[dict[str, Any]],
    agent_key: str | None = None,
    product: str | None = None,
) -> str | None:
    """Optional staff-agent pre-hook (ADR-108/109) — NEVER raises, fail-open.

    Returns sanitized OmniRoute text ya None (None = caller apni existing free_ai
    chain use kare, unchanged). Voice/realtime callers ko yeh function call hi
    nahi karna chahiye — free_ai.chat hook sirf profile=bulk pe engage hota hai.

    When ``agent_key`` is set, ``agent_os_routing`` may forbid OmniRoute entirely
    (billing/voice/compliance) even if flags are ON.
    """
    if not agents_enabled():
        return None
    task = resolve_agent_task(agent_key, product)
    if not task:
        return None
    try:
        result = await generate(task, messages, "INTERNAL_SANITIZED", agent_key=agent_key)
    except SafePayloadError as exc:
        # Secret/unsafe payload = OmniRoute ko mat bhejo, par agent ko zinda rakho
        # (existing chain apni PII-masking ke saath handle karegi).
        logger.warning("[omniroute_client] agent payload rejected: %s", exc)
        _log_route_decision(
            task_type=task,
            privacy_class="INTERNAL_SANITIZED",
            provider=None,
            model=None,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            fallback_reason=None,
            ok=False,
            agent_key=agent_key,
            skip_reason="safe_payload_error",
        )
        return None
    except Exception as exc:  # pragma: no cover — defensive, agent kabhi na gire
        logger.warning("[omniroute_client] agent hook error: %s", type(exc).__name__)
        _log_route_decision(
            task_type=task,
            privacy_class="INTERNAL_SANITIZED",
            provider=None,
            model=None,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            fallback_reason=None,
            ok=False,
            agent_key=agent_key,
            skip_reason=type(exc).__name__.lower(),
        )
        return None
    if result is None:
        _log_route_decision(
            task_type=task,
            privacy_class="INTERNAL_SANITIZED",
            provider=None,
            model=None,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            fallback_reason=None,
            ok=False,
            agent_key=agent_key,
            skip_reason="gateway_or_provider_miss",
        )
        return None
    return result.text or None


def omniroute_client() -> Any | None:
    """Return an AsyncOpenAI-compatible client pointed at OmniRoute, or None.

    Never raises — callers should always have a fallback path if this returns None.
    """
    if not omniroute_available():
        return None
    try:
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            api_key=os.getenv("OMNIROUTE_API_KEY", ""),
            base_url=_OMNIROUTE_BASE_URL,
            timeout=30.0,
        )
    except Exception as e:  # pragma: no cover - defensive, matches free_ai.py pattern
        logger.warning("[omniroute_client] client construction failed: %s", e)
        return None


def get_task_route(task_type: str, privacy_class: str) -> OmniRouteRoute:
    """Return an explicitly approved route or reject external dispatch.

    Customer, payment, compliance, voice, and destructive work deliberately have no
    entry. Callers must use their existing deterministic/direct-provider flows.
    """
    route = _TASK_ROUTES.get(task_type)
    if route is None or privacy_class != route.privacy_class:
        raise SafePayloadError(
            f"OmniRoute external dispatch is not approved for task={task_type!r} "
            f"privacy_class={privacy_class!r}"
        )
    return route


def _responses_url() -> str:
    return f"{os.getenv('OMNIROUTE_BASE_URL', _OMNIROUTE_BASE_URL).rstrip('/')}/responses"


def _timeout_seconds(requested: int | None) -> int:
    configured = os.getenv("OMNIROUTE_TIMEOUT_SECONDS", "30")
    try:
        value = requested if requested is not None else int(configured)
    except (TypeError, ValueError):
        value = 30
    return max(1, min(int(value), 90))


def _response_matches_schema(text: str, response_schema: dict[str, Any] | None) -> bool:
    """Small deterministic schema gate for callers that require JSON output."""
    if response_schema is None:
        return True
    try:
        import json

        parsed = json.loads(text)
    except (TypeError, ValueError):
        return False
    if response_schema.get("type") == "object" and not isinstance(parsed, dict):
        return False
    required = response_schema.get("required", [])
    return isinstance(required, list) and all(key in parsed for key in required)


async def _post_responses(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, headers=headers, json=payload)


async def generate(
    task_type: str,
    messages: list[dict[str, Any]],
    privacy_class: str,
    response_schema: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
    agent_key: str | None = None,
    max_output_tokens: int | None = None,
) -> OmniRouteResult | None:
    """Run one explicit sanitized development task through OmniRoute.

    The function remains fail-open for gateway/provider faults: callers receive None
    and retain responsibility for their existing direct fallback. Privacy admission is
    fail-closed and raises ``SafePayloadError`` before any network attempt.

    Logs a PII-free ``[omniroute_decision]`` line on success/exhaustion (never raw
    prompts, completions, or secrets). ``metadata`` is accepted for API compat but
    deliberately discarded.
    """
    del metadata  # Deliberately never log caller metadata or raw prompt content.
    route = get_task_route(task_type, privacy_class)
    if not omniroute_available():
        _log_route_decision(
            task_type=task_type,
            privacy_class=privacy_class,
            provider=None,
            model=None,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            fallback_reason=None,
            ok=False,
            agent_key=agent_key,
            skip_reason="unavailable",
        )
        return None

    safe_messages = mask_customer_data(messages)
    validate_no_secrets(safe_messages)
    timeout = _timeout_seconds(timeout_seconds)
    try:
        tok_cap = (
            int(max_output_tokens) if max_output_tokens is not None else _DEFAULT_MAX_OUTPUT_TOKENS
        )
    except (TypeError, ValueError):
        tok_cap = _DEFAULT_MAX_OUTPUT_TOKENS
    tok_cap = max(64, min(tok_cap, 8192))
    headers = {"Authorization": f"Bearer {os.getenv('OMNIROUTE_API_KEY', '')}"}
    candidates = [route.primary_model]
    if route.fallback_model:
        candidates.append(route.fallback_model)
    fallback_reason: str | None = None

    for index, model in enumerate(candidates):
        started = time.monotonic()
        payload = {
            "model": model,
            "input": safe_messages,
            "max_output_tokens": tok_cap,
        }
        try:
            response = await _post_responses(_responses_url(), headers, payload, timeout)
            if response.status_code >= 400:
                if response.status_code in _RETRYABLE_STATUS_CODES and index + 1 < len(candidates):
                    fallback_reason = f"http_{response.status_code}"
                    await asyncio.sleep(0.1)
                    continue
                logger.warning(
                    "[omniroute_client] request failed task=%s model=%s status=%s",
                    task_type,
                    model,
                    response.status_code,
                )
                _log_route_decision(
                    task_type=task_type,
                    privacy_class=privacy_class,
                    provider=_provider_label(model),
                    model=model,
                    latency_ms=round((time.monotonic() - started) * 1000),
                    input_tokens=None,
                    output_tokens=None,
                    fallback_reason=fallback_reason,
                    ok=False,
                    agent_key=agent_key,
                    skip_reason=f"http_{response.status_code}",
                )
                return None

            body = response.json()
            text = str(body.get("output_text") or "").strip()
            if not text or not _response_matches_schema(text, response_schema):
                if index + 1 < len(candidates):
                    fallback_reason = "invalid_response_schema" if text else "empty_response"
                    continue
                _log_route_decision(
                    task_type=task_type,
                    privacy_class=privacy_class,
                    provider=_provider_label(model, str(body.get("model") or "") or None),
                    model=model,
                    latency_ms=round((time.monotonic() - started) * 1000),
                    input_tokens=None,
                    output_tokens=None,
                    fallback_reason=fallback_reason,
                    ok=False,
                    agent_key=agent_key,
                    skip_reason="empty_or_invalid_schema",
                )
                return None

            usage = body.get("usage") or {}
            resolved = str(body.get("model") or model)
            result = OmniRouteResult(
                text=text,
                task_type=task_type,
                provider=_provider_label(model, resolved),
                model=resolved,
                latency_ms=round((time.monotonic() - started) * 1000),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                fallback_reason=fallback_reason,
            )
            _log_route_decision(
                task_type=task_type,
                privacy_class=privacy_class,
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                fallback_reason=result.fallback_reason,
                ok=True,
                agent_key=agent_key,
            )
            return result
        except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
            if index + 1 < len(candidates):
                fallback_reason = type(exc).__name__.lower()
                await asyncio.sleep(0.1)
                continue
            logger.warning(
                "[omniroute_client] request unavailable task=%s model=%s error=%s",
                task_type,
                model,
                type(exc).__name__,
            )
            _log_route_decision(
                task_type=task_type,
                privacy_class=privacy_class,
                provider=_provider_label(model),
                model=model,
                latency_ms=None,
                input_tokens=None,
                output_tokens=None,
                fallback_reason=fallback_reason,
                ok=False,
                agent_key=agent_key,
                skip_reason=type(exc).__name__.lower(),
            )
            return None
    _log_route_decision(
        task_type=task_type,
        privacy_class=privacy_class,
        provider=None,
        model=None,
        latency_ms=None,
        input_tokens=None,
        output_tokens=None,
        fallback_reason=fallback_reason,
        ok=False,
        agent_key=agent_key,
        skip_reason="candidates_exhausted",
    )
    return None
