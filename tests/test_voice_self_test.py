"""
Tests for app.voice_agent.self_test — the built-in on-demand voice self-test.

Deterministic + network-free by design: personas run rule-based (brain=None +
use_llm_fallback=False intent → zero LLM/network), live reads local transcripts,
and STACK PROBES ARE OFF here (no edge-tts / provider network in CI). Proves the
orchestrator never raises and the scorecard shape stays stable.
"""

from app.voice_agent import self_test


async def test_personas_only_network_free():
    """Rule-based persona suite passes the project's 0.7 bar (7/7 = 1.0 today)
    and the verdict is well-formed — all without touching the network."""
    rep = await self_test.run_voice_self_test(
        personas=True, stack=False, live=False, llm=False, niche="solar"
    )
    assert isinstance(rep, dict)
    p = rep["personas"]
    assert p["ok"] is True
    assert p["pass_rate"] >= 0.7  # baseline today: 7/7
    assert p["passed"] >= 1
    assert isinstance(p["by_persona"], dict) and p["by_persona"]
    # verdict present + sane
    assert 0.0 <= rep["score"] <= 1.0
    assert rep["status"] in ("ok", "degraded", "fail")
    assert rep["ok"] is True
    assert "ms" in rep


async def test_live_only_no_data_is_neutral():
    """live component never raises even with no transcripts (has_data False)."""
    rep = await self_test.run_voice_self_test(personas=False, stack=False, live=True, llm=False)
    assert rep["live"]["ok"] is True
    assert "score" in rep and "status" in rep


async def test_no_components_is_fail():
    """Nothing selected → fail/0.0 (no component ran), still never raises."""
    rep = await self_test.run_voice_self_test(personas=False, stack=False, live=False, llm=False)
    assert rep["status"] == "fail"
    assert rep["score"] == 0.0
    assert rep["ok"] is False


def test_verdict_weighting_pure():
    """_verdict only weights components that actually ran; empty → fail."""
    score, status = self_test._verdict({"personas": {"pass_rate": 1.0}})
    assert score == 1.0 and status == "ok"

    _, status = self_test._verdict({"personas": {"pass_rate": 0.5}})
    assert status == "fail"  # 0.5 < 0.6

    score, status = self_test._verdict({})
    assert score == 0.0 and status == "fail"

    # stack-only: 2 probes, 1 ok → 0.5 fraction → fail tier
    score, status = self_test._verdict(
        {"stack": {"tts": {"ok": True}, "stt": {"ok": False}, "ok": False}}
    )
    assert score == 0.5 and status == "fail"
