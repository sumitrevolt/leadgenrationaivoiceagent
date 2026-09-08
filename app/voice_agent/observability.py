"""
Observability — Per-Call Tracing
================================

Har voice call ka *poora* picture: kab kya hua, har step (STT / LLM / TTS) me
kitna time laga, kitne tokens / kitna paisa (telephony) khārch hua, aur outcome
kya raha. Yeh exactly woh hai jo LiveKit / Braintrust / Bland dikhate hain —
spans + latency-per-step + token/cost estimate — taaki dashboard par har call
"replay" / debug ho sake.

Design:
  - Pure-python, ZERO external deps. Import-safe, crash-safe.
  - `Span`     -> ek step (name, start/end ms, duration, attributes).
  - `CallTrace`-> ek call ke saare spans + events + totals + cost.
  - `Tracer`   -> spans record karta hai, in-memory ring buffer rakhta hai
                  (recent traces) taaki dashboard read kar sake.
  - Module singleton: `get_tracer()`.

Usage:
    from app.voice_agent.observability import get_tracer
    tracer = get_tracer()
    trace = tracer.start_call("call_123")
    with tracer.span(trace, "stt", engine="vosk"):
        text = stt_transcribe(audio)
    with tracer.span(trace, "llm", model="gemini"):
        reply = await mgr.respond(text, state)
    with tracer.span(trace, "tts", engine="edge"):
        audio_out = tts_synthesize(reply.text)
    tracer.event(trace, "intent", {"type": "interested"})
    tracer.end_call(trace, outcome="qualified")
    print(tracer.to_json(trace))

OpenTelemetry note:
    Yeh module deliberately stdlib-only hai. Agar OTel chahiye to `span()` ke
    andar ek OTel span start/end wrap kiya ja sakta hai (e.g.
    `opentelemetry.trace.get_tracer(__name__).start_as_current_span(name)`),
    par yahan koi hard dependency NAHI hai — production me OTel optional rahe.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Cost / token heuristics (no external billing API needed)
# --------------------------------------------------------------------------- #
# Telephony PSTN cost India ~ ₹0.50-0.80 / min. Conservative default rakha.
DEFAULT_TELEPHONY_INR_PER_MIN = 0.70
# Rough token estimate: ~4 chars per token (OpenAI-ish heuristic).
CHARS_PER_TOKEN = 4
# LLM token cost is ~free on self-hosted/Gemini-free, par estimate ke liye tiny.
DEFAULT_LLM_INR_PER_1K_TOKENS = 0.0


def _now_ms() -> float:
    """Monotonic-ish wall clock in milliseconds (float)."""
    return time.time() * 1000.0


def _iso(ts_ms: float | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def estimate_tokens(text: str) -> int:
    """Cheap token estimate: chars / 4 (min 1 if non-empty)."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #
@dataclass
class Span:
    """Ek single step ka timing record (e.g. one STT / LLM / TTS call)."""

    name: str
    start_ms: float
    end_ms: float | None = None
    duration_ms: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)

    def close(self, end_ms: float | None = None) -> None:
        self.end_ms = _now_ms() if end_ms is None else end_ms
        self.duration_ms = round(max(0.0, self.end_ms - self.start_ms), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_ms": round(self.start_ms, 3),
            "end_ms": round(self.end_ms, 3) if self.end_ms is not None else None,
            "start_at": _iso(self.start_ms),
            "end_at": _iso(self.end_ms),
            "duration_ms": round(self.duration_ms, 3),
            "attributes": dict(self.attributes),
        }


@dataclass
class CallTrace:
    """Ek poori call ka trace — spans + events + totals + cost + outcome."""

    trace_id: str
    call_id: str
    started_at: float  # epoch ms
    ended_at: float | None = None  # epoch ms
    spans: list[Span] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, float] = field(
        default_factory=lambda: {
            "stt_ms": 0.0,
            "llm_ms": 0.0,
            "tts_ms": 0.0,
            "total_ms": 0.0,
        }
    )
    token_estimate: int = 0
    cost_estimate_inr: float = 0.0
    outcome: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "call_id": self.call_id,
            "started_at": _iso(self.started_at),
            "ended_at": _iso(self.ended_at),
            "started_ms": round(self.started_at, 3),
            "ended_ms": round(self.ended_at, 3) if self.ended_at is not None else None,
            "spans": [s.to_dict() for s in self.spans],
            "events": list(self.events),
            "totals": {k: round(v, 3) for k, v in self.totals.items()},
            "token_estimate": self.token_estimate,
            "cost_estimate_inr": round(self.cost_estimate_inr, 4),
            "outcome": self.outcome,
            "metadata": dict(self.metadata),
        }


# --------------------------------------------------------------------------- #
# Tracer
# --------------------------------------------------------------------------- #
# Span names jo totals me roll-up hote hain (prefix match, case-insensitive).
_STEP_BUCKETS = {
    "stt": "stt_ms",
    "asr": "stt_ms",
    "transcribe": "stt_ms",
    "llm": "llm_ms",
    "brain": "llm_ms",
    "respond": "llm_ms",
    "dialog": "llm_ms",
    "tts": "tts_ms",
    "synth": "tts_ms",
    "speak": "tts_ms",
}


class Tracer:
    """
    Records per-call spans/events and keeps a ring buffer of recent traces so a
    dashboard can read the last N calls without any DB.

    Thread-safety: simple append-only usage; good enough for single-process
    async pipelines. (Add a lock if you go multi-thread.)
    """

    def __init__(
        self,
        buffer_size: int = 200,
        telephony_inr_per_min: float = DEFAULT_TELEPHONY_INR_PER_MIN,
        llm_inr_per_1k_tokens: float = DEFAULT_LLM_INR_PER_1K_TOKENS,
    ):
        self._buffer: deque[CallTrace] = deque(maxlen=max(1, buffer_size))
        self.telephony_inr_per_min = telephony_inr_per_min
        self.llm_inr_per_1k_tokens = llm_inr_per_1k_tokens

    # ----------------------- lifecycle ----------------------- #
    def start_call(self, call_id: str, **metadata: Any) -> CallTrace:
        trace = CallTrace(
            trace_id=uuid.uuid4().hex,
            call_id=str(call_id),
            started_at=_now_ms(),
            metadata=dict(metadata),
        )
        self._buffer.append(trace)
        logger.debug(f"trace start call={call_id} trace_id={trace.trace_id}")
        return trace

    def end_call(self, trace: CallTrace, outcome: str | None = None) -> CallTrace:
        trace.ended_at = _now_ms()
        if outcome is not None:
            trace.outcome = outcome
        trace.totals["total_ms"] = round(max(0.0, trace.ended_at - trace.started_at), 3)
        self._recompute_cost(trace)
        logger.debug(
            f"trace end call={trace.call_id} outcome={trace.outcome} "
            f"total_ms={trace.totals['total_ms']} cost_inr={trace.cost_estimate_inr}"
        )
        return trace

    # ----------------------- spans ----------------------- #
    @contextmanager
    def span(self, trace: CallTrace, name: str, **attrs: Any) -> Iterator[Span]:
        """
        Context manager: enter pe span start, exit pe close + totals roll-up.
        Exceptions ko swallow nahi karta (re-raise) par span phir bhi close hota
        hai — taaki failed step ka bhi timing dikhe.
        """
        sp = self.start_span(trace, name, **attrs)
        try:
            yield sp
        except Exception as e:
            sp.attributes.setdefault("error", repr(e))
            raise
        finally:
            self.end_span(trace, sp)

    def start_span(self, trace: CallTrace, name: str, **attrs: Any) -> Span:
        sp = Span(name=name, start_ms=_now_ms(), attributes=dict(attrs))
        trace.spans.append(sp)
        return sp

    def end_span(self, trace: CallTrace, sp: Span) -> Span:
        if sp.end_ms is None:
            sp.close()
        self._rollup(trace, sp)
        # text attrs se token estimate badhao (input/output text agar diya ho)
        for key in ("text", "input", "output", "prompt", "reply"):
            val = sp.attributes.get(key)
            if isinstance(val, str):
                trace.token_estimate += estimate_tokens(val)
        if "tokens" in sp.attributes:
            try:
                trace.token_estimate += int(sp.attributes["tokens"])
            except (TypeError, ValueError):
                pass
        return sp

    # ----------------------- events ----------------------- #
    def event(self, trace: CallTrace, name: str, data: dict[str, Any] | None = None) -> None:
        """Point-in-time marker (intent detected, barge-in, voicemail, error...)."""
        trace.events.append(
            {
                "name": name,
                "at": _iso(_now_ms()),
                "at_ms": round(_now_ms(), 3),
                "data": data or {},
            }
        )

    # ----------------------- VAQI (Deepgram-style reliability legs) ------ #
    # Dormant until call code (turn_detector.py / vobiz_stream.py) calls these
    # at its existing barge-in / no-reply decision points — additive only, no
    # telephony code is touched by shipping these methods. Once wired, they
    # feed `vaqi_summary()` below the same way `latencies`/`missed` already
    # feed the self-test harness's own VAQI number (scripts/agent_tester.py).
    def record_interruption(
        self, trace: CallTrace, *, premature: bool = False, **data: Any
    ) -> None:
        """Log a barge-in/interruption occurrence. ``premature=True`` means the
        agent was still speaking when genuine user speech started (Deepgram's
        VAQI 'Interruptions' leg) — as opposed to a clean, expected barge-in."""
        self.event(trace, "interruption", {"premature": bool(premature), **data})

    def record_missed_response(self, trace: CallTrace, **data: Any) -> None:
        """Log a turn where the agent failed to respond within the expected
        window after the caller finished speaking (Deepgram's VAQI 'Missed
        responses' leg)."""
        self.event(trace, "missed_response", data or {})

    def vaqi_summary(self, n: int = 50) -> dict[str, Any]:
        """VAQI (Voice Agent Quality Index) over the last ``n`` traces:
        Interruptions / Missed responses / Latency — the same 3-leg
        reliability score Deepgram's guide recommends for production voice
        agents. Interruption/missed-response legs read as ``None`` (not 0,
        which would misleadingly read as "perfect") until call code starts
        calling `record_interruption`/`record_missed_response`."""
        traces = self.recent(n)
        completed = [t for t in traces if t.ended_at is not None]
        latencies_ms = [t.totals.get("total_ms", 0.0) for t in completed]
        try:
            from app.voice_agent.voice_metrics import latency_summary
        except Exception:  # pragma: no cover
            latency_summary = None  # type: ignore[assignment]
        latency = latency_summary(latencies_ms) if latency_summary else None

        interruptions = [e for t in traces for e in t.events if e.get("name") == "interruption"]
        missed = [e for t in traces for e in t.events if e.get("name") == "missed_response"]
        premature = sum(1 for e in interruptions if (e.get("data") or {}).get("premature"))

        return {
            "calls_sampled": len(traces),
            "latency": latency,
            "interruptions_total": len(interruptions) or None,
            "premature_interruptions": premature if interruptions else None,
            "interruption_rate": (
                round(premature / len(interruptions), 3) if interruptions else None
            ),
            "missed_responses_total": len(missed),
            "missed_response_rate": round(len(missed) / len(traces), 3) if traces else None,
        }

    # ----------------------- serialization ----------------------- #
    def to_dict(self, trace: CallTrace) -> dict[str, Any]:
        return trace.to_dict()

    def to_json(self, trace: CallTrace, indent: int | None = 2) -> str:
        return json.dumps(trace.to_dict(), indent=indent, default=str, ensure_ascii=False)

    # ----------------------- dashboard read ----------------------- #
    def recent(self, n: int = 20) -> list[CallTrace]:
        """Last `n` traces (newest last) — dashboard ke liye."""
        if n <= 0:
            return []
        items = list(self._buffer)
        return items[-n:]

    def recent_dicts(self, n: int = 20) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.recent(n)]

    def get(self, trace_id: str) -> CallTrace | None:
        for t in reversed(self._buffer):
            if t.trace_id == trace_id:
                return t
        return None

    def clear(self) -> None:
        self._buffer.clear()

    # ----------------------- internals ----------------------- #
    def _rollup(self, trace: CallTrace, sp: Span) -> None:
        bucket = self._bucket_for(sp.name)
        if bucket:
            trace.totals[bucket] = round(trace.totals.get(bucket, 0.0) + sp.duration_ms, 3)

    @staticmethod
    def _bucket_for(name: str) -> str | None:
        low = (name or "").lower()
        for prefix, bucket in _STEP_BUCKETS.items():
            if low.startswith(prefix) or prefix in low:
                return bucket
        return None

    def _recompute_cost(self, trace: CallTrace) -> None:
        total_ms = trace.totals.get("total_ms", 0.0)
        minutes = total_ms / 60000.0
        telephony = minutes * self.telephony_inr_per_min
        llm = (trace.token_estimate / 1000.0) * self.llm_inr_per_1k_tokens
        trace.cost_estimate_inr = round(telephony + llm, 4)
        trace.metadata.setdefault("cost_breakdown", {})
        trace.metadata["cost_breakdown"] = {
            "telephony_inr": round(telephony, 4),
            "llm_inr": round(llm, 4),
            "minutes": round(minutes, 4),
        }


# --------------------------------------------------------------------------- #
# Module singleton
# --------------------------------------------------------------------------- #
_TRACER: Tracer | None = None


def get_tracer() -> Tracer:
    """Process-wide singleton Tracer."""
    global _TRACER
    if _TRACER is None:
        _TRACER = Tracer()
    return _TRACER


__all__ = [
    "Span",
    "CallTrace",
    "Tracer",
    "get_tracer",
    "estimate_tokens",
    "DEFAULT_TELEPHONY_INR_PER_MIN",
    "CHARS_PER_TOKEN",
]


if __name__ == "__main__":  # pragma: no cover
    # Tiny smoke demo (no external services).
    import asyncio

    async def _demo():
        tracer = get_tracer()
        trace = tracer.start_call("demo_call_1", niche="solar", phone="+91...")
        with tracer.span(trace, "stt", engine="vosk", text="Haan boliye"):
            await asyncio.sleep(0.01)
        tracer.event(trace, "intent", {"type": "interested"})
        with tracer.span(trace, "llm", model="gemini", output="Namaste! 2 min hain?"):
            await asyncio.sleep(0.02)
        with tracer.span(trace, "tts", engine="edge"):
            await asyncio.sleep(0.01)
        tracer.end_call(trace, outcome="qualified")
        print(tracer.to_json(trace))
        print("recent:", len(tracer.recent()))

    asyncio.run(_demo())
