import importlib
import json
import os

import pytest


@pytest.fixture
def rl(tmp_path, monkeypatch):
    """Fresh reward module with isolated data files + flag ON."""
    monkeypatch.setenv("RL_ENGINE", "1")
    import app.agents.rl.reward as reward

    importlib.reload(reward)
    monkeypatch.setattr(reward, "_REWARDS", str(tmp_path / "rl_rewards.jsonl"))
    monkeypatch.setattr(reward, "_DEV", str(tmp_path / "claude_feedback.jsonl"))
    return reward


def test_voice_reward_monotonic(rl):
    assert rl.voice_reward({"outcome": "appointment"}) > rl.voice_reward(
        {"outcome": "not_interested"}
    )
    assert rl.voice_reward({"qualified": True}) > rl.voice_reward({"qualified": False})
    assert rl.voice_reward({"conversation_quality": 90}) > rl.voice_reward(
        {"conversation_quality": 20}
    )
    # qa violations penalize
    assert rl.voice_reward({"interest_score": 80, "qa_violations": 3}) < rl.voice_reward(
        {"interest_score": 80}
    )
    assert 0.0 <= rl.voice_reward({"outcome": "dnd"}) <= 1.0


def test_outreach_reward_signs(rl):
    assert rl.outreach_reward({"kind": "signup"}) > 0
    assert rl.outreach_reward({"kind": "unsubscribe"}) < 0
    assert rl.outreach_reward({"kind": "totally_unknown"}) == 0.0
    assert rl.outreach_reward({"intent": "interested"}) > 0


def test_dev_reward(rl):
    assert rl.dev_reward({"user_correction": True}) < 0
    assert rl.dev_reward({"verify_pass": True, "tests_pass": True, "deploy_health": "ok"}) > 0
    assert -1.0 <= rl.dev_reward({"verify_pass": False, "user_correction": True}) <= 1.0


def test_record_inert_when_off(tmp_path, monkeypatch):
    monkeypatch.delenv("RL_ENGINE", raising=False)
    import app.agents.rl.reward as reward

    importlib.reload(reward)
    monkeypatch.setattr(reward, "_REWARDS", str(tmp_path / "r.jsonl"))
    reward.record_reward("voice", "salon", 0.9, ref="c1")
    assert not os.path.exists(str(tmp_path / "r.jsonl"))


def test_record_writes_and_idempotent(rl):
    rl.record_reward("voice", "salon", 0.9, ref="call-1", context={"niche": "salon"})
    rl.record_reward("voice", "salon", 0.9, ref="call-1")  # duplicate ref ignored
    rows = rl._read(rl._REWARDS)
    assert len(rows) == 1
    assert rows[0]["domain"] == "voice"
    assert rows[0]["reward_version"] == rl.REWARD_VERSION
    assert rows[0]["context"]["niche"] == "salon"


def test_unknown_domain_dropped(rl):
    rl.record_reward("bogus", "x", 0.5, ref="z1")
    assert rl._read(rl._REWARDS) == []


def test_graduation_status(rl):
    for i in range(5):
        rl.record_reward("funnel", "scrape_leads", 0.6, ref=f"r{i}")
    g = rl.graduation_status()
    assert g["domains"]["funnel"]["samples"] == 5
    assert g["domains"]["funnel"]["graduated"] is False
    assert g["domains"]["funnel"]["samples_until_graduation"] == g["graduation_n"] - 5


def test_arm_stats(rl):
    rl.record_reward("outreach", "quora", 0.9, ref="a1")
    rl.record_reward("outreach", "quora", 0.1, ref="a2")
    s = rl.arm_stats("outreach")["quora"]
    assert s["n"] == 2
    assert 0.0 <= s["success_rate"] <= 1.0
    assert s["alpha"] >= 1 and s["beta"] >= 1


def test_never_raises_on_garbage(rl):
    rl.record_reward("voice", None, float("nan"), ref=None)  # must not raise
    assert rl.voice_reward("not-a-dict") == 0.5
    assert rl.outreach_reward(None) == 0.0


def test_channel_experiments_emits_reward(tmp_path, monkeypatch):
    monkeypatch.setenv("RL_ENGINE", "1")
    import app.agents.rl.reward as reward

    importlib.reload(reward)
    monkeypatch.setattr(reward, "_REWARDS", str(tmp_path / "rl_rewards.jsonl"))

    import app.marketing.channel_experiments as ce

    out = ce.record_outcome("quora", kind="reply")
    assert out["ok"] is True
    rows = reward._read(reward._REWARDS)
    assert any(r["domain"] == "outreach" and r["arm"] == "quora" for r in rows)


def test_rl_router_shape():
    from app.api.rl import router

    paths = {r.path for r in router.routes}
    assert "/api/rl/summary" in paths
    assert "/api/rl/arms" in paths
    assert "/api/rl/recent" in paths
    assert "/api/rl/dev" in paths
