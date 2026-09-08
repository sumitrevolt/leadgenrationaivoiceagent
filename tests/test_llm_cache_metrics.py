"""LLM cache hit-rate + provider-429 observability (W1.12 revisit-trigger prereq).

The L1 LLM cache (W1.10/W1.11) had ZERO visibility: a cache hit returned early
recording nothing, so the "is L1 hit-rate sufficient or do we need a Redis L2?"
decision (W1.12 deferral trigger) had no data. Also `stats()` exposed only
last_error per provider — no explicit rate-limit (429/quota) count.

- `llm_metrics.record_cache(hit)` writes kind="cache" rows, aggregated SEPARATELY
  from provider stats (must not skew fallback_or_fail_rate / capacity alerts).
- `stats()["providers"][p]["rate_limited"]` counts fail rows with 429/quota-class
  error strings (read-side only — errors were already recorded).
- free_ai's single cache-get site records hit/miss (never-raise, ultra-light).
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from app.platform import llm_metrics

_FREE_AI_PATH = Path(__file__).resolve().parents[1] / "app" / "voice_agent" / "free_ai.py"


def _load_real_free_ai():
    """conftest globally stubs free_ai.chat (offline safety) — load a FRESH module
    instance so the wiring test exercises the REAL chat(); its lazy `from
    app.platform import llm_metrics` still resolves to the shared module (spy works)."""
    spec = importlib.util.spec_from_file_location("free_ai_real_for_test", _FREE_AI_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_record_cache_and_stats_separation(tmp_path, monkeypatch):
    """Cache rows aggregate under stats()['cache'] and must NOT pollute provider
    stats, total_calls, or fallback_or_fail_rate (capacity-alert input)."""
    monkeypatch.setattr(llm_metrics, "_LOG", str(tmp_path / "llm_calls.jsonl"))
    llm_metrics.record_cache(True)
    llm_metrics.record_cache(True)
    llm_metrics.record_cache(False)
    llm_metrics.record("groq", True, 100.0)
    st = llm_metrics.stats()
    assert st["cache"]["lookups"] == 3
    assert st["cache"]["hits"] == 2
    assert st["cache"]["hit_rate"] == round(2 / 3, 3)
    assert "cache" not in st["providers"], "cache rows must not appear as a provider"
    assert st["total_calls"] == 1, "cache lookups must not inflate provider call count"
    assert st["fallback_or_fail_rate"] == 0.0, "cache misses must not skew fail rate"


def test_stats_rate_limited_count(tmp_path, monkeypatch):
    """Fail rows with 429/quota-class errors get an explicit per-provider count."""
    monkeypatch.setattr(llm_metrics, "_LOG", str(tmp_path / "llm_calls.jsonl"))
    llm_metrics.record("groq", False, 50.0, error="429 Too Many Requests")
    llm_metrics.record("groq", False, 50.0, error="connection refused")
    llm_metrics.record("groq", True, 80.0)
    llm_metrics.record("mistral", True, 90.0)
    st = llm_metrics.stats()
    assert st["providers"]["groq"]["rate_limited"] == 1
    assert st["providers"]["mistral"]["rate_limited"] == 0


def test_chat_cache_hit_records_metric(monkeypatch):
    """Wiring: a chat() cache hit must record_cache(True) and return the hit."""
    fa = _load_real_free_ai()
    monkeypatch.setenv("LLM_CACHE", "1")
    monkeypatch.setattr(fa, "_llm_cache_get", lambda k: ("cached reply", "cache-test"))
    calls: list[bool] = []
    monkeypatch.setattr(llm_metrics, "record_cache", lambda hit: calls.append(bool(hit)))
    out = asyncio.run(fa.chat(system="s", messages=[{"role": "user", "content": "hi"}]))
    assert out == ("cached reply", "cache-test")
    assert calls == [True]
