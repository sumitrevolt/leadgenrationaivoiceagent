"""W1.10 — LLM response cache ON for the bulk/content profile (was globally OFF).

Bug: `_llm_cache_on()` read only `LLM_CACHE` (default "0"), so bulk content/blog/SEO
generation — where identical prompts recur — never cached, re-hitting rate-limited free
providers every run. Voice/realtime must stay uncached (dynamic replies).

Fix: `_llm_cache_on(prof)` defaults ON for the "bulk" profile and OFF for realtime when
`LLM_CACHE` is unset; explicit `LLM_CACHE=1/0` still force-on/off across all profiles.
"""

from __future__ import annotations

import app.voice_agent.free_ai as fa


def test_cache_default_on_for_bulk_off_for_realtime(monkeypatch):
    monkeypatch.delenv("LLM_CACHE", raising=False)
    assert fa._llm_cache_on("bulk") is True, "content/bulk profile must cache by default"
    assert fa._llm_cache_on("realtime") is False, "voice/realtime must not cache"
    assert fa._llm_cache_on("") is False


def test_env_forces_on_or_off_for_all_profiles(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "1")
    assert fa._llm_cache_on("realtime") is True  # global force-on wins over profile
    monkeypatch.setenv("LLM_CACHE", "0")
    assert fa._llm_cache_on("bulk") is False  # global force-off wins over profile
