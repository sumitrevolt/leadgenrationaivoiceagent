"""Tests for the VAQI (Deepgram-style Voice Agent Quality Index) additions to
app/voice_agent/observability.py's Tracer — record_interruption /
record_missed_response / vaqi_summary."""

from app.voice_agent.observability import Tracer


def _finished_trace(tracer, call_id="c1"):
    trace = tracer.start_call(call_id)
    with tracer.span(trace, "stt"):
        pass
    tracer.end_call(trace, outcome="qualified")
    return trace


def test_vaqi_summary_empty_tracer_has_no_misleading_zeros():
    tracer = Tracer()
    out = tracer.vaqi_summary()
    assert out["calls_sampled"] == 0
    assert out["interruptions_total"] is None
    assert out["missed_response_rate"] is None


def test_record_missed_response_feeds_vaqi_summary():
    tracer = Tracer()
    t1 = _finished_trace(tracer, "c1")
    tracer.record_missed_response(t1, turn="kya bol rahe ho")
    _finished_trace(tracer, "c2")  # no missed response on this one

    out = tracer.vaqi_summary()
    assert out["calls_sampled"] == 2
    assert out["missed_responses_total"] == 1
    assert out["missed_response_rate"] == 0.5


def test_record_interruption_premature_vs_clean():
    tracer = Tracer()
    t1 = _finished_trace(tracer, "c1")
    tracer.record_interruption(t1, premature=True)
    tracer.record_interruption(t1, premature=False)

    out = tracer.vaqi_summary()
    assert out["interruptions_total"] == 2
    assert out["premature_interruptions"] == 1
    assert out["interruption_rate"] == 0.5


def test_vaqi_summary_latency_reads_call_totals():
    tracer = Tracer()
    _finished_trace(tracer, "c1")
    out = tracer.vaqi_summary()
    assert out["latency"] is not None
    assert out["latency"]["n"] == 1
