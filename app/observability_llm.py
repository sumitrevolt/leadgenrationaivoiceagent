"""
observability_llm.py — gated LLM observability (G1 from Infra_BestStack_GapAnalysis_2026-06).

KYU: requirements-otel.txt sirf generic FastAPI/HTTP tracing deta hai. Per-LLM-call
ka prompt/model/provider/tokens/latency/quality kahin capture nahi hota — poora product
LLM-driven hai, yahi sabse bada blind-spot tha. Ye module wo bharta hai.

DESIGN (tere rules ke hisaab se):
  * OFF by default        -> `ENABLE_LLM_OBS=1` se ON. Bina iske 100% no-op.
  * NEVER-RAISE           -> observability ka koi bhi internal error caller tak nahi jaata
                             (FAIL-OPEN). User-code ka exception NORMAL flow karta (suppress nahi).
  * ZERO hard dependency  -> opentelemetry na ho / OFF ho -> graceful no-op.
  * Backend-agnostic      -> standard **OTel GenAI semantic-convention** spans emit karta.
                             Wahi span tere existing Tempo ME bhi jaata AUR Langfuse ke
                             OTLP endpoint me bhi (Langfuse OTel ingestion support karta).
                             => koi fragile vendor-SDK coupling nahi.

ENABLE karne ke liye:
  .env:  ENABLE_LLM_OBS=1
         ENABLE_OTEL=1
         OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317        (Tempo — already wired)
         # ya Langfuse cloud-free ke liye OTLP:
         # OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
  pip:   requirements-otel.txt (already present, gated)

USAGE (free_ai.py / kisi bhi LLM call ke around — module ko import-safe rakha hai):
    from app.observability_llm import llm_span, observe_llm

    # (a) context manager
    with llm_span("chat", model=model, provider=provider) as span:
        resp = await _call_provider(...)
        span.record(prompt_tokens=pt, completion_tokens=ct, latency_ms=ms, ok=True)

    # (b) decorator (sync ya async dono)
    @observe_llm(operation="embed", model="paraphrase-multilingual-MiniLM-L12-v2")
    async def embed(text): ...
"""
from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

# --- gating ----------------------------------------------------------------
_TRUE = {"1", "true", "yes", "on"}


def _enabled() -> bool:
    return os.environ.get("ENABLE_LLM_OBS", "").strip().lower() in _TRUE


# --- lazy, cached tracer (OTel) — import kabhi raise na kare ----------------
_tracer: Any = None
_tracer_ready: bool = False
_otel_status = None  # set lazily; cached after first import attempt


def _get_tracer() -> Any:
    """OTel tracer return karta hai (ek baar resolve karke cache). Fail -> None."""
    global _tracer, _tracer_ready, _otel_status
    if _tracer_ready:
        return _tracer
    _tracer_ready = True
    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.trace import Status, StatusCode  # type: ignore

        _otel_status = (Status, StatusCode)
        _tracer = trace.get_tracer("leadgen.llm")
    except Exception:  # opentelemetry installed nahi / koi bhi import issue
        _tracer = None
    return _tracer


# GenAI semantic-convention attribute keys (OTel spec).
_K_SYSTEM = "gen_ai.system"
_K_OP = "gen_ai.operation.name"
_K_REQ_MODEL = "gen_ai.request.model"
_K_RES_MODEL = "gen_ai.response.model"
_K_IN_TOK = "gen_ai.usage.input_tokens"
_K_OUT_TOK = "gen_ai.usage.output_tokens"
_K_TOT_TOK = "gen_ai.usage.total_tokens"
_K_LATENCY = "gen_ai.latency_ms"
_K_OUTPUT_PREVIEW = "gen_ai.completion.preview"


class _Span:
    """Patla wrapper — record()/error() OTel span pe attributes set karta.
    Sab kuch guarded: observability ka koi call kabhi raise nahi karega."""

    __slots__ = ("_span", "_t0")

    def __init__(self, span: Any) -> None:
        self._span = span  # None ho sakta (no-op mode)
        self._t0 = time.perf_counter()

    def set(self, key: str, value: Any) -> None:
        if self._span is None or value is None:
            return
        try:
            self._span.set_attribute(key, value)
        except Exception:
            pass

    def record(
        self,
        *,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        latency_ms: Optional[float] = None,
        response_model: Optional[str] = None,
        output_preview: Optional[str] = None,
        ok: Optional[bool] = None,
        **attrs: Any,
    ) -> None:
        """Call ke baad metrics record karo. Sab optional."""
        if self._span is None:
            return
        try:
            self.set(_K_IN_TOK, prompt_tokens)
            self.set(_K_OUT_TOK, completion_tokens)
            if total_tokens is None and (prompt_tokens is not None and completion_tokens is not None):
                total_tokens = int(prompt_tokens) + int(completion_tokens)
            self.set(_K_TOT_TOK, total_tokens)
            if latency_ms is None:
                latency_ms = (time.perf_counter() - self._t0) * 1000.0
            self.set(_K_LATENCY, round(float(latency_ms), 2))
            self.set(_K_RES_MODEL, response_model)
            if output_preview:
                self.set(_K_OUTPUT_PREVIEW, str(output_preview)[:500])
            if ok is False:
                self.set("error", True)
            for k, v in attrs.items():
                self.set(k, v)
        except Exception:
            pass

    def error(self, exc: BaseException) -> None:
        if self._span is None:
            return
        try:
            self._span.record_exception(exc)
            if _otel_status is not None:
                Status, StatusCode = _otel_status
                self._span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
        except Exception:
            pass


@contextmanager
def llm_span(
    operation: str,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    **attrs: Any,
) -> Iterator[_Span]:
    """LLM call ke around context manager.

    Disabled / OTel-absent -> ek no-op _Span (`.record()` chup-chaap kuch nahi karta).
    User-code ka exception NORMALLY propagate hota (suppress NAHI) — bas span pe ERROR mark.
    """
    tracer = _get_tracer() if _enabled() else None
    if tracer is None:
        # No-op path — koi overhead nahi, koi risk nahi.
        yield _Span(None)
        return

    span_name = f"{operation} {model}".strip() if model else operation
    cm = None
    raw = None
    try:
        cm = tracer.start_as_current_span(span_name)
        raw = cm.__enter__()
    except Exception:
        # Span banana fail -> no-op me girao, kabhi raise mat karo.
        yield _Span(None)
        return

    wrapper = _Span(raw)
    wrapper.set(_K_OP, operation)
    wrapper.set(_K_REQ_MODEL, model)
    wrapper.set(_K_SYSTEM, provider)
    for k, v in attrs.items():
        wrapper.set(k, v)

    try:
        yield wrapper
    except BaseException as exc:  # user-code error: mark + re-raise (suppress nahi)
        wrapper.error(exc)
        try:
            if cm is not None:
                cm.__exit__(type(exc), exc, exc.__traceback__)
        except Exception:
            pass
        raise
    else:
        try:
            if cm is not None:
                cm.__exit__(None, None, None)
        except Exception:
            pass


def observe_llm(
    operation: str = "chat",
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    **static_attrs: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator — sync ya async function ko LLM-span me wrap karta.

    Function ki return-value pe se token usage auto-extract karne ki koshish karta
    (best-effort: `.usage.prompt_tokens` / dict["usage"] style). Mile to record, na
    mile to bas latency. Kabhi raise nahi karta (observability layer)."""

    def _decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        import asyncio

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def _aw(*args: Any, **kwargs: Any) -> Any:
                with llm_span(operation, model=model, provider=provider, **static_attrs) as span:
                    result = await fn(*args, **kwargs)
                    _auto_record(span, result)
                    return result

            return _aw

        @functools.wraps(fn)
        def _w(*args: Any, **kwargs: Any) -> Any:
            with llm_span(operation, model=model, provider=provider, **static_attrs) as span:
                result = fn(*args, **kwargs)
                _auto_record(span, result)
                return result

        return _w

    return _decorate


def _auto_record(span: _Span, result: Any) -> None:
    """Best-effort: result se token usage nikaalo (OpenAI/dict-style). Guarded."""
    try:
        usage = getattr(result, "usage", None)
        if usage is None and isinstance(result, dict):
            usage = result.get("usage")
        if usage is None:
            span.record()
            return
        get = (lambda k: getattr(usage, k, None)) if not isinstance(usage, dict) else usage.get
        span.record(
            prompt_tokens=get("prompt_tokens") or get("input_tokens"),
            completion_tokens=get("completion_tokens") or get("output_tokens"),
            total_tokens=get("total_tokens"),
        )
    except Exception:
        try:
            span.record()
        except Exception:
            pass


__all__ = ["llm_span", "observe_llm"]
