"""
test_free_ai_chain_2026_models.py — pure-python (no network/DB/LLM).

Asserts the 2026 EXTRA free models (Qwen3-32B on Groq+Cerebras, Llama-3.3-70B,
Kimi K2) are present in the free-LLM fallback chain AS ADDITIONAL low-priority
entries — i.e. AFTER the proven primaries (mistral/groq-8b/cerebras) so they only
get hit when the primaries exhaust (the Groq-TPD case they help), and BEFORE the
weaker gemini/openrouter-:free tail.
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
        pairs = [(p, m) for (p, m) in chain]
        # Constants exist
        assert free_ai._GROQ_QWEN3_MODEL == "qwen/qwen3-32b"
        assert free_ai._CEREBRAS_QWEN3_MODEL == "qwen-3-32b"
        assert free_ai._GROQ_LLAMA70B_MODEL == "llama-3.3-70b-versatile"
        assert free_ai._GROQ_KIMI_K2_MODEL == "moonshotai/kimi-k2-instruct"
        # Qwen3 added on BOTH Groq and Cerebras free tier
        assert ("groq", free_ai._GROQ_QWEN3_MODEL) in pairs
        assert ("cerebras", free_ai._CEREBRAS_QWEN3_MODEL) in pairs
        # One more strong free multilingual model (Kimi K2) + Llama-3.3-70B
        assert ("groq", free_ai._GROQ_KIMI_K2_MODEL) in pairs
        assert ("groq", free_ai._GROQ_LLAMA70B_MODEL) in pairs
        # Sanity: new ids actually in the model list
        assert free_ai._GROQ_QWEN3_MODEL in models
        assert free_ai._CEREBRAS_QWEN3_MODEL in models
        assert free_ai._GROQ_KIMI_K2_MODEL in models


def test_new_models_are_low_priority_after_primaries():
    """New entries must come AFTER the proven primaries (mistral/groq-8b/cerebras)
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
            idx[("cerebras", free_ai._CEREBRAS_QWEN3_MODEL)],
            idx[("groq", free_ai._GROQ_KIMI_K2_MODEL)],
        ]
        # every new model must come AFTER the last proven primary
        for np in new_positions:
            assert np > last_primary, f"new model at {np} not after primaries ({last_primary})"

        # and BEFORE the weaker tail (gemini)
        gemini_pos = idx[("gemini", free_ai._GEMINI_LLM_MODEL)]
        for np in new_positions:
            assert np < gemini_pos, f"new model at {np} should precede gemini ({gemini_pos})"


def test_new_groq_entries_use_existing_provider_key():
    """New Groq/Cerebras models reuse existing provider names so the per-provider
    circuit-breaker + _client() lookup works unchanged."""
    for profile in ("realtime", "bulk"):
        for p, _m in _chain(profile):
            # ollama entry uses dynamic name; all others must be configured providers
            assert p in free_ai._PROVIDER_CFG or p == "ollama"


def test_describe_lists_new_models():
    d = free_ai.describe()
    llm = d.get("llm_chain", [])
    assert f"groq:{free_ai._GROQ_QWEN3_MODEL}" in llm
    assert f"cerebras:{free_ai._CEREBRAS_QWEN3_MODEL}" in llm
    assert f"groq:{free_ai._GROQ_KIMI_K2_MODEL}" in llm
    assert f"groq:{free_ai._GROQ_LLAMA70B_MODEL}" in llm


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
        # first openrouter entry of any kind
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
    # near the 30-min max (allow scheduling slack), NOT the 60s transient base
    assert remaining > free_ai._LLM_COOLDOWN_MAX_S - 30
    free_ai._LLM_COOLDOWN_UNTIL.pop("nvidia", None)
    free_ai._LLM_TRIP_STREAK.pop("nvidia", None)
