"""
test_free_ai_chain_2026_models.py — pure-python (no network/DB/LLM).

Asserts the supported 2026 EXTRA free Groq models (gpt-oss-120b + qwen3.6-27b)
are present in the free-LLM fallback chain AS ADDITIONAL low-priority entries —
i.e. AFTER the proven primaries (mistral/groq-head/cerebras) so they only get
hit when the primaries exhaust, and BEFORE the weaker gemini/openrouter-:free
tail.

Updated 2026-08-01 from Claude web-research: Groq is decommissioning
llama-3.1-8b-instant + llama-3.3-70b-versatile on 2026-08-16; qwen3-32b and
kimi-k2-instruct are already dead and must not appear in the chain.
"""

from app.voice_agent import free_ai


def _chain(profile: str):
    # _build_llm_chain reads only env (OLLAMA_*) — no network/DB. Returns list of
    # (provider, model) tuples.
    return free_ai._build_llm_chain(profile)


def test_new_models_present_in_both_profiles():
    for profile in ("realtime", "bulk"):
        chain = _chain(profile)
        models = [m for (_p, m) in chain]
        pairs = list(chain)
        # Constants / official Groq replacements
        assert free_ai._GROQ_LLM_MODEL == "openai/gpt-oss-20b"
        assert free_ai._GROQ_QWEN3_MODEL == "qwen/qwen3.6-27b"
        assert free_ai._GROQ_LLAMA70B_MODEL == "openai/gpt-oss-120b"
        # Dead ids must never be called
        assert "llama-3.1-8b-instant" not in models
        assert "llama-3.3-70b-versatile" not in models
        assert "qwen/qwen3-32b" not in models
        assert "moonshotai/kimi-k2-instruct" not in models
        assert ("cerebras", "qwen-3-32b") not in pairs
        assert ("groq", free_ai._GROQ_QWEN3_MODEL) in pairs
        assert ("groq", free_ai._GROQ_LLAMA70B_MODEL) in pairs
        assert free_ai._GROQ_QWEN3_MODEL in models


def test_new_models_are_low_priority_after_primaries():
    """Extra entries must come AFTER the proven primaries (mistral/groq-head/cerebras)
    and BEFORE the gemini/sambanova tail."""
    for profile in ("realtime", "bulk"):
        chain = _chain(profile)
        idx = {}
        for i, (p, m) in enumerate(chain):
            idx.setdefault((p, m), i)  # first occurrence

        # primaries
        primary_positions = [
            idx[("mistral", free_ai._MISTRAL_LLM_MODEL)],
            idx[("groq", free_ai._GROQ_LLM_MODEL)],
            idx[("cerebras", free_ai._CEREBRAS_LLM_MODEL)],
        ]
        last_primary = max(primary_positions)

        new_positions = [
            idx[("groq", free_ai._GROQ_LLAMA70B_MODEL)],
            idx[("groq", free_ai._GROQ_QWEN3_MODEL)],
        ]
        for np in new_positions:
            assert np > last_primary, f"new model at {np} not after primaries ({last_primary})"

        gemini_pos = min(i for i, (p, _m) in enumerate(chain) if p == "gemini")
        for np in new_positions:
            assert np < gemini_pos, f"new model at {np} should precede gemini ({gemini_pos})"


def test_new_groq_entries_use_existing_provider_key():
    """New Groq models reuse existing provider names so the per-provider
    circuit-breaker + _client() lookup works unchanged."""
    for profile in ("realtime", "bulk"):
        for p, _m in _chain(profile):
            assert p in free_ai._PROVIDER_CFG or p == "ollama"


def test_describe_lists_new_models():
    d = free_ai.describe()
    llm = d.get("llm_chain", [])
    assert f"groq:{free_ai._GROQ_LLM_MODEL}" in llm
    assert f"groq:{free_ai._GROQ_QWEN3_MODEL}" in llm
    assert f"groq:{free_ai._GROQ_LLAMA70B_MODEL}" in llm
    assert "cerebras:qwen-3-32b" not in llm
    assert "groq:llama-3.1-8b-instant" not in llm
    assert "groq:moonshotai/kimi-k2-instruct" not in llm


def test_nvidia_nim_present_and_configured():
    """NVIDIA NIM = deep-tail free fallback. Provider registered + default model id."""
    assert "nvidia" in free_ai._PROVIDER_CFG
    assert free_ai._PROVIDER_CFG["nvidia"][0] == "nvidia_api_key"
    assert free_ai._PROVIDER_CFG["nvidia"][1] == free_ai._NVIDIA_BASE
    assert free_ai._NVIDIA_BASE == "https://integrate.api.nvidia.com/v1"
    assert free_ai._NVIDIA_LLM_MODEL == "meta/llama-3.3-70b-instruct"
    for profile in ("realtime", "bulk"):
        chain = _chain(profile)
        assert ("nvidia", free_ai._NVIDIA_LLM_MODEL) in chain


def test_nvidia_nim_deep_tail_placement():
    """NVIDIA must sit AFTER sambanova (conserve metered credits) and BEFORE the
    404-prone openrouter :free tail (70B beats flaky :free as a last resort)."""
    for profile in ("realtime", "bulk"):
        chain = _chain(profile)
        idx = {}
        for i, (p, m) in enumerate(chain):
            idx.setdefault((p, m), i)
        nvidia_pos = idx[("nvidia", free_ai._NVIDIA_LLM_MODEL)]
        sambanova_pos = idx[("sambanova", free_ai._SAMBANOVA_LLM_MODEL)]
        openrouter_pos = min(i for i, (p, _m) in enumerate(chain) if p.startswith("openrouter"))
        assert nvidia_pos > sambanova_pos, "nvidia should follow sambanova (credit conservation)"
        assert nvidia_pos < openrouter_pos, "nvidia should precede the openrouter :free tail"


def test_nvidia_credit_exhaustion_trips_max_cooldown():
    """A credits-dead NVIDIA (402 / out of credits) must get the LONG cooldown so the
    breaker parks it instead of hammering it every fallback (council risk)."""
    free_ai._LLM_COOLDOWN_UNTIL.pop("nvidia", None)
    free_ai._LLM_TRIP_STREAK.pop("nvidia", None)
    free_ai._trip_cooldown("nvidia", "402 Payment Required: out of credits")
    remaining = free_ai._LLM_COOLDOWN_UNTIL.get("nvidia", 0.0) - __import__("time").time()
    assert remaining > free_ai._LLM_COOLDOWN_MAX_S - 30
    free_ai._LLM_COOLDOWN_UNTIL.pop("nvidia", None)
    free_ai._LLM_TRIP_STREAK.pop("nvidia", None)
