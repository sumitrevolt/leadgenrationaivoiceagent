"""
observability_llm.py — gated LLM observability via **Langfuse REST ingestion**.

KYU: poora product LLM-driven hai par per-call model/provider/tokens/latency/output
kahin trace nahi hota tha (yahi #1 blind-spot). Ye module har LLM call ko Langfuse
me bhejta.

KYUN REST (OTel/SDK nahi): image ka `protobuf==4.25.9` Gemini(google-generativeai)
+ Qdrant + onnxruntime/fastembed ke liye PINNED hai. OTel-OTLP exporter / Langfuse
SDK protobuf 5.x maangte = unko todenge. Isliye hum seedha Langfuse ingestion REST
API (JSON over httpx) use karte — httpx already installed (openai dep), zero naya dep.

DESIGN (prod-rules ke hisaab se):
  * OFF by default  -> `ENABLE_LLM_OBS=1` + LANGFUSE keys na ho -> 100% no-op.
  * NEVER-RAISE     -> observability ka koi error caller tak nahi (FAIL-OPEN). User-code
                       ka exception NORMAL propagate karta (suppress nahi).
  * NON-BLOCKING    -> events background daemon-thread queue me; LLM hot-path kabhi
                       block/await nahi karta. Queue-full / network-fail = chup drop.
  * interface STABLE-> llm_span()/observe_llm() signature same (free_ai/structured
                       ke call-sites unchanged).

DO SINKS (independent — ek, dono, ya koi nahi):
  1. Langfuse REST  (ENABLE_LLM_OBS=1 + LANGFUSE keys) — cloud free-tier, zero VPS load.
  2. OTel -> Tempo  (ENABLE_OTEL=1 + opentelemetry installed) — maujooda Grafana/Tempo
     stack reuse, protobuf-SAFE (sirf otel-API import; OTLP exporter boot pe alag).

ENV:
  ENABLE_LLM_OBS=1
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...     (secret — sirf .env me)
  LANGFUSE_BASE_URL=https://us.cloud.langfuse.com   (default; EU/JP/HIPAA alag)
  ENABLE_OTEL=1                      (+ pip install -r requirements-otel.txt) -> Tempo
  OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
"""

from __future__ import annotations

import base64
import functools
import os
import queue
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

_TRUE = {"1", "true", "yes", "on"}


def _env(k: str, d: str = "") -> str:
    return os.environ.get(k, d).strip()


def _enabled() -> bool:
    return (
        _env("ENABLE_LLM_OBS").lower() in _TRUE
        and bool(_env("LANGFUSE_PUBLIC_KEY"))
        and bool(_env("LANGFUSE_SECRET_KEY"))
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _LangfuseSender:
    """Singleton background sender — queue + daemon thread + httpx (sync POST)."""

    _instance: _LangfuseSender | None = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> _LangfuseSender | None:
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                try:
                    cls._instance = _LangfuseSender()
                except Exception:
                    cls._instance = None  # httpx missing / init fail -> no-op
        return cls._instance

    def __init__(self) -> None:
        import httpx  # raises if absent -> get() -> None -> no-op

        pk = _env("LANGFUSE_PUBLIC_KEY")
        sk = _env("LANGFUSE_SECRET_KEY")
        base = _env("LANGFUSE_BASE_URL") or "https://us.cloud.langfuse.com"
        self._url = base.rstrip("/") + "/api/public/ingestion"
        token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        self._headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        self._client = httpx.Client(timeout=5.0)
        self._q: queue.Queue[dict] = queue.Queue(maxsize=2000)
        threading.Thread(target=self._worker, name="langfuse-sender", daemon=True).start()

    def enqueue(self, event: dict) -> None:
        try:
            self._q.put_nowait(event)
        except Exception:
            pass  # full -> drop, never block hot-path

    def _worker(self) -> None:
        while True:
            batch = []
            try:
                batch.append(self._q.get())  # block for first
                for _ in range(50):  # drain a batch
                    try:
                        batch.append(self._q.get_nowait())
                    except queue.Empty:
                        break
            except Exception:
                continue
            try:
                self._client.post(self._url, headers=self._headers, json={"batch": batch})
            except Exception:
                pass  # network/auth fail -> drop silently (never crash)


def _event(etype: str, body: dict) -> dict:
    return {"id": str(uuid.uuid4()), "timestamp": _now_iso(), "type": etype, "body": body}


class _Span:
    __slots__ = (
        "op",
        "model",
        "provider",
        "_t0",
        "_start_iso",
        "trace_id",
        "obs_id",
        "_pt",
        "_ct",
        "_tt",
        "_latency",
        "_out",
        "_ok",
        "_extra",
    )

    def __init__(self, op: str, model, provider, attrs: dict) -> None:
        self.op = op
        self.model = model
        self.provider = provider
        self._t0 = time.perf_counter()
        self._start_iso = _now_iso()
        self.trace_id = str(uuid.uuid4())
        self.obs_id = str(uuid.uuid4())
        self._pt = self._ct = self._tt = None
        self._latency = None
        self._out = None
        self._ok = None
        self._extra = dict(attrs or {})

    def record(
        self,
        *,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        latency_ms=None,
        response_model=None,
        output_preview=None,
        ok=None,
        **attrs,
    ) -> None:
        self._pt, self._ct, self._tt = prompt_tokens, completion_tokens, total_tokens
        self._latency = latency_ms
        self._out = output_preview
        self._ok = ok
        if response_model:
            self._extra["response_model"] = response_model
        if attrs:
            self._extra.update(attrs)

    def set(self, *_a, **_k) -> None:  # OTel-compat no-ops
        pass

    def error(self, *_a, **_k) -> None:
        self._ok = False

    def _flush(self) -> None:
        try:
            sender = _LangfuseSender.get()
            if sender is None:
                return
            latency = self._latency
            if latency is None:
                latency = (time.perf_counter() - self._t0) * 1000.0
            meta = {"provider": self.provider, "latency_ms": round(float(latency), 2)}
            meta.update({k: v for k, v in self._extra.items() if v is not None})
            usage = None
            if self._pt is not None or self._ct is not None or self._tt is not None:
                tt = self._tt
                if tt is None and self._pt is not None and self._ct is not None:
                    tt = int(self._pt) + int(self._ct)
                usage = {"input": self._pt, "output": self._ct, "total": tt, "unit": "TOKENS"}
            out = str(self._out)[:1000] if self._out else None
            name = f"{self.op}:{self.provider}" if self.provider else self.op
            env = os.environ.get("ENVIRONMENT", "production")
            sender.enqueue(
                _event(
                    "trace-create",
                    {
                        "id": self.trace_id,
                        "timestamp": self._start_iso,
                        "name": name,
                        "output": out,
                        "metadata": meta,
                        "tags": ["llm", self.provider or "unknown"],
                        "environment": env,
                    },
                )
            )
            gen = {
                "id": self.obs_id,
                "traceId": self.trace_id,
                "type": "GENERATION",
                "name": name,
                "model": self.model,
                "startTime": self._start_iso,
                "endTime": _now_iso(),
                "output": out,
                "metadata": meta,
                "environment": env,
            }
            if usage is not None:
                gen["usage"] = usage
            if self._ok is False:
                gen["level"] = "ERROR"
            sender.enqueue(_event("generation-create", gen))
        except Exception:
            pass


class _NoopSpan:
    __slots__ = ()

    def record(self, *_a, **_k) -> None:
        pass

    def set(self, *_a, **_k) -> None:
        pass

    def error(self, *_a, **_k) -> None:
        pass


# --------------------------------------------------------------------------- #
# OTel sink (-> Tempo). Langfuse se SWATANTRA (independent). KYUN alag: image ka
# protobuf==4.25.9 PINNED hai (Gemini/Qdrant/fastembed). Yahan hum sirf
# opentelemetry-api (PURE-PYTHON, protobuf-free) lazy-import karte — asli OTLP gRPC
# exporter (protobuf) sirf app boot pe `observability_otel.setup_otel()` me load
# hota (requirements-otel.txt; otel 1.27 = protobuf-4 safe). OTel installed na ho ya
# ENABLE_OTEL unset = 100% no-op. Har LLM call ek `llm.<op>` span (gen_ai.* attrs)
# banata jo maujooda request-trace (FastAPIInstrumentor) ka child ban ke Tempo me
# jaata — Grafana me ab provider/model/tokens/latency dikhte. NEVER-RAISE.
# --------------------------------------------------------------------------- #
def _otel_enabled() -> bool:
    if _env("ENABLE_OTEL").lower() not in _TRUE:
        return False
    try:
        import opentelemetry.trace  # noqa: F401  (pure-python API; no protobuf)

        return True
    except Exception:
        return False


def _otel_start(operation: str, model: Any, provider: Any) -> Any:
    """LLM OTel span start karo (current request-context ka child). None on failure."""
    try:
        from opentelemetry import trace

        # start_span: current active context (FastAPIInstrumentor request span)
        # ka child banata hai. The span stays OPEN; llm_span() makes it current
        # via trace.use_span(end_on_exit=False) for its whole lifetime so
        # set_current_attributes()/annotate() (audit.py gen_ai.run.id) stamp the
        # LLM span itself, and _otel_finish() end()s it. Plain start_span used to
        # leave the span NOT-current -> audit's setter was a silent dead-call.
        sp = trace.get_tracer("app.llm").start_span(f"llm.{operation}")
        try:
            sp.set_attribute("gen_ai.operation.name", operation)
            if provider:
                sp.set_attribute("gen_ai.system", str(provider))
            if model:
                sp.set_attribute("gen_ai.request.model", str(model))
        except Exception:
            pass
        return sp
    except Exception:
        return None


def _otel_finish(sp: Any, span: _Span, ok: bool) -> None:
    """Span ko recorded tokens/latency/ok ke saath close karo. Never-raise."""
    if sp is None:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        if span._pt is not None:
            sp.set_attribute("gen_ai.usage.input_tokens", int(span._pt))
        if span._ct is not None:
            sp.set_attribute("gen_ai.usage.output_tokens", int(span._ct))
        if span._latency is not None:
            sp.set_attribute("gen_ai.latency_ms", float(span._latency))
        final_ok = span._ok if span._ok is not None else ok
        sp.set_attribute("gen_ai.ok", bool(final_ok))
        sp.set_status(Status(StatusCode.OK if final_ok else StatusCode.ERROR))
    except Exception:
        pass
    finally:
        try:
            sp.end()
        except Exception:
            pass


@contextmanager
def llm_span(
    operation: str, *, model: str | None = None, provider: str | None = None, **attrs: Any
) -> Iterator[Any]:
    """LLM call ke around. DO independent sinks:
      * Langfuse REST  -> _enabled()       (ENABLE_LLM_OBS + LANGFUSE_*_KEY)
      * OTel -> Tempo  -> _otel_enabled()  (ENABLE_OTEL + opentelemetry installed)
    Dono OFF = no-op span. User-code exception NORMALLY propagate hota (suppress
    nahi); span ERROR mark + flush/close hota. interface unchanged (call-sites same)."""
    lf_on = _enabled()
    ot_on = _otel_enabled()
    if not (lf_on or ot_on):
        yield _NoopSpan()
        return
    span = _Span(operation, model, provider, attrs)
    otsp = _otel_start(operation, model, provider) if ot_on else None
    ot_ctx = None
    if otsp is not None:
        try:
            from opentelemetry import trace

            # Make the LLM span the CURRENT span for its lifetime so
            # set_current_attributes()/annotate() stamp the right span. The span
            # itself stays open; _otel_finish() end()s it (end_on_exit=False).
            ot_ctx = trace.use_span(otsp, end_on_exit=False).__enter__()
        except Exception:  # pragma: no cover - never break the hot path
            ot_ctx = None
    try:
        yield span
    except BaseException:
        try:
            span.error()
            if lf_on:
                span._flush()
        except Exception:
            pass
        _otel_finish(otsp, span, ok=False)
        if ot_ctx is not None:
            try:
                ot_ctx.__exit__(None, None, None)
            except Exception:
                pass
        raise
    else:
        try:
            if lf_on:
                span._flush()
        except Exception:
            pass
        _otel_finish(otsp, span, ok=True)
        if ot_ctx is not None:
            try:
                ot_ctx.__exit__(None, None, None)
            except Exception:
                pass


def observe_llm(
    operation: str = "chat",
    *,
    model: str | None = None,
    provider: str | None = None,
    **static_attrs: Any,
) -> Callable:
    """Decorator (sync/async) — function ko LLM-span me wrap karta; result se token
    usage best-effort auto-record. Kabhi raise nahi karta."""

    def _decorate(fn: Callable) -> Callable:
        import asyncio

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def _aw(*a, **k):
                with llm_span(operation, model=model, provider=provider, **static_attrs) as s:
                    r = await fn(*a, **k)
                    _auto_record(s, r)
                    return r

            return _aw

        @functools.wraps(fn)
        def _w(*a, **k):
            with llm_span(operation, model=model, provider=provider, **static_attrs) as s:
                r = fn(*a, **k)
                _auto_record(s, r)
                return r

        return _w

    return _decorate


def _auto_record(span: Any, result: Any) -> None:
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


def set_current_attributes(**attrs: Any) -> None:
    """Stamp attrs on the CURRENT OTel span (if OTel enabled + a span is active).

    Makes audit.py's gen_ai.run.id correlation real (OB-01): called inside an
    active llm_span (or request) it lands on the live span. NEVER-RAISE. When
    OTel is off (or no span active / API missing) this is a silent no-op — the
    durable audit-log row still carries run_id (fail-open by design)."""
    if not _otel_enabled():
        return
    try:
        from opentelemetry import trace

        sp = trace.get_current_span()
        if sp is None or not sp.is_recording():
            return
        for k, v in attrs.items():
            if v is not None:
                try:
                    sp.set_attribute(str(k), v)
                except Exception:
                    pass
    except Exception:
        pass


def annotate(**attrs: Any) -> None:
    """Alias of set_current_attributes (Langfuse-ish ergonomics; same no-op rules)."""
    set_current_attributes(**attrs)


__all__ = ["llm_span", "observe_llm", "set_current_attributes", "annotate"]
