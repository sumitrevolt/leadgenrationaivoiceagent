"""W1.11 — LLM cache eviction must be TTL+LRU-ish, not a full `.clear()`.

Bug: at the size bound `_llm_cache_put` did `_LLM_CACHE.clear()` — nuking the ENTIRE
cache (incl. hot, non-expired entries) every time it filled, collapsing hit-rate to ~0
right when caching mattered most.

Fix: `_llm_cache_evict` drops expired entries first, and only if still full evicts the
oldest ~20% by timestamp — hot entries survive.
"""

from __future__ import annotations

import time

import app.voice_agent.free_ai as fa


def test_evict_does_not_nuke_whole_cache(monkeypatch):
    monkeypatch.setattr(fa, "_LLM_CACHE_MAX", 10)
    monkeypatch.setattr(fa, "_LLM_CACHE_TTL_S", 300)
    fa._LLM_CACHE.clear()
    try:
        for i in range(10):
            fa._llm_cache_put(f"k{i}", (f"v{i}", "prov"))
        assert len(fa._LLM_CACHE) == 10
        fa._llm_cache_put("k_new", ("v_new", "prov"))  # overflow → evict, not clear
        assert 1 < len(fa._LLM_CACHE) <= 10, "eviction must NOT nuke the whole cache"
        assert fa._llm_cache_get("k_new") == ("v_new", "prov"), "newest entry must survive"
    finally:
        fa._LLM_CACHE.clear()


def test_evict_prefers_expired_over_live(monkeypatch):
    monkeypatch.setattr(fa, "_LLM_CACHE_MAX", 10)
    monkeypatch.setattr(fa, "_LLM_CACHE_TTL_S", 100)
    fa._LLM_CACHE.clear()
    try:
        now = time.time()
        for i in range(5):
            fa._LLM_CACHE[f"old{i}"] = (now - 1000, (f"o{i}", "p"))  # expired
        for i in range(5):
            fa._LLM_CACHE[f"fresh{i}"] = (now, (f"f{i}", "p"))
        assert len(fa._LLM_CACHE) == 10
        fa._llm_cache_put("k_new", ("v_new", "p"))  # overflow → purge expired first
        for i in range(5):
            assert f"old{i}" not in fa._LLM_CACHE, "expired entries must be purged first"
            assert f"fresh{i}" in fa._LLM_CACHE, "live entries must survive when expired free space"
        assert "k_new" in fa._LLM_CACHE
    finally:
        fa._LLM_CACHE.clear()
