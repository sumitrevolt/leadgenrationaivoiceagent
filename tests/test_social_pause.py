"""Loop-social-8 (2026-07-11): pause + emergency-stop gates.

Contract:
- SOCIAL_EMERGENCY_STOP env=1 → every job paused with reason='emergency_stop'
- SOCIAL_PAUSED_PLATFORMS=x,instagram → jobs on x/instagram paused with
  reason='paused_platform'
- SOCIAL_PAUSED_CLIENTS=c_A,c_B → jobs for those clients paused with
  reason='paused_client'
- Config-file `data/social_engine.json` provides same shape as fallback.
- Corrupt config → fail-CLOSED (emergency_stop=True, all platforms paused).
- `should_pause_job()` never raises.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest


@pytest.fixture()
def paused(monkeypatch, tmp_path):
    """Fresh config file per test."""
    from app.social_engine import pause as _pause

    cfg = tmp_path / "social_engine.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ENGINE_CONFIG", str(cfg))
    for var in ("SOCIAL_EMERGENCY_STOP", "SOCIAL_PAUSED_PLATFORMS", "SOCIAL_PAUSED_CLIENTS"):
        monkeypatch.delenv(var, raising=False)
    return {"cfg": cfg, "mod": _pause}


def test_default_state_nothing_paused(paused):
    assert paused["mod"].emergency_stop_active() is False
    assert paused["mod"].paused_platforms() == set()
    assert paused["mod"].paused_clients() == set()
    ok, reason = paused["mod"].should_pause_job({"platform": "facebook", "client_id": "c1"})
    assert ok is False and reason == ""


def test_env_emergency_stop_wins(paused, monkeypatch):
    monkeypatch.setenv("SOCIAL_EMERGENCY_STOP", "1")
    assert paused["mod"].emergency_stop_active() is True
    ok, reason = paused["mod"].should_pause_job({"platform": "x", "client_id": "c1"})
    assert ok is True and reason == "emergency_stop"


def test_config_file_emergency_stop_fallback(paused):
    paused["cfg"].write_text(json.dumps({"emergency_stop": True}), encoding="utf-8")
    assert paused["mod"].emergency_stop_active() is True


def test_env_paused_platforms_csv(paused, monkeypatch):
    monkeypatch.setenv("SOCIAL_PAUSED_PLATFORMS", "instagram, x")
    assert paused["mod"].paused_platforms() == {"instagram", "x"}
    ok, reason = paused["mod"].should_pause_job({"platform": "x", "client_id": "c1"})
    assert ok is True and reason == "paused_platform"
    # Non-paused platform passes.
    ok2, _ = paused["mod"].should_pause_job({"platform": "facebook", "client_id": "c1"})
    assert ok2 is False


def test_env_paused_clients_csv(paused, monkeypatch):
    monkeypatch.setenv("SOCIAL_PAUSED_CLIENTS", "c_A,c_B")
    assert paused["mod"].paused_clients() == {"c_A", "c_B"}
    ok, reason = paused["mod"].should_pause_job({"platform": "facebook", "client_id": "c_A"})
    assert ok is True and reason == "paused_client"


def test_corrupt_config_fails_closed(paused):
    paused["cfg"].write_text("{ not valid json", encoding="utf-8")
    # Emergency stop treated as ON.
    assert paused["mod"].emergency_stop_active() is True
    # Every known platform paused too.
    p = paused["mod"].paused_platforms()
    assert "facebook" in p and "instagram" in p and "linkedin" in p
    # Job pause = True.
    ok, reason = paused["mod"].should_pause_job({"platform": "facebook", "client_id": "c1"})
    assert ok is True and reason in ("emergency_stop", "paused_platform")


def test_set_config_toggles_pause_at_runtime(paused):
    paused["mod"].set_config(paused_platforms=["gbp"])
    assert "gbp" in paused["mod"].paused_platforms()
    # additive — turn ON emergency stop later without wiping platforms
    paused["mod"].set_config(emergency_stop=True)
    assert paused["mod"].emergency_stop_active() is True
    assert "gbp" in paused["mod"].paused_platforms()


def test_engine_process_queue_honors_pause(paused, monkeypatch, tmp_path):
    """End-to-end: paused platform → skipped + customer_action_required emit."""
    from app.social_engine import engine, store, vault
    from app.social_engine.base import PublishResult, SocialProvider

    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "tokens.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.setenv("SOCIAL_PAUSED_PLATFORMS", "facebook")

    class _P(SocialProvider):
        name = "facebook"
        publish_calls = 0

        def configured(self, account=None):
            return True

        async def publish(self, req, account):
            self.publish_calls += 1
            return PublishResult(ok=True, platform="facebook", post_id="P")

    prov = _P()
    monkeypatch.setattr(engine, "_REGISTRY", {"facebook": prov})

    import asyncio

    engine.enqueue_publish("c1", caption="hi", platforms=["facebook"])
    out = asyncio.run(engine.process_queue())
    assert out["skipped"] == 1
    assert prov.publish_calls == 0
