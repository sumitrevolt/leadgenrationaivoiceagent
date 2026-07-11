from __future__ import annotations

import pytest


def test_legacy_brain_accepts_active_free_mistral_model(monkeypatch):
    from app.voice_agent import llm_brain

    monkeypatch.setattr(llm_brain, "ML_ENABLED", False)
    brain = llm_brain.LLMBrain(model="mistral-small-latest")

    assert brain.provider == "free_ai"


@pytest.mark.asyncio
async def test_free_model_generation_uses_free_ai_chain(monkeypatch):
    from app.voice_agent import free_ai, llm_brain

    monkeypatch.setattr(llm_brain, "ML_ENABLED", False)
    calls: list[dict] = []

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        return "free reply", "mistral"

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    brain = llm_brain.LLMBrain(model="mistral-small-latest")
    out = await brain.generate_response(
        [{"role": "user", "content": "hello"}],
        "salon",
        "Demo Biz",
        "AI Lead Gen SAAS",
    )

    assert out == "free reply"
    assert calls and calls[0]["profile"] == "realtime"
