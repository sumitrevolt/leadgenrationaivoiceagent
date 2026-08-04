"""Honesty contracts: /health/ready LLM label + agent_runtime calling badge."""

from __future__ import annotations

from unittest.mock import patch


def test_check_llm_config_prefers_free_chain_not_gemini_key_alone(monkeypatch):
    """GEMINI_API_KEY present must NOT force provider=gemini when free chain heads groq."""
    from app.api import health as health_mod

    monkeypatch.setattr(health_mod.settings, "gemini_api_key", "AIzaSyFakeGeminiKeyForTestOnly")
    monkeypatch.setattr(health_mod.settings, "google_cloud_project_id", "")
    monkeypatch.setattr(health_mod.settings, "openai_api_key", "")
    monkeypatch.setattr(health_mod.settings, "anthropic_api_key", "")

    fake_desc = {
        "providers": {
            "groq": True,
            "cerebras": True,
            "mistral": True,
            "gemini": True,
        },
        "llm_chain": [
            "groq:openai/gpt-oss-20b",
            "cerebras:gpt-oss-120b",
            "mistral:mistral-small-latest",
            "gemini:gemini-2.5-flash-lite",
        ],
    }
    with patch("app.voice_agent.free_ai.describe", return_value=fake_desc):
        out = health_mod._check_llm_config()
    assert out["status"] == "configured"
    assert out["provider"] == "groq"
    assert "mistral" in out["providers"]
    assert out["provider"] != "gemini"


def test_check_llm_config_gemini_primary_when_chain_heads_gemini(monkeypatch):
    from app.api import health as health_mod

    fake_desc = {
        "providers": {"gemini": True, "groq": True},
        "llm_chain": ["gemini:gemini-2.5-flash-lite", "groq:openai/gpt-oss-20b"],
    }
    with patch("app.voice_agent.free_ai.describe", return_value=fake_desc):
        out = health_mod._check_llm_config()
    assert out["provider"] == "gemini"


def test_runtime_status_calling_badge_follows_owner_os_posture():
    from app.platform import agent_runtime as rt

    with patch(
        "app.platform.owner_os.calling_posture",
        return_value={"live": True, "badge": "Calling LIVE · cap 100/run", "hard_off": False},
    ):
        status = rt.runtime_status()
    assert status["ok"] is True
    assert "LIVE" in status["calling_badge"]
    assert "HARD OFF" not in status["calling_badge"]


def test_frozen_transfer_does_not_claim_platform_dial_hard_off():
    """Swara frozen capability must not confuse Agent Runtime RED with dial campaign."""
    import asyncio
    from types import SimpleNamespace

    from app.platform import agent_runtime_workforce as wf

    ctx = SimpleNamespace(task=SimpleNamespace(agent_id="swara"))
    out = asyncio.run(wf.frozen_transfer_status(ctx))  # type: ignore[arg-type]
    assert out["runtime_dispatch"] == "blocked_red_lane"
    assert out["calling"] == "RUNTIME_RED_BLOCKED"
    assert "platform_dial stays HARD OFF" not in (out.get("note") or "")
