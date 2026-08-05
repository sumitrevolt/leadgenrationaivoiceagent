"""Voice-scoped OmniRoute wrapper for Swara live turns (ADR-108 extension).

Gated by ``OMNIROUTE_VOICE=1`` (INERT default) + ``OMNIROUTE_ENABLED=1`` + key.
Streaming first-token path uses the gateway OpenAI-compatible client; fail-open
falls through to ``free_ai.chat_stream`` / ``free_ai.chat`` unchanged.

Never logs API keys, raw prompts, or unmasked PII.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

from app.platform.safe_ai_payload import SafePayloadError, mask_customer_data, validate_no_secrets
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

TASK_SWARA_LIVE = "leadgen.swara_live"
PRIVACY_CUSTOMER_MASKED = "CUSTOMER_MASKED"

_cancelled: dict[str, float] = {}


def _cancelled_max() -> int:
    try:
        return max(
            16, min(int(os.environ.get("OMNIROUTE_VOICE_CANCELLED_MAX", "256") or "256"), 4096)
        )
    except (TypeError, ValueError):
        return 256


def _prune_cancelled() -> None:
    cap = _cancelled_max()
    if len(_cancelled) <= cap:
        return
    drop_n = len(_cancelled) - cap
    for gid in sorted(_cancelled, key=_cancelled.get)[:drop_n]:
        _cancelled.pop(gid, None)


def voice_enabled() -> bool:
    """True when voice OmniRoute is explicitly enabled and gateway is available."""
    if (os.environ.get("OMNIROUTE_VOICE", "0") or "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    try:
        from app.platform.omniroute_client import omniroute_available

        return omniroute_available()
    except Exception:
        return False


def new_generation_id() -> str:
    return uuid.uuid4().hex[:12]


def cancel_generation(generation_id: str | None) -> None:
    """Mark a generation stale — in-flight streams reject further tokens."""
    if generation_id:
        _cancelled[generation_id] = time.monotonic()
        _prune_cancelled()


def is_cancelled(generation_id: str | None) -> bool:
    return bool(generation_id and generation_id in _cancelled)


def _clear_generation(generation_id: str | None) -> None:
    if generation_id:
        _cancelled.pop(generation_id, None)


def _num(env: str, default: float) -> float:
    try:
        return float(os.environ.get(env, str(default)) or default)
    except (TypeError, ValueError):
        return default


def first_token_timeout_s() -> float:
    return max(0.5, min(_num("OMNIROUTE_VOICE_FIRST_TOKEN_S", 3.0), 15.0))


def stream_idle_timeout_s() -> float:
    return max(0.3, min(_num("OMNIROUTE_VOICE_IDLE_S", 2.5), 10.0))


def stream_total_timeout_s() -> float:
    return max(2.0, min(_num("OMNIROUTE_VOICE_TOTAL_S", 10.0), 30.0))


# --- gateway circuit breaker -------------------------------------------------
# A dead gateway used to cost every single turn its full candidate ladder
# (primary + fallback x first-token timeout) BEFORE fail-open to free_ai, and the
# telecaller retries that per turn — measured 9-14s of dead air on a live call,
# which the customer answers with "hello? hello?" and barges in, so the bot never
# gets to speak. After N consecutive unusable attempts we skip the gateway for a
# cooldown window and fail-open to free_ai immediately. One probe per window
# (half-open) restores it automatically once the gateway is healthy again.
_breaker: dict[str, float] = {"fails": 0.0, "open_until": 0.0}


def _breaker_fail_threshold() -> int:
    try:
        return max(1, min(int(os.environ.get("OMNIROUTE_VOICE_BREAKER_FAILS", "2") or "2"), 20))
    except (TypeError, ValueError):
        return 2


def _breaker_cooldown_s() -> float:
    return max(5.0, min(_num("OMNIROUTE_VOICE_BREAKER_COOLDOWN_S", 120.0), 1800.0))


def breaker_open() -> bool:
    """True while the gateway is quarantined — callers must use free_ai."""
    return time.monotonic() < _breaker["open_until"]


def reset_breaker() -> None:
    _breaker["fails"] = 0.0
    _breaker["open_until"] = 0.0


def _breaker_trip(reason: str) -> None:
    _breaker["fails"] += 1
    if _breaker["fails"] >= _breaker_fail_threshold():
        cooldown = _breaker_cooldown_s()
        _breaker["open_until"] = time.monotonic() + cooldown
        logger.warning(
            "[omniroute_voice] gateway breaker OPEN for %.0fs after %d failures "
            "(last=%s) — voice turns fail-open to free_ai",
            cooldown,
            int(_breaker["fails"]),
            reason,
        )


@dataclass(frozen=True)
class VoiceRouteMeta:
    provider: str
    model: str
    fallback_reason: str | None = None
    latency_ms: int | None = None


def _build_messages(system: str, messages: list[dict[str, str]]) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    if system and system.strip():
        msgs.append({"role": "system", "content": system.strip()})
    for m in messages or []:
        role = m.get("role") or "user"
        if role not in ("system", "user", "assistant"):
            role = "user"
        content = str(m.get("content") or "").strip()
        if content:
            msgs.append({"role": role, "content": content})
    return msgs


def _safe_messages(system: str, messages: list[dict[str, str]]) -> list[dict[str, str]]:
    msgs = _build_messages(system, messages)
    safe = mask_customer_data(msgs)
    validate_no_secrets(safe)
    return safe


def _route_models() -> tuple[str, str | None]:
    from app.platform.omniroute_client import get_task_route

    route = get_task_route(TASK_SWARA_LIVE, PRIVACY_CUSTOMER_MASKED)
    return route.primary_model, route.fallback_model


def _log_voice_decision(
    *,
    ok: bool,
    provider: str | None,
    model: str | None,
    latency_ms: int | None,
    fallback_reason: str | None,
    skip_reason: str | None = None,
    generation_id: str | None = None,
) -> None:
    logger.info(
        "[omniroute_voice] ok=%s task=%s gen=%s provider=%s model=%s "
        "latency_ms=%s fallback=%s skip=%s",
        ok,
        TASK_SWARA_LIVE,
        generation_id or "-",
        provider or "-",
        model or "-",
        latency_ms if latency_ms is not None else "-",
        fallback_reason or "-",
        skip_reason or "-",
    )


async def chat_stream(
    system: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 90,
    temperature: float = 0.6,
    generation_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield token deltas from OmniRoute gateway. Empty = caller uses free_ai."""
    if not voice_enabled():
        return
    gen_id = generation_id or new_generation_id()
    try:
        if is_cancelled(gen_id):
            _log_voice_decision(
                ok=False,
                provider=None,
                model=None,
                latency_ms=None,
                fallback_reason="cancelled",
                skip_reason="barge_in",
                generation_id=gen_id,
            )
            return
        if breaker_open():
            _log_voice_decision(
                ok=False,
                provider=None,
                model=None,
                latency_ms=None,
                fallback_reason="breaker_open",
                skip_reason="breaker_open",
                generation_id=gen_id,
            )
            return
        try:
            safe = _safe_messages(system, messages)
        except SafePayloadError as exc:
            _log_voice_decision(
                ok=False,
                provider=None,
                model=None,
                latency_ms=None,
                fallback_reason=None,
                skip_reason="safe_payload_error",
                generation_id=gen_id,
            )
            logger.warning("[omniroute_voice] payload rejected: %s", exc)
            return
        if not safe:
            return

        from app.platform.omniroute_client import _provider_label, omniroute_client

        client = omniroute_client()
        if client is None:
            _log_voice_decision(
                ok=False,
                provider=None,
                model=None,
                latency_ms=None,
                fallback_reason=None,
                skip_reason="unavailable",
                generation_id=gen_id,
            )
            return

        try:
            primary, fallback = _route_models()
        except SafePayloadError as exc:
            _log_voice_decision(
                ok=False,
                provider=None,
                model=None,
                latency_ms=None,
                fallback_reason=None,
                skip_reason="route_rejected",
                generation_id=gen_id,
            )
            logger.warning("[omniroute_voice] route rejected: %s", exc)
            return

        candidates = [primary]
        if fallback:
            candidates.append(fallback)
        fallback_reason: str | None = None

        for idx, model in enumerate(candidates):
            if is_cancelled(gen_id):
                _log_voice_decision(
                    ok=False,
                    provider=_provider_label(model),
                    model=model,
                    latency_ms=None,
                    fallback_reason="cancelled",
                    skip_reason="barge_in",
                    generation_id=gen_id,
                )
                return
            started = time.monotonic()
            stream = None
            try:
                stream = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=safe,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stream=True,
                    ),
                    timeout=first_token_timeout_s(),
                )
                it = stream.__aiter__()
                got = False
                while True:
                    if is_cancelled(gen_id):
                        _log_voice_decision(
                            ok=False,
                            provider=_provider_label(model),
                            model=model,
                            latency_ms=round((time.monotonic() - started) * 1000),
                            fallback_reason="cancelled",
                            skip_reason="barge_in",
                            generation_id=gen_id,
                        )
                        return
                    if (time.monotonic() - started) > stream_total_timeout_s():
                        raise asyncio.TimeoutError("voice stream total budget")
                    per_wait = first_token_timeout_s() if not got else stream_idle_timeout_s()
                    try:
                        chunk = await asyncio.wait_for(it.__anext__(), timeout=per_wait)
                    except StopAsyncIteration:
                        break
                    delta = ""
                    try:
                        delta = chunk.choices[0].delta.content or ""
                    except Exception:
                        delta = ""
                    if delta:
                        got = True
                        yield delta
                if got:
                    reset_breaker()
                    _log_voice_decision(
                        ok=True,
                        provider=_provider_label(model),
                        model=model,
                        latency_ms=round((time.monotonic() - started) * 1000),
                        fallback_reason=fallback_reason,
                        generation_id=gen_id,
                    )
                    return
                if idx + 1 < len(candidates):
                    fallback_reason = "empty_stream"
                    continue
            except Exception as exc:
                if idx + 1 < len(candidates):
                    fallback_reason = type(exc).__name__.lower()
                    continue
                _breaker_trip(type(exc).__name__.lower())
                _log_voice_decision(
                    ok=False,
                    provider=_provider_label(model),
                    model=model,
                    latency_ms=round((time.monotonic() - started) * 1000),
                    fallback_reason=fallback_reason,
                    skip_reason=type(exc).__name__.lower(),
                    generation_id=gen_id,
                )
                return
            finally:
                if stream is not None:
                    try:
                        await stream.aclose()
                    except Exception:
                        pass
        _breaker_trip(fallback_reason or "candidates_exhausted")
        _log_voice_decision(
            ok=False,
            provider=None,
            model=None,
            latency_ms=None,
            fallback_reason=fallback_reason,
            skip_reason="candidates_exhausted",
            generation_id=gen_id,
        )
    finally:
        _clear_generation(gen_id)


async def chat(
    system: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 90,
    temperature: float = 0.6,
    generation_id: str | None = None,
) -> tuple[str, VoiceRouteMeta | None]:
    """Non-stream voice reply via OmniRoute. ("", None) = fail-open to free_ai."""
    parts: list[str] = []
    meta: VoiceRouteMeta | None = None
    async for tok in chat_stream(
        system,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        generation_id=generation_id,
    ):
        if is_cancelled(generation_id):
            return "", None
        parts.append(tok)
    text = "".join(parts).strip()
    if text:
        meta = VoiceRouteMeta(provider="omniroute", model=TASK_SWARA_LIVE)
        return text, meta
    return "", None


__all__ = [
    "TASK_SWARA_LIVE",
    "PRIVACY_CUSTOMER_MASKED",
    "VoiceRouteMeta",
    "voice_enabled",
    "new_generation_id",
    "cancel_generation",
    "is_cancelled",
    "breaker_open",
    "reset_breaker",
    "first_token_timeout_s",
    "chat_stream",
    "chat",
]
