"""observability_llm — OTel sink coverage (Item D, 2026-08-06).

audit.py:46 was calling obs.set_current_attributes / obs.annotate which did NOT
exist -> gen_ai.run.id was never stamped (dead call). This module now provides
both (no-op unless OTel enabled + span recording) and fixes llm_span parenting
(start_span + use_span(end_on_exit=False) so the LLM span is current).

Tests use a fake opentelemetry.trace (pure-python import under sys.modules) so
they run with zero real OTel deps.
"""

from __future__ import annotations

import sys
import threading
import types
from unittest.mock import MagicMock

import pytest

from app import observability_llm as obs


class _FakeSpan:
    def __init__(self):
        self.attrs = {}
        self.is_recording = lambda: True
        self.ended = False

    def set_attribute(self, k, v):
        self.attrs[k] = v

    def end(self):
        self.ended = True


class _FakeTracer:
    def __init__(self):
        self.span = _FakeSpan()
        self.parent = None

    def start_span(self, name):
        self.span.name = name
        return self.span

    def start_as_current_span(self, name):
        return self._CM(name)

    def _CM(self, name):
        return _NullCM()


class _NullCM:
    def __enter__(self):
        return _FakeSpan()

    def __exit__(self, *a):
        return False


_CURRENT = threading.local()


def _install_fake_otel(monkeypatch):
    trace_mod = types.ModuleType("opentelemetry.trace")

    def get_current_span():
        sp = getattr(_CURRENT, "span", None)
        return sp or MagicMock(is_recording=lambda: False)

    def use_span(sp, end_on_exit=True):
        class CM:
            def __enter__(s):
                _CURRENT.span = sp
                return s

            def __exit__(s, *a):
                _CURRENT.span = None
                return False

        return CM()

    def get_tracer(name):
        t = _FakeTracer()
        _CURRENT.tracer = t
        return t

    trace_mod.get_current_span = get_current_span
    trace_mod.use_span = use_span
    trace_mod.get_tracer = get_tracer

    otel_pkg = types.ModuleType("opentelemetry")
    otel_pkg.trace = trace_mod
    sys.modules["opentelemetry"] = otel_pkg
    sys.modules["opentelemetry.trace"] = trace_mod
    monkeypatch.setenv("ENABLE_OTEL", "1")
    monkeypatch.setenv("ENABLE_LLM_OBS", "0")


@pytest.fixture(autouse=True)
def _clean_sys_modules():
    yield
    sys.modules.pop("opentelemetry", None)
    sys.modules.pop("opentelemetry.trace", None)
    _CURRENT.span = None
    _CURRENT.tracer = None


def test_disabled_set_current_attributes_noop(monkeypatch):
    monkeypatch.setenv("ENABLE_OTEL", "0")
    obs.set_current_attributes(gen_ai_run_id="x")  # must not raise
    obs.annotate(foo="bar")  # must not raise


def test_disabled_llm_span_noop(monkeypatch):
    monkeypatch.setenv("ENABLE_OTEL", "0")
    monkeypatch.setenv("ENABLE_LLM_OBS", "0")
    with obs.llm_span("chat", model="m", provider="p") as s:
        s.record(prompt_tokens=1)
    assert True  # no-op span, no crash


def test_enabled_set_current_attributes_stamps_current_span(monkeypatch):
    _install_fake_otel(monkeypatch)
    # current span not yet set -> no-op (no crash, no attrs on magic mock)
    obs.set_current_attributes(gen_ai_run_id="r1")

    # now stamp inside a recording span
    sp = _FakeSpan()
    _CURRENT.span = sp
    obs.set_current_attributes(gen_ai_run_id="r1", tool="hashtags.research")
    assert sp.attrs.get("gen_ai_run_id") == "r1"
    assert sp.attrs.get("tool") == "hashtags.research"


def test_enabled_annotate_alias(monkeypatch):
    _install_fake_otel(monkeypatch)
    sp = _FakeSpan()
    _CURRENT.span = sp
    obs.annotate(kind="step")
    assert sp.attrs.get("kind") == "step"


def test_llm_span_parents_and_stamps_current(monkeypatch):
    _install_fake_otel(monkeypatch)
    with obs.llm_span("chat", model="gemini", provider="gemini") as s:
        # inside the span, current span is the LLM span
        obs.set_current_attributes(gen_ai_run_id="run-42")
        s.record(prompt_tokens=5, completion_tokens=3)
    assert _CURRENT.tracer is not None
    sp = _CURRENT.tracer.span
    assert sp.name == "llm.chat"
    assert sp.attrs.get("gen_ai_run_id") == "run-42"
    assert sp.ended is True


def test_llm_span_exception_closes_span(monkeypatch):
    _install_fake_otel(monkeypatch)
    with pytest.raises(RuntimeError):
        with obs.llm_span("chat", model="m") as s:
            raise RuntimeError("boom")
    assert _CURRENT.tracer is not None
    assert _CURRENT.tracer.span.ended is True
